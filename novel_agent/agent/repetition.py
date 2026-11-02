"""Repetition gauge: where a chapter says again what it has already said.

Judge v2 marked every Luna chapter down for economy, in both the single-shot
and the sectioned arms, and its reasons were about meaning repeated in new
words: narration restating the line of dialogue just spoken, a caveat voiced
again two paragraphs on, a closing paragraph summarising the one before. A
near-identical-sentence count saw almost none of it (0.1% to 1% of
sentences), so a gauge that can see what the judge sees needs more than one
layer:

  literal   near-identical sentences and shared word runs (difflib and
            6-word n-grams), exact and cheap;
  meaning   each sentence embedded and compared with every sentence before
            it in the chapter; a pair above a threshold is a candidate. The
            threshold is set above the level the masters chapters show,
            since good prose echoes itself on purpose;
  echo      the subset of meaning matches where narration restates speech
            (a quoted sentence followed by an unquoted one that means the
            same), which was the judge's most frequent complaint.

This module is pure logic over an injected embedding function
(``embed(list[str]) -> list[list[float]]``); the caller supplies ChromaDB's
default MiniLM function or anything else. Gauge only: nothing reads it for
decisions yet (the project's instrument-first rule).
"""

import difflib
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Embed = Callable[[Sequence[str]], Sequence[Sequence[float]]]

_SENT_SPLIT = re.compile(r'(?<=[.!?])["”’]?\s+(?=["“‘A-Z])')
_WORD = re.compile(r"[a-z']+")


@dataclass
class Sentence:
    index: int
    paragraph: int
    text: str
    speech: bool


@dataclass
class Match:
    kind: str              # literal | meaning | echo
    later: int             # sentence index of the repeat
    earlier: int           # sentence index it repeats
    score: float
    later_text: str
    earlier_text: str
    distance: int          # sentences between them


@dataclass
class Report:
    sentences: int
    literal: List[Match] = field(default_factory=list)
    meaning: List[Match] = field(default_factory=list)
    echo: List[Match] = field(default_factory=list)

    def rate(self, kind: str) -> float:
        n = len(getattr(self, kind))
        return n / self.sentences if self.sentences else 0.0

    def as_dict(self) -> Dict:
        return {
            "sentences": self.sentences,
            "literal": len(self.literal), "meaning": len(self.meaning),
            "echo": len(self.echo),
            "literal_rate": round(self.rate("literal"), 4),
            "meaning_rate": round(self.rate("meaning"), 4),
            "echo_rate": round(self.rate("echo"), 4),
        }


def paragraphs(prose: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", prose or "") if p.strip()]


def sentences(prose: str, min_words: int = 6) -> List[Sentence]:
    """Sentences with their paragraph index and whether they are speech.

    A sentence is speech when it sits inside quotation marks; the
    paragraph's quote count up to that point decides it, so a dialogue tag
    after the closing quote is narration.
    """
    out: List[Sentence] = []
    for pi, para in enumerate(paragraphs(prose)):
        flat = " ".join(para.split())
        for raw in _SENT_SPLIT.split(flat):
            s = raw.strip()
            if len(_WORD.findall(s.lower())) < min_words:
                continue
            quoted = s.startswith(("“", '"')) or (
                s.count("“") + s.count('"') > 0 and
                len(re.sub(r'[“"].*?[”"]', "", s).split()) < len(s.split()) / 2)
            out.append(Sentence(len(out), pi, s, quoted))
    return out


def _ngrams(text: str, n: int) -> set:
    w = _WORD.findall(text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def literal_matches(sents: List[Sentence], ratio: float = 0.75, run: int = 6) -> List[Match]:
    """Near-identical sentences (difflib ratio) or a shared run of words."""
    out: List[Match] = []
    grams = [_ngrams(s.text, run) for s in sents]
    lows = [s.text.lower() for s in sents]
    for j, s in enumerate(sents):
        best: Optional[Tuple[float, int]] = None
        sm = difflib.SequenceMatcher(None, "", lows[j])
        for i in range(j):
            shared = bool(grams[i] and grams[j] & grams[i])
            sm.set_seq1(lows[i])
            # difflib's full ratio is slow; its two cheap upper bounds rule
            # most pairs out first (a shared word run still counts).
            if not shared and (sm.real_quick_ratio() < ratio or sm.quick_ratio() < ratio):
                continue
            r = sm.ratio()
            if shared:
                r = max(r, ratio)      # a shared six-word run counts
            if r >= ratio and (best is None or r > best[0]):
                best = (r, i)
        if best:
            out.append(Match("literal", j, best[1], round(best[0], 3), s.text,
                             sents[best[1]].text, j - best[1]))
    return out


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def meaning_matches(sents: List[Sentence], embed: Embed, threshold: float,
                    min_distance: int = 1) -> Tuple[List[Match], List[float]]:
    """Sentences whose meaning repeats an earlier sentence's.

    Returns the matches above ``threshold`` and, for calibration, every
    sentence's best similarity to anything before it.
    """
    if not sents:
        return [], []
    vecs = [list(v) for v in embed([s.text for s in sents])]
    norms = [math.sqrt(sum(x * x for x in v)) or 1.0 for v in vecs]
    unit = [[x / n for x in v] for v, n in zip(vecs, norms)]
    out: List[Match] = []
    best_all: List[float] = []
    for j, s in enumerate(sents):
        best, bi = -1.0, -1
        uj = unit[j]
        for i in range(0, j - min_distance + 1):
            ui = unit[i]
            c = float(sum(a * b for a, b in zip(ui, uj)))
            if c > best:
                best, bi = c, i
        best_all.append(best if bi >= 0 else 0.0)
        if bi >= 0 and best >= threshold:
            out.append(Match("meaning", j, bi, round(best, 3), s.text,
                             sents[bi].text, j - bi))
    return out, best_all


def echo_matches(sents: List[Sentence], meaning: List[Match]) -> List[Match]:
    """Meaning matches where narration restates speech (or speech restates
    narration) within a few sentences: the judge's most frequent complaint."""
    out = []
    for m in meaning:
        a, b = sents[m.earlier], sents[m.later]
        if a.speech != b.speech and m.distance <= 6:
            out.append(Match("echo", m.later, m.earlier, m.score, m.later_text,
                             m.earlier_text, m.distance))
    return out


def analyse(prose: str, embed: Optional[Embed], threshold: float = 0.8,
            literal_ratio: float = 0.75) -> Tuple[Report, List[float]]:
    """The gauge for one chapter. ``embed`` None skips the meaning layer."""
    sents = sentences(prose)
    rep = Report(sentences=len(sents))
    rep.literal = literal_matches(sents, ratio=literal_ratio)
    best_all: List[float] = []
    if embed is not None and sents:
        rep.meaning, best_all = meaning_matches(sents, embed, threshold)
        rep.echo = echo_matches(sents, rep.meaning)
    return rep, best_all
