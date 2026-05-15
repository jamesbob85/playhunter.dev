"""Fetch itch.io trending + featured games as an upstream indie signal.

itch.io is where most indies prove a loop before publisher attention or Steam.
A game trending here often becomes a Steam release within 6-18 months — and
sometimes a breakout (e.g. Friday Night Funkin', Vampire Survivors).

Sources: itch.io's /browse/featured + /games/newest HTML pages (no official API).
Cache: data/cache/itch/<sort>.json (stale after 6h)
Run with --refresh to force re-fetch.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import _cache  # noqa: E402

OUT = ROOT / "data" / "raw_itch.json"
STALE = 6 * 3600

SORTS = [
    ("featured", "https://itch.io/browse/featured", "Featured"),
    ("top-rated", "https://itch.io/games/top-rated", "Top rated"),
    ("newest", "https://itch.io/games/newest", "Newest"),
]

UA = "Mozilla/5.0 (scout.playhunter.dev)"


def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


_TITLE_HREF_RE = re.compile(
    r'<a[^>]*\bhref="([^"]+)"[^>]*\bclass="title game_link"[^>]*>([^<]+)</a>'
    r'|<a[^>]*\bclass="title game_link"[^>]*\bhref="([^"]+)"[^>]*>([^<]+)</a>'
)
_AUTHOR_RE = re.compile(
    r'class="game_author"[^>]*>\s*<a[^>]*\bhref="(https://[^"]+\.itch\.io[^"]*)"[^>]*>([^<]+)</a>'
)
_DESC_RE = re.compile(r'class="game_text"[^>]*>([^<]*)<')
_TIP_RE = re.compile(r'data-tooltip="([\d.]+) average rating from ([\d,]+)')


def parse_games(html: str):
    """Itch.io game_cell parser. Splits by data-game_id markers then extracts per-cell."""
    games = []
    # Split on cell boundaries — each cell starts with data-game_id
    cells = re.split(r'<div[^>]*data-game_id="(\d+)"', html)
    # cells[0] = preamble, then alternating gid, content, gid, content...
    for i in range(1, len(cells) - 1, 2):
        gid = cells[i]
        content = cells[i + 1][:6000]  # bound the segment

        t = _TITLE_HREF_RE.search(content)
        if not t:
            continue
        url = t.group(1) or t.group(3)
        title = t.group(2) or t.group(4)

        a = _AUTHOR_RE.search(content)
        author = unescape(a.group(2).strip()) if a else ""
        author_url = a.group(1) if a else None

        d = _DESC_RE.search(content)
        desc = unescape(d.group(1).strip())[:240] if d else ""

        rating, count = None, None
        tip = _TIP_RE.search(content)
        if tip:
            rating = float(tip.group(1))
            count = int(tip.group(2).replace(",", ""))

        games.append({
            "game_id": int(gid),
            "title": unescape(title.strip()),
            "url": url,
            "desc": desc,
            "author": author,
            "author_url": author_url,
            "rating": rating,
            "rating_count": count,
        })
        if len(games) >= 30:
            break
    return games


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    out = {"_source": "itch.io", "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sorts": {}}

    for sort_id, url, label in SORTS:
        cache_key = hash(sort_id) & 0x7FFFFFFF
        cached = _cache.read("itch", cache_key, STALE, args.refresh)
        if cached:
            games = cached.get("payload") or []
            print(f"[{sort_id}] cached: {len(games)} games")
        else:
            try:
                html = fetch_page(url)
                games = parse_games(html)
                print(f"[{sort_id}] fetched + parsed: {len(games)} games")
            except Exception as e:
                games = []
                print(f"[{sort_id}] error: {e}")
            _cache.write("itch", cache_key, {"payload": games, "sort_id": sort_id})
            time.sleep(1.0)

        out["sorts"][sort_id] = {"label": label, "url": url, "games": games}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
