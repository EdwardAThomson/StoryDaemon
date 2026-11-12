"""Word-choice gauge for the blind test. Free: no model calls.

The blind test's first reader picked the real Ferrier passage over
StoryDaemon's on word choice ("more archaic words", "a French phrase"), with
sentence structure already close. This gauge asks whether word choice can be
counted, before any lever is built. For each text it reports, with the words
themselves listed:

- out of its time: words found nowhere in a shelf of novels from
  1778-1871 (the text's own source book left out of the shelf);
- period words: words the shelf uses at least six times as often as modern
  English does (wordfreq, which mixes books, the web, subtitles and news);
- modern words: words modern English uses at least ten times as often as the
  shelf does;
- the author's favourites: the 150 words the source novel (test chapters left
  out) uses most often relative to modern English.

The shelf lives in work/blind/books/ and work/blind/shelf/ (Project
Gutenberg texts, gitignored). Needs `pip install wordfreq` (experiment only).

    venv/bin/python experiments/blind_test/word_gauge.py [--json out.json]
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from novel_agent.agent.style_profile import book_chapters  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work" / "blind"
SOURCE_BOOK = {"pride": "pg1342", "marriage": "pg12669",
               "emma": "pg158", "persuasion": "pg105"}
# Chapters holding these phrases are the test passages: kept out of the
# author's favourites, exactly as the style profiles keep them out.
LEAVE_OUT = {"pride": ["fifty miles of good road"],
             "marriage": ["put on your Lennox face", "Poor Mary was indeed shocked"]}
# (scene, how it was made, path)
TEXTS = [
    ("marr_13", "Ferrier", "austen/marr_13.md"),
    ("marr_13", "StoryDaemon", "out/marr_13/dsl_style.md"),
    ("marr_13", "plain Opus", "out/marr_13/plain.md"),
    ("marr_18", "Ferrier", "austen/marr_18.md"),
    ("marr_18", "StoryDaemon", "out/marr_18/dsl_style.md"),
    ("marr_18", "plain Opus", "out/marr_18/plain.md"),
    ("pp_32", "Austen", "austen/pp_32.md"),
    ("pp_32", "StoryDaemon", "out/pp_32/dsl.md"),
    ("pp_32", "StoryDaemon + style", "out/pp_32/dsl_style.md"),
    ("pp_32", "plain Opus", "out/pp_32/plain.md"),
    ("pp_new", "StoryDaemon + style", "out/pp_new/free_style.md"),
    # emma_III4 and pers_18 have only --fake outputs so far: not gauged.
]
WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")


def tokens(text):
    """Lowercased words with their capitalisation. Hyphens split words, so
    'to-morrow' counts as 'to' + 'morrow' and 'tomorrow' stays whole."""
    text = text.replace("’", "'").replace("‘", "'")
    return [(w.lower(), w[0].isupper()) for w in WORD.findall(text)]


def book_text(stem):
    for d in ("books", "shelf"):
        p = WORK / d / f"{stem}.txt"
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    raise FileNotFoundError(stem)


def shelf_counts():
    """Per-book word counts over every book on the shelf."""
    stems = sorted({p.stem for d in ("books", "shelf") for p in (WORK / d).glob("pg*.txt")})
    per_book = {}
    for stem in stems:
        chapters = book_chapters(book_text(stem))
        text = "\n\n".join(chapters) if chapters else book_text(stem)
        per_book[stem] = Counter(w for w, _ in tokens(text))
    return per_book


def zipf(count, total):
    """Occurrences per billion words, as a log10 (wordfreq's scale)."""
    return math.log10(count / total * 1e9) if count else 0.0


def names_in(text, extra=()):
    """Words only ever capitalised in this text (or minted names): people and places."""
    seen = {}
    for w, cap in tokens(text):
        seen.setdefault(w, set()).add(cap)
    return {w for w, caps in seen.items() if caps == {True}} | {e.lower() for e in extra}


def minted_names():
    names = json.loads((WORK / "names.json").read_text())
    out = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            out.update(t.lower() for t in WORD.findall(x))
    walk(names)
    return out


def main():
    from wordfreq import zipf_frequency

    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    briefs = json.loads((WORK / "briefs.json").read_text())["scenes"]
    per_book = shelf_counts()
    minted = minted_names()
    modern = {}

    def mz(w):
        if w not in modern:
            modern[w] = zipf_frequency(w, "en")
        return modern[w]

    def shelf_without(stem):
        c = Counter()
        for s, counts in per_book.items():
            if s != stem:
                c.update(counts)
        books = Counter()
        for s, counts in per_book.items():
            if s != stem:
                books.update(set(counts))
        return c, sum(c.values()), books

    favourites_cache, shelf_cache, rows = {}, {}, []
    for scene, made, rel in TEXTS:
        path = WORK / rel
        if not path.exists():
            continue
        novel = briefs[scene]["novel"]
        stem = SOURCE_BOOK[novel]
        if stem not in shelf_cache:
            shelf_cache[stem] = shelf_without(stem)
        shelf, total, books = shelf_cache[stem]
        if novel not in favourites_cache:
            src = book_chapters(book_text(stem), LEAVE_OUT.get(novel, []))
            src_text = "\n\n".join(src)
            src_counts = Counter(w for w, _ in tokens(src_text))
            src_total = sum(src_counts.values())
            skip = names_in(src_text)
            scored = [(zipf(c, src_total) - mz(w), w) for w, c in src_counts.items()
                      if c >= 8 and w not in skip and len(w) > 2]
            favourites_cache[novel] = {w for _, w in sorted(scored, reverse=True)[:150]}
        favourites = favourites_cache[novel]

        text = path.read_text()
        skip = names_in(text, minted)
        words = [w for w, _ in tokens(text) if w not in skip]
        n = len(words)
        out_of_time = Counter(w for w in words if len(w) > 2 and shelf[w] == 0)
        period = Counter(w for w in words
                         if shelf[w] >= 30 and books[w] >= 4 and mz(w) < 5.5
                         and zipf(shelf[w], total) - mz(w) >= 0.8)
        modern_words = Counter(w for w in words
                               if mz(w) >= 3.0 and mz(w) - zipf(shelf[w], total) >= 1.0)
        fav = Counter(w for w in words if w in favourites)
        # Rare words: in the period's vocabulary but uncommon today (wordfreq
        # zipf under 3.5, about 3 per million words): "personage", "vapid".
        rare = Counter(w for w in words if len(w) > 2 and shelf[w] > 0 and mz(w) < 3.5)
        long_words = sum(1 for w in words if len(w) >= 10)

        def per_1k(c):
            return round(1000 * sum(c.values()) / n, 1)

        rows.append({
            "scene": scene, "made": made, "words": n,
            "out_of_time_per_1k": per_1k(out_of_time), "out_of_time": dict(out_of_time.most_common()),
            "period_per_1k": per_1k(period), "period": dict(period.most_common()),
            "modern_per_1k": per_1k(modern_words), "modern": dict(modern_words.most_common()),
            "favourites_per_1k": per_1k(fav), "favourites": dict(fav.most_common()),
            "rare_per_1k": per_1k(rare), "rare": dict(rare.most_common()),
            "long_words_per_1k": round(1000 * long_words / n, 1),
        })

    print(f"Shelf: {len(per_book)} books, "
          f"{sum(sum(c.values()) for c in per_book.values()):,} words\n")
    head = (f"{'scene':10} {'made':20} {'words':>6} {'out-of-time':>11} {'period':>7} "
            f"{'modern':>7} {'author fav':>10} {'rare':>6} {'10+ letters':>11}")
    print(head)
    for r in rows:
        print(f"{r['scene']:10} {r['made']:20} {r['words']:>6} {r['out_of_time_per_1k']:>11} "
              f"{r['period_per_1k']:>7} {r['modern_per_1k']:>7} {r['favourites_per_1k']:>10} "
              f"{r['rare_per_1k']:>6} {r['long_words_per_1k']:>11}")
    print()
    for r in rows:
        print(f"== {r['scene']} / {r['made']}")
        for k in ("out_of_time", "modern", "rare", "period"):
            print(f"  {k}: {', '.join(f'{w}' + (f' x{c}' if c > 1 else '') for w, c in list(r[k].items())[:30])}")
    if args.json:
        args.json.write_text(json.dumps({"rows": rows,
                                         "favourites": {k: sorted(v) for k, v in favourites_cache.items()}},
                                        indent=1))


if __name__ == "__main__":
    main()
