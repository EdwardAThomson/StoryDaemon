#!/usr/bin/env python3
"""Gate A, run against the PRODUCTION sampler.

gate_a.py scores the PoC's own Sampler. This scores
novel_agent.agent.scene_skeleton.generate_skeleton, which is what actually
reaches a novel, using the same statistics and the same tolerances. Zero LLM
calls.

Two scales are reported, because they are not the same question:

- chapter scale, sized so a plan is about as long as a masters chapter
  (~58 blocks). This is the like-for-like comparison against the corpus,
  whose statistics are all measured per chapter.
- scene scale, at the real generation.scene_word_targets. Production plans
  are 15-35 blocks, so boundary statistics (openers, closers) carry far more
  weight per plan and long runs have less room. Divergence here is expected
  and is a property of generating scenes rather than chapters; it is reported
  so the size of that effect is known rather than assumed.

Usage:
    python gate_a_production.py --chapters 2000
"""

import argparse
import os
import statistics
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from sampler import Grammar                                    # noqa: E402
from novel_agent.agent import scene_skeleton as sk             # noqa: E402


def measure(chapters, modes):
    trans = Counter()
    runs = defaultdict(list)
    opens, closes, base = Counter(), Counter(), Counter()
    aba_obs = aba_n = 0
    lengths = []
    for seq in chapters:
        if not seq:
            continue
        lengths.append(len(seq))
        base.update(seq)
        opens[seq[0]] += 1
        closes[seq[-1]] += 1
        for a, b in zip(seq, seq[1:]):
            trans[(a, b)] += 1
        cur, n = seq[0], 1
        for m in seq[1:]:
            if m == cur:
                n += 1
            else:
                runs[cur].append(n)
                cur, n = m, 1
        runs[cur].append(n)
        for i in range(len(seq) - 2):
            a, b, c = seq[i], seq[i + 1], seq[i + 2]
            if b != a:
                aba_n += 1
                aba_obs += (c == a)
    tot = sum(base.values())
    row_tot = Counter()
    for (a, _), c in trans.items():
        row_tot[a] += c
    return {
        "base": {m: base[m] / tot for m in modes},
        "row": {a: {b: (trans[(a, b)] / row_tot[a] if row_tot[a] else 0.0)
                    for b in modes} for a in modes},
        "run_mean": {m: statistics.mean(runs[m]) for m in modes if runs[m]},
        "openers": {m: opens[m] / sum(opens.values()) for m in modes},
        "closers": {m: closes[m] / sum(closes.values()) for m in modes},
        "aba": aba_obs / aba_n if aba_n else float("nan"),
        "mean_len": statistics.mean(lengths),
    }


def tv(p, q, modes):
    return 0.5 * sum(abs(p.get(m, 0.0) - q.get(m, 0.0)) for m in modes)


def score(label, chapters, g, modes, strict):
    got = measure(chapters, modes)
    ref_aba = g.raw["aba"]["overall_observed"]
    ref_run = {m: v["mean"] for m, v in g.raw["run_stats"].items()}
    ref_len = statistics.mean(g.unit_lengths)
    checks = []

    def check(name, value, target, tol, fmt="{:.3f}"):
        ok = abs(value - target) <= tol
        checks.append((name, ok))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {fmt.format(value)} "
              f"vs target {fmt.format(target)} (tol {tol:g})")

    print(f"\n===== {label} =====\n")
    print("-- base rates --")
    for m in modes:
        check(f"base {m}", got["base"][m], g.base[m], 0.045)
    print("\n-- transition rows (total variation) --")
    for a in modes:
        tol = 0.10 if g.raw["row_n"][a] >= 1000 else 0.15
        d = tv(got["row"][a], g.row[a], modes)
        checks.append((f"row {a}", d <= tol))
        print(f"[{'PASS' if d <= tol else 'FAIL'}] row {a}: TV {d:.3f} "
              f"(tol {tol})")
    print("\n-- run-length means --")
    for m in modes:
        if m in got["run_mean"] and m in ref_run:
            rel = abs(got["run_mean"][m] - ref_run[m]) / ref_run[m]
            checks.append((f"run {m}", rel <= 0.20))
            print(f"[{'PASS' if rel <= 0.20 else 'FAIL'}] run {m}: "
                  f"{got['run_mean'][m]:.2f} vs {ref_run[m]:.2f} "
                  f"({rel:+.0%}, tol 20%)")
    print("\n-- boundaries --")
    for name, key, tol in (("openers", "openers", 0.10),
                           ("closers", "closers", 0.12)):
        d = tv(got[key], getattr(g, key), modes)
        checks.append((name, d <= tol))
        print(f"[{'PASS' if d <= tol else 'FAIL'}] {name}: TV {d:.3f} "
              f"(tol {tol})")
    print("\n-- structure --")
    check("excursion-return rate", got["aba"], ref_aba, 0.05)
    print(f"       (a flat first-order chain gives "
          f"~{g.raw['aba']['overall_first_order_prediction']:.3f})")
    if strict:
        check("mean chapter blocks", got["mean_len"], ref_len,
              0.2 * ref_len, fmt="{:.1f}")
    else:
        print(f"[----] mean blocks: {got['mean_len']:.1f} "
              f"(masters chapter {ref_len:.1f}; not compared, scenes are "
              f"shorter by design)")
    failed = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} pass"
          + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", type=int, default=2000)
    args = ap.parse_args()
    g = Grammar(os.path.join(HERE, "grammar_reference.json"))
    modes = g.modes

    # Chapter scale: pick the word budget that yields masters-length plans.
    ref_len = statistics.mean(g.unit_lengths)
    words = round(ref_len * sk.mode_word_stats()["DIALOGUE"]["mean"] * 0 +
                  ref_len * 59.8)          # measured pooled words/paragraph
    chapter = [sk.generate_skeleton(words, seed=i) for i in range(args.chapters)]
    fail_a = score(f"chapter scale ({words} words per plan)",
                   chapter, g, modes, strict=True)

    scene = [sk.generate_skeleton(1400, seed=i) for i in range(args.chapters)]
    fail_b = score("scene scale (1400 words, the production default)",
                   scene, g, modes, strict=False)

    print("\n" + "=" * 62)
    print("chapter scale is the like-for-like gate; scene scale is reported "
          "for information.")
    sys.exit(0 if not fail_a else 1)


if __name__ == "__main__":
    main()
