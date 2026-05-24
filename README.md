# name_map

`name_map` 是一个用于生成 **Steam 热门游戏中英文名称对照表** 的小工具。

它的主要用途是：  
从 SteamDB 热门游戏榜单中获取游戏的 Steam AppID 和主要英文名称，然后通过 Wikidata 查询对应游戏的英文别名、简体中文名和繁体中文名，最终生成可供新闻聚合、RSS 筛选、DokuWiki 页面发布使用的名称映射表。

这个项目最初服务于一个游戏新闻聚合机器人：  
机器人读取用户最近游玩的 Steam 游戏后，需要用英文名、缩写名、简体中文名、繁体中文名等多个别名去匹配 RSS / Miniflux 中的相关新闻。

---

## 功能

当前版本支持：

- 读取从 SteamDB Charts 页面导出的 `steamdb_top500.csv`
- 使用 Steam AppID 查询 Wikidata 的 Steam application ID 属性
- 生成游戏中英文名称对照表
- 输出 CSV 文件，方便人工查看和修正
- 输出 JSON 文件，方便程序读取和匹配新闻
- 输出 DokuWiki 表格文本，方便发布到 Wiki 页面

---

## 数据流程

```text
SteamDB Charts 页面
    ↓
浏览器控制台导出 steamdb_top500.csv
    ↓
Python 读取 AppID 和英文名称
    ↓
Wikidata 根据 Steam AppID 匹配游戏条目
    ↓
提取英文别名、简体中文名、繁体中文名
    ↓
生成 CSV / JSON / DokuWiki 表格
````

---

## 为什么不直接用 Python 抓 SteamDB？

SteamDB 对脚本直接访问有反爬限制，直接使用 `requests` 请求 `https://steamdb.info/charts/?sort=24h` 很容易返回：

```text
403 Forbidden
```

因此本项目采用更稳定的方式：

1. 用浏览器正常打开 SteamDB Charts 页面；
2. 在浏览器控制台导出当前页面表格；
3. Python 只读取本地 CSV 文件，不直接抓 SteamDB 网页。

这种方式更稳定，也避免把项目依赖建立在 SteamDB 的网页反爬策略上。

---

## 目录结构建议

```text
name_map/
├── build_steam_wikidata_name_map.py
├── steamdb_top500.csv
├── game_name_map.csv
├── game_aliases_from_wikidata.json
├── game_name_map.dokuwiki.txt
├── requirements.txt
└── README.md
```

---

## 安装依赖

建议使用虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate
```

安装依赖：

```bash
pip install requests beautifulsoup4 lxml
```

如果你使用 `requirements.txt`，可以写入：

```txt
requests
beautifulsoup4
lxml
```

然后执行：

```bash
pip install -r requirements.txt
```

---

## 第一步：从 SteamDB 导出 Top 500 游戏

打开 SteamDB Charts 页面：

```text
https://steamdb.info/charts/?sort=24h
```

等待表格加载完成后，打开浏览器开发者工具：

```text
F12 → Console
```

粘贴仓库中的脚本```script.js```


脚本会下载：

```text
steamdb_top500.csv
```

文件内容类似：

```csv
steamdb_rank,appid,primary_english_name,current,peak_24h,peak_all_time
1,730,"Counter-Strike 2",1233683,1488364,1862531
2,578080,"PUBG: BATTLEGROUNDS",245042,782807,3257248
3,570,"Dota 2",547183,654581,1295114
```

---

## 第二步：运行 Python 程序

确保 `steamdb_top500.csv` 位于项目根目录，然后运行：

```bash
python3 build_steam_wikidata_name_map.py
```

程序会：

1. 读取 `steamdb_top500.csv`
2. 按 `peak_24h` 重新排序
3. 取前 500 个游戏
4. 使用 Steam AppID 查询 Wikidata
5. 生成名称对照表

---

## 输出文件

程序运行完成后会生成以下文件：

### `game_name_map.csv`

适合人工查看和修正。

字段示例：

```csv
appid,steamdb_rank,primary_english_name,english_alias_1,english_alias_2,zh_hans_name,zh_hant_name,wikidata_qid,match_status
730,1,Counter-Strike 2,CS2,,反恐精英2,絕對武力2,Q839861,matched_by_p1733
```

### `game_aliases_from_wikidata.json`

适合程序读取。

示例：

```json
{
  "730": {
    "steamdb_rank": 1,
    "name": "Counter-Strike 2",
    "aliases": [
      "Counter-Strike 2",
      "CS2",
      "反恐精英2",
      "絕對武力2"
    ],
    "wikidata_qid": "Q839861",
    "match_status": "matched_by_p1733"
  }
}
```

### `game_name_map.dokuwiki.txt`

适合直接写入 DokuWiki 页面。

示例：

```dokuwiki
====== Steam 热门游戏中英文名对照表 ======

数据来源：SteamDB 24h 峰值排序前 500；Wikidata P1733。

^ 排名 ^ AppID ^ 主要英文名称 ^ 英文别名 1 ^ 英文别名 2 ^ 简体中文 ^ 繁体中文 ^ Wikidata ^ 匹配状态 ^
| 1 | 730 | Counter-Strike 2 | CS2 |  | 反恐精英2 | 絕對武力2 | [[https://www.wikidata.org/wiki/Q839861|Q839861]] | matched_by_p1733 |
```

---

## 输入 CSV 格式

程序默认读取：

```text
steamdb_top500.csv
```

至少需要包含以下字段：

```csv
steamdb_rank,appid,primary_english_name
```

推荐包含完整字段：

```csv
steamdb_rank,appid,primary_english_name,current,peak_24h,peak_all_time
```

字段说明：

| 字段                     | 含义                 |
| ---------------------- | ------------------ |
| `steamdb_rank`         | SteamDB 排名         |
| `appid`                | Steam AppID        |
| `primary_english_name` | SteamDB 页面显示的主要英文名 |
| `current`              | 当前在线人数             |
| `peak_24h`             | 24 小时在线峰值          |
| `peak_all_time`        | 历史在线峰值             |

---

## Wikidata 匹配方式

本项目优先使用 Steam AppID 精确匹配 Wikidata 条目。

匹配逻辑：

```sparql
?item wdt:P1733 ?steamAppId.
```

其中 `P1733` 是 Wikidata 中的 Steam application ID 属性。

相比直接用英文名搜索，AppID 匹配更可靠，可以避免：

* 同名游戏
* 标点差异
* 英文名与中文名不一致
* 游戏本体、DLC、旧版、新版混淆
* 缩写误匹配

---

## 匹配状态说明

输出表中的 `match_status` 目前主要有：

| 状态                 | 含义                           |
| ------------------ | ---------------------------- |
| `matched_by_p1733` | 通过 Wikidata Steam AppID 成功匹配 |
| `not_found`        | Wikidata 中未找到对应 Steam AppID  |

`not_found` 并不一定表示数据错误，可能是：

* 游戏较新，Wikidata 还没有条目
* Wikidata 条目缺少 Steam AppID
* 该 AppID 是工具、软件、Demo、Mod 或非标准游戏
* SteamDB 中存在特殊条目

---

## 常见问题

### 1. Python 直接抓 SteamDB 返回 403

这是正常情况。请使用浏览器控制台导出 CSV，不要直接用 `requests` 抓 SteamDB 页面。

### 2. `steamdb_top500.csv 为空或格式不正确`

请检查 CSV 是否包含：

```csv
appid,primary_english_name
```

如果 `primary_english_name` 全部为空，说明浏览器导出脚本抓错了链接。请使用本 README 中新版控制台脚本。

### 3. Wikidata 匹配数量不满 500

这是正常情况。Wikidata 不是 Steam 官方数据库，不保证每个 Steam AppID 都有对应条目。

### 4. 中文名为空

可能原因：

* Wikidata 条目没有中文标签
* 只有 `zh`，没有 `zh-hans` 或 `zh-hant`
* 游戏较新，中文条目尚未维护

后续可以考虑加入 Steam Store 多语言名称作为 fallback。

### 5. 英文别名为空

并不是所有 Wikidata 游戏条目都有英文 alias。没有英文别名时，程序仍会保留 SteamDB 主英文名。

---

## 后续计划

可以继续改进：

* 增加 Steam Store `schinese` / `tchinese` 名称作为 Wikidata 未命中的 fallback
* 对 `not_found` 条目生成待人工审核列表
* 加入自动英文缩写生成，例如 `Baldur's Gate 3 → BG3`
* 加入人工修正文件 `manual_aliases.json`
* 支持一键发布 `game_name_map.dokuwiki.txt` 到 DokuWiki
* 支持 GitHub Actions 定期更新
* 支持输出 SQLite 数据库，供更复杂的系统使用

---

## 许可证

MIT License。

---

## 免责声明

本项目仅用于个人学习、数据整理和新闻聚合辅助。

SteamDB、Steam、Wikidata 分别属于其各自的所有者。
本项目不隶属于 Valve、SteamDB 或 Wikidata。
