"""Import a worldgen languages file alongside a world.

The sibling ``world-building`` generator can write every people's constructed
language as JSON (``worldgen/languages@0.1``): one entry per realm or faction
(keyed by the world file's own ids, ``R0``/``F1``) plus any unaffiliated
tongue such as ``elder``, each with a full lexicon, grammar, script and a set
of meaningful place and person names. ``map_languages`` turns that into what a
novel can use without an LLM:

- a compact *notes* block per people (language name, family and relatives,
  word order in one phrase, a dozen everyday words) that lands under
  ``state["world"]["languages"]`` and from there in the writer prompt;
- one ``Lore`` item per language, through the same path ``world_import``
  uses for world lore, so the planner finds it by search like any fact;
- a project-local name bank per people, written to ``memory/languages.json``
  and read by ``NameGenerator`` so ``name.generate`` can draw a realm's own
  names for a character of that realm.

It is pure and deterministic given the two files: no LLM calls, no I/O
beyond ``load_languages``, and ids come from ``MemoryManager`` at persist
time, exactly as ``world_import.persist_world`` does it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import logging

from .world_import import (
    REGION_SCHEMA,
    SECTOR_SCHEMA,
    WORLDGEN_TAG,
    _cap,
    _index,
    _join,
    _lore,
    schema_of,
)

logger = logging.getLogger(__name__)

LANGUAGES_SCHEMA = "worldgen/languages@0.1"
BANK_FILE_SCHEMA = "storydaemon/language-banks@0.1"
BANK_FILE_NAME = "languages.json"      # under <project>/memory/
LANGUAGES_SUFFIX = "-languages.json"   # auto-detected beside the world file

DEFAULT_WORDS_PER_LANGUAGE = 12

# The everyday words offered to the writer, in preference order. Nouns and
# verbs from tiers 1 and 2 of the worldgen lexicon: things a character would
# actually say or swear by. The first ``words`` found win, so two languages
# from the same world show the same English words side by side.
EVERYDAY_NOUNS = [
    "water", "fire", "king", "mother", "sword", "friend", "father", "god",
    "sun", "moon", "sea", "house", "bread", "horse", "queen", "gold", "war",
    "city", "stone", "river", "night", "road", "ship", "blood", "heart",
    "wind", "death", "home", "lord", "child",
]
EVERYDAY_VERBS = [
    "see", "give", "go", "come", "kill", "love", "speak", "fight", "know",
    "die", "take", "run", "eat", "drink", "sleep", "say", "hold", "rule",
]
VERB_SHARE = 1 / 3  # of the words shown, roughly this many are verbs


class UnknownLanguagesSchemaError(ValueError):
    """The file is not a worldgen languages file this importer understands."""


class LanguagesMismatchError(ValueError):
    """The languages file names peoples the world file does not have."""


@dataclass
class LanguageNotes:
    """One people's language, reduced to what the writer needs to see."""
    people: str                       # realm/faction id, or e.g. "elder"
    people_name: str                  # "Vokekuk Principality"
    name: str                         # "Quqo"
    family: Optional[str] = None      # family id or None
    family_name: str = ""             # "the Òňun family"
    relatives: List[str] = field(default_factory=list)   # "Kesen (Esek Principality)"
    word_order: str = ""              # one phrase
    morphology: str = ""              # one phrase
    script: str = ""                  # one phrase
    words: Dict[str, str] = field(default_factory=dict)  # english -> native spelling
    places: List[Dict[str, str]] = field(default_factory=list)   # {name, meaning}
    persons: List[Dict[str, str]] = field(default_factory=list)  # {name, meaning}
    in_world: bool = True             # the people id matched the world file

    def to_dict(self) -> Dict[str, Any]:
        return {
            "people": self.people,
            "people_name": self.people_name,
            "name": self.name,
            "family": self.family,
            "family_name": self.family_name,
            "relatives": list(self.relatives),
            "word_order": self.word_order,
            "morphology": self.morphology,
            "script": self.script,
            "words": dict(self.words),
        }


@dataclass
class LanguageEntities:
    """What a languages file maps to, before any id is assigned."""
    schema: str
    seed: str
    families: List[Dict[str, Any]]
    languages: List[LanguageNotes]
    lore: List[Dict[str, Any]] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        return {
            "languages": len(self.languages),
            "families": len(self.families),
            "lore": len(self.lore),
            "names": sum(len(n.places) + len(n.persons) for n in self.languages),
        }

    def notes_block(self) -> Dict[str, Any]:
        """The ``languages`` block for ``state["world"]`` (the writer reads it)."""
        return {
            "schema": self.schema,
            "seed": self.seed,
            "families": [
                {"id": f.get("id"), "name": f.get("name"),
                 "members": list(f.get("members") or [])}
                for f in self.families
            ],
            "peoples": [n.to_dict() for n in self.languages],
        }

    def bank_file(self) -> Dict[str, Any]:
        """The per-people name banks ``NameGenerator`` loads."""
        return {
            "schema": BANK_FILE_SCHEMA,
            "seed": self.seed,
            "peoples": {
                n.people: {
                    "people_name": n.people_name,
                    "language": n.name,
                    "people": [dict(p) for p in n.persons],
                    "places": [dict(p) for p in n.places],
                }
                for n in self.languages
            },
        }

    def setting_sentence(self) -> str:
        """One sentence for the foundation setting: who speaks what."""
        spoken = [f"{n.name} ({n.people_name})" for n in self.languages if n.in_world]
        if not spoken:
            return ""
        n = len(spoken)
        return (f"{'One tongue is' if n == 1 else f'{n} tongues are'} spoken: "
                f"{_join(spoken)}.")


# ============================================================================
# Loading and validation
# ============================================================================

def load_languages(path: str) -> Dict[str, Any]:
    """Read a worldgen languages file and check it carries the known schema."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise UnknownLanguagesSchemaError(
            f"{path} is not a worldgen languages file: expected a JSON object")
    languages_schema_of(data)
    return data


def languages_schema_of(data: Dict[str, Any]) -> str:
    schema = data.get("schema")
    if schema != LANGUAGES_SCHEMA:
        raise UnknownLanguagesSchemaError(
            f"Unknown languages schema {schema!r}; expected {LANGUAGES_SCHEMA}")
    return schema


def default_languages_path(world_path) -> Path:
    """``<world stem>-languages.json`` beside the world file."""
    world_path = Path(world_path)
    return world_path.with_name(world_path.stem + LANGUAGES_SUFFIX)


def world_people(world_data: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """The peoples a world file has, as id -> {name, full_name}.

    A region's peoples are its realms; a sector's are its factions. The ids
    are what a languages file keys its entries by.
    """
    schema = schema_of(world_data)
    peoples: Dict[str, Dict[str, str]] = {}
    if schema == REGION_SCHEMA:
        for realm in world_data.get("realms") or []:
            rid = realm.get("id")
            if rid:
                gov = realm.get("government") or {}
                peoples[rid] = {
                    "name": realm.get("name") or rid,
                    "full_name": gov.get("fullName") or realm.get("name") or rid,
                }
    elif schema == SECTOR_SCHEMA:
        for faction in world_data.get("factions") or []:
            fid = faction.get("id")
            if fid:
                peoples[fid] = {
                    "name": faction.get("name") or fid,
                    "full_name": faction.get("name") or fid,
                }
    return peoples


def check_people_match(lang_data: Dict[str, Any], world_data: Dict[str, Any]) -> None:
    """Raise LanguagesMismatchError unless the files describe the same world.

    Every realm- or faction-shaped people id (``R…``/``F…``) in the languages
    file must be a people of the world file, and at least one must match: a
    languages file written for another seed has the same ids as this one only
    by accident, and the names it carries would belong to nobody. Ids that
    are not realm or faction shaped (``elder``) are unaffiliated tongues and
    need no match.
    """
    peoples = world_people(world_data)
    ids = [str(entry.get("people") or "") for entry in lang_data.get("languages") or []]
    affiliated = [i for i in ids if _looks_like_people_id(i)]
    missing = [i for i in affiliated if i not in peoples]
    if missing:
        raise LanguagesMismatchError(
            f"The languages file names {_join(sorted(missing))}, which the world "
            f"file does not have (its peoples: {_join(sorted(peoples)) or 'none'}). "
            "Were they written from the same seed?")
    if peoples and not affiliated:
        raise LanguagesMismatchError(
            "The languages file names none of the world's peoples "
            f"({_join(sorted(peoples))}); it describes a different world.")
    seed_l, seed_w = lang_data.get("seed"), world_data.get("seed")
    if seed_l and seed_w and seed_l != seed_w:
        logger.warning("languages seed %r differs from world seed %r; the ids "
                       "match, so importing anyway", seed_l, seed_w)


def _looks_like_people_id(people_id: str) -> bool:
    return (len(people_id) >= 2 and people_id[0] in "RF" and people_id[1:].isdigit())


# ============================================================================
# Mapping
# ============================================================================

def map_languages(
    lang_data: Dict[str, Any],
    world_data: Optional[Dict[str, Any]] = None,
    words_per_language: int = DEFAULT_WORDS_PER_LANGUAGE,
) -> LanguageEntities:
    """Reduce a languages file to notes, lore and name banks.

    ``world_data`` supplies the peoples' names and is checked for a match
    when given; without it the file's own ``peopleName`` is used throughout.
    """
    languages_schema_of(lang_data)
    peoples = world_people(world_data) if world_data is not None else {}
    if world_data is not None:
        check_people_match(lang_data, world_data)

    families = list(lang_data.get("families") or [])
    family_by_id = {f.get("id"): f for f in families}
    entries = list(lang_data.get("languages") or [])
    lang_name_by_people = {
        str(e.get("people")): (e.get("language") or {}).get("name") or "" for e in entries}
    people_name_by_id = {
        str(e.get("people")): _people_display_name(e, peoples) for e in entries}

    notes: List[LanguageNotes] = []
    for entry in entries:
        pid = str(entry.get("people") or "")
        lang = entry.get("language") or {}
        fam = family_by_id.get(entry.get("family")) or {}
        relatives = [
            f"{lang_name_by_people.get(m, m)} ({people_name_by_id.get(m, m)})"
            for m in (fam.get("members") or []) if m != pid and m in lang_name_by_people
        ]
        grammar = lang.get("grammar") or {}
        names = entry.get("names") or {}
        notes.append(LanguageNotes(
            people=pid,
            people_name=people_name_by_id[pid],
            name=lang.get("name") or f"the tongue of {people_name_by_id[pid]}",
            family=entry.get("family"),
            family_name=fam.get("name") or "",
            relatives=relatives,
            word_order=word_order_phrase(grammar),
            morphology=morphology_phrase(grammar),
            script=script_phrase(lang.get("script") or {}),
            words=everyday_words(lang.get("lexicon") or [], words_per_language),
            places=_names(names.get("places")),
            persons=_names(names.get("people")),
            in_world=pid in peoples,
        ))

    lore = [language_lore(n) for n in notes]
    return LanguageEntities(
        schema=LANGUAGES_SCHEMA,
        seed=str(lang_data.get("seed") or ""),
        families=families,
        languages=notes,
        lore=lore,
    )


def _people_display_name(entry: Dict[str, Any], peoples: Dict[str, Dict[str, str]]) -> str:
    pid = str(entry.get("people") or "")
    if pid in peoples:
        return peoples[pid]["full_name"]
    return entry.get("peopleName") or pid


def _names(items: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for item in items or []:
        if isinstance(item, str):
            item = {"name": item}
        name = (item.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "meaning": (item.get("meaning") or "").strip()})
    return out


_WORD_ORDER = {
    "SVO": "subject, verb, object, as in English",
    "SOV": "subject, object, verb, with the verb last",
    "VSO": "verb first, then subject, then object",
    "VOS": "verb first, then object, then subject",
    "OVS": "object first, then verb, then subject",
    "OSV": "object first, then subject, then verb",
}

_MORPHOLOGY = {
    "isolating": "words do not inflect",
    "agglutinative": "words are built from strings of clear suffixes",
    "fusional": "endings fuse several meanings at once",
    "polysynthetic": "a whole clause can be one long word",
}


def word_order_phrase(grammar: Dict[str, Any]) -> str:
    order = (grammar.get("wordOrder") or "").upper()
    phrase = _WORD_ORDER.get(order, f"{order} order" if order else "")
    adjective = grammar.get("adjective")
    if adjective in ("before", "after"):
        phrase = (phrase + "; " if phrase else "") + f"adjectives {adjective} the noun"
    return phrase


def morphology_phrase(grammar: Dict[str, Any]) -> str:
    morph = (grammar.get("morphology") or "").lower()
    phrase = _MORPHOLOGY.get(morph, morph)
    cases = grammar.get("cases") or []
    if cases:
        phrase = (phrase + ", " if phrase else "") + f"{len(cases)} noun cases"
    return phrase


_SCRIPT_KIND = {
    "alphabet": "an alphabet",
    "abjad": "an abjad (consonants only)",
    "abugida": "an abugida",
    "syllabary": "a syllabary",
    "logographic": "a logographic script",
}

_DIRECTION = {"ltr": "left to right", "rtl": "right to left", "ttb": "top to bottom"}


def script_phrase(script: Dict[str, Any]) -> str:
    kind = (script.get("kind") or "").lower()
    if not kind:
        return ""
    phrase = f"written in {_SCRIPT_KIND.get(kind, kind)}"
    direction = _DIRECTION.get((script.get("direction") or "").lower())
    if direction:
        phrase += f", {direction}"
    return phrase


def everyday_words(lexicon: Iterable[Dict[str, Any]], count: int = DEFAULT_WORDS_PER_LANGUAGE,
                   max_tier: int = 2) -> Dict[str, str]:
    """A dozen everyday words, english -> native spelling, in a fixed order.

    Nouns and verbs from the lexicon's tiers 1 and 2 only (tier 0 is derived
    vocabulary, tier 3 is genre-specific), chosen by the preference lists
    above so the same English words appear for every language of a world.
    """
    count = max(0, int(count))
    by_english: Dict[Tuple[str, str], str] = {}
    for w in lexicon:
        try:
            tier = int(w.get("tier", 99))
        except (TypeError, ValueError):
            continue
        if tier < 1 or tier > max_tier:
            continue
        form = (w.get("spelling") or w.get("ipa") or "").strip()
        eng = (w.get("english") or "").strip().lower()
        pos = (w.get("pos") or "").strip().lower()
        if eng and form and pos in ("n", "v"):
            by_english.setdefault((eng, pos), form)
    n_verbs = int(round(count * VERB_SHARE))
    verbs = [e for e in EVERYDAY_VERBS if (e, "v") in by_english][:n_verbs]
    nouns = [e for e in EVERYDAY_NOUNS if (e, "n") in by_english][:max(0, count - len(verbs))]
    words = {e: by_english[(e, "n")] for e in nouns}
    words.update({e: by_english[(e, "v")] for e in verbs})
    return words


def language_lore(notes: LanguageNotes) -> Dict[str, Any]:
    """One lore fact per language, for the planner's lore list and search."""
    sentences = []
    if notes.in_world:
        head = f"The people of {notes.people_name} speak {notes.name}"
    else:
        head = f"{_cap(notes.people_name)} is {notes.name}"
    if notes.family_name and notes.relatives:
        head += f", a tongue of {notes.family_name} related to {_join(notes.relatives)}"
    elif notes.relatives:
        head += f", related to {_join(notes.relatives)}"
    elif notes.family_name:
        head += f", the only tongue of {notes.family_name}"
    else:
        head += ", related to no other living tongue"
    sentences.append(head + ".")
    structure = [p for p in (notes.word_order, notes.morphology) if p]
    if structure:
        sentences.append(f"Its order is {structure[0]}" + (f"; {structure[1]}" if len(structure) > 1 else "") + ".")
    if notes.script:
        sentences.append(_cap(notes.script) + ".")
    sample = list(notes.words.items())[:4]
    if sample:
        sentences.append("Their word for " + _join([f"{e} is {w}" for e, w in sample]) + ".")
    if notes.places:
        shown = notes.places[:3]
        sentences.append("Place names in it: " + _join(
            [f"{p['name']} ({p['meaning']})" if p.get("meaning") else p["name"] for p in shown]) + ".")
    return _lore(" ".join(sentences), category="language", lore_type="fact",
                 importance="normal", tags=["language", notes.people, notes.name])


# ============================================================================
# The writer's line
# ============================================================================

def languages_line(block: Optional[Dict[str, Any]], people_id: Optional[str],
                   max_words: Optional[int] = None) -> str:
    """The compact Languages line for one people, or '' when it has none.

    Reads the ``state["world"]["languages"]`` block. Limited to one language
    so the prompt does not grow with the number of realms in the world.
    """
    notes = find_language_notes(block, people_id)
    if not notes:
        return ""
    head = f"**Language:** The people of {notes.get('people_name') or notes.get('people')} speak {notes.get('name')}"
    if notes.get("relatives"):
        # "Gaipo (Principality of Vavarsrai)" -> "Gaipo": the line is compact
        kin = [r.split(" (")[0] for r in list(notes["relatives"])[:3]]
        head += f" (kin to {_join(kin)})"
    parts = [head + "."]
    structure = [p for p in (notes.get("word_order"), notes.get("morphology")) if p]
    if structure:
        parts.append("Order: " + "; ".join(structure) + ".")
    words = list((notes.get("words") or {}).items())
    if max_words is not None:
        words = words[:max(0, int(max_words))]
    if words:
        parts.append("Everyday words: " + ", ".join(f"{e} *{w}*" for e, w in words) + ".")
    parts.append("A native word may be dropped into dialogue or thought where this "
                 "character would use one; never invent words beyond these.")
    return " ".join(parts)


def find_language_notes(block: Optional[Dict[str, Any]], people_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """The notes dict for a people id or name, else None."""
    if not block or not people_id:
        return None
    key = str(people_id).strip().lower()
    for notes in block.get("peoples") or []:
        if key in (str(notes.get("people") or "").lower(),
                   str(notes.get("people_name") or "").lower(),
                   str(notes.get("name") or "").lower()):
            return notes
    return None


# ============================================================================
# Persistence
# ============================================================================

def persist_languages(memory, entities: LanguageEntities, vector_store=None) -> Dict[str, Any]:
    """Write the lore through a MemoryManager and the name banks to memory/.

    Mirrors ``world_import.persist_world``: ids from ``generate_lore_id``,
    indexing best-effort.
    """
    from .memory.entities import Lore

    created: Dict[str, Any] = {"lore": [], "bank_file": ""}
    for spec in entities.lore:
        lore = Lore(id=memory.generate_lore_id(), **spec)
        memory.save_lore(lore)
        _index(vector_store, "index_lore", lore)
        created["lore"].append(lore.id)

    bank_path = bank_file_path(memory.project_path)
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    with open(bank_path, "w", encoding="utf-8") as f:
        json.dump(entities.bank_file(), f, ensure_ascii=False, indent=2)
    created["bank_file"] = str(bank_path)
    return created


def bank_file_path(project_dir) -> Path:
    """Where a project's per-people name banks live."""
    return Path(project_dir) / "memory" / BANK_FILE_NAME


def languages_state_record(path: str, entities: LanguageEntities,
                           created: Optional[Dict[str, Any]] = None,
                           auto_detected: bool = False) -> Dict[str, Any]:
    """The ``languages`` block under ``state["world"]``: notes plus provenance."""
    record = entities.notes_block()
    record.update({
        "source": os.path.abspath(path),
        "auto_detected": bool(auto_detected),
        "imported_at": datetime.now().isoformat(),
        "counts": entities.counts(),
    })
    if created:
        record["entity_ids"] = {"lore": list(created.get("lore", []))}
        if created.get("bank_file"):
            record["bank_file"] = created["bank_file"]
    return record
