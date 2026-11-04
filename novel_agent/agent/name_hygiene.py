"""Keep every name in a novel one the generator minted.

StoryDaemon mints names in Python and lets the model select them, and the
character records held to that in every validation run. The leak was in the
text that rides alongside the records (diagnosed 2026-11-02 on eleven runs of
one premise):

- the protagonist's ``description`` was the archetype copied verbatim, so a
  foundation that wrote "Elena Marsh, a determined naturalist" into the
  archetype field gave the minted Rowland Bosworth a record that called him
  Elena Marsh in every writer prompt;
- the premise goes verbatim to the planner, which wrote ``character.generate``
  descriptions such as "Yusuf is an experienced quartermaster", so the minted
  Richard Huntington was called Yusuf in his own record and 128 times in the
  prose.

Nothing here invents a name or parses one out to use it. The functions find
name-shaped text so a caller can drop it from a description, say so at
project creation, or count it in the prose as a gauge. Pure logic: no I/O, no
LLM, no state; every caller must guard it so a hygiene failure never costs a
scene.
"""

import re
from typing import Iterable, List, Set, Tuple

TITLES = {
    'Mr', 'Mrs', 'Ms', 'Miss', 'Dr', 'Doctor', 'Professor', 'Prof',
    'Captain', 'Lieutenant', 'Sergeant', 'Major', 'Colonel', 'General',
    'Lord', 'Lady', 'Sir', 'Dame', 'Agent', 'Detective', 'Officer',
    'Commander', 'Admiral', 'Father', 'Brother', 'Sister', 'Master',
}

# Capitalised words that are not names. Sentence starters are handled by
# position, not by this list, so it only needs the words that are capitalised
# wherever they fall.
NOT_NAMES = {
    'I', 'The', 'A', 'An', 'And', 'But', 'Or', 'So', 'Yet', 'For', 'Nor',
    'Then', 'When', 'While', 'After', 'Before', 'If', 'Not', 'No', 'Yes',
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    'January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December',
    'Earth', 'Mars', 'Moon', 'Sun', 'God', 'Gods', 'Heaven', 'Hell',
    'North', 'South', 'East', 'West', 'English', 'French', 'Spanish', 'Latin',
    'Admiralty', 'Navy', 'Army', 'Crown', 'Church', 'Parliament',
    'He', 'She', 'It', 'They', 'We', 'You', 'Who', 'Whoever', 'Whatever',
    'Whom', 'Someone', 'Something', 'Nobody', 'Nothing', 'Everyone', 'Anyone',
    'There', 'That', 'This', 'These', 'Those', 'Still', 'Instead', 'Outside',
    'Inside', 'Nearly', 'Ahead', 'Behind', 'Below', 'Above', 'Once', 'Now',
    'Here', 'Only', 'Even', 'Perhaps', 'One', 'Two', 'Three', 'Four', 'Five',
    'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
    'Fourteen', 'Fifteen', 'Twenty', 'Thirty', 'Hundred', 'Thousand',
}

_WORD = r"[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?"
_TITLE_RE = re.compile(r"\b(" + "|".join(sorted(TITLES)) + r")\.?\s+(" + _WORD + r"(?:\s+" + _WORD + r")?)")
_APPOSITIVE_RE = re.compile(r"\b(" + _WORD + r"(?:\s+" + _WORD + r")?),\s+(?:a|an|the|his|her|their|its|our|my)\s+[a-z]")
_RELATIVE_RE = re.compile(r"\b(" + _WORD + r"(?:\s+" + _WORD + r")?),?\s+(?:who|whom|whose)\b")
_SUBJECT_RE = re.compile(r"(?:^|[.;:!?]\s+|\n\s*)(" + _WORD + r"(?:\s+" + _WORD + r")?)\s+(?:is|was|has|had|who|whose)\b")
_ATTRIBUTION_RE = re.compile(r"\b(?:said|asked|replied|answered|shouted|whispered|muttered|called|told)\s+(" + _WORD + r")\b")
_FULL_NAME_RE = re.compile(r"\b(" + _WORD + r"\s+" + _WORD + r")\b")
_POSSESSIVE_RE = re.compile(r"\b(" + _WORD + r")'s\b")
_TOKEN_RE = re.compile(r"\b(" + _WORD + r")\b")
_SENTENCE_START_RE = re.compile(r"(?:^|[.;:!?…]\s*|\n\s*|[\"“”‘’'—–-]\s*)(" + _WORD + r")\b")
PLACE_WORDS = {
    'Keep', 'Reach', 'Abbey', 'Bay', 'Island', 'Islands', 'Point', 'Head', 'Cove',
    'Harbour', 'Harbor', 'Hall', 'House', 'Street', 'Road', 'Bridge', 'Tower',
    'Station', 'Deep', 'Sound', 'Strait', 'Cape', 'Rock', 'Rocks', 'Shoal',
    'Shoals', 'River', 'Lake', 'Sea', 'Ocean', 'Mount', 'Hill', 'Hills', 'Valley',
    'Forest', 'Wood', 'Woods', 'Castle', 'Fort', 'Port', 'City', 'Town', 'Expedition',
    'Company', 'Survey', 'Office', 'Society', 'Institute', 'Ship', 'Brig',
}


def _clean(candidate: str) -> str:
    words = [w for w in candidate.split() if w]
    while words and words[0] in TITLES:
        words = words[1:]
    if not words or any(w in NOT_NAMES for w in words):
        return ""
    if len(words) > 1 and words[-1] in PLACE_WORDS:
        return ""
    return " ".join(words)


def candidate_names(text: str) -> List[str]:
    """Name-shaped spans in ``text``: the person-shaped patterns a premise or a
    description uses to introduce someone. Sorted, without titles."""
    text = text or ""
    lowered = set(re.findall(r"\b[a-z]+\b", text))
    found: Set[str] = set()
    for rx in (_TITLE_RE, _ATTRIBUTION_RE, _POSSESSIVE_RE, _FULL_NAME_RE):
        for m in rx.finditer(text):
            c = _clean(m.group(m.lastindex))
            if c:
                found.add(c)
    for rx in (_APPOSITIVE_RE, _SUBJECT_RE, _RELATIVE_RE):
        for m in rx.finditer(text):
            c = _clean(m.group(1))
            if c:
                found.add(c)
    # "the Alcyone", "the Meridian's charts": a capitalised word after "the"
    # is a ship, a house or an expedition, not a person.
    found = {c for c in found
             if not re.search(r"\bthe\s+[*_]?" + re.escape(c) + r"\b", text)}
    # A word the same text also uses in lower case is a common word that
    # happened to start a sentence ("Salt crusted the rail"), not a name.
    return sorted(c for c in found if not any(w.lower() in lowered for w in c.split()))


def frequent_names(text: str, min_count: int = 3) -> List[str]:
    """Single capitalised words used ``min_count`` times or more away from a
    sentence start and never in lower case. This is how a premise name shows
    up in prose: "Yusuf" 128 times, with no title and no attribution to catch."""
    text = text or ""
    lowered = set(re.findall(r"\b[a-z]+\b", text))
    starts = {}
    for m in _SENTENCE_START_RE.finditer(text):
        starts[m.group(1)] = starts.get(m.group(1), 0) + 1
    counts = {}
    for m in _TOKEN_RE.finditer(text):
        w = m.group(1)
        if w in NOT_NAMES or w in TITLES or w.lower() in lowered:
            continue
        counts[w] = counts.get(w, 0) + 1
    out = []
    for w, n in counts.items():
        # A word only ever seen opening a sentence still counts once it
        # recurs enough: a scene in which 12 of 13 "Yusuf"s open a paragraph
        # is the ordinary shape of a named character acting.
        mid = n - starts.get(w, 0)
        if n >= min_count and (mid >= 1 or n >= 2 * min_count):
            out.append(w)
    return sorted(out)


def world_words(text: str) -> Set[str]:
    """Capitalised words in a foundation that are not person-shaped: the
    ship, the lost expedition, the sea. They belong to the author and are
    excluded from the prose gauge, which is after people only."""
    text = text or ""
    people = set(w for c in candidate_names(text) for w in c.split())
    return set(w for w in re.findall(_WORD, text) if w not in people and w not in NOT_NAMES)


def known_name_parts(known: Iterable[str]) -> Set[str]:
    """Every whole name and every word of it, lower-cased, so a candidate
    matches by first name, family name or both."""
    parts: Set[str] = set()
    for name in known or ():
        name = (name or "").strip()
        if not name:
            continue
        parts.add(name.lower())
        for w in name.split():
            parts.add(w.lower())
    return parts


def foreign_names(text: str, known: Iterable[str], frequent_min: int = 0,
                  ignore: Iterable[str] = ()) -> List[str]:
    """Names in ``text`` that are not the generator's. A candidate is known if
    it, or any word of it, is a known name or a word of one. ``frequent_min``
    above zero also admits the bare repeated words ``frequent_names`` finds;
    ``ignore`` drops candidates made only of the given words (the foundation's
    world nouns)."""
    parts = known_name_parts(known)
    skip = set(ignore or ())
    candidates = set(candidate_names(text))
    if frequent_min > 0:
        candidates.update(frequent_names(text, frequent_min))
    out = []
    for c in candidates:
        words = c.split()
        if c.lower() in parts or any(w.lower() in parts for w in words):
            continue
        if skip and all(w in skip for w in words):
            continue
        out.append(c)
    return sorted(out)


def count_mentions(text: str, names: Iterable[str]) -> int:
    """How many times any of ``names`` (whole or by word) occurs in ``text``."""
    text = text or ""
    total = 0
    seen: Set[str] = set()
    for name in names or ():
        for w in [name] + (name.split() if " " in name else []):
            if w and w not in seen:
                seen.add(w)
                total += len(re.findall(r"\b" + re.escape(w) + r"\b", text))
    return total


def prose_gauge(text: str, roster: Iterable[str], foundation: dict) -> dict:
    """The per-scene names gauge (tick step 8.6, instrument only): which names
    the prose uses that the generator never minted, split into the ones that
    came in through the foundation text and the rest. ``foundation`` is the
    state's story_foundation dict (premise, protagonist_archetype, setting)."""
    foundation = foundation or {}
    f_text = " ".join(str(foundation.get(k) or "") for k in ("premise", "protagonist_archetype", "setting"))
    given = (foundation.get("protagonist_name") or "").strip()
    known = list(roster or ()) + ([given] if given else [])
    from_foundation = foreign_names(f_text, known)
    world = world_words(f_text)
    in_prose = foreign_names(text, known, frequent_min=3, ignore=world)
    leaked = [n for n in in_prose if any(
        w.lower() in known_name_parts(from_foundation) for w in n.split())]
    other = [n for n in in_prose if n not in leaked]
    return {
        "unregistered_names": in_prose,
        "foundation_names_in_prose": leaked,
        "foundation_name_mentions": count_mentions(text, leaked),
        "other_unregistered_names": other,
    }


def name_shaped_head(text: str) -> str:
    """The text before the first comma when it reads like a name (one to four
    capitalised words, titles allowed), else ''. The protagonist warning's
    test, kept in one place."""
    head = (text or "").split(",")[0].strip()
    words = head.split()
    if 1 <= len(words) <= 4 and all(w[:1].isupper() for w in words if w):
        return head
    return ""


def strip_name_head(text: str) -> Tuple[str, str]:
    """Drop a name-shaped head from an archetype so the record describes a
    role, not a second name. "Elena Marsh, a determined naturalist searching
    for her brother" becomes ("A determined naturalist searching for her
    brother", "Elena Marsh"). Text with no such head is returned unchanged
    with an empty head; a head with nothing after it is also left alone,
    since an empty description helps nobody."""
    text = (text or "").strip()
    head = name_shaped_head(text)
    if not head or "," not in text:
        return text, ""
    rest = text.split(",", 1)[1].strip()
    if not rest:
        return text, ""
    return rest[0].upper() + rest[1:], head


def clean_description(description: str, minted_first: str, minted_family: str,
                      known: Iterable[str]) -> Tuple[str, List[str]]:
    """Hold an LLM-authored character description to the roster.

    The one deterministic rewrite is the diagnosed failure: a description whose
    subject is a name the generator never minted ("Yusuf is an experienced
    quartermaster", "Yusuf, the quartermaster, has sailed...") is about the
    character being created, so that name becomes the minted one throughout.
    Any other foreign name is reported, not touched: "Elena's brother" may
    point at someone real under a premise name, and guessing would be worse
    than saying so. Returns (description, foreign names still present)."""
    text = (description or "").strip()
    minted = " ".join(w for w in (minted_first, minted_family) if w).strip()
    roster = set(known or ())
    if minted:
        roster.add(minted)
    foreign = foreign_names(text, roster)
    if not text or not minted_first:
        return text, foreign
    m = _SUBJECT_RE.match(text) or _APPOSITIVE_RE.match(text)
    if m and m.start(1) == 0:
        subject = _clean(m.group(1))
        if subject and subject in foreign:
            text = re.sub(r"\b" + re.escape(subject) + r"(?=\b|'s)", minted_first, text)
            for w in subject.split():
                text = re.sub(r"\b" + re.escape(w) + r"(?=\b|'s)", minted_first, text)
            foreign = foreign_names(text, roster)
    return text, foreign


_FEMALE = re.compile(r"\b(she|her|hers|herself)\b", re.I)
_MALE = re.compile(r"\b(he|him|his|himself)\b", re.I)


def gender_from_text(text: str) -> str:
    """"female" or "male" when the text's pronouns say so unambiguously, else
    "". Used only where the author's or planner's own text already states a
    gender for the person being minted, so the minted name agrees with it."""
    text = text or ""
    f, m = len(_FEMALE.findall(text)), len(_MALE.findall(text))
    if f and not m:
        return "female"
    if m and not f:
        return "male"
    if f >= 2 * m and f >= 2:
        return "female"
    if m >= 2 * f and m >= 2:
        return "male"
    return ""


def replace_name(text: str, old: str, first: str, family: str = "") -> str:
    """Put a minted name where an unminted one stood: the whole old name
    becomes the minted full name, any lone word of it the minted first name."""
    if not text or not old or not first:
        return text
    full = " ".join(w for w in (first, family) if w)
    out = re.sub(r"\b" + re.escape(old) + r"\b", full if " " in old else first, text)
    if " " in old:
        for w in old.split():
            out = re.sub(r"\b" + re.escape(w) + r"\b", first, out)
    return out


PLAN_TEXT_FIELDS = (
    "scene_intention", "key_change", "progress_milestone", "progress_step",
    "palette_shift", "transition_path", "dialogue_targets", "rationale",
)


def unminted_people_in_plan(plan: dict, known: Iterable[str],
                            ignore: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """People the plan's own text names who have no record: [(name, the
    sentence that introduces them)]. Person-shaped patterns only (never a
    bare repeated word), so a ship or a place in the intention is not minted
    as a person. ``ignore`` holds world nouns and existing location and
    faction names."""
    plan = plan or {}
    skip = set(ignore or ())
    parts = known_name_parts(known)
    found: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    for key in PLAN_TEXT_FIELDS:
        text = plan.get(key)
        if not isinstance(text, str) or not text:
            continue
        for name in candidate_names(text):
            words = name.split()
            if name in seen or name.lower() in parts or any(w.lower() in parts for w in words):
                continue
            if all(w in skip for w in words) or name in skip:
                continue
            seen.add(name)
            sentence = next((s_ for s_ in re.split(r"(?<=[.;!?])\s+", text) if name in s_), text)
            found.append((name, sentence.strip()))
    return found


GENDERS = ("male", "female")


def require_gender(gender, who: str) -> str:
    """The gender as recorded, or a hard failure.

    Gender is a fact recorded with a minted name. It is never guessed, never
    defaulted and never drawn at random (Ed, 2026-11-04: "absolutely no coin
    flipping; there must be a hard crash"). Anything other than an explicit
    "male" or "female" raises.
    """
    value = (gender or "").strip().lower() if isinstance(gender, str) else ""
    if value not in GENDERS:
        raise ValueError(
            f"No gender for {who}: got {gender!r}. Gender is recorded with the "
            f"minted name and must be given explicitly as 'male' or 'female'; "
            f"it is never guessed or drawn at random.")
    return value


def require_consistent(text: str, gender: str, who: str, field: str) -> None:
    """Raise when text written about a person states the other gender.

    A record that says male beside a description that says "her" is the
    Hugh-called-"she" fault (2026-11-03). Text with no pronouns, or mixed
    pronouns about several people, passes; a clear contradiction does not.
    """
    stated = gender_from_text(text)
    if stated and stated != gender:
        raise ValueError(
            f"{who} is recorded as {gender}, but the {field} says {stated} "
            f"({text[:120]!r}). Fix the {field} or the gender; the two must agree.")
