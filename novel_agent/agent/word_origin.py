"""Word origin: how much of a text is plain Old English and how much came in
from French and Latin.

Tolkien's prose is about 89% Germanic and 8% Latinate (a Legendarium table of
five fantasy authors); Ferrier's *Marriage* is about 79% and 20%. The share
is one of the clearest differences between registers, and a length count only
stands in for it: in the blind test the long-word target brought StoryDaemon's
long words up to Ferrier's level but left its short everyday words (sure,
manner, sense) as Germanic as plain Opus's.

The table (``novel_agent/data/word_origin.json``) is built by
``scripts/build_word_origin_table.py`` from hand labels and the Etymological
Wordnet. A word it lacks is tried without its ending (stones, walked), then by
a Latin suffix rule (-tion, -ity, -ous), and is otherwise left out of the
shares. Names (words only ever capitalised in the text) are left out too.

Pure and stdlib only.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

TABLE = Path(__file__).resolve().parent.parent / "data" / "word_origin.json"

_WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
_LATIN_SUFFIX = re.compile(r"(tion|sion|ity|ment|ance|ence|ancy|ency|ous|ive|ible|able|"
                           r"ate|ure|ary|ory|ical|ial|ual|ient|iant|ism|ist|ize|ise|ify)s?$")
_ENDINGS = (("ies", "y"), ("ied", "y"), ("ier", "y"), ("iest", "y"), ("ily", "y"),
            ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"),
            ("ly", ""), ("er", ""), ("est", ""), ("ness", ""), ("ful", ""),
            ("less", ""), ("ment", ""), ("ion", "e"), ("ation", "e"))


@lru_cache(maxsize=1)
def _table() -> dict:
    groups = json.loads(TABLE.read_text(encoding="utf-8"))["groups"]
    return {w: g for g, words in groups.items() for w in words.split()}


@lru_cache(maxsize=1)
def _grammar_words() -> frozenset:
    """The small grammar words (the, of, he, was), left out of the content share.
    The same list as the experiment gauge (experiments/blind_test/word_origin.py)."""
    return frozenset("""a an the and or but nor if so as than that this these those then
there here where when while what which who whom whose why how not no yes of to in on at
by for from with into onto upon over under about after before between through without
within against among up down out off again once i me my mine myself we us our ours you
your yours he him his himself she her hers herself it its itself they them their theirs
themselves is am are was were be been being have has had having do does did doing will
would shall should can could may might must ought all any both each few more most other
some such only own same too very just also even still yet ever never""".split())


def _stems(w: str) -> list:
    out = [w[:-2]] if w.endswith("'s") else []
    for suffix, repl in _ENDINGS:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            base = w[: len(w) - len(suffix)] + repl
            out.append(base)
            if len(base) > 3 and base[-1] == base[-2] and not repl:   # stopped -> stop
                out.append(base[:-1])
    return out


def origin(word: str) -> Optional[str]:
    """'G', 'R', 'Gk', 'O', or None when unknown, for one lowercased word."""
    table = _table()
    if word in table:
        return table[word]
    for stem in _stems(word):
        if stem in table:
            return table[stem]
    if len(word) > 6 and _LATIN_SUFFIX.search(word):
        return "R"
    return None


def _words_without_names(text: str) -> list:
    text = text.replace("’", "'").replace("‘", "'")
    found = [(w.lower(), w[0].isupper()) for w in _WORD.findall(text)]
    lower = {w for w, cap in found if not cap}
    return [w for w, cap in found if (not cap or w in lower) and "'" not in w]


def origin_shares(text: str) -> dict:
    """Shares of words by origin, as percentages of the words whose origin is
    known. ``latinate_pct`` and ``germanic_pct`` count every word, as the
    Legendarium table does; ``latinate_content_pct`` leaves out the grammar
    words, which are almost all Old English in any text and so hide
    differences. ``origin_known_pct`` is how many words the table placed."""
    words = _words_without_names(text)
    grammar = _grammar_words()

    def shares(ws):
        groups = [origin(w) for w in ws]
        known = [g for g in groups if g]
        if not known:
            return 0.0, 0.0, 0.0
        pct = lambda g: round(100 * known.count(g) / len(known), 1)      # noqa: E731
        return pct("R"), pct("G"), round(100 * len(known) / len(groups), 1)

    latinate, germanic, known = shares(words)
    latinate_content, _, _ = shares([w for w in words if w not in grammar])
    return {"latinate_pct": latinate, "germanic_pct": germanic,
            "latinate_content_pct": latinate_content, "origin_known_pct": known}
