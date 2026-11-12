#!/usr/bin/env python3
"""Austen's own paragraph plan for each blind-test passage.

For every paragraph of the renamed excerpt: its dominant kind (the skeleton's
modes), the speaker for DIALOGUE (a cast key from briefs.json), its length in
words, and one plain line of what happens, in our words, never hers. The small
labelling model drafts it; the overlap check below flags any line that borrows
Austen's wording, and the plan is checked by hand before it is used.

    venv/bin/python experiments/blind_test/austen_plans.py --scenes emma_III4,pers_18,pp_32 --max-usd 0.05
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments" / "dsl_validation"))
import judge_v2 as J  # noqa: E402

WORK = REPO / "work" / "blind"
MODES = {
    "SETTING": "description of place, weather, objects, atmosphere",
    "CHARACTER_DESC": "description of a person's looks, dress or manner",
    "LORE": "background, history or explanation of how things stand",
    "DIALOGUE": "dominated by quoted speech (one speaker's turn)",
    "ACTION": "events happening now: movement, gesture, physical activity, or narrated events",
    "INTERIORITY": "a character's thoughts, feelings, reasoning, judgments",
    "TRANSITION": "a short bridge in time or place",
}

PROMPT = """Below is a passage from a novel, split into numbered paragraphs, and the cast.

Cast (key: name, role):
{cast}

Paragraphs:
{paras}

For EVERY paragraph, in order, give:
- "kind": its single dominant mode, one of:
{modes}
- "speaker": for DIALOGUE only, the cast key of the one person speaking (else "").
- "what": ONE plain sentence saying what happens in that paragraph, naming people by
  their names as given in the paragraphs. Use your own plain modern words. Do NOT
  quote, echo or closely paraphrase the passage's wording, images or turns of phrase;
  say only what happens or what is said in substance.

Reply with JSON only: {{"paragraphs": [{{"kind": "...", "speaker": "...", "what": "..."}}, ...]}}
with exactly {n} entries."""


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def shared_runs(line, source_words, n=4):
    w = re.findall(r"[a-z']+", line.lower().replace("’", "'"))
    grams = {tuple(source_words[i:i + n]) for i in range(len(source_words) - n + 1)}
    return [" ".join(w[i:i + n]) for i in range(len(w) - n + 1) if tuple(w[i:i + n]) in grams]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--max-usd", type=float, required=True)
    args = ap.parse_args()
    briefs = json.loads((WORK / "briefs.json").read_text())
    names = json.loads((WORK / "names.json").read_text())
    budget = J.Budget(args.max_usd)
    out_dir = WORK / "plans"
    out_dir.mkdir(exist_ok=True)
    for sid in args.scenes.split(","):
        brief = briefs["scenes"][sid]
        people = names[brief["novel"]]["people"]
        text = (WORK / "austen" / f"{sid}.md").read_text()
        paras = paragraphs(text)
        cast = "\n".join(f"- {k}: {people[k]['first']} {people[k]['last']}, {role}"
                         for k, role in brief["cast"].items())
        prompt = PROMPT.format(
            cast=cast, n=len(paras),
            modes="\n".join(f"    {k}: {v}" for k, v in MODES.items()),
            paras="\n\n".join(f"({i + 1}) {p}" for i, p in enumerate(paras)))
        reply = J.call(J.LABEL_MODEL, prompt, budget, max_tokens=6000)
        data = J.parse_json(reply) if hasattr(J, "parse_json") else json.loads(reply)
        items = (data or {}).get("paragraphs") or []
        if len(items) != len(paras):
            print(f"[plans] {sid}: {len(items)} items for {len(paras)} paragraphs; not saved")
            continue
        src = re.findall(r"[a-z']+", text.lower().replace("’", "'"))
        for it, p in zip(items, paras):
            it["words"] = len(p.split())
            it["kind"] = str(it.get("kind", "")).upper()
            it["echo"] = shared_runs(it.get("what", ""), src)
        (out_dir / f"{sid}.json").write_text(json.dumps(items, indent=1))
        bad = [i + 1 for i, it in enumerate(items) if it["kind"] not in MODES]
        echoes = sum(1 for it in items if it["echo"])
        print(f"[plans] {sid}: {len(items)} paragraphs, unknown kinds at {bad or 'none'}, "
              f"{echoes} lines sharing 4-word runs with Austen (${budget.usd:.4f} so far)")


if __name__ == "__main__":
    main()
