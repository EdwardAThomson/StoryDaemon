#!/usr/bin/env python3
"""Gate A: does the skeleton sampler reproduce the masters' block statistics?

Generates N synthetic chapters (label sequences only, zero LLM calls),
computes the same statistics scripts/block_grammar_tables.py measures on the
masters corpus, and compares them to grammar_reference.json with explicit
tolerances. Exit code 0 = all checks pass.

The one number a flat first-order Markov sampler cannot hit is the
excursion-and-return rate (masters 0.355 vs flat-chain 0.238); it is the
direct test that the scene layer is doing its job.

Usage:
    python gate_a.py --chapters 3000 --seed 1
"""

import argparse
import os
import statistics
import sys
from collections import Counter, defaultdict

from sampler import Grammar, Params, Sampler

HERE = os.path.dirname(os.path.abspath(__file__))


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
    row_tot = Counter()
    for (a, _), c in trans.items():
        row_tot[a] += c
    return {
        "base": {m: base[m] / sum(base.values()) for m in modes},
        "row": {a: {b: (trans[(a, b)] / row_tot[a] if row_tot[a] else 0.0)
                    for b in modes} for a in modes},
        "row_n": row_tot,
        "run_mean": {m: statistics.mean(runs[m]) for m in modes if runs[m]},
        "openers": {m: opens[m] / sum(opens.values()) for m in modes},
        "closers": {m: closes[m] / sum(closes.values()) for m in modes},
        "aba": aba_obs / aba_n if aba_n else 0.0,
        "mean_len": statistics.mean(lengths),
    }


def tv(p, q, modes):
    return 0.5 * sum(abs(p.get(m, 0) - q.get(m, 0)) for m in modes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--grammar",
                    default=os.path.join(HERE, "grammar_reference.json"))
    args = ap.parse_args()

    g = Grammar(args.grammar)
    modes = g.modes
    s = Sampler(g, Params(), seed=args.seed)
    got = measure(s.chapters(args.chapters), modes)

    ref_aba = g.raw["aba"]["overall_observed"]
    ref_flat = g.raw["aba"]["overall_first_order_prediction"]
    ref_run = {m: v["mean"] for m, v in g.raw["run_stats"].items()}
    ref_len = statistics.mean(g.unit_lengths)

    checks = []

    def check(name, value, target, tol, fmt="{:.3f}"):
        ok = abs(value - target) <= tol
        checks.append(ok)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: got {fmt.format(value)} "
              f"vs target {fmt.format(target)} (tol {tol:g})")

    print(f"Gate A on {args.chapters} chapters (seed {args.seed})\n")

    print("-- base rates (abs diff per mode) --")
    for m in modes:
        check(f"base {m}", got["base"][m], g.base[m], 0.045)

    print("\n-- transition rows (total variation distance) --")
    for a in modes:
        tol = 0.10 if g.raw["row_n"][a] >= 1000 else 0.15
        d = tv(got["row"][a], g.row[a], modes)
        ok = d <= tol
        checks.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] row {a}: TV {d:.3f} (tol {tol})")

    print("\n-- run-length means (relative) --")
    for m in modes:
        if m in got["run_mean"] and m in ref_run:
            rel = abs(got["run_mean"][m] - ref_run[m]) / ref_run[m]
            ok = rel <= 0.20
            checks.append(ok)
            print(f"[{'PASS' if ok else 'FAIL'}] run {m}: "
                  f"{got['run_mean'][m]:.2f} vs {ref_run[m]:.2f} "
                  f"({rel:+.0%}, tol 20%)")

    print("\n-- boundaries --")
    d = tv(got["openers"], g.openers, modes)
    checks.append(d <= 0.10)
    print(f"[{'PASS' if d <= 0.10 else 'FAIL'}] openers: TV {d:.3f} (tol 0.10)")
    d = tv(got["closers"], g.closers, modes)
    checks.append(d <= 0.12)
    print(f"[{'PASS' if d <= 0.12 else 'FAIL'}] closers: TV {d:.3f} (tol 0.12)")

    print("\n-- structure --")
    check("excursion-return rate", got["aba"], ref_aba, 0.05)
    print(f"       (flat first-order chain would give ~{ref_flat:.3f})")
    check("mean chapter blocks", got["mean_len"], ref_len, 0.2 * ref_len,
          fmt="{:.1f}")

    n_fail = checks.count(False)
    print(f"\n{'ALL CHECKS PASS' if n_fail == 0 else f'{n_fail} CHECKS FAILED'} "
          f"({checks.count(True)}/{len(checks)})")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
