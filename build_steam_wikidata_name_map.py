import csv
import json
import re
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


STEAMDB_CHARTS_URL = "https://steamdb.info/charts/?sort=24h"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

OUTPUT_CSV = Path("game_name_map.csv")
OUTPUT_JSON = Path("game_aliases_from_wikidata.json")
OUTPUT_DOKUWIKI = Path("game_name_map.dokuwiki.txt")

TOP_N = 500

HEADERS = {
    # SteamDB 和 Wikidata 都建议带清晰 UA，避免被当成异常请求
    "User-Agent": "doge24190-game-news-bot/0.1 contact: me@doge24190.top",
}

def fetch_steam_app_name(appid: str, lang: str = "english") -> str:
    resp = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={
            "appids": appid,
            "l": lang,
            "filters": "basic",
        },
        headers=HEADERS,
        timeout=20,
    )

    if resp.status_code != 200:
        return ""

    data = resp.json().get(str(appid), {})
    if not data.get("success"):
        return ""

    return data.get("data", {}).get("name", "").strip()


def load_steamdb_top_games_from_csv(path: str = "steamdb_top500.csv", limit: int = 500) -> list[dict]:
    rows = []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            appid = row.get("appid", "").strip()
            name = row.get("primary_english_name", "").strip()
            rank = row.get("steamdb_rank", "").strip()

            if not appid:
                continue

            # 如果 CSV 里的游戏名为空，就用 Steam Store API 自动补
            if not name:
                print(f"补全游戏名：{appid}")
                name = fetch_steam_app_name(appid, "english")
                time.sleep(0.3)

            if not name:
                print(f"跳过：{appid} 无法获取游戏名")
                continue

            rows.append({
                "steamdb_rank": int(rank) if rank.isdigit() else len(rows) + 1,
                "appid": appid,
                "primary_english_name": name,
            })

            if len(rows) >= limit:
                break

    if not rows:
        raise RuntimeError("steamdb_top500.csv 为空，或所有 AppID 都无法获取游戏名")

    return rows


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def wikidata_query_by_appids(appids: list[str]) -> dict[str, dict[str, Any]]:
    """
    通过 Wikidata P1733 / Steam application ID 批量查询。
    返回 appid -> Wikidata 信息。
    """
    if not appids:
        return {}

    values = " ".join(f'"{appid}"' for appid in appids)

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

    resp = requests.get(
        WIKIDATA_SPARQL_URL,
        headers={
            **HEADERS,
            "Accept": "application/sparql-results+json",
        },
        params={
            "query": query,
            "format": "json",
        },
        timeout=60,
    )
    resp.raise_for_status()

    data = resp.json()
    result = {}

    for binding in data.get("results", {}).get("bindings", []):
        appid = binding["steamAppId"]["value"]
        item_url = binding["item"]["value"]
        qid = item_url.rsplit("/", 1)[-1]

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


def get_value(binding: dict[str, Any], key: str) -> str:
    if key not in binding:
        return ""
    return binding[key].get("value", "").strip()


def split_aliases(value: str) -> list[str]:
    if not value:
        return []

    aliases = []
    seen = set()

    for item in value.split("|"):
        item = clean_name(item)
        key = item.lower()
        if item and key not in seen:
            aliases.append(item)
            seen.add(key)

    return aliases


def clean_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value


def pick_two_english_aliases(primary_name: str, aliases: list[str]) -> list[str]:
    """
    最多选两个英文 alias。
    过滤掉和主名完全相同的 alias。
    """
    selected = []
    primary_key = primary_name.lower()

    for alias in aliases:
        if alias.lower() == primary_key:
            continue
        if alias not in selected:
            selected.append(alias)
        if len(selected) >= 2:
            break

    return selected


def pick_chinese_name(label: str, generic_zh_label: str, aliases: list[str]) -> str:
    """
    优先使用明确语言标签的 label；
    没有的话用 zh label；
    再没有就用第一个 alias。
    """
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

        en_aliases = pick_two_english_aliases(primary_name, wd["en_aliases"])

        zh_hans_name = pick_chinese_name(
            wd["zh_hans_label"],
            wd["zh_label"],
            wd["zh_hans_aliases"] + wd["zh_aliases"],
        )

        zh_hant_name = pick_chinese_name(
            wd["zh_hant_label"],
            wd["zh_label"],
            wd["zh_hant_aliases"] + wd["zh_aliases"],
        )

        rows.append({
            "appid": appid,
            "steamdb_rank": game["steamdb_rank"],
            "primary_english_name": primary_name,
            "english_alias_1": en_aliases[0] if len(en_aliases) > 0 else "",
            "english_alias_2": en_aliases[1] if len(en_aliases) > 1 else "",
            "zh_hans_name": zh_hans_name,
            "zh_hant_name": zh_hant_name,
            "wikidata_qid": wd["wikidata_qid"],
            "match_status": "matched_by_p1733",
        })

    return rows


def save_csv(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
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

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows: list[dict[str, Any]]) -> None:
    data = {}

    for row in rows:
        aliases = [
            row["primary_english_name"],
            row["english_alias_1"],
            row["english_alias_2"],
            row["zh_hans_name"],
            row["zh_hant_name"],
        ]

        aliases = unique_non_empty(aliases)

        data[row["appid"]] = {
            "steamdb_rank": row["steamdb_rank"],
            "name": row["primary_english_name"],
            "aliases": aliases,
            "wikidata_qid": row["wikidata_qid"],
            "match_status": row["match_status"],
        }

    OUTPUT_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def unique_non_empty(values: list[str]) -> list[str]:
    result = []
    seen = set()

    for value in values:
        value = clean_name(value)
        if not value:
            continue

        key = value.lower()
        if key in seen:
            continue

        result.append(value)
        seen.add(key)

    return result


def save_dokuwiki_table(rows: list[dict[str, Any]]) -> None:
    lines = []
    lines.append("====== Steam 热门游戏中英文名对照表 ======")
    lines.append("")
    lines.append(f"数据来源：SteamDB 24h 峰值排序前 {TOP_N}；Wikidata P1733。")
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

    OUTPUT_DOKUWIKI.write_text("\n".join(lines), encoding="utf-8")


def escape_dokuwiki(value: str) -> str:
    """
    简单避免表格竖线破坏格式。
    DokuWiki 表格内竖线容易切列。
    """
    return value.replace("|", "／").strip()


def main():
    print("1. 读取本地 SteamDB Top 500 CSV...")
    steam_games = load_steamdb_top_games_from_csv("steamdb_top500.csv", TOP_N)
    print(f"已读取 {len(steam_games)} 个游戏")

    print("2. 查询 Wikidata P1733...")
    wikidata_map = {}

    appids = [game["appid"] for game in steam_games]

    for index, batch in enumerate(chunked(appids, 50), start=1):
        print(f"查询批次 {index}: {len(batch)} 个 AppID")
        wikidata_map.update(wikidata_query_by_appids(batch))
        time.sleep(1)

    print(f"Wikidata 匹配到 {len(wikidata_map)} 个游戏")

    print("3. 生成表格...")
    rows = build_rows(steam_games, wikidata_map)

    save_csv(rows)
    save_json(rows)
    save_dokuwiki_table(rows)

    matched = sum(1 for row in rows if row["match_status"] == "matched_by_p1733")
    print(f"完成：匹配 {matched}/{len(rows)}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"JSON: {OUTPUT_JSON}")
    print(f"DokuWiki: {OUTPUT_DOKUWIKI}")


if __name__ == "__main__":
    main()
