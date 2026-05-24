(() => {
  const table = document.querySelector("#table-apps");

  if (!table) {
    console.error("没有找到 #table-apps 表格。请确认当前页面是 SteamDB charts 页面。");
    return;
  }

  const rows = [...table.querySelectorAll("tbody tr.app")];

  const data = rows
    .map((tr) => {
      const tds = [...tr.querySelectorAll("td")];

      const appid =
        tr.dataset.appid ||
        tr.querySelector('a[href^="/app/"]')?.getAttribute("href")?.match(/\/app\/(\d+)\//)?.[1] ||
        "";

      const name =
        tr.querySelector("td:nth-child(3) a.b")?.textContent?.trim().replace(/\s+/g, " ") ||
        tds[2]?.textContent?.trim().replace(/\s+/g, " ") ||
        "";

      const current = Number(tds[3]?.dataset.sort || "0");
      const peak24h = Number(tds[4]?.dataset.sort || "0");
      const peakAllTime = Number(tds[5]?.dataset.sort || "0");

      if (!appid || !name) return null;

      return {
        appid,
        primary_english_name: name,
        current,
        peak_24h: peak24h,
        peak_all_time: peakAllTime,
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.peak_24h - a.peak_24h)
    .slice(0, 500)
    .map((row, index) => ({
      steamdb_rank: index + 1,
      ...row,
    }));

  if (data.length === 0) {
    console.error("没有解析到任何游戏。");
    return;
  }

  const emptyNameCount = data.filter(row => !row.primary_english_name).length;

  console.log(`解析到 ${data.length} 条记录。`);
  console.log(`空名称数量：${emptyNameCount}`);
  console.table(data.slice(0, 10));

  const escapeCsv = (value) => {
    const text = String(value ?? "");
    return `"${text.replace(/"/g, '""')}"`;
  };

  const csv = [
    [
      "steamdb_rank",
      "appid",
      "primary_english_name",
      "current",
      "peak_24h",
      "peak_all_time"
    ].join(","),
    ...data.map(row =>
      [
        row.steamdb_rank,
        row.appid,
        escapeCsv(row.primary_english_name),
        row.current,
        row.peak_24h,
        row.peak_all_time,
      ].join(",")
    )
  ].join("\n");

  // 加 BOM，方便 Excel / WPS 正确识别 UTF-8
  const blob = new Blob(["\ufeff" + csv], {
    type: "text/csv;charset=utf-8",
  });

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = "steamdb_top500.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();

  URL.revokeObjectURL(url);
})();