"""Fetch Gamalytic per-game data with per-game caching.

Cache: data/cache/gamalytic/<appid>.json (stale after 12h)
Run with --refresh to force re-fetch.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import _env  # noqa: E402
import _cache  # noqa: E402
import _universe  # noqa: E402
_env.load()

OUT = ROOT / "data" / "raw_gamalytic.json"

ENDPOINT = "https://api.gamalytic.com/game"
RATE_DELAY = 0.3
STALE_SECONDS = 12 * 3600


def fetch(appid: int, key: str):
    req = urllib.request.Request(
        f"{ENDPOINT}/{appid}",
        headers={"api-key": key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e)}


def slim(data: dict) -> dict:
    slim = {k: data[k] for k in (
        "name", "followers", "reviews", "reviewsSteam", "reviewScore",
        "avgPlaytime", "tags", "genres", "features", "developers", "publishers",
        "releaseDate", "EAReleaseDate", "firstReleaseDate", "unreleased",
        "earlyAccess", "wishlists", "owners", "players", "copiesSold",
        "revenue", "totalRevenue", "price", "steamPercent",
    ) if k in data}
    slim["countryData"] = data.get("countryData") or {}
    slim["audienceOverlap"] = (data.get("audienceOverlap") or [])[:10]
    hist = data.get("history") or []
    if isinstance(hist, list):
        slim["history_last90"] = hist[-90:] if len(hist) > 90 else hist
    return slim


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("GAMALYTIC_API_KEY")
    if not key:
        print("No GAMALYTIC_API_KEY. Writing empty.")
        OUT.write_text(json.dumps({"_no_creds": True, "games": {}}, indent=2))
        return

    candidates = _universe.load_candidates(include_other=True)
    out = {"games": {}}
    hit, miss = 0, 0
    for i, g in enumerate(candidates):
        appid = g["appid"]
        cached = _cache.read("gamalytic", appid, STALE_SECONDS, args.refresh)
        if cached:
            data = cached.get("payload")
            hit += 1
        else:
            raw = fetch(appid, key)
            if raw and not raw.get("_error"):
                data = slim(raw)
            else:
                data = raw or {"_error": "no_data"}
            _cache.write("gamalytic", appid, {"payload": data})
            miss += 1
            time.sleep(RATE_DELAY)
        out["games"][str(appid)] = data
        if (i + 1) % 25 == 0 or i == 0:
            print(f"[{i+1}/{len(candidates)}] {appid}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}  (cache hits: {hit}, fresh fetches: {miss})")


if __name__ == "__main__":
    main()
