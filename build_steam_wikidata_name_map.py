import argparse
import csv
import json
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests


WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"

TOP_N = 500
QUERY_BATCH_SIZE = 50
REQUEST_TIMEOUT = 60

HEADERS = {
    # Steam / Wikidata 都建议带清晰 UA，避免被当成异常请求。
    "User-Agent": "doge24190-game-news-bot/0.2 contact: me@doge24190.top",
}

FIELDNAMES = [
    "appid",
    "steamdb_rank",
    "primary_english_name",
    "english_alias_1",
    "english_alias_2",
    "zh_hans_name",
    "zh_hant_name",
    "wikidata_qid",
    "match_status",
]


class RunContext:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"警告：{message}")

    def error(self, stage: str, message: str, **extra: Any) -> None:
        item = {"stage": stage, "message": message, **extra}
        self.errors.append(item)
        print(f"错误（已跳过）：[{stage}] {message}")


# ---------- 通用工具 ----------

def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def unique_non_empty(values: list[str]) -> list[str]:
    result = []
    seen = set()

    for value in values:
        value = clean_name(value)
        if not value:
            continue

        key = value.casefold()
        if key in seen:
            continue

        result.append(value)
        seen.add(key)

    return result


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def get_value(binding: dict[str, Any], key: str) -> str:
    if key not in binding:
        return ""
    return clean_name(binding[key].get("value", ""))


def split_aliases(value: str) -> list[str]:
    if not value:
        return []
    return unique_non_empty(value.split("|"))


def parse_int(value: str, fallback: int = 0) -> int:
    text = clean_name(value).replace(",", "")
    return int(text) if text.isdigit() else fallback


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "csv": output_dir / "game_name_map.csv",
        "json": output_dir / "game_aliases_from_wikidata.json",
        "dokuwiki": output_dir / "game_name_map.dokuwiki.txt",
        "report": output_dir / "run_report.json",
        "input_copy": output_dir / "steamdb_top500.csv",
    }


def resolve_input_csv(input_path: Path, run_date: str, output_root: Path) -> Path:
    candidates = [
        input_path,
        Path(f"steamdb_top500_{run_date}.csv"),
        output_root / run_date / "steamdb_top500.csv",
        output_root / run_date / f"steamdb_top500_{run_date}.csv",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    tried = "\n".join(f"- {candidate}" for candidate in candidates)
    raise FileNotFoundError(f"找不到 SteamDB CSV。已尝试：\n{tried}")


# ---------- Steam Store fallback ----------

def fetch_steam_app_name(session: requests.Session, appid: str, lang: str = "english") -> str:
    try:
        resp = session.get(
            STEAM_APPDETAILS_URL,
            params={"appids": appid, "l": lang, "filters": "basic"},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json().get(str(appid), {})
    except (requests.RequestException, ValueError, TypeError) as exc:
        print(f"补全游戏名失败：{appid} ({exc})")
        return ""

    if not data.get("success"):
        return ""

    return clean_name(data.get("data", {}).get("name", ""))


# ---------- 输入 CSV ----------

def load_steamdb_top_games_from_csv(path: Path, limit: int, ctx: RunContext) -> list[dict[str, Any]]:
    rows = []
    session = requests.Session()

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])

        if "appid" not in fieldnames:
            raise RuntimeError("输入 CSV 缺少必要字段 appid")

        if "primary_english_name" not in fieldnames:
            ctx.warn("输入 CSV 缺少 primary_english_name 字段，将尝试用 Steam Store API 补全。")

        for line_number, row in enumerate(reader, start=2):
            appid = clean_name(row.get("appid", ""))
            name = clean_name(row.get("primary_english_name", ""))
            rank_text = clean_name(row.get("steamdb_rank", ""))

            if not appid:
                ctx.warn(f"第 {line_number} 行缺少 appid，已跳过。")
                continue

            if not re.fullmatch(r"\d+", appid):
                ctx.warn(f"第 {line_number} 行 appid 非数字：{appid}，已跳过。")
                continue

            if not name:
                print(f"补全游戏名：{appid}")
                name = fetch_steam_app_name(session, appid, "english")
                time.sleep(0.3)

            if not name:
                ctx.warn(f"第 {line_number} 行 appid={appid} 无法获取游戏名，已跳过。")
                continue

            rows.append({
                "steamdb_rank": parse_int(rank_text, len(rows) + 1),
                "appid": appid,
                "primary_english_name": name,
            })

            if len(rows) >= limit:
                break

    if not rows:
        raise RuntimeError("SteamDB CSV 为空，或所有 AppID 都无法获取游戏名。")

    return rows


# ---------- Wikidata ----------

def wikidata_query_by_appids(session: requests.Session, appids: list[str]) -> dict[str, dict[str, Any]]:
    """通过 Wikidata P1733 / Steam application ID 批量查询。"""
    if not appids:
        return {}

    values = " ".join(f'"{appid}"' for appid in appids if re.fullmatch(r"\d+", appid))
    if not values:
        return {}

    query = f"""
SELECT ?item ?itemLabel ?steamAppId
       ?enLabel ?zhHansLabel ?zhHantLabel ?zhLabel
       (GROUP_CONCAT(DISTINCT ?enAlias; separator="|") AS ?enAliases)
       (GROUP_CONCAT(DISTINCT ?zhHansAlias; separator="|") AS ?zhHansAliases)
       (GROUP_CONCAT(DISTINCT ?zhHantAlias; separator="|") AS ?zhHantAliases)
       (GROUP_CONCAT(DISTINCT ?zhAlias; separator="|") AS ?zhAliases)
WHERE {{
  VALUES ?steamAppId {{ {values} }}
  ?item wdt:P1733 ?steamAppId.

  OPTIONAL {{ ?item rdfs:label ?enLabel. FILTER(LANG(?enLabel) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?zhHansLabel. FILTER(LANG(?zhHansLabel) = "zh-hans") }}
  OPTIONAL {{ ?item rdfs:label ?zhHantLabel. FILTER(LANG(?zhHantLabel) = "zh-hant") }}
  OPTIONAL {{ ?item rdfs:label ?zhLabel. FILTER(LANG(?zhLabel) = "zh") }}

  OPTIONAL {{ ?item skos:altLabel ?enAlias. FILTER(LANG(?enAlias) = "en") }}
  OPTIONAL {{ ?item skos:altLabel ?zhHansAlias. FILTER(LANG(?zhHansAlias) = "zh-hans") }}
  OPTIONAL {{ ?item skos:altLabel ?zhHantAlias. FILTER(LANG(?zhHantAlias) = "zh-hant") }}
  OPTIONAL {{ ?item skos:altLabel ?zhAlias. FILTER(LANG(?zhAlias) = "zh") }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
GROUP BY ?item ?itemLabel ?steamAppId ?enLabel ?zhHansLabel ?zhHantLabel ?zhLabel
"""

    resp = session.get(
        WIKIDATA_SPARQL_URL,
        headers={**HEADERS, "Accept": "application/sparql-results+json"},
        params={"query": query, "format": "json"},
        timeout=REQUEST_TIMEOUT,
    )

    # 429 时把 Retry-After 信息交给上层重试逻辑。
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "")
        raise RuntimeError(f"Wikidata 请求过于频繁，HTTP 429，Retry-After={retry_after or 'unknown'}")

    resp.raise_for_status()
    data = resp.json()
    result = {}

    for binding in data.get("results", {}).get("bindings", []):
        appid = get_value(binding, "steamAppId")
        item_url = get_value(binding, "item")
        qid = item_url.rsplit("/", 1)[-1] if item_url else ""

        if not appid or not qid:
            continue

        result[appid] = {
            "wikidata_qid": qid,
            "en_label": get_value(binding, "enLabel"),
            "zh_hans_label": get_value(binding, "zhHansLabel"),
            "zh_hant_label": get_value(binding, "zhHantLabel"),
            "zh_label": get_value(binding, "zhLabel"),
            "en_aliases": split_aliases(get_value(binding, "enAliases")),
            "zh_hans_aliases": split_aliases(get_value(binding, "zhHansAliases")),
            "zh_hant_aliases": split_aliases(get_value(binding, "zhHantAliases")),
            "zh_aliases": split_aliases(get_value(binding, "zhAliases")),
        }

    return result


def wikidata_query_with_retry(session: requests.Session, appids: list[str], ctx: RunContext, retries: int = 3) -> dict[str, dict[str, Any]]:
    last_error = ""

    for attempt in range(1, retries + 1):
        try:
            return wikidata_query_by_appids(session, appids)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries:
                sleep_seconds = min(2 ** attempt, 10)
                print(f"Wikidata 查询失败，{sleep_seconds}s 后重试 ({attempt}/{retries})：{last_error}")
                time.sleep(sleep_seconds)
            else:
                ctx.error(
                    "wikidata",
                    f"批次查询失败，已保留这些游戏为 not_found：{last_error}",
                    appids=appids,
                )

    return {}


# ---------- 名称挑选 ----------

def pick_two_english_aliases(primary_name: str, aliases: list[str]) -> list[str]:
    selected = []
    primary_key = primary_name.casefold()

    for alias in aliases:
        if alias.casefold() == primary_key:
            continue
        if alias not in selected:
            selected.append(alias)
        if len(selected) >= 2:
            break

    return selected


def pick_chinese_name(label: str, generic_zh_label: str, aliases: list[str]) -> str:
    if label:
        return label
    if generic_zh_label:
        return generic_zh_label
    if aliases:
        return aliases[0]
    return ""


def build_rows(steam_games: list[dict[str, Any]], wikidata_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []

    for game in steam_games:
        appid = game["appid"]
        primary_name = game["primary_english_name"]
        wd = wikidata_map.get(appid)

        if not wd:
            rows.append({
                "appid": appid,
                "steamdb_rank": game["steamdb_rank"],
                "primary_english_name": primary_name,
                "english_alias_1": "",
                "english_alias_2": "",
                "zh_hans_name": "",
                "zh_hant_name": "",
                "wikidata_qid": "",
                "match_status": "not_found",
            })
            continue

        en_aliases = pick_two_english_aliases(primary_name, wd.get("en_aliases", []))

        zh_hans_name = pick_chinese_name(
            wd.get("zh_hans_label", ""),
            wd.get("zh_label", ""),
            wd.get("zh_hans_aliases", []) + wd.get("zh_aliases", []),
        )

        zh_hant_name = pick_chinese_name(
            wd.get("zh_hant_label", ""),
            wd.get("zh_label", ""),
            wd.get("zh_hant_aliases", []) + wd.get("zh_aliases", []),
        )

        rows.append({
            "appid": appid,
            "steamdb_rank": game["steamdb_rank"],
            "primary_english_name": primary_name,
            "english_alias_1": en_aliases[0] if len(en_aliases) > 0 else "",
            "english_alias_2": en_aliases[1] if len(en_aliases) > 1 else "",
            "zh_hans_name": zh_hans_name,
            "zh_hant_name": zh_hant_name,
            "wikidata_qid": wd.get("wikidata_qid", ""),
            "match_status": "matched_by_p1733",
        })

    return rows


# ---------- 输出 ----------

def save_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows: list[dict[str, Any]], path: Path) -> None:
    data = {}

    for row in rows:
        aliases = unique_non_empty([
            row["primary_english_name"],
            row["english_alias_1"],
            row["english_alias_2"],
            row["zh_hans_name"],
            row["zh_hant_name"],
        ])

        data[row["appid"]] = {
            "steamdb_rank": row["steamdb_rank"],
            "name": row["primary_english_name"],
            "aliases": aliases,
            "wikidata_qid": row["wikidata_qid"],
            "match_status": row["match_status"],
        }

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def escape_dokuwiki(value: str) -> str:
    return clean_name(value).replace("|", "／")


def save_dokuwiki_table(rows: list[dict[str, Any]], path: Path, top_n: int) -> None:
    lines = []
    lines.append("====== Steam 热门游戏中英文名对照表 ======")
    lines.append("")
    lines.append(f"数据来源：SteamDB 24h 峰值排序前 {top_n}；Wikidata P1733。")
    lines.append("")
    lines.append("^ 排名 ^ AppID ^ 主要英文名称 ^ 英文别名 1 ^ 英文别名 2 ^ 简体中文 ^ 繁体中文 ^ Wikidata ^ 匹配状态 ^")

    for row in rows:
        qid = row["wikidata_qid"]
        qid_text = f"[[https://www.wikidata.org/wiki/{qid}|{qid}]]" if qid else ""
        lines.append(
            "| "
            + " | ".join([
                escape_dokuwiki(str(row["steamdb_rank"])),
                escape_dokuwiki(row["appid"]),
                escape_dokuwiki(row["primary_english_name"]),
                escape_dokuwiki(row["english_alias_1"]),
                escape_dokuwiki(row["english_alias_2"]),
                escape_dokuwiki(row["zh_hans_name"]),
                escape_dokuwiki(row["zh_hant_name"]),
                qid_text,
                escape_dokuwiki(row["match_status"]),
            ])
            + " |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def save_report(ctx: RunContext, paths: dict[str, Path], rows: list[dict[str, Any]], input_csv: Path) -> None:
    matched = sum(1 for row in rows if row["match_status"] == "matched_by_p1733")
    report = {
        "input_csv": str(input_csv),
        "output_dir": str(ctx.output_dir),
        "total_rows": len(rows),
        "matched": matched,
        "not_found": len(rows) - matched,
        "warnings": ctx.warnings,
        "errors": ctx.errors,
        "outputs": {key: str(path) for key, path in paths.items()},
    }
    paths["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 主流程 ----------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 Steam 热门游戏中英文名称对照表。")
    parser.add_argument("--input", default="steamdb_top500.csv", help="SteamDB 导出的 CSV，默认 steamdb_top500.csv")
    parser.add_argument("--date", default=date.today().isoformat(), help="输出目录名，默认今天，格式 YYYY-MM-DD")
    parser.add_argument("--output-root", default=".", help="输出根目录，默认当前目录")
    parser.add_argument("--top", type=int, default=TOP_N, help=f"处理前 N 个游戏，默认 {TOP_N}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_date = clean_name(args.date)

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_date):
        print("错误：--date 必须使用 YYYY-MM-DD 格式。", file=sys.stderr)
        return 2

    output_root = Path(args.output_root)
    output_dir = output_root / run_date
    output_dir.mkdir(parents=True, exist_ok=True)

    ctx = RunContext(output_dir)
    paths = output_paths(output_dir)

    try:
        input_csv = resolve_input_csv(Path(args.input), run_date, output_root)
        if input_csv.resolve() != paths["input_copy"].resolve():
            shutil.copy2(input_csv, paths["input_copy"])
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    try:
        print("1. 读取本地 SteamDB CSV...")
        steam_games = load_steamdb_top_games_from_csv(input_csv, args.top, ctx)
        print(f"已读取 {len(steam_games)} 个游戏")
    except Exception as exc:
        print(f"错误：读取输入 CSV 失败：{exc}", file=sys.stderr)
        return 1

    print("2. 查询 Wikidata P1733...")
    wikidata_map: dict[str, dict[str, Any]] = {}
    appids = [game["appid"] for game in steam_games]
    session = requests.Session()

    for index, batch in enumerate(chunked(appids, QUERY_BATCH_SIZE), start=1):
        print(f"查询批次 {index}: {len(batch)} 个 AppID")
        wikidata_map.update(wikidata_query_with_retry(session, batch, ctx))
        time.sleep(1)

    print(f"Wikidata 匹配到 {len(wikidata_map)} 个游戏")

    print("3. 生成表格...")
    rows = build_rows(steam_games, wikidata_map)

    save_csv(rows, paths["csv"])
    save_json(rows, paths["json"])
    save_dokuwiki_table(rows, paths["dokuwiki"], args.top)
    save_report(ctx, paths, rows, input_csv)

    matched = sum(1 for row in rows if row["match_status"] == "matched_by_p1733")
    print(f"完成：匹配 {matched}/{len(rows)}")
    print(f"输出目录：{output_dir}")
    print(f"CSV: {paths['csv']}")
    print(f"JSON: {paths['json']}")
    print(f"DokuWiki: {paths['dokuwiki']}")
    print(f"运行报告: {paths['report']}")

    if ctx.errors:
        print(f"注意：运行中有 {len(ctx.errors)} 个非致命错误，详情见 {paths['report']}。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
