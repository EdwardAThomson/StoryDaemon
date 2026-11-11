#!/usr/bin/env python3
"""Can Opus recite a book? A cheap recall probe for choosing the blind test's book.

For each book, four paragraphs from deep in it (between 20% and 90% of the
way through, evenly spaced, at least 130 words of prose) are cut after 50
words. One call per book gives Opus the four openings, names the book and
author, and asks for the next words exactly as printed. The score is how much
of each reply sits in five-word runs of the true next 80 words, and the
longest run of words it got right. A book Opus has memorised scores high;
one it only knows of scores near zero.

    venv/bin/python experiments/blind_test/recall_probe.py --max-usd 0.12
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments" / "dsl_validation"))
import judge_v2 as J  # noqa: E402

BOOKS = REPO / "work" / "blind" / "books"
MODEL = "anthropic/claude-opus-5.5"
CANDIDATES = [
    ("pg1342.txt", "Pride and Prejudice", "Jane Austen", None),
    ("pg12669.txt", "Marriage", "Susan Ferrier", None),
    ("pg8937.txt", "Patronage", "Maria Edgeworth", "PATRONAGE."),
    ("pg41286.txt", "Miss Marjoribanks", "Margaret Oliphant", None),
    ("pg41196.txt", "Self-Control", "Mary Brunton", None),
]
HEAD, TAIL, PER_BOOK = 50, 80, 4

PROMPT = """Below are the openings of {n} passages from the novel *{title}* by {author}.
For each, write the next {tail} words or so EXACTLY as they appear in the
original text. If you do not know the exact words, give your best guess at
them; do not explain or apologise.

{items}

Reply with JSON only: {{"continuations": ["...", "..."]}} with {n} strings, in order."""


def body(text, start_mark=None):
    s = text.find("*** START OF")
    e = text.find("*** END OF")
    t = text[text.find("\n", s) + 1 if s >= 0 else 0: e if e > 0 else len(text)]
    if start_mark and start_mark in t:
        t = t[t.find(start_mark):]
    t = re.sub(r"\[Illustration[^\]]*\]", "", t, flags=re.S)
    return re.sub(r"_([^_]+)_", r"\1", t)


def passages(t):
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", t)]
    n = len(paras)
    good = [i for i in range(int(n * 0.2), int(n * 0.9))
            if len(paras[i].split()) >= HEAD + 80 and not paras[i].isupper()]
    picks = [good[int(k * (len(good) - 1) / (PER_BOOK - 1))] for k in range(PER_BOOK)]
    out = []
    for i in picks:
        w = paras[i].split()
        nxt = (w[HEAD:] + " ".join(paras[i + 1:i + 3]).split())[:TAIL]
        out.append((" ".join(w[:HEAD]), " ".join(nxt)))
    return out


def norm(t):
    return re.findall(r"[a-z']+", t.lower().replace("’", "'"))


def score(reply, truth, k=5):
    a, b = norm(truth), norm(reply)
    if not b:
        return 0.0, 0
    grams = {tuple(a[i:i + k]) for i in range(len(a) - k + 1)}
    hits = {j for i in range(len(b) - k + 1) if tuple(b[i:i + k]) in grams for j in range(i, i + k)}
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            m = 0
            while i + m < len(a) and j + m < len(b) and a[i + m] == b[j + m]:
                m += 1
            best = max(best, m)
    return len(hits) / len(b), best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-usd", type=float, required=True)
    args = ap.parse_args()
    budget = J.Budget(args.max_usd)
    report = {}
    for fname, title, author, mark in CANDIDATES:
        ps = passages(body((BOOKS / fname).read_text(), mark))
        items = "\n\n".join(f"({i + 1}) ...{h}" for i, (h, _t) in enumerate(ps))
        reply = J.call(MODEL, PROMPT.format(n=len(ps), title=title, author=author, tail=TAIL, items=items),
                       budget, max_tokens=4000)
        conts = (J.parse_json(reply) or {}).get("continuations") or []
        rows = []
        for (h, truth), c in zip(ps, conts + [""] * len(ps)):
            share, run = score(c, truth)
            rows.append({"head": h, "truth": truth, "reply": c, "share": round(share, 3), "longest_run": run})
        report[title] = rows
        mean = sum(r["share"] for r in rows) / len(rows)
        print(f"[recall] {title} ({author}): {100 * mean:.0f}% of reply words in true 5-word runs; "
              f"longest runs {[r['longest_run'] for r in rows]} (${budget.usd:.3f} so far)", flush=True)
    (REPO / "work" / "blind" / "recall_probe.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
