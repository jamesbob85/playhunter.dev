"""Fetch IGDB per-game data with per-game caching.

IGDB shares OAuth with Twitch (same Client ID + Secret).

Pulls:
  - popscore (hypes-driven popularity score)
  - hypes (pre-launch interest signal)
  - follows (IGDB-tracked followers)
  - aggregated_rating / aggregated_rating_count (critic score)
  - total_rating (combined critic + user score)
  - rating / rating_count (user score)
  - themes, genres, keywords (rich taxonomy)
  - game_modes (Singleplayer, Multiplayer, Co-op, MMO, Battle Royale, Split screen)
  - multiplayer_modes (online co-op, offline co-op, etc.)
  - player_perspectives (FPS, 3rd-person, isometric, etc.)
  - game_engines (Unity, Unreal, etc.)
  - similar_games (id list; can join in a second pass)

Cache: data/cache/igdb/<appid>.json (stale after 24h)
Resolution-by-name cache: data/cache/igdb_id/<appid>.json (stale 30d)

Run with --refresh to force re-fetch.
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

OUT = ROOT / "data" / "raw_igdb.json"

CLIENT_ID = os.environ.get("IGDB_CLIENT_ID") or os.environ.get("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("IGDB_CLIENT_SECRET") or os.environ.get("TWITCH_CLIENT_SECRET")

STALE = 24 * 3600
ID_STALE = 30 * 24 * 3600

GAME_FIELDS = ",".join([
    "id", "name", "slug", "summary", "url",
    "hypes", "follows",
    "rating", "rating_count",
    "aggregated_rating", "aggregated_rating_count",
    "total_rating", "total_rating_count",
    "first_release_date",
    "release_dates",
    "themes.name",
    "genres.name",
    "keywords.name",
    "game_modes.name",
    "multiplayer_modes.*",
    "player_perspectives.name",
    "game_engines.name",
    "similar_games.id",
    "similar_games.name",
    "involved_companies.company.name",
    "involved_companies.developer",
    "involved_companies.publisher",
    "category",
    "status",
    "websites.url",
    "websites.category",
])

# Endpoint for the popscore (popularity) metric — IGDB exposes it separately
POP_PRIMITIVES = "/v4/popularity_primitives"
POP_TYPES_TO_LABEL = {
    1: "igdb_visits",
    2: "igdb_want_to_play",
    3: "igdb_played",
    4: "igdb_playing",
    5: "wikipedia_visits",
    6: "steam_24h_peak",
    7: "steam_positive_reviews",
    8: "steam_negative_reviews",
    9: "youtube_popularity",
    10: "steam_marketplace_volume",
}


def get_token() -> str:
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(
        "https://id.twitch.tv/oauth2/token",
        data=body, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]


def igdb_post(path: str, body: str, token: str):
    req = urllib.request.Request(
        f"https://api.igdb.com{path}",
        data=body.encode(),
        headers={
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def resolve_igdb_id(appid: int, name: str, twitch_igdb_id, token: str):
    """Return the IGDB game id for an appid. Prefer the id provided by Twitch (which already
    matches IGDB). Fallback to name search."""
    cached = _cache.read("igdb_id", appid, ID_STALE, False)
    if cached:
        return cached.get("payload")

    payload = None
    if twitch_igdb_id and str(twitch_igdb_id) != "0":
        payload = int(twitch_igdb_id)
    else:
        # Search by name. IGDB search returns approximate matches.
        q = f'search "{name}"; fields id,name; limit 5;'
        try:
            results = igdb_post("/v4/games", q, token)
            if results:
                payload = results[0]["id"]
        except Exception:
            payload = None
    _cache.write("igdb_id", appid, {"payload": payload})
    return payload


def fetch_game(igdb_id: int, token: str):
    body = f"fields {GAME_FIELDS}; where id = {igdb_id};"
    results = igdb_post("/v4/games", body, token)
    if not results:
        return None
    g = results[0]
    return g


def fetch_pop(igdb_id: int, token: str):
    """Fetch popularity_primitives for one game across all source types."""
    body = (
        f"fields game_id,popularity_type,value,calculated_at; "
        f"where game_id = {igdb_id}; sort calculated_at desc; limit 50;"
    )
    try:
        results = igdb_post(POP_PRIMITIVES, body, token)
    except Exception as e:
        return {"_error": str(e)}
    by_type = {}
    for r in results:
        t = r.get("popularity_type")
        label = POP_TYPES_TO_LABEL.get(t, f"type_{t}")
        # Keep only the most recent for each type (sorted desc above)
        by_type.setdefault(label, r)
    return by_type


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if not (CLIENT_ID and CLIENT_SECRET):
        print("No IGDB/Twitch credentials. Writing empty.")
        OUT.write_text(json.dumps({"_no_creds": True, "games": {}}, indent=2))
        return

    token = get_token()
    candidates = _universe.load_candidates(include_other=True)
    # Try to pull igdb_id from twitch cache if available
    twitch_data = {}
    twitch_blob_path = ROOT / "data" / "raw_twitch.json"
    if twitch_blob_path.exists():
        try:
            twitch_data = json.loads(twitch_blob_path.read_text())
        except Exception:
            twitch_data = {}

    out = {"games": {}}
    hit, miss = 0, 0

    for i, g in enumerate(candidates):
        appid = g["appid"]
        name = g.get("name") or ""
        if not name:
            continue

        cached = _cache.read("igdb", appid, STALE, args.refresh)
        if cached:
            payload = cached.get("payload")
            hit += 1
        else:
            tw_match = (twitch_data.get("games") or {}).get(name) or {}
            tw_igdb_id = tw_match.get("igdb_id") if isinstance(tw_match, dict) else None
            try:
                igdb_id = resolve_igdb_id(appid, name, tw_igdb_id, token)
                if igdb_id:
                    game = fetch_game(igdb_id, token)
                    pop = fetch_pop(igdb_id, token)
                    payload = {"game": game, "popularity": pop, "igdb_id": igdb_id}
                else:
                    payload = {"_no_match": True}
            except Exception as e:
                payload = {"_error": str(e)}
            _cache.write("igdb", appid, {"payload": payload})
            miss += 1
            time.sleep(0.3)

        out["games"][str(appid)] = payload
        if (i + 1) % 25 == 0 or i == 0:
            gn = (payload.get("game") or {}).get("name") if isinstance(payload, dict) else None
            hypes = (payload.get("game") or {}).get("hypes") if isinstance(payload, dict) else None
            print(f"[{i+1}/{len(candidates)}] {gn or name} hypes={hypes}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}  (cache hits: {hit}, fresh fetches: {miss})")


if __name__ == "__main__":
    main()
