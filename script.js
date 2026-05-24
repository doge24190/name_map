(() => {
  const rows = [...document.querySelectorAll("table tbody tr")];

  const data = rows
    .map((tr, index) => {
      const appLink = tr.querySelector('a[href^="/app/"]');
      if (!appLink) return null;

      const href = appLink.getAttribute("href") || "";
      const match = href.match(/\/app\/(\d+)\//);
      if (!match) return null;

      const appid = match[1];
      const name = appLink.textContent.trim().replace(/\s+/g, " ");

      return {
        steamdb_rank: index + 1,
        appid,
        primary_english_name: name,
      };
    })
    .filter(Boolean)
    .slice(0, 500);

  const csv = [
    "steamdb_rank,appid,primary_english_name",
    ...data.map(row =>
      [
        row.steamdb_rank,
        row.appid,
        `"${row.primary_english_name.replace(/"/g, '""')}"`
      ].join(",")
    )
  ].join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "steamdb_top500.csv";
  a.click();

  URL.revokeObjectURL(url);

  console.log(`已导出 ${data.length} 条记录`);
})();
