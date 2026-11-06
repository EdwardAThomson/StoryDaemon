"""Voices gauge: can the characters in a chapter be told apart by their speech?

Judge v2 scored every model chapter lowest on voices, with the same reason
each time: everyone speaks in one formal, procedural register and could not
be told apart without the tags. This gauge measures that without a model, so
a fix (a persona per character) can be judged against numbers, and so the
masters can set a ceiling against overdoing it.

Three steps, all plain Python:

  who speaks   each paragraph's quoted speech is given to a speaker from its
               tag ("Hugh said", "said Mr. Darcy"), from a paragraph that
               opens on a known speaker's name, or, in an exchange, by
               alternation inside an unbroken run of speech paragraphs (the speaker
               before last). A bare "he said" is not resolved. Anything else stays
               unattributed: precision over coverage, and the share attributed
               is reported.
  tell apart   for each pair of speakers, how far apart their pooled lines
               are, against the same lines dealt between the two at random.
               1.0 means no voice of their own; 1.5 means half as far apart
               again as chance. Two separate tests: HOW they speak (the
               common small words, contractions, punctuation) and WHAT they
               talk about (the remaining words).
  too much     dialect spellings (goin', 'em, ain't) and a speaker's own
               repeated phrases, per 1,000 words of speech, the "jarring"
               ceiling.

Pure stdlib, no state, no I/O. Gauge only: nothing reads it for decisions.

RESULT (2026-11-04), kept as a record: the tell-apart tests do NOT work.
Over ten Project Gutenberg novels against the m1/e1/e2 runs, neither per-line
style rates nor pooled small-word profiles against a shuffle baseline
separated the masters (1.05) from the model runs (0.78 to 1.23); per-feature
gaps mostly measure who asks and who explains, so Luna even scored more
distinct than Austen. Judge v2's voices score separates them (masters 4.5,
Opus 3.5, Luna 2.3) and is the gauge in use. The dialect counter does work
(masters 2.6, Opus 3.1, Luna 0 per 1,000 spoken words). Nothing imports this
module.
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

QUOTE_RE = re.compile(r'“([^”]*)”|"([^"]*)"')
OPEN_ONLY_RE = re.compile(r'“([^”]*)$')

SPEECH_VERBS = (
    "said|says|asked|asks|replied|replies|cried|answered|returned|rejoined|"
    "exclaimed|added|continued|repeated|observed|remarked|whispered|muttered|"
    "murmured|called|shouted|began|interrupted|demanded|inquired|enquired|"
    "insisted|suggested|admitted|agreed|protested|retorted|resumed|pursued|"
    "snapped|growled|sighed|told|went on|answered|urged|declared|explained|"
    "observed|ventured|faltered|stammered|groaned|roared|bawled|sang out|"
    "put in|broke in|called out|cried out|said quietly|said softly"
)
TITLE = r"(?:(?:Mr|Mrs|Miss|Ms|Dr|Captain|Capt|Sir|Lady|Lord|Colonel|Squire|Master|Mistress|Madame|Monsieur|Father|Mother|Aunt|Uncle)\.?\s+)"
NAME = rf"(?:{TITLE}?[A-Z][a-zé'’-]+(?:\s+[A-Z][a-zé'’-]+)?)"
WHO = rf"(?P<who>{NAME}|the\s+[a-z]+|I|he|she|He|She)"
VERB = rf"(?P<verb>{SPEECH_VERBS})"
Q = "\u0001"  # marker left where a quotation stood
TAG_AFTER = [re.compile(rf"{Q}[,!?.—–-]*\s*{WHO}\s+{VERB}\b"),
             re.compile(rf"{Q}[,!?.—–-]*\s*{VERB}\s+{WHO}\b")]
TAG_BEFORE = [re.compile(rf"\b{WHO}\s+{VERB}\b[^{Q}]{{0,60}}[,:]\s*{Q}")]
PRONOUNS = {"he", "she", "He", "She"}
NOT_NAMES = {"The", "But", "And", "Then", "When", "Yes", "No", "Oh", "Well",
             "It", "This", "That", "There", "What", "Why", "How", "If", "So",
             "Now", "Here", "His", "Her", "They", "We", "You", "Your", "My",
             "A", "An", "As", "At", "In", "On", "For", "With", "All", "One",
             "Not", "Nor", "Or", "Yet", "Still", "Just", "Only", "After",
             "Before", "Again", "Ah", "Aye", "Sir", "Madam", "God", "Heaven"}

FUNCTION_WORDS = (
    "the a an and but or of to in on at for with by from as that which it is "
    "was be have had not no i me my you your we he she they this there so if "
    "what all do will would shall should can could must very well oh now then "
    "just only too much quite indeed sir").split()
FUNCTION_SET = set(FUNCTION_WORDS)
HEDGES = re.compile(r"\b(perhaps|maybe|i think|i suppose|i dare say|i daresay|"
                    r"i believe|might|rather|somewhat|i fancy|i expect|"
                    r"it may be|i'm not sure|i am not sure)\b")
CONTRACTION = re.compile(r"\b\w+(?:n['’]t|['’](?:ll|ve|re|m|d))\b|\b(?:i['’]m|'tis|'twas)\b", re.I)
DIALECT = re.compile(r"\b\w{2,}in['’](?=\W|$)|['’](?:em|ere|ow|is|im)\b|\bain['’]t\b|"
                     r"\b(?:o['’]|th['’]|ol['’]|yer|ye|nowt|summat|innit|dunno|gonna|"
                     r"wanna|gotta|'cause|lemme|gimme)(?=\W|$)", re.I)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")
STOP = set(FUNCTION_WORDS) | set(
    "is are were been being am has having does did doing its it's his her him "
    "hers our ours us their them theirs these those who whom whose where when "
    "why how any some more most other such own same than up down out over "
    "off into about again here once both each few nor yes oh ah let get got "
    "go going come came one two say said know think see like make made".split())

MIN_LINE_WORDS = 4
MIN_SPEAKER_WORDS = 120
MAX_SPEAKERS = 4


@dataclass
class Turn:
    para: int
    speaker: str  # "" when unattributed
    text: str
    how: str = ""  # tag | name | alternation | pronoun | ""


@dataclass
class ChapterVoices:
    turns: list
    speech_words: int
    attributed_words: int
    speakers: dict  # speaker -> words
    how_score: float | None = None  # distance over chance, style
    what_score: float | None = None  # distance over chance, subject
    k: int = 0  # speakers in the tests
    profiles: dict = field(default_factory=dict)
    dialect_per_k: float = 0.0
    catchphrase_per_k: float = 0.0
    catchphrases: list = field(default_factory=list)

    def as_dict(self):
        return {
            "speech_words": self.speech_words,
            "attributed_share": round(self.attributed_words / self.speech_words, 3)
            if self.speech_words else None,
            "speakers": self.speakers,
            "k": self.k,
            "how_score": self.how_score,
            "what_score": self.what_score,
            "profiles": self.profiles,
            "dialect_per_1000": round(self.dialect_per_k, 2),
            "catchphrase_per_1000": round(self.catchphrase_per_k, 2),
            "catchphrases": self.catchphrases,
        }


# --- who speaks ----------------------------------------------------------------------

def paragraphs(prose):
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", prose) if p.strip()]


def _speech_and_narration(par):
    spans = [m.group(1) if m.group(1) is not None else m.group(2)
             for m in QUOTE_RE.finditer(par)]
    narration = QUOTE_RE.sub(Q, par)
    tail = OPEN_ONLY_RE.search(narration)  # a speech running on to the next paragraph
    if tail:
        spans.append(tail.group(1))
        narration = narration[:tail.start()] + Q
    return [s.strip() for s in spans if s.strip()], narration


def canonical(who, known):
    """Map a tag's subject onto one speaker key ("Mr. Darcy" and "Darcy" agree)."""
    w = re.sub(r"\s+", " ", who.strip())
    if w == "I":
        return "I"
    if w.lower().startswith("the "):
        return w.lower()
    bare = re.sub(rf"^{TITLE}", "", w).strip()
    last = bare.split()[-1] if bare else w
    first = bare.split()[0] if bare else w
    for k in known:
        kb = re.sub(rf"^{TITLE}", "", k).split()
        if kb and (kb[-1] == last or kb[0] == first):
            return k
    return w


def _find_tag(narration):
    for rx in TAG_AFTER + TAG_BEFORE:
        m = rx.search(narration)
        if m:
            who = m.group("who")
            first = who.split()[0]
            if who not in PRONOUNS and first in NOT_NAMES and not who.lower().startswith("the "):
                continue
            return who
    return None


def attribute(prose, roster=None):
    """[Turn] for every paragraph with speech. ``roster`` is an optional list of
    known names (first, last or full); masters chapters learn theirs from tags."""
    pars = paragraphs(prose)
    parsed = [_speech_and_narration(p) for p in pars]
    known = list(roster or [])
    # first pass: names that appear as explicit tag subjects
    for spans, narr in parsed:
        if spans:
            who = _find_tag(narr)
            if who and who not in PRONOUNS and who != "I" and not who.lower().startswith("the "):
                c = canonical(who, known)
                if c not in known:
                    known.append(c)
    name_rx = None
    if known:
        alts = sorted({re.escape(n) for k in known for n in
                       [k, re.sub(rf"^{TITLE}", "", k)] + re.sub(rf"^{TITLE}", "", k).split()
                       if len(n) > 2}, key=len, reverse=True)
        name_rx = re.compile(r"(?<![A-Za-z])(" + "|".join(alts) + r")(?![a-z])")

    turns, history = [], []  # history: (para index, speaker) of attributed turns
    for i, (spans, narr) in enumerate(parsed):
        if not spans:
            continue
        text = " ".join(spans)
        who, how = _find_tag(narr), ""
        speaker = ""
        if who and who not in PRONOUNS:
            speaker, how = canonical(who, known), "tag"
        elif name_rx is not None:
            head = narr.split(Q)[0]
            m = name_rx.search(head) if head.strip() else None
            if m and m.start() < 40:
                speaker, how = canonical(m.group(1), known), "name"
        # alternation only inside an unbroken run of speech paragraphs: any
        # narration paragraph between turns can hand the floor to anyone
        if (not speaker and len(history) >= 2 and history[-1][0] == i - 1
                and history[-2][0] == i - 2):
            a, b = history[-1][1], history[-2][1]
            if a and b and a != b:
                speaker, how = b, "alternation"
        turns.append(Turn(i, speaker, text, how))
        history.append((i, speaker))
    return turns


# --- tell apart ----------------------------------------------------------------------

def words(text):
    return [w.lower().replace("’", "'") for w in WORD_RE.findall(text)]


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if WORD_RE.search(s)]


def content_counts(text, drop):
    return Counter(w for w in words(text) if w not in STOP and w not in drop and len(w) > 2)


def how_bag(text):
    """HOW a line is said, as counts: the common small words, contractions,
    and the punctuation that carries tone (? ! ; — ...)."""
    ws = words(text)
    c = Counter(w for w in ws if w in FUNCTION_SET)
    c["<contraction>"] = len(CONTRACTION.findall(text))
    c["<other-word>"] = len(ws) - sum(c[w] for w in FUNCTION_SET if w in c)
    for mark, key in (("?", "<q>"), ("!", "<x>"), (";", "<semi>"), ("—", "<dash>"),
                      ("--", "<dash>"), ("...", "<ellipsis>"), ("…", "<ellipsis>"),
                      (",", "<comma>")):
        c[key] += text.count(mark)
    c["<sentence>"] = len(sentences(text)) or 1
    return c


def _hellinger(a, b):
    na, nb = sum(a.values()), sum(b.values())
    if not na or not nb:
        return 0.0
    bc = sum(math.sqrt((v / na) * (b.get(k, 0) / nb)) for k, v in a.items())
    return math.sqrt(max(0.0, 1 - bc))


def _pair_ratio(lines_a, lines_b, bag, rng, shuffles):
    """Distance between two speakers' pooled lines, over the mean distance when
    the same lines are dealt between them at random (1.0 = no voice of their own)."""
    def dist(xs, ys):
        pa, pb = Counter(), Counter()
        for x in xs:
            pa.update(x)
        for y in ys:
            pb.update(y)
        return _hellinger(pa, pb)
    obs = dist(lines_a, lines_b)
    pool = lines_a + lines_b
    null = []
    for _ in range(shuffles):
        rng.shuffle(pool)
        null.append(dist(pool[:len(lines_a)], pool[len(lines_a):]))
    base = sum(null) / len(null)
    return obs / base if base else None


def tell_apart(by_speaker, drop_names=(), shuffles=200, seed=7):
    """(how, what, k). For every pair of main speakers: how far apart their
    pooled lines are, divided by how far apart the same lines are when dealt
    between the two at random. 1.0 means the two have no voice of their own;
    1.5 means half as far apart again as chance. Averaged over pairs. The
    shuffle keeps each speaker's number of lines, so a short scene cannot
    score well by luck. ``how`` compares small words, contractions and
    punctuation; ``what`` compares the remaining words."""
    import random
    rng = random.Random(seed)
    drop = {w.lower() for n in drop_names for w in WORD_RE.findall(n)}
    lines = {s: [t for t in texts if len(words(t)) >= MIN_LINE_WORDS]
             for s, texts in by_speaker.items()}
    lines = {s: v for s, v in lines.items() if len(v) >= 3}
    if len(lines) < 2:
        return None, None, 0
    hows = {s: [how_bag(t) for t in v] for s, v in lines.items()}
    whats = {s: [content_counts(t, drop) for t in v] for s, v in lines.items()}
    spk = list(lines)
    hr, wr = [], []
    for i in range(len(spk)):
        for j in range(i + 1, len(spk)):
            a, b = spk[i], spk[j]
            hr.append(_pair_ratio(list(hows[a]), list(hows[b]), None, rng, shuffles))
            wr.append(_pair_ratio(list(whats[a]), list(whats[b]), None, rng, shuffles))
    hr = [x for x in hr if x is not None]
    wr = [x for x in wr if x is not None]
    return (round(sum(hr) / len(hr), 3) if hr else None,
            round(sum(wr) / len(wr), 3) if wr else None, len(spk))


def profile(texts):
    text = " ".join(texts)
    ws = words(text)
    n = max(len(ws), 1)
    sents = sentences(text) or [text]
    return {
        "words": len(ws),
        "words_per_sentence": round(n / len(sents), 1),
        "contractions_per_100": round(100 * len(CONTRACTION.findall(text)) / n, 1),
        "questions_share": round(sum(s.rstrip().endswith("?") for s in sents) / len(sents), 2),
        "exclaims_share": round(sum(s.rstrip().endswith("!") for s in sents) / len(sents), 2),
        "hedges_per_100": round(100 * len(HEDGES.findall(text.lower().replace("’", "'"))) / n, 1),
    }


# --- too much ------------------------------------------------------------------------

def catchphrases(by_speaker, min_repeats=3):
    """A speaker's own 3-word runs said at least ``min_repeats`` times in the
    chapter and never by anyone else."""
    grams = {}
    for s, texts in by_speaker.items():
        c = Counter()
        for t in texts:
            ws = words(t)
            c.update(" ".join(ws[i:i + 3]) for i in range(len(ws) - 2))
        grams[s] = c
    out = []
    for s, c in grams.items():
        for g, n in c.items():
            if n >= min_repeats and not any(grams[o].get(g) for o in grams if o != s):
                if not all(w in STOP for w in g.split()):
                    out.append((s, g, n))
    return out


def analyse(prose, roster=None):
    turns = attribute(prose, roster)
    total = sum(len(words(t.text)) for t in turns)
    by_speaker = defaultdict(list)
    for t in turns:
        if t.speaker:
            by_speaker[t.speaker].append(t.text)
    attributed = sum(len(words(x)) for v in by_speaker.values() for x in v)
    sizes = {s: sum(len(words(x)) for x in v) for s, v in by_speaker.items()}
    top = sorted((s for s in by_speaker if sizes[s] >= MIN_SPEAKER_WORDS), key=lambda s: -sizes[s])
    main = {s: by_speaker[s] for s in top[:MAX_SPEAKERS]}
    names = list(roster or []) + list(by_speaker)
    how, what, k = tell_apart(main, names) if len(main) >= 2 else (None, None, 0)
    dialect = sum(len(DIALECT.findall(t.text)) for t in turns)
    cps = catchphrases(main)
    return ChapterVoices(
        turns=turns, speech_words=total, attributed_words=attributed,
        speakers=dict(sorted(sizes.items(), key=lambda kv: -kv[1])),
        how_score=how, what_score=what, k=k,
        profiles={s: profile(v) for s, v in main.items()},
        dialect_per_k=1000 * dialect / total if total else 0.0,
        catchphrase_per_k=1000 * sum(n for _, _, n in cps) / total if total else 0.0,
        catchphrases=[f"{s}: {g} (x{n})" for s, g, n in cps],
    )
