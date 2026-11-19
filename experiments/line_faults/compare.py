"""Compare line-fault counts across texts: a shelf of books and any scenes.

Free: no model calls. Usage:

    python experiments/line_faults/compare.py --books DIR --scenes FILE [FILE...]
    python experiments/line_faults/compare.py --fetch DIR     # download the shelf

--books   a folder of Project Gutenberg plain-text files (pgNNNN.txt). Each
          book is measured whole (its chapters pooled), and the table ends
          with the lowest, middle and highest book on the shelf. "closing
          refl." for a book is the share of its chapters that end that way.
--scenes  Markdown or text files. A Markdown file is split at its "## " and
          "### " headings, and each section of 300+ words is one row, labelled
          by its heading.
--found   also print examples of what the pattern counts matched.

The books are not committed. --fetch downloads the shelf below from
gutenberg.org, pausing between requests.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "line_faults", ROOT / "novel_agent" / "agent" / "line_faults.py")
lf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lf)

# Older novels, 1813 to 1874. Gutenberg id -> label.
SHELF = {
    12669: "Ferrier, Marriage (1818)",
    1342: "Austen, Pride and Prejudice (1813)",
    158: "Austen, Emma (1815)",
    1260: "C. Bronte, Jane Eyre (1847)",
    599: "Thackeray, Vanity Fair (1848)",
    4276: "Gaskell, North and South (1855)",
    3409: "Trollope, Barchester Towers (1857)",
    1400: "Dickens, Great Expectations (1861)",
    145: "Eliot, Middlemarch (1871)",
    107: "Hardy, Far from the Madding Crowd (1874)",
}

SHOW = [k for k in lf.MEASURES]
SHORT = {
    "speech_with_business_pct": "speech+busy %",
    "stock_cues_per_1k": "stock cues",
    "named_feelings_per_1k": "named feel.",
    "filter_verbs_per_1k": "filters",
    "non_sight_sense_pct": "non-sight %",
    "fancy_tag_pct": "fancy tag %",
    "tag_adverbs_per_1k": "tag adverbs",
    "hedges_per_1k": "hedges",
    "began_to_per_1k": "began to",
    "similes_per_1k": "similes",
    "sentence_length_variation": "sent. var.",
    "closing_reflection": "closing refl.",
}


def fetch(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for pg in SHELF:
        dest = out / f"pg{pg}.txt"
        if dest.exists():
            continue
        url = f"https://www.gutenberg.org/cache/epub/{pg}/pg{pg}.txt"
        req = urllib.request.Request(url, headers={"User-Agent": "line-faults-gauge"})
        dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        print(f"fetched {dest.name}", flush=True)
        time.sleep(2)


def book_chapters(text: str) -> list:
    """Chapters of a Gutenberg text: the body between the START and END
    markers, split at CHAPTER headings; chapters under 800 words are dropped
    (contents pages, stray headings)."""
    text = text.replace("\r", "")
    start = re.search(r"\*\*\* ?START OF.*?\*\*\*", text)
    end = re.search(r"\*\*\* ?END OF", text)
    body = text[start.end() if start else 0: end.start() if end else len(text)]
    parts = re.split(r"\n\s*(?:CHAPTER|Chapter)\s+[IVXLC\d]+[^\n]*\n", body)
    out = []
    for part in parts:
        # Gutenberg wraps lines; join each paragraph into one line.
        paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", part) if p.strip()]
        chapter = "\n\n".join(paras)
        if len(chapter.split()) >= 800:
            out.append(chapter)
    return out


def sections(path: Path) -> list:
    """[(label, text)] for a scenes file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".md":
        return [(path.stem, text)]
    out, label, buf = [], path.stem, []
    for line in text.split("\n"):
        if re.match(r"#{2,3} ", line):
            out.append((label, "\n".join(buf)))
            label, buf = line.lstrip("# ").strip()[:60], []
        else:
            buf.append(line)
    out.append((label, "\n".join(buf)))
    return [(l, t) for l, t in out if len(t.split()) >= 300]


def fmt(v):
    return "   -" if v is None else f"{v:>6}"


def row(label, m):
    return f"{label[:44]:44} {m.get('words', ''):>7} " + " ".join(f"{fmt(m.get(k)):>13}" for k in SHOW)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", type=Path)
    ap.add_argument("--books", type=Path)
    ap.add_argument("--scenes", type=Path, nargs="*", default=[])
    ap.add_argument("--found", action="store_true")
    args = ap.parse_args(argv)
    if args.fetch:
        fetch(args.fetch)
        return 0

    print(f"{'':44} {'words':>7} " + " ".join(f"{SHORT[k]:>13}" for k in SHOW))
    shelf = {k: [] for k in SHOW}
    if args.books:
        for pg, label in SHELF.items():
            path = args.books / f"pg{pg}.txt"
            if not path.exists():
                continue
            chapters = book_chapters(path.read_text(encoding="utf-8", errors="replace"))
            if not chapters:
                continue
            # Pooled over the whole book: most of these are rare events, and a
            # per-chapter middle value would read zero for nearly all of them.
            m = lf.measure("\n\n".join(chapters))
            m["closing_reflection"] = round(
                statistics.mean(lf.closing_reflection(c) for c in chapters), 2)
            for k in SHOW:
                if m[k] is not None:
                    shelf[k].append(m[k])
            print(row(f"{label} [{len(chapters)} ch]", m))
            if args.found:
                print("   ", lf.found("\n\n".join(chapters), 12))
        if any(shelf.values()):
            for name, pick in (("shelf: lowest book", min), ("shelf: middle book", statistics.median),
                               ("shelf: highest book", max)):
                print(row(name, {k: round(pick(v), 2) if v else None for k, v in shelf.items()}))
        print()
    for path in args.scenes:
        for label, text in sections(path):
            print(row(label, lf.measure(text)))
            if args.found:
                print("   ", lf.found(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
