"""Style profiles: an author's measured habits, told to the writer as targets.

A profile is a handful of free text counts measured from a real novel
(sentence length and spread, speech share, semicolons, dashes, contractions,
"seemed/felt" words, the "said" share). With ``generation.style_profile`` set,
the writer is given them as numbers for a scene of its length.

The blind test (docs/BLIND_TEST_2026-11.md) is where this was proved: with
targets measured from Susan Ferrier's *Marriage*, StoryDaemon's sentences,
paragraphs and speech share landed near hers, where plain Opus wrote short
sentences with no semicolons or dashes at all.

Pure and stdlib only. Profiles ship in ``novel_agent/data/styles/`` and are
measured by ``scripts/style_profile.py``; the books themselves are not
committed.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Callable, Iterable, Optional

STYLES_DIR = Path(__file__).resolve().parent.parent / "data" / "styles"

# The counts the writer is given, in the order the section states them.
TARGET_KEYS = (
    "sentence_mean_words", "sentence_spread", "short_sentence_pct",
    "long_sentence_pct", "speech_word_pct", "semicolons_per_1k",
    "dashes_per_1k", "said_share", "contractions_per_1k", "seemed_felt_per_1k",
)

_TELL = ("something", "somehow", "seemed", "seem ", "felt ", "feel ",
         "realized", "realised", "suddenly", "as if", "as though")
_TAGS = r"\b(said|asked|replied|answered|cried|whispered|muttered|called|snapped|murmured)\b"
_CONTRACTION = re.compile(r"(n't|'ll|'re|'ve|'m)$")


def _paragraphs(text: str) -> list:
    return [p.strip() for p in re.split(r"\n\s*\n", text)
            if p.strip() and not p.strip().startswith("#")]


def _sentences(text: str) -> list:
    return [s for s in re.split(r'(?<=[.!?])["”’]?\s+(?=[A-Z"“‘])', text)
            if s.split()]


def _words(text: str) -> list:
    return re.findall(r"[A-Za-z']+", text)


def _common_words(text: str) -> list:
    """Lowercased words, leaving out names: a word that is only ever
    capitalised in this text is taken for a person or a place."""
    words = _words(text.replace("’", "'"))
    lower = {w for w in words if w[0].islower()}
    return [w.lower() for w in words if w[0].islower() or w.lower() in lower]


def measure(text: str) -> dict:
    """The profile counts for one text. Raises ValueError on an empty text."""
    text = text.replace("\r", "")
    words = _words(text.replace("’", "'"))
    if not words:
        raise ValueError("no words to measure")
    n = len(words)
    paras = _paragraphs(text)
    lengths = [len(_words(s)) for s in _sentences(" ".join(paras)) if _words(s)]
    quoted = sum(len(_words(q)) for q in re.findall(r'["“]([^"”]*)["”]', text))
    low = text.lower()

    def per_1k(count):
        return round(1000 * count / n, 1)

    tags = len(re.findall(_TAGS, low))
    return {
        "sentence_mean_words": round(statistics.mean(lengths), 1),
        "sentence_spread": round(statistics.pstdev(lengths), 1),
        "short_sentence_pct": round(100 * sum(1 for x in lengths if x <= 6) / len(lengths)),
        "long_sentence_pct": round(100 * sum(1 for x in lengths if x >= 30) / len(lengths)),
        "speech_word_pct": round(100 * quoted / n),
        "semicolons_per_1k": per_1k(text.count(";")),
        "dashes_per_1k": per_1k(text.count("—") + text.count("--")),
        "said_share": round(len(re.findall(r"\bsaid\b", low)) / max(1, tags), 2),
        "contractions_per_1k": per_1k(sum(1 for w in words if _CONTRACTION.search(w.lower()))),
        "seemed_felt_per_1k": per_1k(sum(low.count(x) for x in _TELL)),
        "ly_per_1k": per_1k(sum(1 for w in words if w.lower().endswith("ly") and len(w) > 4)),
        "paragraph_median_words": statistics.median(len(_words(p)) for p in paras),
        # Word choice (2026-11-12 word gauge): authors of the period reach for
        # long abstract words (indelicacy, injudicious) where Opus writes the
        # period with short concrete ones. Ferrier 38 per 1,000, Opus 13-26.
        "long_words_per_1k": _long_words_per_1k(text),
    }


def _long_words_per_1k(text: str) -> float:
    words = _common_words(text)
    return round(1000 * sum(1 for w in words if len(w) >= LONG_WORD) / max(1, len(words)), 1)


LONG_WORD = 10


def favourite_words(text: str, modern_zipf: Callable[[str], float],
                    count: int = 40, min_letters: int = 9, min_uses: int = 5) -> list:
    """The long words this text uses most often relative to modern English.

    ``modern_zipf(word)`` gives a word's modern frequency on wordfreq's scale
    (log10 of uses per billion words); the script passes
    ``wordfreq.zipf_frequency``, so this module stays stdlib only. Names and
    possessives are left out. From Ferrier's *Marriage* this gives
    solicitude, insupportable, remonstrance, approbation, obstinacy...
    """
    import math
    words = [w for w in _common_words(text) if "'" not in w]
    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    total = len(words)
    scored = [(math.log10(n / total * 1e9) - modern_zipf(w), w)
              for w, n in counts.items() if len(w) >= min_letters and n >= min_uses]
    return [w for _, w in sorted(scored, reverse=True)[:count]]


def book_chapters(text: str, leave_out: Iterable[str] = (),
                  drop_indented: bool = False) -> list:
    """A Project Gutenberg novel cut into cleaned chapters.

    Keeps what lies between the Gutenberg start and end markers, removes
    illustration captions and _italic_ marks, splits on CHAPTER headings and
    drops what comes before the first heading (title page, preface, contents)
    and any piece under 200 words. A chapter holding
    any phrase in ``leave_out`` is dropped: that is how a test passage is kept
    out of the profile it will be compared against. ``drop_indented`` removes
    indented paragraphs (epigraphs, in books that open chapters with them).
    """
    text = text.replace("\r", "")
    start = re.search(r"\*\*\* ?START OF[^\n]*\n", text)
    end = re.search(r"\*\*\* ?END OF", text)
    text = text[start.end() if start else 0:end.start() if end else len(text)]
    text = re.sub(r"\[Illustration[^\]]*\]", "", text, flags=re.S)
    parts = re.split(r"^\s*CHAPTER\s+[IVXLCl0-9]+\.?[^\n]*$", text, flags=re.M)
    if len(parts) > 1:
        parts = parts[1:]          # what comes before the first chapter is front matter
    chapters = []
    for part in parts:
        if len(part.split()) <= 200:
            continue
        if any(phrase in part for phrase in leave_out):
            continue
        paras = [p for p in re.split(r"\n\s*\n", part) if p.strip()]
        if drop_indented:
            paras = [p for p in paras if not p.startswith("    ")]
        part = "\n\n".join(" ".join(p.split()) for p in paras)
        chapters.append(re.sub(r"_([^_]+)_", r"\1", part))
    return chapters


def available_profiles() -> list:
    return sorted(p.stem for p in STYLES_DIR.glob("*.json"))


def load_profile(name: str) -> dict:
    """A shipped profile by name, or a path to a profile file.

    An unknown name raises, like a pinned name bank: a misspelled setting
    should stop the run, not quietly write without targets.
    """
    path = Path(name)
    if path.suffix != ".json":
        path = STYLES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown style profile {name!r}. "
                         f"Shipped profiles: {', '.join(available_profiles())}")
    profile = json.loads(path.read_text())
    missing = [k for k in TARGET_KEYS if k not in profile]
    if missing:
        raise ValueError(f"Style profile {name!r} lacks {', '.join(missing)}")
    return profile


def style_targets_section(profile: dict, words: int,
                          measured_from: str = "the period's own novels") -> str:
    """The targets as plain lines, turned into counts for a scene of ``words``."""
    def count(rate):
        return max(1, round(rate * words / 1000))

    if profile["contractions_per_1k"] < 0.5:
        contractions = ('No contractions anywhere, in speech or narration: '
                        '"do not", "cannot", "I am", "it is".')
    else:
        contractions = (f"Contractions only in speech, about "
                        f"{count(profile['contractions_per_1k'])} in the scene; "
                        "none in narration.")
    return f"""

**Style targets (measured from {measured_from}; hit these numbers):**
- Sentences average about {round(profile['sentence_mean_words'])} words, and their lengths vary a great deal: about {profile['short_sentence_pct']}% are 6 words or fewer and about {profile['long_sentence_pct']}% run to 30 words or more. Build the long ones from balanced clauses joined by commas and semicolons.
- Semicolons: about {count(profile['semicolons_per_1k'])} in this scene ({profile['semicolons_per_1k']} per 1,000 words), in narration and in speech.
- Dashes: about {count(profile['dashes_per_1k'])} in this scene, written as an em dash (—), where speech breaks off or turns.
- {contractions}
- Speech: about {profile['speech_word_pct']}% of the scene's words inside quotation marks.
- "said" for about {round(profile['said_share'] * 100)}% of speech tags; otherwise "replied", "cried", "answered" and the like.
- Avoid "seemed", "felt", "as if", "as though", "suddenly", "somehow": at most {count(profile['seemed_felt_per_1k'])} in the whole scene.{_word_choice_lines(profile, count)}"""


def _word_choice_lines(profile: dict, count) -> str:
    """The word-choice targets, for profiles measured with them (older
    profiles without them render exactly as before)."""
    lines = ""
    if profile.get("long_words_per_1k"):
        lines += (f"\n- Word choice: about {count(profile['long_words_per_1k'])} words of ten "
                  f"letters or more in this scene ({profile['long_words_per_1k']} per 1,000 "
                  "words). Most should be abstract words of judgement, feeling and manners, "
                  "not names of objects.")
    if profile.get("favourite_words"):
        lines += ("\n- Words of this kind the period favours, to reach for where they fit "
                  "(each at most once, and never strung together): "
                  + ", ".join(profile["favourite_words"]) + ".")
    return lines


def profile_from_config(config) -> Optional[dict]:
    """The profile ``generation.style_profile`` names, or None when unset."""
    name = config.get("generation.style_profile") if config is not None else None
    if not name or str(name).lower() in ("none", "off"):
        return None
    return load_profile(str(name))
