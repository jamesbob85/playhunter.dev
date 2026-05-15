"""Per-game cache helper.

Each source caches into  data/cache/<source>/<appid>.json  with a top-level
"fetched_at" Unix timestamp. Records older than `max_age_seconds` are treated
as stale and re-fetched. Pass refresh=True (e.g. via CLI flag) to force.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

CACHE_ROOT = Path(__file__).resolve().parent.parent / "data" / "cache"


def cache_path(source: str, appid: int) -> Path:
    p = CACHE_ROOT / source / f"{appid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read(source: str, appid: int, max_age_seconds: int, refresh: bool = False):
    if refresh:
        return None
    p = cache_path(source, appid)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except Exception:
        return None
    ts = data.get("fetched_at")
    if ts is None:
        return None
    if (time.time() - ts) > max_age_seconds:
        return None
    return data


def write(source: str, appid: int, payload: dict) -> None:
    p = cache_path(source, appid)
    payload = {"fetched_at": time.time(), **payload}
    p.write_text(json.dumps(payload, indent=2))


def aggregate(source: str) -> dict:
    """Aggregate all per-game cache entries into a single dict keyed by appid."""
    folder = CACHE_ROOT / source
    out = {}
    if not folder.exists():
        return out
    for p in sorted(folder.glob("*.json")):
        try:
            out[p.stem] = json.loads(p.read_text())
        except Exception:
            continue
    return out
