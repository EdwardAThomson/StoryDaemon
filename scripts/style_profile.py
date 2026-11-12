#!/usr/bin/env python3
"""Measure a style profile from a Project Gutenberg novel. Free: no model calls.

    python scripts/style_profile.py work/blind/books/pg12669.txt --name marriage \\
        --source "Susan Ferrier, Marriage (1818), Project Gutenberg 12669" \\
        --leave-out "put on your Lennox face" --leave-out "Poor Mary was indeed shocked" \\
        --drop-indented

writes novel_agent/data/styles/marriage.json, which `generation.style_profile:
marriage` then puts in front of the writer. --leave-out drops any chapter
holding that phrase, so a passage you will compare against stays out of the
profile. The book itself is never committed.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from novel_agent.agent.style_profile import (  # noqa: E402
    STYLES_DIR, book_chapters, favourite_words, measure)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("book", type=Path)
    ap.add_argument("--name", required=True, help="profile name, e.g. marriage")
    ap.add_argument("--source", required=True, help="author, title, year, edition")
    ap.add_argument("--leave-out", action="append", default=[], metavar="PHRASE",
                    help="drop every chapter holding this phrase (repeatable)")
    ap.add_argument("--drop-indented", action="store_true",
                    help="drop indented paragraphs (chapter epigraphs)")
    ap.add_argument("--out", type=Path, help="default: novel_agent/data/styles/<name>.json")
    args = ap.parse_args()

    chapters = book_chapters(args.book.read_text(encoding="utf-8"),
                             args.leave_out, args.drop_indented)
    if not chapters:
        sys.exit("no chapters found: does the book use CHAPTER headings?")
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
        **profile}, indent=1) + "\n")
    print(f"{out}: {note}")
    for k, v in profile.items():
        print(f"  {k:24} {v}")


if __name__ == "__main__":
    main()
