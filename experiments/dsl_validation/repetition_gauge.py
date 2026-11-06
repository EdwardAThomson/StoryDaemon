#!/usr/bin/env python3
"""Run the repetition gauge (agent/repetition.py) over the masters calibration
chapters and every campaign cell, local and free (ChromaDB's bundled MiniLM).

    venv/bin/python experiments/dsl_validation/repetition_gauge.py [--threshold 0.8] [--show CELL]

Prints, per arm, the rate of sentences flagged at each layer and the
distribution of best-prior-similarity, so the meaning threshold can be set
above the masters' level. --show prints the flagged pairs for one cell.
"""
import argparse
import collections
import glob
import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import cells, scenes  # noqa: E402
from novel_agent.agent.repetition import analyse  # noqa: E402

OUT = REPO / "work" / "dsl" / "judged" / "repetition.json"


def embedder():
    from chromadb.utils import embedding_functions as ef
    f = ef.DefaultEmbeddingFunction()
    return lambda texts: f(list(texts))


def chapters():
    """[(arm, chapter_id, prose)] for the masters and every e1/e2 cell."""
    out = []
    for p in sorted(glob.glob(str(REPO / "experiments/dsl_validation/calibration/*.txt"))):
        out.append(("masters", Path(p).stem, open(p).read()))
    for name, proj in sorted(cells().items()):
        if name.startswith("e3") or "v0" in name:
            continue
        for sid, prose, _ in scenes(proj):
            out.append((name, f"{name}/{sid}", prose))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--show", help="print flagged pairs for one arm")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    embed = embedder()
    rows, dist = [], collections.defaultdict(list)
    for arm, cid, prose in chapters():
        rep, best = analyse(prose, embed, threshold=args.threshold)
        dist[arm] += best
        rows.append({"arm": arm, "chapter": cid, **rep.as_dict(),
                     "pairs": [m.__dict__ for m in rep.literal + rep.meaning + rep.echo]})
        if args.show and arm == args.show:
            print(f"\n=== {cid}")
            for m in rep.meaning:
                tag = "ECHO" if any(e.later == m.later for e in rep.echo) else "    "
                print(f"  {tag} {m.score:.2f} d={m.distance:3d}\n       A: {m.earlier_text[:140]}\n       B: {m.later_text[:140]}")
    Path(args.out).write_text(json.dumps(rows, indent=1))
    print(f"\n{'arm':30s} {'chap':>4s} {'sents':>6s} {'literal':>8s} {'meaning':>8s} {'echo':>6s}   p50   p90   p95  >=.7  >=.75  >=.8  >=.85")
    by = collections.defaultdict(list)
    for r in rows:
        by[r["arm"]].append(r)
    for arm in sorted(by, key=lambda a: (a != "masters", a)):
        rs = by[arm]; n = sum(r["sentences"] for r in rs)
        lit = sum(r["literal"] for r in rs) / n; mea = sum(r["meaning"] for r in rs) / n
        ech = sum(r["echo"] for r in rs) / n
        d = sorted(dist[arm]); q = lambda p: d[int(p * (len(d) - 1))]
        ge = lambda t: sum(x >= t for x in d) / len(d)
        print(f"{arm:30s} {len(rs):4d} {n:6d} {lit:8.3f} {mea:8.3f} {ech:6.3f}  {q(.5):.2f}  {q(.9):.2f}  {q(.95):.2f}  {ge(.7):.3f}  {ge(.75):.3f}  {ge(.8):.3f}  {ge(.85):.3f}")


if __name__ == "__main__":
    main()
