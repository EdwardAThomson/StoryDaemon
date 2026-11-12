#!/usr/bin/env python3
"""Run the voices gauge (agent/voices.py) over masters novels and campaign
cells. Local and free: no model calls.

    venv/bin/python experiments/dsl_validation/voices_gauge.py [--books DIR] [--show CHAPTER]

Masters novels are Project Gutenberg plain texts under work/voices/books/
(gitignored), split into chapters. Per arm it prints the share of speech it
could attribute, the two tell-apart scores (how they speak, what they talk
about; 0 = no better than guessing, 1 = always right), and the "too much"
counts. --show prints one chapter's attributed turns, for checking by hand.
"""
import argparse
import glob
import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import cells, scenes  # noqa: E402
from novel_agent.agent.voices import analyse  # noqa: E402

BOOKS = REPO / "work" / "voices" / "books"
OUT = REPO / "work" / "voices" / "voices.json"
STRETCH_WORDS = 14000
HEADING = re.compile(r"^\s*(CHAPTER|Chapter|STAVE)\b.*$", re.M)


def book_chapters(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    s = text.find("*** START OF")
    e = text.find("*** END OF")
    text = text[text.find("\n", s) + 1 if s >= 0 else 0: e if e > 0 else None]
    title = re.search(r"^Title:\s*(.+)$", Path(path).read_text(errors="replace"), re.M)
    title = title.group(1).split(";")[0].split(":")[0].strip() if title else Path(path).stem
    parts = HEADING.split(text)
    if len(parts) > 5:
        chunks = [b for b in HEADING.split(text)[::2]]
    else:
        chunks = []
    if len(chunks) < 5:  # no chapter headings: ~3,000-word windows on paragraph breaks
        pars = re.split(r"\n\s*\n", text)
        chunks, cur, n = [], [], 0
        for p in pars:
            cur.append(p)
            n += len(p.split())
            if n >= 3000:
                chunks.append("\n\n".join(cur)); cur, n = [], 0
        if cur:
            chunks.append("\n\n".join(cur))
    out = []
    for i, c in enumerate(chunks):
        if len(c.split()) >= 800:
            out.append((f"{title} #{i}", c))
    return out


def roster(project):
    names = []
    for f in sorted((project / "memory" / "characters").glob("*.json")):
        c = json.loads(f.read_text())
        full = " ".join(x for x in [c.get("first_name"), c.get("family_name")] if x)
        if full:
            names.append(full)
    return names


def units(books_dir, cell_filter):
    out = []
    """A unit is a stretch of story: a whole model run, or consecutive masters
    chapters adding up to about as many words (STRETCH_WORDS), since a voice
    belongs to a character across a story, not to one scene."""
    out = []
    for name, proj in sorted(cells().items()):
        if cell_filter and not re.search(cell_filter, name):
            continue
        prose = "\n\n".join(p for _, p, _ in scenes(proj))
        out.append((name, name, prose, roster(proj)))
    for p in sorted(glob.glob(str(Path(books_dir) / "*.txt"))):
        cur, ids = [], []
        for cid, prose in book_chapters(p):
            cur.append(prose); ids.append(cid)
            if sum(len(c.split()) for c in cur) >= STRETCH_WORDS:
                out.append(("masters", f"{ids[0]}..{ids[-1].split('#')[-1]}", "\n\n".join(cur), None))
                cur, ids = [], []
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 2) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", default=str(BOOKS))
    ap.add_argument("--cells", default=r"^(m1-|e1-luna-.*-on|e2-luna-.*-single)")
    ap.add_argument("--show")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    rows = []
    for arm, cid, prose, r in units(args.books, args.cells):
        v = analyse(prose, r)
        if args.show and cid == args.show:
            for t in v.turns:
                print(f"[{t.para:3}] {t.speaker or '?':22} {t.how:11} {t.text[:110]}")
        rows.append({"arm": arm, "chapter": cid, **v.as_dict()})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, indent=1))

    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row["arm"]].append(row)
    print(f"{'arm':32} {'units':>5} {'tested':>6} {'attrib':>6} {'speakers':>8} "
          f"{'how':>5} {'what':>5} {'dialect':>7} {'catch':>6}")
    for arm, rs in by_arm.items():
        tested = [r for r in rs if r["how_score"] is not None]
        print(f"{arm:32} {len(rs):5} {len(tested):6} "
              f"{mean([r['attributed_share'] for r in rs if r['speech_words'] >= 300]) or 0:6.2f} "
              f"{mean([r['k'] for r in tested]) or 0:8.1f} "
              f"{mean([r['how_score'] for r in tested]) or 0:5.2f} "
              f"{mean([r['what_score'] for r in tested]) or 0:5.2f} "
              f"{mean([r['dialect_per_1000'] for r in rs if r['speech_words'] >= 300]) or 0:7.2f} "
              f"{mean([r['catchphrase_per_1000'] for r in rs if r['speech_words'] >= 300]) or 0:6.2f}")


if __name__ == "__main__":
    main()
