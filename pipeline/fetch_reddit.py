"""Fetch Reddit subreddit subscriber counts as a community-velocity signal.

Tracks both:
  1. Per-game subreddits (mapped from seed games + curated upstream candidates).
     Subscriber-growth deltas appear once snapshot history accumulates.
  2. Cross-cutting taste subreddits (r/pcgaming, r/IndieDev, etc.) for
     baseline cohort-size context.

Uses Reddit's public JSON endpoint (no auth needed, polite UA + rate limit).
Cache: data/cache/reddit/<subreddit>.json (stale after 12h)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import _cache  # noqa: E402
import _universe  # noqa: E402

OUT = ROOT / "data" / "raw_reddit.json"
STALE = 12 * 3600

UA = "scout.playhunter.dev:v1 (by /u/scoutbot)"

# Per-game subreddit overrides — when the auto-derived name from title differs.
# Most games can be derived from the title (e.g. "Manor Lords" → "ManorLords").
GAME_SUBS_OVERRIDES = {
    "1030300": "HollowKnight",       # Silksong discussion lives in HK sub
    "3241660": "REPOgame",
    "1145350": "HadesTheGame",
    "1458140": "PacificDriveGame",
    "553850":  "Helldivers",
    "2622380": "Eldenring",          # includes Nightreign
    "2358720": "BlackMythWukong",
    "1962700": "Subnautica",         # Subnautica 2 → same sub
    "1086940": "BaldursGate3",
    "2767030": "marvelrivals",
    "2807960": "Battlefield",        # Battlefield 6 → Battlefield sub
    "3321460": "CrimsonDesert",
}


def derive_subreddit_name(title: str) -> str:
    """Best-effort: strip punctuation + spaces from title."""
    import re
    s = re.sub(r"[^A-Za-z0-9]+", "", title or "")
    return s[:21] if s else ""

# Cross-cutting taste subreddits
TASTE_SUBS = [
    "pcgaming",
    "Games",
    "IndieDev",
    "indiegaming",
    "gaming",
    "GameDeals",
    "Steam",
    "patientgamers",
    "truegaming",
]


def fetch_sub(name: str):
    url = f"https://www.reddit.com/r/{name}/about.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    return d.get("data") or {}


def slim(rec: dict) -> dict:
    return {
        "display_name": rec.get("display_name") or rec.get("display_name_prefixed"),
        "subscribers": rec.get("subscribers"),
        "active_user_count": rec.get("active_user_count") or rec.get("accounts_active"),
        "created_utc": rec.get("created_utc"),
        "title": rec.get("title"),
        "public_description": (rec.get("public_description") or "")[:200],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    out = {
        "_source": "reddit",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "games": {},
        "taste": {},
    }

    candidates = _universe.load_candidates(include_other=True)
    all_targets = []
    for c in candidates:
        appid = str(c["appid"])
        sub = GAME_SUBS_OVERRIDES.get(appid) or derive_subreddit_name(c.get("name", ""))
        if sub:
            all_targets.append(("game", appid, sub))
    for sub in TASTE_SUBS:
        all_targets.append(("taste", None, sub))

    hit, miss = 0, 0
    for i, (kind, appid, sub) in enumerate(all_targets):
        cache_key = hash(sub) & 0x7FFFFFFF
        cached = _cache.read("reddit", cache_key, STALE, args.refresh)
        if cached:
            payload = cached.get("payload")
            hit += 1
        else:
            try:
                payload = slim(fetch_sub(sub))
            except Exception as e:
                payload = {"_error": str(e), "name": sub}
            _cache.write("reddit", cache_key, {"payload": payload, "subreddit": sub})
            miss += 1
            time.sleep(0.8)  # be polite

        if kind == "game":
            out["games"][appid] = {"subreddit": sub, **payload}
        else:
            out["taste"][sub] = payload

        if (i + 1) % 30 == 0 or i == 0:
            sub_count = payload.get("subscribers") if isinstance(payload, dict) else None
            print(f"[{i+1}/{len(all_targets)}] r/{sub}: " + (f"{sub_count:,}" if isinstance(sub_count, int) else "—"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}  (cache hits: {hit}, fresh fetches: {miss})")


if __name__ == "__main__":
    main()
