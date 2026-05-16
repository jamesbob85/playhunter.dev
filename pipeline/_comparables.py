"""Shared helper: load comparables library + compute nearest neighbours.

Used by both build.py (adds nearest_comparables to scout-data.json) and
generate_theses.py (uses them as ground-truth references in the LLM prompt).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPARABLES_PATH = ROOT / "data" / "comparables.json"


def load_comparables():
    if not COMPARABLES_PATH.exists():
        return []
    return (json.loads(COMPARABLES_PATH.read_text()).get("comparables") or [])


def comparables_by_id():
    return {c["id"]: c for c in load_comparables()}


def nearest_comparables(game, comp_lib, k=3):
    """Score each comparable by similarity to the game. Returns top k.

    Similarity = weighted sum of:
      - cluster overlap (3 pts per shared primary/secondary cluster, +2 if primary aligned)
      - stage match (2-3 pts depending on arc terminus)
      - team-size bucket match (2 pts)
    Self-matches excluded by name.
    """
    if not comp_lib:
        return []

    game_clusters = set(game.get("meta_clusters") or [])
    stage = game.get("stage")
    studio = (game.get("studio") or "").lower()
    if any(x in studio for x in ("zeekerss", "tvgs", "concernedape", "team cherry")):
        team_bucket = "small"
    elif any(x in studio for x in ("larian", "fromsoftware", "bethesda", "cdpr", "rockstar", "valve")):
        team_bucket = "large"
    else:
        team_bucket = "medium"

    game_name_norm = (game.get("name") or "").strip().lower()
    # For high-confidence breakout candidates, don't surface flop comparables —
    # flops are reference-library entries for risk-tagging, not "your game looks like this."
    high_conviction = game.get("confidence") in ("High", "Medium") and game.get("score", 0) >= 55
    scored_list = []
    for c in comp_lib:
        if (c.get("name") or "").strip().lower() == game_name_norm:
            continue
        if high_conviction and c.get("outcome") == "flop":
            continue
        score = 0
        comp_clusters = {c.get("primary_cluster")} | set(c.get("secondary_clusters") or [])
        shared = game_clusters & comp_clusters
        score += 3 * len(shared)
        if c.get("primary_cluster") in game_clusters:
            score += 2

        arc = (c.get("stage_arc") or "").lower()
        if stage == "Launched" and any(t in arc for t in ("durable", "phenom", "hit", "settled", "recover", "flop", "long-tail")):
            score += 2
        elif stage == "EA" and "ea" in arc:
            score += 3
        elif stage == "Announced" and ("wishlist" in arc or "pre-launch" in arc or "announce" in arc):
            score += 3

        ct = c.get("team_size") or 0
        comp_bucket = "small" if ct <= 5 else "medium" if ct <= 100 else "large"
        if comp_bucket == team_bucket:
            score += 2

        if score <= 1:
            continue
        scored_list.append((score, c))

    scored_list.sort(key=lambda kv: kv[0], reverse=True)
    out = []
    for score, c in scored_list[:k]:
        out.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "year": c.get("year"),
            "outcome": c.get("outcome"),
            "peak_ccu": c.get("peak_ccu"),
            "primary_cluster": c.get("primary_cluster"),
            "stage_arc": c.get("stage_arc"),
            "key_lesson": c.get("key_lesson"),
            "similarity": score,
        })
    return out
