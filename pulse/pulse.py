#!/usr/bin/env python3
"""Twitch pulse poller — per-category viewers, channel counts, and creator sets.

Sweeps the top-100 Twitch categories and records, per category:
  ts, game_id, game_name, igdb_id, viewers (sum), channels (distinct live)

Modes:
  --once --csv-dir DIR    one sweep, append to DIR/YYYY-MM-DD.csv  (GitHub Actions)
  --loop --db PATH        sweep every 15 min, SQLite incl. distinct creators (local)

Credentials: TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET from the environment,
or an env file passed via --env-file (never printed).

Rate budget: app tokens get ~800 points/min; a sweep is ~300-600 requests
paced at <=8 req/s, so a sweep finishes in ~1-2 min well under budget.
Deep pagination in huge categories (Just Chatting) is capped at 60 pages;
streams are deduped by user_id within a sweep (Twitch pagination can
duplicate entries as viewership churns).
"""
import argparse
import csv
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"
PAGE_CAP = 60          # max pages per category (100 streams/page)
REQ_INTERVAL = 0.13    # ~8 req/s
SWEEP_MINUTES = 15


def load_env_file(path):
    if not path or not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Twitch:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self._last_req = 0.0

    def _authenticate(self):
        body = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }).encode()
        req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            self.token = json.load(r)["access_token"]

    def get(self, path, params, _retry=True):
        wait = self._last_req + REQ_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        if self.token is None:
            self._authenticate()
        url = f"{HELIX}{path}?{urllib.parse.urlencode(params, doseq=True)}"
        req = urllib.request.Request(url, headers={
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
        })
        self._last_req = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401 and _retry:
                self.token = None
                return self.get(path, params, _retry=False)
            if e.code == 429 and _retry:
                reset = float(e.headers.get("Ratelimit-Reset", time.time() + 15))
                time.sleep(max(1.0, reset - time.time()))
                return self.get(path, params, _retry=False)
            raise


def full_sweep(tw):
    """Paginate ALL live streams (no category filter) — the entire live tail.
    Returns (ts, rows, creators). ~1000 pages at peak (~2-3 min paced)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    agg = {}   # game_id -> {name, viewers, users:set}
    cursor = None
    for _ in range(1500):
        params = {"first": 100, "type": "live"}
        if cursor:
            params["after"] = cursor
        resp = tw.get("/streams", params)
        for s in resp["data"]:
            gid = s.get("game_id") or "0"
            a = agg.setdefault(gid, {"name": s.get("game_name") or "?",
                                     "viewers": 0, "users": set()})
            if s["user_id"] not in a["users"]:
                a["users"].add(s["user_id"])
                a["viewers"] += s["viewer_count"]
        cursor = resp.get("pagination", {}).get("cursor")
        if not cursor or not resp["data"]:
            break
    rows = [{"ts": ts, "game_id": gid, "game_name": a["name"], "igdb_id": "",
             "viewers": a["viewers"], "channels": len(a["users"])}
            for gid, a in agg.items()]
    rows.sort(key=lambda r: -r["viewers"])
    creators = {gid: a["users"] for gid, a in agg.items()}
    return ts, rows, creators


def sweep(tw):
    """One full sweep. Returns (ts, rows, creators) where rows are per-category
    aggregates and creators maps game_id -> set of user_ids seen live."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    top = tw.get("/games/top", {"first": 100})["data"]
    rows, creators = [], {}
    for cat in top:
        gid = cat["id"]
        seen = {}  # user_id -> viewer_count (dedupe across pages)
        cursor = None
        for _ in range(PAGE_CAP):
            params = {"game_id": gid, "first": 100, "type": "live"}
            if cursor:
                params["after"] = cursor
            resp = tw.get("/streams", params)
            for s in resp["data"]:
                seen[s["user_id"]] = s["viewer_count"]
            cursor = resp.get("pagination", {}).get("cursor")
            if not cursor or not resp["data"]:
                break
        rows.append({
            "ts": ts,
            "game_id": gid,
            "game_name": cat["name"],
            "igdb_id": cat.get("igdb_id") or "",
            "viewers": sum(seen.values()),
            "channels": len(seen),
        })
        creators[gid] = set(seen)
    return ts, rows, creators


def append_csv(csv_dir, rows):
    os.makedirs(csv_dir, exist_ok=True)
    day = rows[0]["ts"][:10] if rows else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(csv_dir, f"{day}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "game_id", "game_name", "igdb_id", "viewers", "channels"])
        if new:
            w.writeheader()
        w.writerows(rows)
    return path


def open_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS polls(
            ts TEXT, game_id TEXT, game_name TEXT, igdb_id TEXT,
            viewers INTEGER, channels INTEGER);
        CREATE INDEX IF NOT EXISTS polls_game ON polls(game_id, ts);
        CREATE TABLE IF NOT EXISTS creators(
            game_id TEXT, user_id TEXT, first_seen TEXT, last_seen TEXT,
            PRIMARY KEY(game_id, user_id));
        CREATE TABLE IF NOT EXISTS full_polls(
            ts TEXT, game_id TEXT, game_name TEXT,
            viewers INTEGER, channels INTEGER);
        CREATE INDEX IF NOT EXISTS full_polls_game ON full_polls(game_id, ts);
    """)
    return db


def record_db(db, ts, rows, creators):
    db.executemany(
        "INSERT INTO polls VALUES(:ts,:game_id,:game_name,:igdb_id,:viewers,:channels)", rows)
    for gid, users in creators.items():
        db.executemany(
            "INSERT INTO creators VALUES(?,?,?,?) ON CONFLICT(game_id,user_id) "
            "DO UPDATE SET last_seen=excluded.last_seen",
            [(gid, u, ts, ts) for u in users])
    db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--csv-dir")
    ap.add_argument("--db")
    ap.add_argument("--env-file")
    args = ap.parse_args()

    load_env_file(args.env_file)
    cid = os.environ.get("TWITCH_CLIENT_ID")
    sec = os.environ.get("TWITCH_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET not set")
    tw = Twitch(cid, sec)
    db = open_db(args.db) if args.db else None

    cycle = 0
    while True:
        started = time.monotonic()
        try:
            ts, rows, creators = sweep(tw)
            if args.csv_dir:
                append_csv(args.csv_dir, rows)
            if db is not None:
                record_db(db, ts, rows, creators)
            total_creators = sum(len(v) for v in creators.values())
            print(f"{ts} sweep ok: {len(rows)} categories, "
                  f"{sum(r['viewers'] for r in rows):,} viewers, "
                  f"{total_creators:,} live channels", flush=True)
            # hourly: the full live tail (every stream on Twitch)
            if db is not None and args.loop and cycle % 4 == 0:
                fts, frows, fcreators = full_sweep(tw)
                db.executemany(
                    "INSERT INTO full_polls VALUES(:ts,:game_id,:game_name,:viewers,:channels)",
                    frows)
                for gid, users in fcreators.items():
                    db.executemany(
                        "INSERT INTO creators VALUES(?,?,?,?) ON CONFLICT(game_id,user_id) "
                        "DO UPDATE SET last_seen=excluded.last_seen",
                        [(gid, u, fts, fts) for u in users])
                db.commit()
                print(f"{fts} FULL sweep: {len(frows):,} games live, "
                      f"{sum(r['viewers'] for r in frows):,} viewers, "
                      f"{sum(r['channels'] for r in frows):,} channels", flush=True)
        except Exception as e:  # keep the loop alive on transient failures
            print(f"sweep failed: {e!r}", file=sys.stderr, flush=True)
        cycle += 1
        if args.once or not args.loop:
            break
        elapsed = time.monotonic() - started
        time.sleep(max(30.0, SWEEP_MINUTES * 60 - elapsed))


if __name__ == "__main__":
    main()
