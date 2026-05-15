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


def build_user_message(game: dict) -> str:
    signals_lines = []
    for s in game["signals"]:
        signals_lines.append(f"  - {s['name']}: {s['value_label']} (magnitude {s['magnitude']:.2f}, family={s['family']})")
    signals_block = "\n".join(signals_lines)

    return f"""Game: {game['name']}
Studio: {game['studio']}
Stage: {game['stage_label']}
Price: {game['price']}
Release date: {game.get('release_date') or 'TBD'}
Genres: {', '.join(game.get('genres') or []) or 'unspecified'}
Meta clusters this fits: {', '.join(game.get('meta_clusters') or []) or 'none tagged'}

Computed readings:
  Breakout Score: {game['score']} (delta {game['score_delta']:+d})
  Confidence: {game['confidence']} ({game['confidence_families']} of 5 signal families firing)
  Scale band: {game['scale']} (projected peak CCU {game['scale_band'][0]:,}–{game['scale_band'][1]:,})
  Meta modifier: {game['meta_modifier']}

This week's signal readings:
{signals_block}

Real Steam data:
  Current CCU snapshot: {game['real_signals']['ccu']:,}
  Players (last 2 weeks): {game['real_signals']['players_2weeks']:,}
  Reviews: {game['real_signals']['reviews_total']:,} total, {game['real_signals']['review_ratio']*100:.0f}% positive

Now produce the JSON thesis per the task spec. Lead with the business read.
If a stat (e.g. "70% of the time in our comparables") would help your point,
state it — but only if it's a reasonable industry rule-of-thumb you can defend.
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

    out = {}
    if not api_key:
        print("No ANTHROPIC_API_KEY — writing stub theses.")
        for g in games:
            out[str(g["id"])] = stub_thesis(g)
        OUT.write_text(json.dumps(out, indent=2))
        print(f"wrote {OUT} (all stubbed)")
        return

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
