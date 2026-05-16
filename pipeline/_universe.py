"""Shared helper: load the discovered universe.

Each fetcher uses this instead of the deprecated seed_games.json so the entire
pipeline operates on the dynamically-discovered candidate set.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNIVERSE = ROOT / "data" / "universe.json"


def load_candidates(include_other: bool = True):
    """Return list of candidates. Each candidate has appid, name, lifecycle_class
    plus everything from fetch_universe's classifier.

    include_other=True keeps mature-launched games for Universe browsing.
    """
    if not UNIVERSE.exists():
        return []
    u = json.loads(UNIVERSE.read_text())
    out = list(u.get("eligible") or [])
    if include_other:
        out = out + list(u.get("other_launched") or [])
    return out


def load_eligible_only():
    """Just pre-launch + just-launched. Used for fetchers that only care about
    breakout-eligible candidates."""
    if not UNIVERSE.exists():
        return []
    return list((json.loads(UNIVERSE.read_text()).get("eligible") or []))
