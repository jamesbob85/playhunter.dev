// refresh-facts.mjs — the FACTS layer.
// Pulls live listing data from Google Play for every game in the roster and
// writes src/data/facts/<slug>.json. Editorial content never lives here;
// this file's output is machine-owned and safe to regenerate any time.
//
//   node scripts/refresh-facts.mjs            # refresh all
//   node scripts/refresh-facts.mjs balatro    # refresh one slug

import gplay from 'google-play-scraper';
import { writeFile, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'src', 'data', 'facts');

// slug -> Play package id. Slugs are the site's top-level URLs.
const ROSTER = {
  'balatro': 'com.playstack.balatro.android',
  'stardew-valley': 'com.chucklefish.stardewvalley',
  'dead-cells': 'com.playdigious.deadcells.mobile',
  'slay-the-spire': 'com.humble.SlayTheSpire',
  'monument-valley-2': 'com.ustwo.monumentvalley2',
  'terraria': 'com.and.games505.TerrariaPaid',
  'bloons-td-6': 'com.ninjakiwi.bloonstd6',
  'dont-starve': 'com.kleientertainment.doNotStarvePocket',
  'papers-please': 'com.llc3909.papersplease',
  'monument-valley': 'com.ustwo.monumentvalley',
  'mini-metro': 'nz.co.codepoint.minimetro',
  'the-room': 'com.FireproofStudios.TheRoom',
};

const only = process.argv[2];
const entries = Object.entries(ROSTER).filter(([slug]) => !only || slug === only);

await mkdir(OUT, { recursive: true });

let failures = 0;
for (const [slug, appId] of entries) {
  try {
    const a = await gplay.app({ appId, country: 'us', lang: 'en' });
    const facts = {
      slug,
      appId,
      fetchedAt: new Date().toISOString().slice(0, 10),
      title: a.title,
      developer: a.developer,
      playUrl: `https://play.google.com/store/apps/details?id=${appId}`,
      price: a.price,               // number, USD
      priceText: a.priceText ?? (a.price ? `$${a.price.toFixed(2)}` : 'Free'),
      free: a.free,
      offersIAP: a.offersIAP ?? false,
      IAPRange: a.IAPRange ?? null,
      adSupported: a.adSupported ?? false,
      score: a.score ? Math.round(a.score * 10) / 10 : null,
      ratings: a.ratings ?? null,   // count
      reviews: a.reviews ?? null,
      installs: a.maxInstalls ? formatInstalls(a.maxInstalls) : a.installs,
      contentRating: a.contentRating ?? null,
      genre: a.genre ?? null,
      updated: a.updated ? new Date(a.updated).toISOString().slice(0, 10) : null,
      released: a.released ?? null,
      androidVersion: a.androidVersionText ?? null,
      icon: a.icon,
      headerImage: a.headerImage ?? null,
      video: a.video ?? null,
      videoImage: a.videoImage ?? null,
      screenshots: (a.screenshots ?? []).slice(0, 8),
      summary: a.summary ?? null,   // Play's own 80-char pitch, useful for OG fallback
    };
    await writeFile(join(OUT, `${slug}.json`), JSON.stringify(facts, null, 2) + '\n');
    console.log(`ok   ${slug.padEnd(20)} ${facts.priceText.padEnd(7)} ${facts.score}★ ${facts.installs} ${facts.offersIAP ? '+IAP' : ''}`);
  } catch (err) {
    failures++;
    console.error(`FAIL ${slug}: ${err.message}`);
  }
}
if (failures) process.exit(1);

function formatInstalls(n) {
  if (n >= 1e7) return `${Math.floor(n / 1e6)}M+`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M+`;
  if (n >= 1e3) return `${Math.floor(n / 1e3)}K+`;
  return `${n}+`;
}
