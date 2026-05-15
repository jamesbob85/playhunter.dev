"""Orchestrator: merge scored games + theses into scout-data.json.

Also produces:
  - top_movers
  - high_conviction list (≥2 entries)
  - wild_bets list (≥2 entries)
  - meta heat (heating + cooling clusters)
  - "The Read" editorial — LLM-generated if API key present, else templated

Run order (intended):
  python pipeline/fetch_steam.py
  python pipeline/fetch_twitch.py
  python pipeline/score.py
  python pipeline/generate_theses.py
  python pipeline/build.py     <-- this file
"""
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from persona import SCOUT_SYSTEM_PROMPT  # noqa: E402
from _comparables import load_comparables, nearest_comparables  # noqa: E402

SCORED = ROOT / "data" / "scored.json"
THESES = ROOT / "data" / "theses.json"
RAW_ROBLOX = ROOT / "data" / "raw_roblox.json"
RAW_ITCH = ROOT / "data" / "raw_itch.json"
COMPARABLES = ROOT / "data" / "comparables.json"
OUT = ROOT / "data" / "scout-data.json"

THE_READ_PROMPT = """Write "The Read" — Scout's top-of-page editorial for today.

Length: 50-90 words, one paragraph.
Form: present-tense. Open with a market frame (the thing happening in the
industry RIGHT NOW). Name one specific game as the test case. End with a
hook to the rest of the brief.

You'll be given today's top movers and which meta clusters are heating up.

Follow Scout's hard rules: no banned vocab, business-first framing, one
pull-quotable line. Output plain text only — no quotes, no attribution."""


def build_upstream():
    """Compose the Upstream section from Roblox + itch.io fetches."""
    out = {
        "roblox": [],
        "itch": [],
        "note": "Treat upstream signals with a grain of salt. Listed as taste vectors, not direct breakout candidates.",
    }

    if RAW_ROBLOX.exists():
        roblox = json.loads(RAW_ROBLOX.read_text())
        trending = (roblox.get("sorts") or {}).get("top-trending", {}).get("games") or []
        seen = set()
        for g in trending:
            if g.get("is_sponsored") or g.get("name") in seen:
                continue
            seen.add(g.get("name"))
            ratio = g.get("approval_ratio") or 0
            pc = g.get("player_count") or 0
            out["roblox"].append({
                "name": g.get("name"),
                "source": "Roblox",
                "signal_label": f"{pc:,} concurrent · {round(ratio * 100)}% approval",
                "player_count": pc,
                "approval_ratio": ratio,
                "min_age": g.get("min_age"),
                "url": g.get("url"),
                "why": (
                    "Mass concurrent attention on a kid-skewing taste vector."
                    if pc >= 30000
                    else "Trending pattern in the Roblox cohort — watch for genre spillover."
                ),
            })
            if len(out["roblox"]) >= 6:
                break

    if RAW_ITCH.exists():
        itch = json.loads(RAW_ITCH.read_text())
        sorts = itch.get("sorts") or {}
        seen = set()
        for sort_id in ("featured", "top-rated", "newest"):
            for g in (sorts.get(sort_id) or {}).get("games") or []:
                title = (g.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                rating = g.get("rating")
                count = g.get("rating_count")
                signal = []
                if rating and count:
                    signal.append(f"★{rating:.2f} ({count:,})")
                signal.append(sort_id)
                out["itch"].append({
                    "name": title,
                    "source": "itch.io",
                    "author": g.get("author") or "",
                    "signal_label": " · ".join(signal),
                    "rating": rating,
                    "rating_count": count,
                    "sort": sort_id,
                    "url": g.get("url"),
                    "desc": (g.get("desc") or "")[:160],
                    "why": (
                        "Strong indie traction pre-Steam. Itch breakouts have historically crossed to Steam within 6-18 months."
                        if rating and count and count >= 1000
                        else "New indie release — small signal but worth tracking."
                    ),
                })
                if len(out["itch"]) >= 8:
                    break
            if len(out["itch"]) >= 8:
                break

    return out


def cluster_velocities_with_titles(games):
    """For each meta cluster, aggregate mean score-delta and capture top contributing games."""
    bucket = defaultdict(list)
    for g in games:
        for c in g.get("meta_clusters") or []:
            bucket[c].append(g)
    out = {}
    for cluster, entries in bucket.items():
        if not entries:
            continue
        avg_delta = sum(g["score_delta"] for g in entries) / len(entries)
        # Top contributors: highest score_delta within cluster
        top = sorted(entries, key=lambda g: g["score_delta"], reverse=True)
        out[cluster] = {
            "avg_delta": avg_delta,
            "count": len(entries),
            "titles": [
                {"id": g["id"], "name": g["name"], "delta": g["score_delta"], "score": g["score"], "stage": g["stage_label"]}
                for g in top[:4]
            ],
            "bottom_titles": [
                {"id": g["id"], "name": g["name"], "delta": g["score_delta"], "score": g["score"], "stage": g["stage_label"]}
                for g in top[::-1][:4]
            ],
        }
    return out


def build_meta(games):
    velocities = cluster_velocities_with_titles(games)
    sorted_clusters = sorted(velocities.items(), key=lambda kv: kv[1]["avg_delta"], reverse=True)
    heating = []
    for c, v in sorted_clusters:
        if v["avg_delta"] > 0:
            heating.append({
                "name": c,
                "delta_pct": round(v["avg_delta"] * 1.5, 1),
                "count": v["count"],
                "titles": v["titles"][:3],
            })
    heating = heating[:4]
    cooling = []
    for c, v in sorted_clusters[::-1]:
        if v["avg_delta"] < 0:
            cooling.append({
                "name": c,
                "delta_pct": round(v["avg_delta"] * 1.5, 1),
                "count": v["count"],
                "titles": v["bottom_titles"][:3],
            })
    cooling = cooling[:4]
    return {
        "heating": heating,
        "cooling": cooling,
        "weekly_piece_title": pick_weekly_piece_title(heating),
        "weekly_piece_id": "weekly-2026-W20",
    }


def pick_weekly_piece_title(heating: list[dict]) -> str:
    if heating:
        c = heating[0]["name"]
        return f"Why {c.lower()} keeps pulling rank, and what the next breakout in the cluster probably looks like."
    return "What changed in player taste this week."


def make_pull(game: dict, theses: dict) -> str:
    t = theses.get(str(game["id"]), {})
    return t.get("pull_quote") or game.get("short_description") or ""


def generate_the_read(games, heating, cadence="daily"):
    """Return the editorial paragraph for the given cadence.

    Looks for data/the_read_{cadence}.txt as a hand-written override first.
    Falls back to data/the_read.txt for backward compat, then to LLM/template.
    """
    for candidate in (
        ROOT / "data" / f"the_read_{cadence}.txt",
        ROOT / "data" / "the_read.txt",
    ):
        if candidate.exists():
            text = candidate.read_text().strip()
            if text:
                return text

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        if not heating:
            return f"{games[0]['name']} leads the board today at {games[0]['score']} with a {games[0]['score_delta']:+d} delta. Synthesized signal mix — re-run with ANTHROPIC_API_KEY for Scout's editorial read."
        top = games[0]
        cluster = heating[0]["name"].lower()
        return f"{cluster.capitalize()} keeps pulling rank — the cluster ran +{heating[0]['delta_pct']}% velocity this week. {top['name']} is today's test case at {top['score']} ({top['score_delta']:+d}), a {top['confidence'].lower()}-conviction read that the cluster's shelf life is longer than the consensus take."

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    top5 = [
        {"name": g["name"], "score": g["score"], "delta": g["score_delta"], "stage": g["stage_label"], "scale": g["scale"]}
        for g in games[:6]
    ]
    ctx = json.dumps({"movers_top": top5, "heating": heating}, indent=2)
    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=400,
        system=SCOUT_SYSTEM_PROMPT + "\n\n" + THE_READ_PROMPT,
        messages=[{"role": "user", "content": ctx}],
    )
    return resp.content[0].text.strip().strip('"').strip("'")


def main():
    games = json.loads(SCORED.read_text())
    theses = json.loads(THESES.read_text()) if THESES.exists() else {}
    comp_lib = load_comparables()

    # Attach nearest comparables BEFORE generate_theses runs (it reads from this)
    # and thesis after (or fall back to whatever theses.json holds).
    for g in games:
        g["nearest_comparables"] = nearest_comparables(g, comp_lib)
        g["thesis"] = theses.get(str(g["id"]), {})

    movers = sorted(games, key=lambda g: abs(g["score_delta"]), reverse=True)[:6]
    movers_compact = [
        {
            "id": g["id"], "name": g["name"], "score": g["score"], "delta": g["score_delta"],
            "scale": g["scale"], "stage": g["stage_label"], "confidence": g["confidence"],
            "header_image": g.get("header_image"),
        }
        for g in movers
    ]

    # Conviction = high-signal active products. Excludes settled phenoms.
    high_conviction = [
        g for g in games
        if not g.get("is_mature_phenom")
        and g["confidence"] in ("High", "Medium")
        and g["scale"] in ("Phenom", "Hit", "Cult")
        and g["score"] >= 55
    ]
    high_conviction.sort(key=lambda g: (g["confidence"] == "High", g["score"], g["score_delta"]), reverse=True)

    # Wild bets = high-delta picks not in conviction. Lower base rate but higher payoff.
    conviction_ids = {g["id"] for g in high_conviction[:2]}
    wild_bets = [
        g for g in games
        if g["id"] not in conviction_ids
        and not g.get("is_mature_phenom")
        and g["score_delta"] >= 12
        and g["score"] >= 30
    ]
    wild_bets.sort(key=lambda g: g["score_delta"], reverse=True)

    def slim_for_listing(g):
        return {
            "id": g["id"], "name": g["name"], "score": g["score"], "delta": g["score_delta"],
            "scale": g["scale"], "stage": g["stage_label"], "confidence": g["confidence"],
            "meta_modifier": g["meta_modifier"], "meta_clusters": g["meta_clusters"],
            "pull_quote": make_pull(g, theses),
            "header_image": g.get("header_image"),
        }

    meta = build_meta(games)
    the_read = {
        "daily": generate_the_read(games, meta["heating"], "daily"),
        "weekly": generate_the_read(games, meta["heating"], "weekly"),
        "monthly": generate_the_read(games, meta["heating"], "monthly"),
    }

    games_by_id = {str(g["id"]): g for g in games}

    # ---- Persist daily snapshot for future W/W and M/M deltas ----
    snap_dir = ROOT / "data" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    snapshot = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "games": {
            str(g["id"]): {
                "name": g["name"],
                "score": g["score"],
                "stage": g["stage"],
                "followers": g["real_signals"].get("followers"),
                "wishlists": g["real_signals"].get("wishlists"),
                "owners": g["real_signals"].get("owners"),
                "revenue": g["real_signals"].get("revenue"),
                "reviews_total": g["real_signals"].get("reviews_total"),
                "review_ratio": g["real_signals"].get("review_ratio"),
                "twitch_viewers": g["real_signals"].get("twitch_viewers"),
                "twitch_streams": g["real_signals"].get("twitch_streams"),
                "igdb_hypes": g["real_signals"].get("igdb_hypes"),
                "reddit_subscribers": g["real_signals"].get("reddit_subscribers"),
            } for g in games
        },
    }
    (snap_dir / f"{today}.json").write_text(json.dumps(snapshot, indent=2))

    # Trim snapshots older than 60 days
    cutoff = time.time() - 60 * 86400
    for p in snap_dir.glob("*.json"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except Exception:
            pass

    upstream = build_upstream()

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cadence": "daily",
        "upstream": upstream,
        "the_read": the_read["daily"],  # backward compat
        "the_read_by_cadence": the_read,
        "the_read_author": "Scout",
        "movers": movers_compact,
        "high_conviction": [slim_for_listing(g) for g in high_conviction[:2]],
        "wild_bets": [slim_for_listing(g) for g in wild_bets[:2]],
        "meta": meta,
        "games": games_by_id,
        "universe_count": len(games),
    }
    OUT.write_text(json.dumps(output, indent=2))
    print(f"wrote {OUT} ({len(games)} games, {len(movers_compact)} movers)")


if __name__ == "__main__":
    main()
