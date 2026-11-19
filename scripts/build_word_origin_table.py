#!/usr/bin/env python3
"""Build novel_agent/data/word_origin.json, the word-origin table. Free.

Each common English word is given one origin group:

    G   Old English or Norse (hand, look, sword, the, of)
    R   French or Latin (manner, pleasure, voice, occasion)
    Gk  Greek (melancholy, energy, story)
    O   another language (sofa, piano, guinea)

Sources, in order of precedence:

1. hand labels in experiments/blind_test/word_origin_labels.json (the most
   frequent words the table below lacks or gets wrong; how they were made and
   checked is in that file);
2. Gerard de Melo's Etymological Wordnet (mined from Wiktionary, CC BY-SA 3.0),
   as bundled in the `ety` pip package: a word's origin is followed through
   Middle English to Old English, Norse, Old French or Latin, skipping affixes;
3. the small grammar words (the, of, he, was), which the Wordnet leaves out
   and which are almost all Old English.

Words are kept only if wordfreq ranks them among the 80,000 most used English
words, which keeps the file small. Needs `pip install ety wordfreq` (build
time only; StoryDaemon reads the JSON with the stdlib).

    venv/bin/python scripts/build_word_origin_table.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "blind_test"))
from word_origin import FUNCTION, Origins  # noqa: E402

OUT = ROOT / "novel_agent" / "data" / "word_origin.json"
# Grammar words from French or Latin; every other one in FUNCTION is native.
FUNCTION_ROMANCE = {"very", "just", "because", "except", "during", "per", "via"}


def main():
    from wordfreq import top_n_list

    o = Origins()
    common = set(top_n_list("en", 80000))
    groups = {"G": [], "R": [], "Gk": [], "O": []}
    seen = set()

    def put(word, group):
        if word in seen or group not in groups:
            return
        seen.add(word)
        groups[group].append(word)

    for w, g in o.labels.items():          # labels win, X words are left out
        seen.add(w) if g == "X" else put(w, g)
    for w in FUNCTION | FUNCTION_ROMANCE:
        put(w, "R" if w in FUNCTION_ROMANCE else "G")
    for w in o.d["eng"]:
        if w in common and w.isalpha() and w.islower():
            g = o._lookup(w)
            put(w, "O" if g == "other" else g)

    out = {
        "about": ("Word origin groups for common English words: G Old English or "
                  "Norse, R French or Latin, Gk Greek, O other. Built by "
                  "scripts/build_word_origin_table.py from hand labels (most "
                  "frequent gaps and errors) and Gerard de Melo's Etymological "
                  "Wordnet (from Wiktionary), which is licensed CC BY-SA 3.0; "
                  "this derived table is shared under the same licence."),
        "groups": {g: " ".join(sorted(ws)) for g, ws in groups.items()},
    }
    OUT.write_text(json.dumps(out, indent=0) + "\n")
    print(OUT, {g: len(ws) for g, ws in groups.items()},
          f"{OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
