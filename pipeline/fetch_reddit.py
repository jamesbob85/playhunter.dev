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

OUT = ROOT / "data" / "raw_reddit.json"
STALE = 12 * 3600

UA = "scout.playhunter.dev:v1 (by /u/scoutbot)"

# Per-game subreddits (when one exists for a tracked title)
GAME_SUBS = {
    "1030300": "HollowKnight",      # also covers Silksong discussion
    "1966720": "lethalcompany",
    "3164500": "Schedule_I",
    "3241660": "REPOgame",
    "1145350": "HadesTheGame",
    "1363080": "ManorLords",
    "1601580": "Frostpunk",
    "1458140": "PacificDriveGame",
    "553850":  "Helldivers",
    "2198150": "TinyGlade",
    "1086940": "BaldursGate3",
    "2622380": "Eldenring",          # includes Nightreign
    "1623730": "Palworld",
    "2358720": "BlackMythWukong",
}

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

    all_targets = []
    for appid, sub in GAME_SUBS.items():
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

        sub_count = payload.get("subscribers") if isinstance(payload, dict) else None
        print(f"[{i+1}/{len(all_targets)}] r/{sub}: " + (f"{sub_count:,}" if isinstance(sub_count, int) else "—"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}  (cache hits: {hit}, fresh fetches: {miss})")


if __name__ == "__main__":
    main()
