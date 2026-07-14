#!/usr/bin/env python3
"""Regenerate the measured tables in docs/MASTERS_BLOCK_GRAMMAR_STUDY.md.

Reads the nd1 block-rhythm sidecars (per-paragraph primary/secondary labels,
produced by the analyzer repo's narrative_dynamics benchmark, DeepSeek judge)
and prints every table as Markdown, or dumps the full statistics as JSON for
downstream consumers (experiments/block_grammar_poc reads that JSON).
No LLM calls; pure aggregation.

Usage:
    python scripts/block_grammar_tables.py                   # Markdown tables
    python scripts/block_grammar_tables.py --include-giants  # + judged giants
    python scripts/block_grammar_tables.py --json PATH       # machine-readable

Default scope excludes the giants so the numbers match the masters corpus
report (21 books). Re-run with --include-giants after the giant runs are
aggregated, and update the doc's scope line accordingly.
"""

import argparse
import glob
import json
import os
import statistics
from collections import Counter, defaultdict

SIDE_DIR = os.path.join(os.path.dirname(__file__), "..",
                        "work", "corpus", "scores", "nd1_ab", "deepseek")
GIANTS = {"collins-womaninwhite", "eliot-middlemarch", "dickens-bleakhouse",
          "dumas-montecristo", "tolstoy-warandpeace"}
MODES = ["SETTING", "CHARACTER_DESC", "LORE", "DIALOGUE", "ACTION",
         "INTERIORITY", "TRANSITION"]
SHORT = {"SETTING": "SET", "CHARACTER_DESC": "CHR", "LORE": "LOR",
         "DIALOGUE": "DLG", "ACTION": "ACT", "INTERIORITY": "INT",
         "TRANSITION": "TRN"}


def load_books(include_giants):
    books = {}
    for path in sorted(glob.glob(os.path.join(SIDE_DIR, "*.nd.json"))):
        name = os.path.basename(path).replace(".nd.json", "")
        if not include_giants and name in GIANTS:
            continue
        with open(path) as f:
            books[name] = json.load(f)
    return books


def compute(books):
    """Aggregate every statistic once; both output modes read this."""
    agg = {
        "trans": Counter(), "runs": defaultdict(list),
        "opens": Counter(), "closes": Counter(), "base": Counter(),
        "pos_decile": defaultdict(Counter), "tension_band": defaultdict(Counter),
        "sec_pairs": Counter(), "sec_total": 0, "prim_total": 0,
        "aba_obs": Counter(), "aba_n": Counter(), "unit_lengths": [],
        "trans2": Counter(),
    }
    for name, d in books.items():
        br = d["metrics"]["block_rhythm"]
        tu = sorted(d["metrics"]["tension_trajectory"]["per_unit"],
                    key=lambda u: u["index"])
        bu = sorted(br["per_unit"], key=lambda u: u["index"])
        seqs = []
        for pos, u in enumerate(bu):
            seq = [l[0] for l in u["labels"] if l and l[0]]
            agg["prim_total"] += len(u["labels"])
            for l in u["labels"]:
                if l and l[0] and l[1]:
                    agg["sec_total"] += 1
                    agg["sec_pairs"][(l[0], l[1])] += 1
            if not seq:
                continue
            seqs.append(seq)
            agg["unit_lengths"].append(len(seq))
            agg["base"].update(seq)
            agg["opens"][seq[0]] += 1
            agg["closes"][seq[-1]] += 1
            for a, b in zip(seq, seq[1:]):
                agg["trans"][(a, b)] += 1
            cur, n = seq[0], 1
            for m in seq[1:]:
                if m == cur:
                    n += 1
                else:
                    agg["runs"][cur].append(n)
                    cur, n = m, 1
            agg["runs"][cur].append(n)
            for i in range(len(seq) - 2):
                a, b, c = seq[i], seq[i + 1], seq[i + 2]
                agg["trans2"][(a, b, c)] += 1
                if b != a:
                    agg["aba_n"][(a, b)] += 1
                    if c == a:
                        agg["aba_obs"][(a, b)] += 1
            if pos < len(tu):
                t = tu[pos]["tension"]
                band = ("calm(<=3)" if t <= 3
                        else "high(>=7)" if t >= 7 else "mid(4-6)")
                agg["tension_band"][band].update(seq)
        flat = [m for s in seqs for m in s]
        for i, m in enumerate(flat):
            agg["pos_decile"][min(9, i * 10 // len(flat))][m] += 1

    row_tot = Counter()
    for (a, _), c in agg["trans"].items():
        row_tot[a] += c
    agg["row_tot"] = row_tot
    agg["p"] = lambda a, b: (agg["trans"][(a, b)] / row_tot[a]
                             if row_tot[a] else 0.0)
    return agg


def print_tables(books, agg):
    trans, runs, p = agg["trans"], agg["runs"], agg["p"]
    base, row_tot = agg["base"], agg["row_tot"]

    print(f"Scope: {len(books)} books, {sum(base.values())} labeled paragraphs, "
          f"{sum(trans.values())} within-unit transitions.\n")

    print("## Transition matrix P(next | current)\n")
    print("| from \\ to | " + " | ".join(SHORT[m] for m in MODES) + " | n |")
    print("|---|" + "---:|" * (len(MODES) + 1))
    for a in MODES:
        cells = " | ".join(f"{p(a, b):.3f}" for b in MODES)
        print(f"| {a} | {cells} | {row_tot[a]:,} |")

    print("\n## Run lengths (consecutive same-mode paragraphs)\n")
    print("| mode | mean | geometric-implied mean | median | p90 | max | runs |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for m in MODES:
        r = runs[m]
        if not r:
            continue
        implied = 1.0 / (1.0 - p(m, m)) if p(m, m) < 1 else float("inf")
        print(f"| {m} | {statistics.mean(r):.2f} | {implied:.2f} | "
              f"{statistics.median(r):.0f} | {sorted(r)[int(len(r)*0.9)]} | "
              f"{max(r)} | {len(r):,} |")

    tot_base = sum(base.values())
    to, tc = sum(agg["opens"].values()), sum(agg["closes"].values())
    print("\n## Unit boundary grammar (vs base rate)\n")
    print("| mode | base rate | opens unit | closes unit |")
    print("|---|---:|---:|---:|")
    for m in MODES:
        print(f"| {m} | {base[m]/tot_base:.3f} | {agg['opens'][m]/to:.3f} | "
              f"{agg['closes'][m]/tc:.3f} |")

    print("\n## Mode share by book-position decile\n")
    print("| decile | " + " | ".join(SHORT[m] for m in MODES) + " |")
    print("|---|" + "---:|" * len(MODES))
    for dec in range(10):
        c = agg["pos_decile"][dec]
        t = sum(c.values())
        print(f"| {dec} | " + " | ".join(f"{c[m]/t:.3f}" for m in MODES) + " |")

    print("\n## Mode share by unit tension band\n")
    print("| band | n paragraphs | " + " | ".join(SHORT[m] for m in MODES) + " |")
    print("|---|---:|" + "---:|" * len(MODES))
    for band in ["calm(<=3)", "mid(4-6)", "high(>=7)"]:
        c = agg["tension_band"][band]
        t = sum(c.values())
        print(f"| {band} | {t:,} | " +
              " | ".join(f"{c[m]/t:.3f}" for m in MODES) + " |")

    print(f"\n## Secondary shading ({agg['sec_total']:,}/{agg['prim_total']:,} "
          f"paragraphs, {agg['sec_total']/agg['prim_total']:.1%})\n")
    print("| primary + secondary | count |")
    print("|---|---:|")
    for (pr, se), c in agg["sec_pairs"].most_common(10):
        print(f"| {pr} + {se} | {c:,} |")

    aba_n, aba_obs = agg["aba_n"], agg["aba_obs"]
    tot_n = sum(aba_n.values())
    tot_obs = sum(aba_obs.values())
    tot_exp = sum(p(b, a) * cnt for (a, b), cnt in aba_n.items())
    print("\n## Excursion-and-return (A -> B -> back-to-A) test\n")
    print(f"All genuine switches pooled (n={tot_n:,}): observed return rate "
          f"{tot_obs/tot_n:.3f} vs first-order prediction {tot_exp/tot_n:.3f}.\n")
    print("| pattern (n >= 200) | n | observed return | predicted | excess |")
    print("|---|---:|---:|---:|---:|")
    rows = []
    for (a, b), cnt in aba_n.items():
        if cnt >= 200:
            o = aba_obs[(a, b)] / cnt
            rows.append((o - p(b, a), a, b, cnt, o, p(b, a)))
    for dlt, a, b, cnt, o, e in sorted(rows, reverse=True):
        print(f"| {a} -> {b} -> back | {cnt:,} | {o:.3f} | {e:.3f} | {dlt:+.3f} |")


def _second_order(agg, min_n):
    """P(next | prev, current) for contexts with enough support.

    This is the kernel the PoC sampler uses for within-scene dynamics: the
    excursion-and-return behaviour (doc Section 7) is a second-order
    statistic, so sampling from this kernel reproduces it by construction.
    Sparse contexts fall back to the first-order row at load time.
    """
    ctx_tot = Counter()
    for (a, b, c), n in agg["trans2"].items():
        ctx_tot[(a, b)] += n
    out = {}
    for (a, b), tot in sorted(ctx_tot.items()):
        if tot < min_n:
            continue
        out[f"{a}|{b}"] = {
            "n": tot,
            "next": {c: agg["trans2"][(a, b, c)] / tot
                     for c in MODES if agg["trans2"][(a, b, c)]},
        }
    return out


def dump_json(books, agg, path):
    trans, runs, p = agg["trans"], agg["runs"], agg["p"]
    base = agg["base"]
    tot_base = sum(base.values())
    to, tc = sum(agg["opens"].values()), sum(agg["closes"].values())
    aba_n, aba_obs = agg["aba_n"], agg["aba_obs"]
    tot_n = sum(aba_n.values())

    out = {
        "meta": {
            "n_books": len(books),
            "books": sorted(books),
            "n_paragraphs": tot_base,
            "n_transitions": sum(trans.values()),
            "source": "nd1_ab/deepseek sidecars via scripts/block_grammar_tables.py",
        },
        "modes": MODES,
        "base_rates": {m: base[m] / tot_base for m in MODES},
        "transition": {a: {b: p(a, b) for b in MODES} for a in MODES},
        "row_n": {a: agg["row_tot"][a] for a in MODES},
        "run_stats": {
            m: {
                "mean": statistics.mean(runs[m]),
                "median": statistics.median(runs[m]),
                "p90": sorted(runs[m])[int(len(runs[m]) * 0.9)],
                "max": max(runs[m]),
                "n_runs": len(runs[m]),
            } for m in MODES if runs[m]
        },
        "unit_openers": {m: agg["opens"][m] / to for m in MODES},
        "unit_closers": {m: agg["closes"][m] / tc for m in MODES},
        "unit_lengths_blocks": sorted(agg["unit_lengths"]),
        "aba": {
            "overall_observed": sum(aba_obs.values()) / tot_n,
            "overall_first_order_prediction":
                sum(p(b, a) * cnt for (a, b), cnt in aba_n.items()) / tot_n,
            "n_switches": tot_n,
            "pairs": {
                f"{a}|{b}": {
                    "n": cnt,
                    "observed_return": aba_obs[(a, b)] / cnt,
                    "first_order_prediction": p(b, a),
                }
                for (a, b), cnt in sorted(aba_n.items()) if cnt >= 30
            },
        },
        "second_order": _second_order(agg, min_n=80),
        "tension_bands": {
            band: {m: c[m] / sum(c.values()) for m in MODES}
            for band, c in agg["tension_band"].items()
        },
        "shading": {
            "rate": agg["sec_total"] / agg["prim_total"],
            "top_pairs": [
                {"primary": pr, "secondary": se, "count": c}
                for (pr, se), c in agg["sec_pairs"].most_common(20)
            ],
        },
    }
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-giants", action="store_true")
    ap.add_argument("--json", metavar="PATH",
                    help="dump full statistics as JSON instead of tables")
    args = ap.parse_args()
    books = load_books(args.include_giants)
    agg = compute(books)
    if args.json:
        dump_json(books, agg, args.json)
    else:
        print_tables(books, agg)


if __name__ == "__main__":
    main()
