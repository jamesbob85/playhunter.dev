"""Discover Scout's candidate universe dynamically.

Replaces the static seed_games.json. Pulls from multiple Steam endpoints to
build a candidate set focused on breakout-eligible lifecycle stages:

  Bucket A (pre-launch) — top-wishlisted unreleased
  Bucket B (just-launched) — released within the last 90 days
  Bucket C (curated seeds) — small hand-curated supplement for known cases

Each candidate gets a lifecycle_class so downstream filters can keep front-page
lists focused on actually-breakout-eligible titles.

Output: data/universe.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import _cache  # noqa: E402

OUT = ROOT / "data" / "universe.json"
UA = "Mozilla/5.0 (scout.playhunter.dev)"

# Steam appdetails cache lives in steam/<appid>.json (used by fetch_steam too)
APPDETAILS_STALE = 24 * 3600
WISHLIST_LIST_STALE = 12 * 3600
NEW_RELEASES_STALE = 12 * 3600

NOW = time.time()
RECENT_LAUNCH_DAYS = 90    # how recently a launched game can be to count
COMING_SOON_HORIZON_DAYS = 540  # how far out we look for pre-launch (18 months)


def fetch_search_page(query_string: str, count: int = 100) -> str:
    """Fetch a Steam search results HTML payload via the infinite-scroll endpoint."""
    url = f"https://store.steampowered.com/search/?{query_string}&infinite=1&count={count}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    return data.get("results_html", "")


_APPID_NAME_RE = re.compile(
    r'data-ds-appid="(\d+)"[^>]*>.*?<span class="title">([^<]+)</span>',
    re.DOTALL,
)


def parse_appids(html: str):
    seen = set()
    out = []
    for appid, name in _APPID_NAME_RE.findall(html):
        # Skip bundles / packages — only solo appids
        if "," in appid:
            continue
        if appid in seen:
            continue
        seen.add(appid)
        out.append((int(appid), unescape(name).strip()))
    return out


def fetch_appdetails_cached(appid: int) -> dict:
    """Re-uses the steam cache from fetch_steam.py so we don't double-fetch."""
    cached = _cache.read("steam", appid, APPDETAILS_STALE, False)
    if cached:
        return cached.get("payload") or {}
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        rec = data.get(str(appid), {})
        if not rec.get("success"):
            payload = None
        else:
            d = rec["data"]
            payload = {
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
        payload = {"_error": str(e)}
    _cache.write("steam", appid, {"payload": payload})
    time.sleep(0.4)  # rate-limit politeness
    return payload or {}


# Steam release_date strings vary wildly. Try to extract a year+month at least.
def parse_release_date(rd_str: str):
    if not rd_str:
        return None
    rd_str = rd_str.strip()
    # ISO-like: "Mar 14, 2026", "14 Mar, 2026", "2025-03-14"
    for fmt in ("%b %d, %Y", "%d %b, %Y", "%Y-%m-%d", "%B %d, %Y", "%b %Y", "%B %Y", "%Y"):
        try:
            return time.mktime(time.strptime(rd_str, fmt))
        except (ValueError, OverflowError):
            pass
    return None


def classify(appdetails: dict, coming_soon_pool: bool):
    """Determine lifecycle classification for a candidate.

    Returns one of:
      - 'pre-launch'         : coming_soon=true, hasn't shipped
      - 'just-launched'      : shipped within RECENT_LAUNCH_DAYS
      - 'launched'           : shipped longer ago than recent window
      - 'unknown'            : insufficient data
    """
    if not appdetails or appdetails.get("_error"):
        return "unknown"
    if appdetails.get("coming_soon"):
        return "pre-launch"
    if "Early Access" in (appdetails.get("genres") or []):
        # EA gets bucketed by how recent the EA release was
        ts = parse_release_date(appdetails.get("release_date"))
        if ts and (NOW - ts) <= RECENT_LAUNCH_DAYS * 86400:
            return "just-launched"
        return "launched"
    rd_str = appdetails.get("release_date")
    ts = parse_release_date(rd_str)
    if ts is None:
        return "unknown"
    if ts > NOW:
        return "pre-launch"
    if (NOW - ts) <= RECENT_LAUNCH_DAYS * 86400:
        return "just-launched"
    return "launched"


def hand_curated_seeds():
    """A small supplement of known interesting cases we want tracked regardless."""
    return [
        # Recent/upcoming we want guaranteed in the universe
        (3164500, "Schedule I"),
        (3241660, "R.E.P.O."),
        (1363080, "Manor Lords"),
        (1145350, "Hades II"),
        (2622380, "ELDEN RING NIGHTREIGN"),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-lists", action="store_true", help="Force refresh of source-list caches (not per-appid)")
    args = ap.parse_args()

    # ---- Source 1: top wishlisted ----
    list_cache_key = hash("steam-topwishlists-100") & 0x7FFFFFFF
    cached = _cache.read("universe_lists", list_cache_key, WISHLIST_LIST_STALE, args.refresh_lists)
    if cached:
        wishlist_html = cached.get("payload") or ""
        print(f"[top-wishlisted] cached")
    else:
        wishlist_html = fetch_search_page("filter=topwishlists&category1=998,996,997", 100)  # category1 998 = all games incl coming soon
        _cache.write("universe_lists", list_cache_key, {"payload": wishlist_html})
        print(f"[top-wishlisted] fetched {len(wishlist_html)} bytes")
    wishlist_candidates = parse_appids(wishlist_html)

    # ---- Source 2: new releases by top-sellers ----
    nr_key = hash("steam-new-releases-100") & 0x7FFFFFFF
    cached_nr = _cache.read("universe_lists", nr_key, NEW_RELEASES_STALE, args.refresh_lists)
    if cached_nr:
        nr_html = cached_nr.get("payload") or ""
        print(f"[new-releases] cached")
    else:
        # Steam's new-releases page, sorted by recently released top sellers
        nr_html = fetch_search_page("filter=topsellers&os=win", 100)
        _cache.write("universe_lists", nr_key, {"payload": nr_html})
        print(f"[new-releases] fetched {len(nr_html)} bytes")
    nr_candidates = parse_appids(nr_html)

    # ---- Source 3: upcoming (ordered by release date) ----
    up_key = hash("steam-upcoming-100") & 0x7FFFFFFF
    cached_up = _cache.read("universe_lists", up_key, WISHLIST_LIST_STALE, args.refresh_lists)
    if cached_up:
        up_html = cached_up.get("payload") or ""
        print(f"[upcoming] cached")
    else:
        up_html = fetch_search_page("filter=comingsoon&os=win&supportedlang=english&hidef2p=1", 100)
        _cache.write("universe_lists", up_key, {"payload": up_html})
        print(f"[upcoming] fetched {len(up_html)} bytes")
    up_candidates = parse_appids(up_html)

    # ---- Source 4: hand-curated ----
    curated = hand_curated_seeds()

    print(f"\nRaw candidates: wishlists={len(wishlist_candidates)} newreleases={len(nr_candidates)} upcoming={len(up_candidates)} curated={len(curated)}")

    # ---- Dedupe + classify ----
    seen = set()
    universe = []
    sources_by_appid = {}

    for src_label, src_list in [
        ("curated", curated),
        ("wishlists", wishlist_candidates),
        ("upcoming", up_candidates),
        ("newreleases", nr_candidates),
    ]:
        for appid, name in src_list:
            if appid in seen:
                sources_by_appid[appid].append(src_label)
                continue
            seen.add(appid)
            sources_by_appid[appid] = [src_label]
            universe.append({"appid": appid, "name_from_list": name})

    # Classify each by fetching appdetails (cached)
    classified = []
    counts = {"pre-launch": 0, "just-launched": 0, "launched": 0, "unknown": 0, "non-game": 0}
    for i, c in enumerate(universe):
        details = fetch_appdetails_cached(c["appid"])
        # Skip soundtracks / DLC / videos
        if details.get("type") not in (None, "game") and details.get("type") != "game":
            counts["non-game"] += 1
            continue
        classification = classify(details, coming_soon_pool=c["appid"] in {a for a, _ in up_candidates})
        counts[classification] = counts.get(classification, 0) + 1
        classified.append({
            "appid": c["appid"],
            "name": details.get("name") or c["name_from_list"],
            "lifecycle_class": classification,
            "release_date": details.get("release_date"),
            "coming_soon": details.get("coming_soon", False),
            "is_free": details.get("is_free", False),
            "price": details.get("price"),
            "developers": details.get("developers") or [],
            "publishers": details.get("publishers") or [],
            "header_image": details.get("header_image"),
            "short_description": details.get("short_description"),
            "genres": details.get("genres") or [],
            "categories": details.get("categories") or [],
            "sources": sources_by_appid.get(c["appid"]),
        })
        if (i + 1) % 25 == 0:
            print(f"  classified {i+1}/{len(universe)}...")

    print(f"\nClassification counts: {counts}")

    # ---- Keep only breakout-eligible lifecycle classes ----
    eligible = [c for c in classified if c["lifecycle_class"] in ("pre-launch", "just-launched")]
    other = [c for c in classified if c["lifecycle_class"] in ("launched",)]

    print(f"\nFINAL UNIVERSE: {len(eligible)} eligible (pre-launch + just-launched), {len(other)} other launched (kept for Universe view)")

    output = {
        "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": counts,
        "eligible": eligible,
        "other_launched": other,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
