#!/usr/bin/env python3
"""Gate C: does skeleton guidance move the known failure metrics?

A/B test. Both arms share the premise, writer model, temperature, and an
approximate word budget; only the skeleton arm sees structure:

  baseline arm: premise + "write a chapter, ~W words" (today's single-shot
                SceneWriter shape, no structural guidance)
  skeleton arm: identical, plus a Gate-A skeleton with the [n] marker
                protocol Gate B validated

Both outputs are re-annotated with the corpus judge protocol and compared,
pooled per arm, against the masters' bands on the PRE-REGISTERED failure
metrics of generated prose (BLOCK_DECOMPOSITION_STUDY.md):

  1. interiority self-transition  (generated ~0.40 vs masters 0.205,
                                   band ceiling ~0.29)
  2. secondary shading rate       (masters pooled 0.204; floor bar 0.10)

plus descriptive context (mode shares, dialogue run length, excursion-and-
return rate). Pass = the skeleton arm sits inside the bands AND is no
farther from the masters than the baseline on metric 1.

Structural metrics only in v1; st1 surface scoring (slop/MTLD/cliche) needs
the analyzer venv's heavy deps and is a follow-up.

Usage:
    python3 gate_c.py --fake                    # plumbing test, no network
    python3 gate_c.py --chapters 2 --seed 23    # short controlled real run
    python3 gate_c.py --rescore runs/gatec-s23-c2

Note the small-n warning: interiority transitions are ~9% of blocks, so
2-chapter debug runs measure metric 1 on very few events. Scale --chapters
before treating a verdict as real.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gate_b import (FakeLLM, OpenRouterLLM, PauseRun,            # noqa: E402
                    judge_annotations, render_marked, split_paragraphs,
                    writer_prompt, JUDGE_MODEL, PREMISE)
from sampler import Grammar, Params, Sampler                      # noqa: E402

WORDS_PER_BLOCK = 90          # word budget both arms share
INT_SELF_CEILING = 0.30       # masters band ceiling (~0.28-0.29) + rounding
SHADING_FLOOR = 0.10          # full-corpus masters floor is 0.106 (Austen)
MIN_INT_EVENTS = 20           # below this, metric 1 is noise: warn loudly


def baseline_prompt(n_words, chapter_no):
    return f"""{PREMISE}

Write chapter {chapter_no} of this novel as continuous prose, roughly
{n_words} words. Separate paragraphs with single blank lines. No headings,
no commentary: prose only."""


class FakeLLMC(FakeLLM):
    """Fake for plumbing tests: the baseline arm chains interiority (the
    known failure mode), so the fake run should FAIL the baseline on metric 1
    and PASS the skeleton arm, proving the scorecard discriminates."""

    _BASELINE_SEQ = ["SETTING", "INTERIORITY", "INTERIORITY", "INTERIORITY",
                     "ACTION", "INTERIORITY", "INTERIORITY", "DIALOGUE",
                     "INTERIORITY", "INTERIORITY", "INTERIORITY", "ACTION"]

    def __call__(self, prompt):
        if "continuous prose" in prompt:      # baseline writer
            from gate_b import FAKE_PARA
            return "\n\n".join(FAKE_PARA[m] for m in self._BASELINE_SEQ)
        return super().__call__(prompt)


# --- metrics -----------------------------------------------------------------------

def arm_metrics(chapters):
    """Pool structural metrics over one arm's chapters (never across a
    chapter boundary, matching the corpus convention)."""
    share = Counter()
    shaded = labeled = 0
    int_out = int_self = 0
    dlg_runs = []
    aba_obs = aba_n = 0
    for ch in chapters:
        anns = ch["annotations"]
        seq = [(a or {}).get("primary") for a in anns]
        for a in anns:
            if a and a.get("primary"):
                labeled += 1
                share[a["primary"]] += 1
                if a.get("secondary"):
                    shaded += 1
        clean = [s for s in seq if s]          # holes split nothing here;
        for a, b in zip(clean, clean[1:]):      # debug runs have few holes
            if a == "INTERIORITY":
                int_out += 1
                int_self += (b == "INTERIORITY")
        run = 0
        for s in clean + [None]:
            if s == "DIALOGUE":
                run += 1
            elif run:
                dlg_runs.append(run)
                run = 0
        for i in range(len(clean) - 2):
            a, b, c = clean[i], clean[i + 1], clean[i + 2]
            if b != a:
                aba_n += 1
                aba_obs += (c == a)
    return {
        "n_paragraphs": labeled,
        "mode_share": {m: round(share[m] / labeled, 3) for m in share}
        if labeled else {},
        "shading_rate": round(shaded / labeled, 3) if labeled else None,
        "int_self_transition":
            round(int_self / int_out, 3) if int_out else None,
        "int_transitions_n": int_out,
        "dialogue_run_mean":
            round(sum(dlg_runs) / len(dlg_runs), 2) if dlg_runs else None,
        "return_rate": round(aba_obs / aba_n, 3) if aba_n else None,
    }


# --- driver ------------------------------------------------------------------------

def run_arm(name, prompts, judge, writer, run_dir, skeletons=None):
    chapters = []
    for i, prompt in enumerate(prompts):
        if skeletons:   # skeleton arm: enforce the marker protocol
            prose, numbers, paras, flags = render_marked(
                writer, prompt, len(skeletons[i]))
        else:           # baseline arm: unmarked by design
            prose = writer(prompt)
            numbers, paras = split_paragraphs(prose)
            flags = None
        anns = judge_annotations(paras, judge)
        rec = {"arm": name, "prose": prose, "paragraphs": paras,
               "numbers": numbers, "annotations": anns, "flags": flags}
        if skeletons:
            rec["skeleton"] = skeletons[i]
        chapters.append(rec)
        json.dump(rec, open(os.path.join(
            run_dir, f"{name}_chapter_{i}.json"), "w"), indent=1)
        print(f"{name} chapter {i}: {len(paras)} paragraphs judged")
    return chapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", type=int, default=2)
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--max-blocks", type=int, default=24,
                    help="short controlled skeletons for debug runs")
    ap.add_argument("--writer-model", default=JUDGE_MODEL)
    ap.add_argument("--pause-after-calls", type=int, default=None,
                    help="stop cleanly after N billed LLM calls; re-run the "
                         "same command to resume (cache hits are free)")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--rescore", nargs="+", metavar="RUN_DIR",
                    help="rescore one run dir, or POOL several chunk runs "
                         "into one verdict (chunked-verdict workflow)")
    args = ap.parse_args()

    if args.rescore:
        chapters = []
        for d in args.rescore:
            chapters.extend(
                json.load(open(os.path.join(d, f)))
                for f in sorted(os.listdir(d))
                if re.match(r"(baseline|skeleton)_chapter_", f))
        arms = {n: [c for c in chapters if c["arm"] == n]
                for n in ("baseline", "skeleton")}
        if len(args.rescore) > 1:
            print(f"pooling {len(args.rescore)} chunk runs: "
                  + ", ".join(os.path.basename(d.rstrip('/'))
                              for d in args.rescore))
        report(arms, args.rescore[0])
        return

    tag = "fake" if args.fake else f"s{args.seed}-c{args.chapters}"
    run_dir = os.path.join(HERE, "runs", f"gatec-{tag}")
    os.makedirs(run_dir, exist_ok=True)

    sampler = Sampler(Grammar(os.path.join(HERE, "grammar_reference.json")),
                      Params(), seed=args.seed)
    skeletons = []
    while len(skeletons) < args.chapters:
        sk = sampler.chapter()
        if len(sk) <= args.max_blocks:
            skeletons.append(sk)

    budget = {"calls": 0, "max": args.pause_after_calls}
    writer = (FakeLLMC() if args.fake
              else OpenRouterLLM(args.writer_model, budget=budget))
    judge = writer if args.fake else OpenRouterLLM(JUDGE_MODEL, budget=budget)

    try:
        arms = {
            "baseline": run_arm(
                "baseline",
                [baseline_prompt(len(sk) * WORDS_PER_BLOCK, i + 2)
                 for i, sk in enumerate(skeletons)],
                judge, writer, run_dir),
            "skeleton": run_arm(
                "skeleton",
                [writer_prompt(sk, chapter_no=i + 2)
                 for i, sk in enumerate(skeletons)],
                judge, writer, run_dir, skeletons=skeletons),
        }
    except PauseRun as e:
        print(f"PAUSED: {e}. Completed chapters are saved; every billed "
              f"response is cached. Re-run the same command to resume, "
              f"then the scorecard runs at the end.")
        sys.exit(3)
    report(arms, run_dir)


def report(arms, run_dir):
    g = Grammar(os.path.join(HERE, "grammar_reference.json"))
    masters = {
        "int_self_transition": round(
            g.row["INTERIORITY"]["INTERIORITY"], 3),
        "shading_rate": round(g.raw["shading"]["rate"], 3),
        "return_rate": round(g.raw["aba"]["overall_observed"], 3),
        "mode_share": {m: round(g.base[m], 3)
                       for m in ("DIALOGUE", "ACTION", "INTERIORITY")},
    }
    m = {name: arm_metrics(chs) for name, chs in arms.items()}

    print(f"\nGate C scorecard -> {run_dir}")
    print(f"{'metric':28s} {'masters':>9s} {'baseline':>9s} {'skeleton':>9s}")
    rows = [
        ("interiority self-trans", masters["int_self_transition"],
         m["baseline"]["int_self_transition"],
         m["skeleton"]["int_self_transition"]),
        ("shading rate", masters["shading_rate"],
         m["baseline"]["shading_rate"], m["skeleton"]["shading_rate"]),
        ("return rate", masters["return_rate"],
         m["baseline"]["return_rate"], m["skeleton"]["return_rate"]),
        ("dialogue share", masters["mode_share"]["DIALOGUE"],
         m["baseline"]["mode_share"].get("DIALOGUE"),
         m["skeleton"]["mode_share"].get("DIALOGUE")),
        ("dialogue run mean", 3.32,
         m["baseline"]["dialogue_run_mean"],
         m["skeleton"]["dialogue_run_mean"]),
    ]
    for name, mv, bv, sv in rows:
        fmt = lambda v: "  n/a" if v is None else f"{v:9.3f}"
        print(f"{name:28s} {mv:9.3f} {fmt(bv)} {fmt(sv)}")
    for arm in ("baseline", "skeleton"):
        if m[arm]["int_transitions_n"] < MIN_INT_EVENTS:
            print(f"WARNING: {arm} arm has only "
                  f"{m[arm]['int_transitions_n']} interiority transitions; "
                  f"metric 1 is noisy at this scale (need >= "
                  f"{MIN_INT_EVENTS}; scale --chapters)")

    sk_int = m["skeleton"]["int_self_transition"]
    bl_int = m["baseline"]["int_self_transition"]
    target = masters["int_self_transition"]
    sk_n = m["skeleton"]["int_transitions_n"]
    bl_n = m["baseline"]["int_transitions_n"]
    results = []

    def check(name, ok, conclusive=True):
        """Tri-state: a metric measured on too few events is INCONCLUSIVE,
        never PASS or FAIL (verdict noise was the first bug this gate's
        debug run caught)."""
        state = ("PASS" if ok else "FAIL") if conclusive else "INCONCLUSIVE"
        results.append(state)
        print(f"[{state}] {name}")

    check(f"skeleton int-self <= {INT_SELF_CEILING} (band ceiling)",
          sk_int is not None and sk_int <= INT_SELF_CEILING,
          conclusive=sk_n >= MIN_INT_EVENTS)
    check(f"skeleton shading >= {SHADING_FLOOR} (masters floor)",
          (m["skeleton"]["shading_rate"] or 0) >= SHADING_FLOOR)
    check("skeleton no farther from masters than baseline on int-self",
          sk_int is not None and (
              bl_int is None
              or abs(sk_int - target) <= abs(bl_int - target)),
          conclusive=sk_n >= MIN_INT_EVENTS and bl_n >= MIN_INT_EVENTS)

    json.dump({"masters": masters, "arms": m, "results": results},
              open(os.path.join(run_dir, "summary.json"), "w"), indent=1)
    if "FAIL" in results:
        print("GATE NOT PASSED")
        sys.exit(1)
    if "INCONCLUSIVE" in results:
        print("INCONCLUSIVE: scale --chapters for a real verdict")
        sys.exit(2)
    print("ALL CHECKS PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
