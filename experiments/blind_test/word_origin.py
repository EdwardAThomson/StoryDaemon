"""Word origin gauge: how much of a text's vocabulary is Old English (and
Norse) and how much came in from French and Latin. Free: no model calls.

Why: the long-word rate is a stand-in for "Latinate" and gets authors like
Tolkien backwards (his long words are few and his short words old). Origin is
the measure itself.

The table is the Etymological Wordnet data bundled in the `ety` pip package
(experiment only, read straight from its JSON). A word's origin follows the
chain eng -> Middle English -> Old English / Old French / Latin, skipping
affixes, so "darkness" goes dark -> derk -> deorc (Old English). Words the
table lacks get a small inflection strip (stones -> stone, walked -> walk) and
then a Latin-suffix rule (-tion, -ity, -ous, ...).

The table has holes on both sides (hand, eye and face are missing, and so are
chair, effect and spirit), and many common words stop at a Middle English form
with no onward link (king, but also opinion, table, castle). So the 1,200 most
frequent such words carry hand labels, in word_origin_labels.json (how they
were made and checked is in that file). A Middle English form with no onward
link and no label counts as unknown.

Counted over content words only: function words (the, of, and, he) are almost
all Old English in every text and would swamp the difference. Names (words
only ever capitalised) are left out.

    venv/bin/python experiments/blind_test/word_origin.py FILE_OR_STEM ...
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ETY = next((ROOT / "venv" / "lib").glob("python*/site-packages/ety/data/etymologies.json"), None)
LABELS = Path(__file__).with_name("word_origin_labels.json")

GERMANIC = {"ang", "non", "odt", "dum", "gml", "goh", "gmh", "osx", "ofs", "frk", "got",
            "deu", "nld", "fry", "dan", "swe", "isl", "nor", "nob", "sco", "gem", "gmw"}
ROMANCE = {"fro", "frm", "fra", "xno", "lat", "ita", "spa", "por", "cat", "pro", "frp",
           "lla", "ml", "la"}
GREEK = {"grc", "ell"}

LATIN_SUFFIX = re.compile(r"(tion|sion|ity|ment|ance|ence|ancy|ency|ous|ive|ible|able|"
                          r"ate|ure|ary|ory|ical|ial|ual|ient|iant|ism|ist|ize|ise|ify)s?$")

FUNCTION = set("""a an the and or but nor if so as than that this these those then there
here where when while what which who whom whose why how not no yes of to in on at by for
from with into onto upon over under about after before between through without within
against among up down out off again once i me my mine myself we us our ours you your
yours he him his himself she her hers herself it its itself they them their theirs
themselves is am are was were be been being have has had having do does did doing will
would shall should can could may might must ought all any both each few more most other
some such only own same too very just also even still yet ever never""".split())

WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")


class Origins:
    def __init__(self, path=ETY, labels=LABELS):
        if path is None or not Path(path).exists():
            raise FileNotFoundError("needs `pip install ety` in venv/ (experiment only)")
        self.d = json.loads(Path(path).read_text())
        self.labels = json.loads(Path(labels).read_text())["labels"] if labels else {}
        self.cache = {}

    def _chain(self, word, lang, depth=0):
        """Origin group for a (word, language) pair: G, R, Gk, other, or None."""
        if lang in GERMANIC:
            return "G"
        if lang in ROMANCE:
            return "R"
        if lang in GREEK:
            return "Gk"
        if depth > 6:
            return None
        if lang in ("eng", "enm"):
            srcs = self.d.get(lang, {}).get(word)
            return self._from_sources(srcs, depth + 1) if srcs else None
        return "other"

    def _from_sources(self, srcs, depth):
        pairs = [(w, l) for s in srcs for w, l in s.items()]
        stems = [(w, l) for w, l in pairs if not (w.startswith("-") or w.endswith("-"))]
        for w, l in stems or pairs:
            got = self._chain(w, l, depth)
            if got:
                return got
        return None

    def _lookup(self, w):
        if w in self.labels:
            return self.labels[w]
        srcs = self.d["eng"].get(w)
        return self._from_sources(srcs, 0) if srcs else None

    def origin(self, w):
        """(group, how) for a lowercased word; how is 'label', 'table', 'stem' or
        'suffix'. Group 'X' means not a word to count."""
        if w in self.cache:
            return self.cache[w]
        got, how = self._lookup(w), ("label" if w in self.labels else "table")
        if got is None:
            how = "stem"
            for cand in _stems(w):
                got = self._lookup(cand)
                if got:
                    break
        if got is None and LATIN_SUFFIX.search(w) and len(w) > 6:
            got, how = "R", "suffix"
        self.cache[w] = (got, how if got else None)
        return self.cache[w]


def _stems(w):
    out = []
    if w.endswith("'s"):
        out.append(w[:-2])
    for suf, rep in (("ies", "y"), ("ied", "y"), ("ier", "y"), ("iest", "y"), ("ily", "y"),
                     ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"),
                     ("ly", ""), ("er", ""), ("est", ""), ("ness", ""), ("ful", ""),
                     ("less", ""), ("ment", ""), ("ion", "e"), ("ation", "e")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[: len(w) - len(suf)] + rep
            out.append(base)
            if len(base) > 3 and base[-1] == base[-2] and not rep:      # stopped -> stop
                out.append(base[:-1])
    return out


def content_words(text):
    text = text.replace("’", "'").replace("‘", "'")
    toks = [(w.lower(), w[0].isupper()) for w in WORD.findall(text)]
    caps = {}
    for w, c in toks:
        caps.setdefault(w, set()).add(c)
    names = {w for w, c in caps.items() if c == {True}}
    return [w for w, _ in toks if w not in names and w not in FUNCTION
            and "'" not in w and len(w) > 1]


def measure(text, origins):
    words = content_words(text)
    groups, how, unknown, by_group = Counter(), Counter(), Counter(), {}
    words = [w for w in words if origins.origin(w)[0] != "X"]
    for w in words:
        g, h = origins.origin(w)
        if g is None:
            unknown[w] += 1
            continue
        groups[g] += 1
        how[h] += 1
        by_group.setdefault(g, Counter())[w] += 1
    known = sum(groups.values())
    return {
        "content_words": len(words),
        "coverage_pct": round(100 * known / len(words), 1) if words else 0.0,
        "old_english_pct": round(100 * groups["G"] / known, 1) if known else 0.0,
        "french_latin_pct": round(100 * groups["R"] / known, 1) if known else 0.0,
        "greek_pct": round(100 * groups["Gk"] / known, 1) if known else 0.0,
        "by_suffix_rule_pct": round(100 * how["suffix"] / known, 1) if known else 0.0,
        "by_label_pct": round(100 * how["label"] / known, 1) if known else 0.0,
        "unknown": dict(unknown.most_common(25)),
        "top": {g: dict(c.most_common(25)) for g, c in by_group.items()},
    }


def main(argv):
    o = Origins()
    for arg in argv:
        p = Path(arg)
        text = p.read_text(encoding="utf-8", errors="replace")
        m = measure(text, o)
        print(f"{p.name:28} words {m['content_words']:>7} cover {m['coverage_pct']:>5}%  "
              f"OE {m['old_english_pct']:>5}%  Fr/Lat {m['french_latin_pct']:>5}%  "
              f"Gk {m['greek_pct']:>4}%  (suffix rule {m['by_suffix_rule_pct']}%)")


if __name__ == "__main__":
    main(sys.argv[1:])
