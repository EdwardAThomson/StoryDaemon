#!/usr/bin/env python3
"""Judge novel-project scenes with the corpus protocol and score them
against the masters' block statistics: the production version of Gate C.

Takes one or more project scene directories (each a cell), annotates every
scene's paragraphs with the corpus DeepSeek judge (cached, resumable), and
prints the Gate C metric table for each cell next to the masters.

    python3 judge_scenes.py ../../work/skeltest/prod-on_*/scenes \
                            ../../work/skeltest/prod-off_*/scenes
"""

import argparse
import glob
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gate_b import OpenRouterLLM, judge_annotations, JUDGE_MODEL  # noqa: E402
from gate_c import arm_metrics                                     # noqa: E402
from sampler import Grammar                                        # noqa: E402


def scene_paragraphs(path):
    """Prose paragraphs of a saved scene (header stripped)."""
    content = open(path).read()
    prose = content.split("\n---\n", 1)[-1]
    return [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dirs", nargs="+",
                    help="one scenes/ directory per cell")
    ap.add_argument("--out", default=os.path.join(HERE, "runs",
                                                  "judge_scenes_last.json"))
    args = ap.parse_args()

    judge = OpenRouterLLM(JUDGE_MODEL)
    g = Grammar(os.path.join(HERE, "grammar_reference.json"))
    masters = {
        "int_self": g.row["INTERIORITY"]["INTERIORITY"],
        "shading": g.raw["shading"]["rate"],
        "return": g.raw["aba"]["overall_observed"],
        "dlg_share": g.base["DIALOGUE"],
        "dlg_run": 3.32,
        "words_per_para": 90.0,
    }

    cells = {}
    for d in args.scene_dirs:
        cell = os.path.basename(os.path.dirname(d.rstrip("/")))
        chapters, wpp = [], []
        for f in sorted(glob.glob(os.path.join(d, "*.md"))):
            paras = scene_paragraphs(f)
            wpp.extend(len(p.split()) for p in paras)
            anns = judge_annotations(paras, judge)
            chapters.append({"annotations": anns})
            print(f"  judged {f}: {len(paras)} paragraphs", flush=True)
        m = arm_metrics(chapters)
        m["words_per_para"] = round(statistics.mean(wpp), 1) if wpp else None
        cells[cell] = m

    rows = [
        ("interiority self-trans", "int_self_transition", "int_self"),
        ("shading rate", "shading_rate", "shading"),
        ("return rate", "return_rate", "return"),
        ("dialogue share", None, "dlg_share"),
        ("dialogue run mean", "dialogue_run_mean", "dlg_run"),
        ("words per paragraph", "words_per_para", "words_per_para"),
    ]
    names = list(cells)
    print("\n" + f"{'metric':24s} {'masters':>9s} "
          + " ".join(f"{n[:14]:>15s}" for n in names))
    for label, key, mkey in rows:
        vals = []
        for n in names:
            if key is None:
                v = cells[n]["mode_share"].get("DIALOGUE")
            else:
                v = cells[n][key]
            vals.append("    n/a" if v is None else f"{v:15.3f}")
        print(f"{label:24s} {masters[mkey]:9.3f} " + " ".join(vals))
    for n in names:
        print(f"({n}: {cells[n]['n_paragraphs']} paragraphs, "
              f"{cells[n]['int_transitions_n']} interiority events)")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"masters": masters, "cells": cells}, open(args.out, "w"),
              indent=1)
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
