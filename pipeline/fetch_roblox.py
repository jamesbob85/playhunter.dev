"""Fetch top trending Roblox experiences as an upstream taste signal.

Roblox skews young; what trends here often becomes a genre/mechanic signal
for the PC cohort 2-5 years out. Treat with explicit grain of salt.

Source: apis.roblox.com/explore-api/v1/get-sort-content (no auth)
Cache: data/cache/roblox/top-trending.json (stale after 6h)
Run with --refresh to force re-fetch.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import _cache  # noqa: E402

OUT = ROOT / "data" / "raw_roblox.json"
STALE = 6 * 3600

SORTS = [
    ("top-trending", "Top trending"),
    ("popular", "Popular"),
    ("top-rated", "Top rated"),
]


def fetch_sort(sort_id: str):
    url = f"https://apis.roblox.com/explore-api/v1/get-sort-content?sortId={sort_id}&sessionId=scout-{int(time.time())}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (scout.playhunter.dev)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    return d.get("games") or []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    out = {"_source": "roblox-explore-api", "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sorts": {}}

    for sort_id, label in SORTS:
        # cache key uses 0 as a synthetic "appid"
        cache_key = hash(sort_id) & 0x7FFFFFFF
        cached = _cache.read("roblox", cache_key, STALE, args.refresh)
        if cached:
            games = cached.get("payload") or []
            print(f"[{sort_id}] cached: {len(games)} games")
        else:
            try:
                games = fetch_sort(sort_id)
                print(f"[{sort_id}] fetched: {len(games)} games")
            except Exception as e:
                games = []
                print(f"[{sort_id}] error: {e}")
            _cache.write("roblox", cache_key, {"payload": games, "sort_id": sort_id})
            time.sleep(0.4)

        # Slim each entry
        slim = []
        for g in games[:30]:
            up = int(g.get("totalUpVotes") or 0)
            down = int(g.get("totalDownVotes") or 0)
            total = up + down
            ratio = (up / total) if total else 0.0
            slim.append({
                "universe_id": g.get("universeId"),
                "root_place_id": g.get("rootPlaceId"),
                "name": g.get("name"),
                "player_count": int(g.get("playerCount") or 0),
                "up_votes": up,
                "down_votes": down,
                "approval_ratio": round(ratio, 3),
                "min_age": g.get("minimumAge"),
                "age_label": g.get("ageRecommendationDisplayName"),
                "is_sponsored": g.get("isSponsored", False),
                "url": f"https://www.roblox.com/games/{g.get('rootPlaceId')}",
            })
        out["sorts"][sort_id] = {"label": label, "games": slim}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
