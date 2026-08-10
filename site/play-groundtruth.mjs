// Ground-truth pass: verify Google Play presence for every game in the
// Twitch love universe, and capture monetization flags in the same call.
//
// For each of the 936 games (availability.json, top-1000 categories, 365d):
//   1. If IGDB gave a Play package id -> gplay.app({appId}) and GATE the hit
//      by developer match (IGDB's Minecraft uid points at a clone app — the
//      gate catches exactly this).
//   2. Else gplay.search(title) -> gate top hits by normalized-title
//      similarity AND developer≈IGDB company. Bare title matches without a
//      developer anchor are recorded as weak (review list), never as on-Play.
//   3. Countries in order: us, in, jp, kr, br — first gated hit wins
//      ("on Play" = live in ANY of the five, per the audit's policy).
//
// Monetization per found app: free, offersIAP, IAPRange, adSupported.
// Resumable: one JSON per twitch_id in GamesDiscovery/data/play-truth/.
// Pace: ~1.1 req/s with jitter. Run: node play-groundtruth.mjs
import gplay from "google-play-scraper";
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";

const AVAIL = "/Users/kavs/vibes/GamesDiscovery/data/availability.json";
const OUT = "/Users/kavs/vibes/GamesDiscovery/data/play-truth";
const COUNTRIES = ["us", "in", "jp", "kr", "br"];

const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pace = () => sleep(900 + Math.random() * 400);

function devMatch(appDev, companies) {
  if (!companies || !companies.length) return false;
  const a = norm(appDev);
  if (!a) return false;
  return companies.some((c) => {
    const n = norm(c);
    return n && (a.includes(n) || n.includes(a));
  });
}

function slim(app) {
  return {
    appId: app.appId, title: app.title, developer: app.developer,
    free: app.free, price: app.price, offersIAP: app.offersIAP,
    IAPRange: app.IAPRange ?? null, adSupported: app.adSupported ?? null,
    installs: app.maxInstalls ?? app.installs ?? null,
    ratings: app.ratings ?? null, score: app.score ?? null,
    released: app.released ?? null, url: app.url,
  };
}

async function checkPackage(pkg, companies) {
  for (const country of COUNTRIES) {
    try {
      const app = await gplay.app({ appId: pkg, country });
      await pace();
      if (!companies?.length || devMatch(app.developer, companies))
        return { found: true, via: "package", country, app: slim(app) };
      return { found: false, via: "package-dev-mismatch", suspect: slim(app) };
    } catch { await pace(); }
  }
  return null;
}

async function searchTitle(name, companies) {
  const target = norm(name);
  let weak = null;
  for (const country of COUNTRIES) {
    try {
      const hits = await gplay.search({ term: name, num: 5, country });
      await pace();
      for (const h of hits) {
        const ht = norm(h.title);
        const titleOk = ht === target || ht.startsWith(target) || target.startsWith(ht);
        if (!titleOk) continue;
        if (devMatch(h.developer, companies))
          return { found: true, via: "search", country, app: slim(h) };
        if (!weak) weak = { via: "search-weak", country, app: slim(h) };
      }
    } catch { await pace(); }
  }
  return weak ? { found: false, ...weak } : null;
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const avail = JSON.parse(await readFile(AVAIL, "utf8"));
  const games = avail
    .filter((g) => g.is_game && g.windows?.["365"])
    .sort((a, b) => b.windows["365"].viewminutes - a.windows["365"].viewminutes)
    .slice(0, 1000);

  let done = 0, found = 0, weak = 0, missing = 0;
  for (const g of games) {
    const path = `${OUT}/${g.twitch_id}.json`;
    try { await stat(path); done++; continue; } catch {}
    const ig = g.igdb || {};
    const companies = ig.companies || [];
    let result = null;
    if (ig.play_package) result = await checkPackage(ig.play_package, companies);
    if (!result || (!result.found && result.via === "package-dev-mismatch"))
      result = (await searchTitle(g.name, companies)) ?? result;
    result ??= { found: false, via: "no-hit" };
    result.name = g.name;
    result.twitch_id = g.twitch_id;
    result.igdb_said_play = !!(ig.stores?.play || ig.play_package);
    await writeFile(path, JSON.stringify(result));
    done++;
    if (result.found) found++;
    else if (result.via?.includes("weak")) weak++;
    else missing++;
    if (done % 50 === 0)
      console.log(`[${done}/${games.length}] found=${found} weak=${weak} miss=${missing} — ${g.name}`);
  }
  console.log(`DONE: ${done} checked this run+cache; new: found=${found} weak=${weak} miss=${missing}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
