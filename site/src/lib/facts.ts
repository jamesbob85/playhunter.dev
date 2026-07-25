// Facts layer accessor. One JSON per game, machine-written by
// scripts/refresh-facts.mjs. Editorial pages merge these at build time.

export interface Facts {
  slug: string;
  appId: string;
  fetchedAt: string;
  title: string;
  developer: string;
  playUrl: string;
  price: number;
  priceText: string;
  free: boolean;
  offersIAP: boolean;
  IAPRange: string | null;
  adSupported: boolean;
  score: number | null;
  ratings: number | null;
  reviews: number | null;
  installs: string;
  contentRating: string | null;
  genre: string | null;
  updated: string | null;
  released: string | null;
  androidVersion: string | null;
  icon: string;
  headerImage: string | null;
  video: string | null;
  videoImage: string | null;
  screenshots: string[];
  summary: string | null;
}

const modules = import.meta.glob<{ default: Facts }>('../data/facts/*.json', { eager: true });

export const allFacts: Record<string, Facts> = Object.fromEntries(
  Object.values(modules).map((m) => [m.default.slug, m.default])
);

export function getFacts(slug: string): Facts {
  const f = allFacts[slug];
  if (!f) throw new Error(`No facts JSON for slug "${slug}" — run: node scripts/refresh-facts.mjs`);
  return f;
}

// Play CDN images accept a size suffix (=w<px>). Strip any existing one first.
export function playImg(url: string, w: number): string {
  return `${url.split('=')[0]}=w${w}`;
}

export function fmtCount(n: number | null): string {
  if (n == null) return '—';
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
}

// outbound chokepoint — every Play link goes through here
export function playLink(facts: Facts): string {
  return `${facts.playUrl}&referrer=utm_source%3Dplayhunter`;
}
