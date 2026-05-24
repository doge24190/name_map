<<<<<<< HEAD
// 在 SteamDB Charts 页面控制台运行：
// https://steamdb.info/charts/?sort=24h
// 说明：浏览器出于安全限制通常不会允许 download 属性自动创建子文件夹，
// 因此这里导出 steamdb_top500_YYYY-MM-DD.csv；Python 程序会把结果统一放进 YYYY-MM-DD/ 目录。
(async () => {
  const TOP_N = 500;
  const today = new Date().toISOString().slice(0, 10);
=======
(() => {
  const rows = [...document.querySelectorAll("table tbody tr")];
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7

<<<<<<< HEAD
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const cleanText = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

  const parseNumber = (value) => {
    const text = cleanText(value).replace(/,/g, "");
    const number = Number(text);
    return Number.isFinite(number) ? number : 0;
  };
=======
  const data = rows
    .map((tr, index) => {
      const appLink = tr.querySelector('a[href^="/app/"]');
      if (!appLink) return null;
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7

<<<<<<< HEAD
  const getCellNumber = (td) => {
    if (!td) return 0;
    return parseNumber(td.dataset?.sort || td.textContent || "0");
  };
=======
      const href = appLink.getAttribute("href") || "";
      const match = href.match(/\/app\/(\d+)\//);
      if (!match) return null;
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7

<<<<<<< HEAD
  const escapeCsv = (value) => {
    const text = String(value ?? "");
    return `"${text.replace(/"/g, '""')}"`;
  };
=======
      const appid = match[1];
      const name = appLink.textContent.trim().replace(/\s+/g, " ");
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7

<<<<<<< HEAD
  const readHeaders = (table) => {
    const headers = [...(table.tHead?.querySelectorAll("th") || [])].map((th) =>
      cleanText(th.textContent)
    );

    const indexOf = (names, fallback) => {
      for (const name of names) {
        const index = headers.findIndex(
          (header) => header.toLowerCase() === name.toLowerCase()
        );
        if (index >= 0) return index;
      }
      return fallback;
    };

    return {
      name: indexOf(["Name"], 2),
      current: indexOf(["Current"], 3),
      peak24h: indexOf(["24h Peak", "24h peak"], 4),
      peakAllTime: indexOf(["All-Time Peak", "All Time Peak"], 5),
    };
  };
=======
      return {
        steamdb_rank: index + 1,
        appid,
        primary_english_name: name,
      };
    })
    .filter(Boolean)
    .slice(0, 500);
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7

<<<<<<< HEAD
  const readGameName = (tr, indexes) => {
    const cells = [...tr.cells];
    const nameCell = cells[indexes.name];

    const candidates = [
      nameCell?.querySelector('a.b[href^="/app/"]'),
      nameCell?.querySelector('a[href^="/app/"]:not([aria-hidden="true"])'),
      tr.querySelector('td:nth-child(3) a.b[href^="/app/"]'),
      tr.querySelector('a.b[href^="/app/"]'),
      ...tr.querySelectorAll('a[href^="/app/"]:not([aria-hidden="true"])'),
    ].filter(Boolean);

    for (const el of candidates) {
      const text = cleanText(el.textContent);
      if (text) return text;
    }

    // 最后兜底：从单元格文本中找第一个不像数字/符号的值。
    for (const td of cells) {
      const text = cleanText(td.textContent);
      if (text && !/^\+?$/.test(text) && !/^[\d,.]+\.?$/.test(text)) {
        return text;
      }
    }

    return "";
  };

  const readRows = () => {
    const table = document.querySelector("#table-apps");
    if (!table) return { table: null, rows: [], data: [] };

    const indexes = readHeaders(table);
    const rows = [...table.querySelectorAll("tbody tr.app")];

    const data = rows
      .map((tr) => {
        const cells = [...tr.cells];

        const appid = cleanText(
          tr.dataset?.appid ||
            tr
              .querySelector('a[href^="/app/"]')
              ?.getAttribute("href")
              ?.match(/\/app\/(\d+)\//)?.[1] ||
            ""
        );

        const name = readGameName(tr, indexes);

        if (!appid || !name) {
          return null;
        }

        return {
          appid,
          primary_english_name: name,
          current: getCellNumber(cells[indexes.current]),
          peak_24h: getCellNumber(cells[indexes.peak24h]),
          peak_all_time: getCellNumber(cells[indexes.peakAllTime]),
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.peak_24h - a.peak_24h)
      .slice(0, TOP_N)
      .map((row, index) => ({
        steamdb_rank: index + 1,
        ...row,
      }));

    return { table, rows, data };
  };

  let result = readRows();

  // 如果页面脚本还没把表格填好，最多等 15 秒。
  for (let i = 0; i < 30 && result.data.length === 0; i += 1) {
    await sleep(500);
    result = readRows();
  }

  if (!result.table) {
    console.error("没有找到 #table-apps 表格。请确认当前页面是 SteamDB Charts 页面。");
    return;
  }

  if (result.data.length === 0) {
    console.error("没有解析到任何带名称的游戏。请等表格加载完成后重试。");
    console.log("已发现的行数：", result.rows.length);
    return;
  }

  const missingNameCount = result.rows.length - result.data.length;

  if (missingNameCount > 0) {
    console.warn(`有 ${missingNameCount} 行缺少 appid 或游戏名，已跳过。`);
  }

  console.log(`解析到 ${result.data.length} 条记录。`);
  console.table(result.data.slice(0, 10));

=======
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7
  const csv = [
<<<<<<< HEAD
    [
      "steamdb_rank",
      "appid",
      "primary_english_name",
      "current",
      "peak_24h",
      "peak_all_time",
    ].join(","),
    ...result.data.map((row) =>
=======
    "steamdb_rank,appid,primary_english_name",
    ...data.map(row =>
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7
      [
        row.steamdb_rank,
        row.appid,
        `"${row.primary_english_name.replace(/"/g, '""')}"`
      ].join(",")
    ),
  ].join("\n");

<<<<<<< HEAD
  const blob = new Blob(["\ufeff" + csv], {
    type: "text/csv;charset=utf-8",
  });

=======
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
<<<<<<< HEAD
  a.download = `steamdb_top500_${today}.csv`;
  document.body.appendChild(a);
=======
  a.download = "steamdb_top500.csv";
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7
  a.click();

  URL.revokeObjectURL(url);
<<<<<<< HEAD

  console.log(
    `已导出 steamdb_top500_${today}.csv。Python 程序会把输出文件放入 ${today}/ 文件夹。`
  );
=======

  console.log(`已导出 ${data.length} 条记录`);
>>>>>>> 7733e26286e158c2d829451f14723b7482151fa7
})();
