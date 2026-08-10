// Chart freshness: how much of today's Play top-grossing chart belongs to
// recently launched games? Fetches the US top-200 grossing (parse-play),
// resolves each title's release date (google-play-scraper, cached), and
// emits counts of 2025+/2024+ launches in the top 50/100/200.
// Output: GamesDiscovery/data/play-chart-freshness.json
import { fetchTopCharts } from "parse-play";
import gplay from "google-play-scraper";
import { readFile, writeFile, mkdir } from "node:fs/promises";

const OUT = "/Users/kavs/vibes/GamesDiscovery/data/play-chart-freshness.json";
const CACHE = "/Users/kavs/vibes/GamesDiscovery/data/play-release-dates.json";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let cache = {};
try { cache = JSON.parse(await readFile(CACHE, "utf8")); } catch {}

const chart = await fetchTopCharts(
  { category: "GAME", chart: "topgrossing", count: 200 },
  { country: "US", language: "en" },
);
console.log(`chart: ${chart.length} entries`);

const rows = [];
for (const [i, e] of chart.entries()) {
  const appId = e.app_id ?? e.appId;
  const name = e.name ?? e.title;
  if (!(appId in cache)) {
    try {
      const app = await gplay.app({ appId, country: "us" });
      cache[appId] = app.released ?? null;   // e.g. "Mar 19, 2018"
    } catch { cache[appId] = null; }
    await sleep(1000 + Math.random() * 300);
    if (i % 25 === 24) {
      await writeFile(CACHE, JSON.stringify(cache));
      console.log(`[${i + 1}/200] cached`);
    }
  }
  const rel = cache[appId];
  const year = rel ? new Date(rel).getFullYear() : null;
  rows.push({ rank: i + 1, name, appId, released: rel, year });
}
await writeFile(CACHE, JSON.stringify(cache));

const summary = {};
for (const n of [50, 100, 200]) {
  const band = rows.slice(0, n);
  const known = band.filter((r) => r.year);
  summary[`top${n}`] = {
    launched_2025plus: known.filter((r) => r.year >= 2025).length,
    launched_2024plus: known.filter((r) => r.year >= 2024).length,
    unknown_release: band.length - known.length,
  };
}
const fresh = rows.filter((r) => r.year >= 2025).map((r) => `${r.name} (#${r.rank})`);
await writeFile(OUT, JSON.stringify({
  fetched: new Date().toISOString().slice(0, 10),
  country: "US", chart: "topgrossing",
  summary, launched_2025: fresh, rows,
}, null, 1));
console.log(JSON.stringify(summary, null, 1));
console.log("2025 launches on the chart:", fresh.join(" · ") || "none");
