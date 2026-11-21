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

from novel_agent.agent.line_faults import measure as line_fault_counts
from novel_agent.agent.word_origin import origin_shares

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
        # Word origin (2026-11-14): share of words from French or Latin, counted
        # over every word as the Legendarium table counts it (Tolkien 8%,
        # Ferrier about 20%), and over content words only.
        **{k: v for k, v in origin_shares(text).items()
           if k in ("latinate_pct", "latinate_content_pct")},
        # Feelings named outright in narration (she was angry, his fear), per
        # 1,000 words of narration (2026-11-19, from line_faults). Modern advice
        # calls it a fault; older novels do it freely, so each profile carries
        # its own figure and range rather than a rule that it is on or off.
        "named_feelings_per_1k": line_fault_counts(text)["named_feelings_per_1k"],
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


CHAPTER_HEADING = r"^\s*CHAPTER\s+[IVXLCl0-9]+\.?[^\n]*$"


def book_chapters(text: str, leave_out: Iterable[str] = (),
                  drop_indented: bool = False, heading: str = CHAPTER_HEADING) -> list:
    """A Project Gutenberg novel cut into cleaned chapters.

    Keeps what lies between the Gutenberg start and end markers, removes
    illustration captions and _italic_ marks, splits on CHAPTER headings (or
    the ``heading`` pattern, a multiline regex for books that head chapters
    another way, such as "I: THE CASTLE OF LORD JUSS") and
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
    parts = re.split(heading, text, flags=re.M)
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
                          measured_from: str = "the period's own novels",
                          word_list: bool = False, sentence_counts: bool = False,
                          word_origin: bool = False) -> str:
    """The targets as plain lines, turned into counts for a scene of ``words``.

    A profile's ``favourite_words`` stay out of the prompt unless
    ``word_list`` is set (only the blind test's ``dsl_words`` arm does, to
    reproduce its 2026-11-12 run). Sent to the writer, the list was overused
    (12-14 list words in a scene where Ferrier uses 5) and the long-word rate
    alone did the work with no overuse (2026-11-13). The list stays in the
    profile for reference.

    ``sentence_counts`` and ``word_origin`` add two lines under test
    (2026-11-19, off by default): the after-writing check found every styled
    Ferrier scene still under her range on sentence length and spread and on
    the French/Latin share, with the percentages above already in the prompt."""
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
- Avoid "seemed", "felt", "as if", "as though", "suddenly", "somehow": at most {count(profile['seemed_felt_per_1k'])} in the whole scene.{_word_choice_lines(profile, count, word_list)}{_sentence_count_line(profile, words) if sentence_counts else ""}{_word_origin_line(profile) if word_origin else ""}"""


def _sentence_count_line(profile: dict, words: int) -> str:
    """The sentence targets as counts for this scene: told only the mean and
    the shares, Opus still wrote Ferrier scenes at 14-20 words a sentence
    against her 25 (2026-11-19 style check)."""
    sentences = max(1, round(words / profile["sentence_mean_words"]))
    short = round(sentences * profile["short_sentence_pct"] / 100)
    long = round(sentences * profile["long_sentence_pct"] / 100)
    return (f"\n- Sentence count: a scene of {words} words at this length is only about "
            f"{sentences} sentences in all. At most {short} of them 6 words or fewer; about "
            f"{long} of them 30 words or more. This holds in speech too: a speaker's turn "
            "is often one long sentence of several clauses, not several short ones.")


def _word_origin_line(profile: dict) -> str:
    """The French/Latin share, for profiles measured with it."""
    pct = profile.get("latinate_pct")
    if not pct:
        return ""
    return (f"\n- Word origin: about {round(pct)}% of all words (one in "
            f"{round(100 / pct)}) come from French or Latin; plain modern prose has about "
            "13%. Where a plain Old English word and a French or Latin one would both "
            "serve, take the French or Latin one more often than modern prose would "
            "(certain for sure, enquire for ask, assist for help), above all in narration "
            "and in the speech of educated characters.")


def _word_choice_lines(profile: dict, count, word_list: bool = False) -> str:
    """The word-choice targets, for profiles measured with them (older
    profiles without them render exactly as before)."""
    lines = ""
    if profile.get("long_words_per_1k"):
        lines += (f"\n- Word choice: about {count(profile['long_words_per_1k'])} words of ten "
                  f"letters or more in this scene ({profile['long_words_per_1k']} per 1,000 "
                  "words). Most should be abstract words of judgement, feeling and manners, "
                  "not names of objects.")
    if word_list and profile.get("favourite_words"):
        lines += ("\n- Words of this kind the period favours, to reach for where they fit "
                  "(each at most once, and never strung together): "
                  + ", ".join(profile["favourite_words"]) + ".")
    return lines


def chapter_ranges(chapters: list, low: int = 10, high: int = 90,
                   min_words: int = 800) -> dict:
    """The p10-p90 range of each numeric count across a book's chapters:
    what a scene can vary within and still read like the book. Chapters under
    ``min_words`` are skipped (too short for stable counts)."""
    per = [measure(c) for c in chapters if len(c.split()) >= min_words]
    if len(per) < 3:
        return {}
    out = {}
    for key, value in per[0].items():
        if not isinstance(value, (int, float)):
            continue
        cuts = statistics.quantiles([m[key] for m in per], n=100, method="inclusive")
        out[key] = [round(cuts[low - 1], 1), round(cuts[high - 1], 1)]
    return out


def profile_check(text: str, profile: dict, min_words: int = 800) -> dict:
    """How a written scene sits against a profile's chapter ranges. Gauge only.

    Each count the profile has a range for is measured on the scene and marked
    ``above`` or ``below`` when it falls outside the book's p10-p90 chapter
    range. A range is how far the author's own chapters vary, so one count
    outside it is a hint, not a fault; the record is for reading across a run
    which counts the writer misses again and again. A scene under
    ``min_words`` (the shortest chapter the ranges were taken from) is still
    checked but marked ``short``, since its counts are less stable.
    """
    ranges = profile.get("ranges") or {}
    counts = measure(text)
    outside = {}
    for key, (low, high) in ranges.items():
        value = counts.get(key)
        if not isinstance(value, (int, float)):
            continue
        if value < low:
            outside[key] = {"value": value, "range": [low, high], "side": "below"}
        elif value > high:
            outside[key] = {"value": value, "range": [low, high], "side": "above"}
    words = len(_words(text))
    return {
        "profile": profile.get("name"),
        "words": words,
        "short": words < min_words,
        "checked": sum(1 for k in ranges if isinstance(counts.get(k), (int, float))),
        "outside": outside,
        "counts": counts,
    }


def profile_from_config(config) -> Optional[dict]:
    """The profile ``generation.style_profile`` names, or None when unset."""
    name = config.get("generation.style_profile") if config is not None else None
    if not name or str(name).lower() in ("none", "off"):
        return None
    return load_profile(str(name))
