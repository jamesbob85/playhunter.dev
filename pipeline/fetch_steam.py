"""Fetch static Steam facts + SteamSpy player snapshot, with per-game caching.

Sources (no key needed):
  - store.steampowered.com/api/appdetails
  - steamspy.com/api.php

Cache: data/cache/steam/<appid>.json (stale after 24h)
       data/cache/steamspy/<appid>.json (stale after 6h)
Run with --refresh to force re-fetch.

Aggregates into data/raw_steam.json.
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

OUT = ROOT / "data" / "raw_steam.json"

UA = "Mozilla/5.0 (scout.playhunter.dev research bot)"
STEAM_STALE = 24 * 3600
SPY_STALE = 6 * 3600


def get_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_appdetails(appid: int):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=en"
    try:
        data = get_json(url)
        rec = data.get(str(appid), {})
        if not rec.get("success"):
            return None
        d = rec["data"]
        return {
            "name": d.get("name"),
            "type": d.get("type"),
            "is_free": d.get("is_free", False),
            "release_date": d.get("release_date", {}).get("date"),
            "coming_soon": d.get("release_date", {}).get("coming_soon", False),
            "developers": d.get("developers", []),
            "publishers": d.get("publishers", []),
            "price": (d.get("price_overview", {}) or {}).get("final_formatted"),
            "header_image": d.get("header_image"),
            "capsule_image": d.get("capsule_image"),
            "genres": [g.get("description") for g in d.get("genres", [])],
            "categories": [c.get("description") for c in d.get("categories", [])],
            "short_description": d.get("short_description"),
            "platforms": d.get("platforms", {}),
        }
    except Exception as e:
        return {"_error": str(e)}


def fetch_steamspy(appid: int):
    url = f"https://steamspy.com/api.php?request=appdetails&appid={appid}"
    try:
        d = get_json(url)
        if not d or d.get("name") in (None, "", "null"):
            return None
        return {
            "owners": d.get("owners"),
            "players_forever": d.get("players_forever"),
            "players_2weeks": d.get("players_2weeks"),
            "average_forever": d.get("average_forever"),
            "average_2weeks": d.get("average_2weeks"),
            "ccu": d.get("ccu"),
            "score_rank": d.get("score_rank"),
            "positive": d.get("positive"),
            "negative": d.get("negative"),
            "tags": d.get("tags") if isinstance(d.get("tags"), dict) else {},
        }
    except Exception as e:
        return {"_error": str(e)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="Force refresh of all cached records")
    args = ap.parse_args()

    candidates = _universe.load_candidates(include_other=True)
    if not candidates:
        print("No universe.json — run fetch_universe.py first.")
        return
    out = {}
    hit, miss = 0, 0
    for i, g in enumerate(candidates):
        appid = g["appid"]

        cached_steam = _cache.read("steam", appid, STEAM_STALE, args.refresh)
        cached_spy = _cache.read("steamspy", appid, SPY_STALE, args.refresh)

        if cached_steam:
            details = cached_steam.get("payload")
            hit += 1
        else:
            details = fetch_appdetails(appid)
            _cache.write("steam", appid, {"payload": details})
            miss += 1
            time.sleep(0.7)

        if cached_spy:
            spy = cached_spy.get("payload")
            hit += 1
        else:
            spy = fetch_steamspy(appid)
            _cache.write("steamspy", appid, {"payload": spy})
            miss += 1
            time.sleep(0.7)

        if (i + 1) % 25 == 0 or i == 0:
            print(f"[{i+1}/{len(candidates)}] {appid} {(details or {}).get('name') or '?'}", flush=True)
        out[str(appid)] = {
            "appid": appid,
            "seed": {
                "appid": appid,
                "twitch_name": (details or {}).get("name") or g.get("name"),
                "stage_hint": g.get("lifecycle_class"),
                "lifecycle_class": g.get("lifecycle_class"),
                "meta_clusters": [],
            },
            "appdetails": details,
            "steamspy": spy,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}  (cache hits: {hit}, fresh fetches: {miss})")


if __name__ == "__main__":
    main()
