#!/usr/bin/env python3
"""Measure a style profile from Project Gutenberg novels. Free: no model calls.

    python scripts/style_profile.py work/blind/books/pg12669.txt --name marriage \\
        --source "Susan Ferrier, Marriage (1818), Project Gutenberg 12669" \\
        --leave-out "put on your Lennox face" --leave-out "Poor Mary was indeed shocked" \\
        --drop-indented

writes novel_agent/data/styles/marriage.json, which `generation.style_profile:
marriage` then puts in front of the writer. --leave-out drops any chapter
holding that phrase, so a passage you will compare against stays out of the
profile. The book itself is never committed.

Several books make a shelf profile (an author, or a kind of book): their
chapters are pooled.

    python scripts/style_profile.py work/blind/shelf/pg169.txt \
        work/blind/shelf/pg3055.txt work/blind/shelf/pg61077.txt \
        work/blind/shelf/pg67090.txt --name old_fantasy --source "..."

Each count also gets its range across the chapters (p10 to p90), under
"ranges". A book that heads its chapters without the word CHAPTER is split
on lines like "I: THE CASTLE OF LORD JUSS" or "XII. THE ESCAPE" instead.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from novel_agent.agent.style_profile import (  # noqa: E402
    STYLES_DIR, book_chapters, chapter_ranges, favourite_words, measure)

# For books with no CHAPTER headings: a line holding only a Roman numeral, a
# colon or full stop, and an upper-case title.
NUMBERED_TITLE = r"^\s*[IVXLC]+[:.]\s+[A-Z][A-Z’' ,\-]+\s*$"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("books", type=Path, nargs="+")
    ap.add_argument("--name", required=True, help="profile name, e.g. marriage")
    ap.add_argument("--source", required=True, help="author, title, year, edition")
    ap.add_argument("--leave-out", action="append", default=[], metavar="PHRASE",
                    help="drop every chapter holding this phrase (repeatable)")
    ap.add_argument("--drop-indented", action="store_true",
                    help="drop indented paragraphs (chapter epigraphs)")
    ap.add_argument("--out", type=Path, help="default: novel_agent/data/styles/<name>.json")
    args = ap.parse_args()

    chapters, counts = [], []
    for book in args.books:
        text = book.read_text(encoding="utf-8", errors="replace")
        found = max(book_chapters(text, args.leave_out, args.drop_indented),
                    book_chapters(text, args.leave_out, args.drop_indented,
                                  heading=NUMBERED_TITLE), key=len)
        if not found:
            sys.exit(f"{book}: no chapters found (no CHAPTER or numbered-title headings)")
        chapters += found
        counts.append(f"{book.stem} {len(found)}")
    text = "\n\n".join(chapters)
    profile = measure(text)
    try:
        from wordfreq import zipf_frequency
        profile["favourite_words"] = favourite_words(
            text, lambda w: zipf_frequency(w, "en"))
    except ImportError:
        print("wordfreq is not installed (pip install wordfreq): "
              "the profile has no favourite_words list")
    note = f"{len(chapters)} chapters"
    if len(args.books) > 1:
        note += f" ({', '.join(counts)})"
    if args.leave_out:
        note += f", leaving out the chapters holding: {'; '.join(args.leave_out)}"
    if args.drop_indented:
        note += ", epigraphs removed"
    out = args.out or STYLES_DIR / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "name": args.name,
        "source": f"{args.source}; {note}",
        "measured": datetime.date.today().isoformat(),
        **profile,
        "ranges": chapter_ranges(chapters)}, indent=1) + "\n")
    print(f"{out}: {note}")
    for k, v in profile.items():
        print(f"  {k:24} {v}")


if __name__ == "__main__":
    main()
