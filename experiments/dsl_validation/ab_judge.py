#!/usr/bin/env python3
"""Judge the same-plan A/B written by ab_sectioned.py.

For each scene: the single-call version and the per-item version, written from
the identical brief and paragraph plan.

  richness  pairwise, both orders (cancels position bias): which version is
            richer on specificity, sensory detail, inner life and subtext,
            with a 1-5 score per version per dimension
  register  judge_v2's register-fit prompt, each version alone
  craft     judge_v2's five craft scores, each version alone
  plan      judge_v2's plan checks (mode labels by a small model, word range
            and one speaker per DIALOGUE item in Python)
  joins     blind continuity check on windows around paragraph boundaries:
            in the per-item version every boundary is a join between calls;
            the single-call version at the same boundaries is the control
  repeat    the free repetition gauge (agent/repetition.py), no LLM

Every call is cached and budgeted through judge_v2.call, so a re-run is free.

    venv/bin/python experiments/dsl_validation/ab_judge.py --name ab1-opus55-alcyone --max-usd 0.8
"""

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_v2 as J  # noqa: E402
from judge import SEAM_PROMPT, paragraphs, parse_json, window  # noqa: E402
import run_cell  # noqa: E402

ARMS = ("single", "peritem")
DIMS = ("specificity", "sensory", "inner_life", "subtext")

RICHNESS_PROMPT = """Two versions of the same scene from a novel follow. They were written from the \
same brief and the same paragraph plan, so the events and the order are meant to be the same. \
Compare them for RICHNESS only, on four questions:

specificity: exact, particular things (a named tool, a precise gesture, a detail only this place \
or person would have) rather than generic ones.
sensory:     the reader can see, hear, smell, feel the scene; detail comes through the senses, \
not through labels.
inner_life:  the point-of-view character's thoughts, memories and reactions are present and \
particular to them, shown rather than named.
subtext:     people mean more than they say; the important things are carried under the talk.

Do not reward length for its own sake, and ignore paragraphing.

=== VERSION X ===
{x}
=== END X ===

=== VERSION Y ===
{y}
=== END Y ===

Reply with JSON only:
{{"specificity": "X"|"Y"|"tie", "sensory": "X"|"Y"|"tie", "inner_life": "X"|"Y"|"tie", \
"subtext": "X"|"Y"|"tie", "overall": "X"|"Y"|"tie", \
"scores_x": {{"specificity": <1-5>, "sensory": <1-5>, "inner_life": <1-5>, "subtext": <1-5>}}, \
"scores_y": {{"specificity": <1-5>, "sensory": <1-5>, "inner_life": <1-5>, "subtext": <1-5>}}, \
"reason": "<three sentences: the clearest difference, with a short quote from each>"}}"""


def scene_pairs(project):
    ab = project / "ab"
    out = []
    for p in sorted(ab.glob("scene_*_single.md")):
        n = p.name.split("_")[1]
        texts, metas = {}, {}
        for arm in ARMS:
            texts[arm] = (ab / f"scene_{n}_{arm}.md").read_text().strip()
            metas[arm] = json.loads((ab / f"scene_{n}_{arm}.json").read_text())
        if texts["peritem"]:
            out.append((n, texts, metas))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--max-usd", type=float, default=0.8)
    ap.add_argument("--joins", type=int, default=6, help="joins sampled per scene")
    args = ap.parse_args()
    project = run_cell.find_project(args.name)
    out_path = project / "ab" / "judged.json"
    budget = J.Budget(args.max_usd)
    rng = random.Random(11)
    results = []
    try:
        for n, texts, metas in scene_pairs(project):
            row = {"scene": n, "words": {a: len(texts[a].split()) for a in ARMS}}
            skeleton = metas["single"].get("scene_skeleton")

            # richness, both orders
            votes = []
            for x_arm, y_arm in (ARMS, ARMS[::-1]):
                v = parse_json(J.call(J.JUDGE_MODEL, RICHNESS_PROMPT.format(
                    x=texts[x_arm], y=texts[y_arm]), budget, max_tokens=900)) or {}
                name = {"X": x_arm, "Y": y_arm}
                votes.append({
                    "order": f"{x_arm} first",
                    **{d: name.get(v.get(d), "tie") for d in DIMS + ("overall",)},
                    "scores": {x_arm: v.get("scores_x"), y_arm: v.get("scores_y")},
                    "reason": v.get("reason"),
                })
            row["richness"] = votes

            for arm in ARMS:
                text = texts[arm]
                paras = paragraphs(text)
                reg = parse_json(J.call(J.JUDGE_MODEL, J.REGISTER_PROMPT.format(text=text), budget)) or {}
                craft = parse_json(J.call(J.JUDGE_MODEL, J.CRAFT_PROMPT.format(text=text), budget)) or {}
                row.setdefault("register", {})[arm] = reg
                row.setdefault("craft", {})[arm] = craft
                if skeleton:
                    modes = "\n".join(f"- {m}: {g}" for m, g in J.MODE_GUIDE.items())
                    numbered = "\n\n".join(f"({i+1}) {p}" for i, p in enumerate(paras))
                    lab = parse_json(J.call(J.LABEL_MODEL, J.LABEL_PROMPT.format(
                        modes=modes, paras=numbered, n=len(paras)), budget, max_tokens=1500)) or {}
                    row.setdefault("plan", {})[arm] = J.plan_checks(paras, skeleton, lab.get("labels"))
                row.setdefault("compliance", {})[arm] = metas[arm].get("skeleton_compliance")

            # joins: the same boundaries in both versions, blind
            pi, si = paragraphs(texts["peritem"]), paragraphs(texts["single"])
            cands = list(range(2, min(len(pi), len(si)) - 1))
            joins = []
            for b in sorted(rng.sample(cands, min(args.joins, len(cands)))):
                for arm, ps in (("peritem", pi), ("single", si)):
                    w, join_after = window(ps, b)
                    v = parse_json(J.call(J.JUDGE_MODEL, SEAM_PROMPT.format(text=w),
                                          budget, max_tokens=300)) or {}
                    joins.append({"arm": arm, "boundary": b, "true_join_after": join_after, **v})
            row["joins"] = joins
            results.append(row)
            print(f"[ab-judge] scene {n} done (${budget.usd:.3f} so far)", flush=True)
    except J.StopRun as e:
        print(f"[ab-judge] stopped: {e}", flush=True)

    # repetition gauge, free and local
    try:
        from novel_agent.agent.repetition import analyse
        from repetition_gauge import embedder
        emb = embedder()
        for row, (n, texts, _m) in zip(results, scene_pairs(project)):
            row["repetition"] = {}
            for arm in ARMS:
                rep, _best = analyse(texts[arm], emb)
                s = max(rep.sentences, 1)
                row["repetition"][arm] = {
                    "sentences": rep.sentences,
                    "literal_rate": round(len(rep.literal) / s, 3),
                    "meaning_rate": round(len(rep.meaning) / s, 3),
                    "echo_rate": round(len(rep.echo) / s, 3),
                }
    except Exception as e:  # noqa: BLE001
        print(f"[ab-judge] repetition gauge skipped: {e}")

    out_path.write_text(json.dumps(results, indent=1))
    print(f"[ab-judge] wrote {out_path}; {budget.calls} billed calls, ${budget.usd:.3f}")


if __name__ == "__main__":
    main()
