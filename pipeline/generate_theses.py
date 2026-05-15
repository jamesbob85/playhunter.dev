"""Generate Scout-voiced theses for each scored game using the Anthropic SDK."""
from __future__ import annotations
"""

Requires ANTHROPIC_API_KEY in env. If not set, writes a stub thesis for each
game so the rest of the pipeline still produces a working scout-data.json.

Output: data/theses.json keyed by appid.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from persona import SCOUT_SYSTEM_PROMPT, CARD_TASK_PROMPT, lint  # noqa: E402

SCORED = ROOT / "data" / "scored.json"
OUT = ROOT / "data" / "theses.json"

MODEL = "claude-opus-4-7"


from _comparables import comparables_by_id


def _load_comparables_index():
    return comparables_by_id()


def build_user_message(game: dict) -> str:
    signals_lines = []
    for s in game.get("signals") or []:
        signals_lines.append(f"  - {s['name']}: {s['value_label']} (magnitude {s['magnitude']:.2f}, family={s['family']}, real={s.get('real', False)})")
    signals_block = "\n".join(signals_lines)

    rs = game.get("real_signals") or {}
    real_block_lines = []
    for key, label in [
        ("revenue", "Lifetime revenue"),
        ("owners", "Estimated owners"),
        ("followers", "Steam followers"),
        ("wishlists", "Wishlists"),
        ("reviews_total", "Reviews total"),
        ("review_ratio", "Review % positive"),
        ("twitch_viewers", "Twitch live viewers"),
        ("twitch_streams", "Twitch streams"),
        ("igdb_hypes", "IGDB hypes"),
        ("reddit_subscribers", "Reddit subscribers"),
    ]:
        v = rs.get(key)
        if v is None or v == 0:
            continue
        if key == "review_ratio":
            real_block_lines.append(f"  - {label}: {v * 100:.0f}%")
        elif key == "revenue":
            real_block_lines.append(f"  - {label}: ${v:,}")
        else:
            real_block_lines.append(f"  - {label}: {v:,}")
    real_block = "\n".join(real_block_lines) if real_block_lines else "  (none available)"

    # Comparables block — Scout's grounded reference
    comp_index = _load_comparables_index()
    nearest = game.get("nearest_comparables") or []
    comp_lines = []
    for nc in nearest[:3]:
        full = comp_index.get(nc.get("id"), {})
        peak = full.get("peak_ccu")
        peak_str = f"{peak/1000:.0f}K peak CCU" if peak else "no CCU recorded"
        lesson = full.get("key_lesson") or ""
        sig = " · ".join((full.get("signal_signature") or [])[:2])
        comp_lines.append(
            f"  • {full.get('name')} ({full.get('year')}, {full.get('outcome')}, {peak_str}) — "
            f"{full.get('stage_arc', '')}\n    lesson: {lesson}\n    signal sig: {sig}"
        )
    comp_block = "\n".join(comp_lines) if comp_lines else "  (none — game has no clear cluster match in the library)"

    return f"""Game: {game['name']}
Studio: {game['studio']}
Stage: {game['stage_label']}
Price: {game.get('price') or 'TBD'}
Release date: {game.get('release_date') or 'TBD'}
Genres: {', '.join(game.get('genres') or []) or 'unspecified'}
Meta clusters this fits: {', '.join(game.get('meta_clusters') or []) or 'none tagged'}

Computed readings:
  Breakout Score: {game['score']} (delta {game['score_delta']:+d})
  Confidence: {game['confidence']} ({game['confidence_families']} of 5 signal families firing)
  Scale band: {game['scale']} (projected peak CCU {game['scale_band'][0]:,}–{game['scale_band'][1]:,})
  Meta modifier: {game['meta_modifier']}

This week's signal readings (● = real, ○ = synth):
{signals_block}

Real numbers (live from Steam / Gamalytic / Twitch / IGDB / Reddit):
{real_block}

Nearest comparables in Scout's library (use these as factual ground truth — cite them by name with the magnitude gap stated):
{comp_block}

Now produce the JSON thesis per the task spec. Lead with the business read.
You must name one of the comparables above in the "comparable" field and state the magnitude gap by number.
"""


def call_anthropic(client, user_msg: str) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SCOUT_SYSTEM_PROMPT + "\n\n" + CARD_TASK_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)


def lint_and_flag(thesis: dict) -> list[str]:
    flat = " ".join([
        " ".join(thesis.get("the_read") or []),
        thesis.get("against_consensus") or "",
        thesis.get("comparable") or "",
        thesis.get("what_would_change_my_mind") or "",
        " ".join(thesis.get("risks") or []),
        thesis.get("pull_quote") or "",
    ])
    return lint(flat)


def stub_thesis(game: dict) -> dict:
    pull = f"{game['name']} sits at {game['score']} with {game['confidence'].lower()} conviction."
    return {
        "the_read": [
            f"{game['name']} reads {game['score']}/100 with {game['confidence_families']} of 5 signal families firing. The stage cohort puts that in the top decile for {game['stage_label']}.",
            f"Signal mix leans on {max(game['signals'], key=lambda s: s['magnitude'])['name'].lower()} — currently the strongest contributor.",
            "Stub thesis: no Anthropic API key was present at build time. Re-run with ANTHROPIC_API_KEY set to generate the full Scout-voiced thesis.",
        ],
        "against_consensus": "",
        "comparable": f"No comparable selected without LLM. Manual review needed against the closest stage-cohort breakout in the comparables library.",
        "what_would_change_my_mind": f"A two-week flat read on the leading signal family would compress {game['name']} back into the Watch tier.",
        "risks": ["Synthesized deltas — re-run after 7 days of real snapshots.", "Thesis is stubbed without Anthropic API key."],
        "pull_quote": pull,
        "_stub": True,
    }


def main():
    games = json.loads(SCORED.read_text())
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        if OUT.exists():
            print(f"No ANTHROPIC_API_KEY — keeping existing {OUT.name} (won't overwrite with stubs).")
        else:
            print("No ANTHROPIC_API_KEY and no existing theses — writing stubs as bootstrap.")
            out = {str(g["id"]): stub_thesis(g) for g in games}
            OUT.write_text(json.dumps(out, indent=2))
        return

    out = {}

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    for i, g in enumerate(games):
        print(f"[{i+1}/{len(games)}] {g['name']} ({g['stage_label']})", flush=True)
        try:
            thesis = call_anthropic(client, build_user_message(g))
            lint_hits = lint_and_flag(thesis)
            if lint_hits:
                print(f"  LINT FAIL: {lint_hits} — regenerating once")
                regen_user = build_user_message(g) + f"\n\nYour previous attempt used banned phrases: {lint_hits}. Rewrite without them."
                thesis = call_anthropic(client, regen_user)
                lint_hits = lint_and_flag(thesis)
                if lint_hits:
                    print(f"  LINT FAIL after retry: {lint_hits} — keeping anyway, flagging")
                    thesis["_lint_hits"] = lint_hits
            out[str(g["id"])] = thesis
        except Exception as e:
            print(f"  ERROR: {e} — falling back to stub")
            out[str(g["id"])] = stub_thesis(g)

    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
