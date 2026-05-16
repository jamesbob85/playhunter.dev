"""Fetch live Twitch signals with per-game caching.

Cache: data/cache/twitch/<appid>.json (stale after 1h — live data)
Twitch gameId lookup is cached separately under data/cache/twitch_id/<appid>.json
(stale after 30d — these never change).

Run with --refresh to force re-fetch.

Requires TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET. Reads from .env automatically.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import _env  # noqa: E402
import _cache  # noqa: E402
import _universe  # noqa: E402
_env.load()

OUT = ROOT / "data" / "raw_twitch.json"

CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET")

LIVE_STALE = 3600           # 1h
ID_STALE = 30 * 24 * 3600   # 30d


def get_token() -> str:
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(
        "https://id.twitch.tv/oauth2/token",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]


def helix(path: str, token: str, params):
    url = f"https://api.twitch.tv/helix/{path}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def resolve_game_id(appid: int, name: str, token: str):
    cached = _cache.read("twitch_id", appid, ID_STALE, False)
    if cached:
        return cached.get("payload")
    games = helix("games", token, {"name": name}).get("data", [])
    payload = games[0] if games else None
    _cache.write("twitch_id", appid, {"payload": payload})
    return payload


def fetch_live_signals(game_id: str, token: str):
    streams = helix("streams", token, {"game_id": game_id, "first": 100}).get("data", [])
    viewers = sum(s.get("viewer_count", 0) for s in streams)
    top_tier = [s for s in streams if s.get("viewer_count", 0) >= 10_000]
    mid_tier = [s for s in streams if 1_000 <= s.get("viewer_count", 0) < 10_000]
    small = [s for s in streams if s.get("viewer_count", 0) < 1_000]
    return {
        "game_id": game_id,
        "current_streams": len(streams),
        "current_viewers": viewers,
        "top_tier_count": len(top_tier),
        "mid_tier_count": len(mid_tier),
        "small_count": len(small),
        "top_streamers": [
            {"user": s.get("user_login"), "viewers": s.get("viewer_count"), "title": (s.get("title") or "")[:120]}
            for s in streams[:10]
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if not (CLIENT_ID and CLIENT_SECRET):
        print("TWITCH_CLIENT_ID/SECRET not set. Writing empty.")
        OUT.write_text(json.dumps({"_no_creds": True, "games": {}}, indent=2))
        return

    token = get_token()
    candidates = _universe.load_candidates(include_other=True)
    out = {"_synthetic": False, "games": {}}
    hit, miss = 0, 0

    for i, g in enumerate(candidates):
        appid = g["appid"]
        name = g.get("name") or ""
        if not name:
            continue
        cached_live = _cache.read("twitch", appid, LIVE_STALE, args.refresh)
        if cached_live:
            payload = cached_live.get("payload")
            hit += 1
        else:
            try:
                game_info = resolve_game_id(appid, name, token)
                if game_info:
                    payload = fetch_live_signals(game_info["id"], token)
                    payload["box_art_url"] = game_info.get("box_art_url")
                    payload["twitch_game_name"] = game_info.get("name")
                    payload["igdb_id"] = game_info.get("igdb_id")
                else:
                    payload = {"_no_match": True, "query": name}
            except Exception as e:
                payload = {"_error": str(e)}
            _cache.write("twitch", appid, {"payload": payload})
            miss += 1
            time.sleep(0.25)

        out["games"][name] = payload
        out["games"].setdefault("_by_appid", {})[str(appid)] = name
        if (i + 1) % 25 == 0 or i == 0:
            summary = (
                f"{payload.get('current_streams', 0)} streams, {payload.get('current_viewers', 0)} viewers"
                if isinstance(payload, dict) and "current_streams" in payload else "—"
            )
            print(f"[{i+1}/{len(candidates)}] {name}: {summary}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}  (cache hits: {hit}, fresh fetches: {miss})")


if __name__ == "__main__":
    main()
