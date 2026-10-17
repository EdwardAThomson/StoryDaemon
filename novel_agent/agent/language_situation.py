"""The language situation of a scene: who can understand whom.

Pure Python over the ``state["world"]["languages"]`` notes block an imported
world leaves behind. Given the POV character's people and the peoples of
whoever else is in the room (the location's realm or faction, the characters
the plan puts in the scene), it says one of four things:

- ``shared``: everyone present speaks the one tongue;
- ``related``: the others speak a tongue of the same family, so the two
  sides half-understand each other, with effort and not fluently;
- ``foreign``: someone present shares no tongue with the POV character;
- ``unknown``: no data (no languages imported, or nobody's people is known).

The verdict is rendered as one short line for the writer and the planner, so
the planner can pick a phrase or a misunderstanding on purpose and the
writer can let a line of speech go untranslated when the POV character would
not understand it. There is no intelligibility number in the file, so
"related" means "same family" and nothing finer. No LLM, no I/O, no state.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..languages_import import find_language_notes

SHARED, RELATED, FOREIGN, UNKNOWN = "shared", "related", "foreign", "unknown"
SITUATIONS = (SHARED, RELATED, FOREIGN, UNKNOWN)

Resolver = Callable[[Optional[str]], Optional[str]]


def people_of_character(character) -> Optional[str]:
    """A character's people: ``metadata.worldgen.people`` (set by
    character.generate), else a free-text ``metadata.affiliation``."""
    if character is None:
        return None
    meta = getattr(character, "metadata", None) or {}
    worldgen = meta.get("worldgen") or {}
    if worldgen.get("people"):
        return str(worldgen["people"])
    if meta.get("affiliation"):
        return str(meta["affiliation"])
    return None


def people_of_location(location) -> Optional[str]:
    """A location's people: the realm or faction that holds it (an imported
    settlement or world carries it), else a free-text ``affiliation``."""
    if location is None:
        return None
    meta = getattr(location, "metadata", None) or {}
    worldgen = meta.get("worldgen") or {}
    for key in ("realm_id", "owner_faction_id"):
        if worldgen.get(key):
            return str(worldgen[key])
    if meta.get("affiliation"):
        return str(meta["affiliation"])
    return None


def language_situation(
    block: Optional[Dict[str, Any]],
    pov_people: Optional[str],
    others: Iterable[Tuple[Optional[str], Optional[str]]],
    resolve: Optional[Resolver] = None,
    pov_label: str = "",
) -> Dict[str, Any]:
    """Classify a scene's language situation.

    ``others`` is a list of ``(label, people)`` pairs: the label is who it is
    ("Zhailo", "the innkeeper"; None or '' means the locals), the people a
    worldgen id or a name the block knows. ``resolve`` maps a free-text
    people to an id (``NameGenerator.resolve_people``); without it, the block
    is searched by id, people name and language name.

    Returns ``{"status", "pov_language", "pov_people", "others", "line"}``,
    where ``others`` lists each party that does not share the POV's tongue as
    ``{"label", "people", "language", "relation"}`` and ``line`` is the
    sentence for the prompts ('' when unknown).
    """
    empty = {"status": UNKNOWN, "pov_language": "", "pov_people": "", "others": [], "line": ""}
    if not block:
        return empty
    pov_notes = _notes_for(block, pov_people, resolve)
    if not pov_notes:
        return empty

    pov_language = pov_notes.get("name") or ""
    pov_family = pov_notes.get("family")
    seen = set()
    parties: List[Dict[str, Any]] = []
    known_other = False
    for label, people in others:
        notes = _notes_for(block, people, resolve)
        if not notes:
            continue
        known_other = True
        if notes.get("people") == pov_notes.get("people") or notes.get("name") == pov_language:
            continue
        key = (str(label or "").strip().lower(), notes.get("people"))
        if key in seen:
            continue
        seen.add(key)
        related = bool(pov_family) and notes.get("family") == pov_family
        parties.append({
            "label": str(label or "").strip(),
            "people": notes.get("people") or "",
            "people_name": notes.get("people_name") or "",
            "language": notes.get("name") or "",
            "family_name": notes.get("family_name") or "",
            "relation": RELATED if related else FOREIGN,
        })

    if not known_other:
        return {**empty, "pov_language": pov_language, "pov_people": pov_notes.get("people") or ""}
    if not parties:
        status = SHARED
    elif all(p["relation"] == RELATED for p in parties):
        status = RELATED
    else:
        status = FOREIGN
    result = {
        "status": status,
        "pov_language": pov_language,
        "pov_people": pov_notes.get("people") or "",
        "others": parties,
    }
    result["line"] = situation_line(result, pov_label=pov_label)
    return result


def situation_line(situation: Dict[str, Any], pov_label: str = "") -> str:
    """One sentence for the prompts, or '' when the situation is unknown."""
    status = situation.get("status")
    lang = situation.get("pov_language") or ""
    if status == UNKNOWN or not lang:
        return ""
    who = (pov_label or "").strip() or "the POV character"
    if status == SHARED:
        return f"Language situation: everyone present speaks {lang}."
    clauses = []
    for party in situation.get("others") or []:
        speaker = party.get("label") or "the people here"
        clause = f"{speaker} speak{'' if _plural(speaker) else 's'} {party['language']}"
        if party["relation"] == RELATED:
            clause += f", related to {lang}"
            if party.get("family_name"):
                clause += f" ({party['family_name']})"
        else:
            clause += f", which shares nothing with {lang}"
        clauses.append(clause)
    body = "; ".join(clauses)
    if status == RELATED:
        tail = ("they can follow each other with effort, not fluently: slow speech, "
                "familiar words, misheard ones")
    else:
        tail = (f"what is said in it reaches {who} as sound, not meaning, unless someone "
                "translates or a few learned words carry it")
    return f"Language situation: {who} speaks {lang}; {body}; {tail}."


def _plural(label: str) -> bool:
    low = label.lower()
    return low.startswith(("the people", "the locals", "the crowd", "the crew", "the guards",
                           "the soldiers", "the villagers", "the townsfolk"))


def _notes_for(block: Dict[str, Any], people: Optional[str],
               resolve: Optional[Resolver]) -> Optional[Dict[str, Any]]:
    if not people:
        return None
    notes = find_language_notes(block, people)
    if notes is None and resolve is not None:
        try:
            resolved = resolve(people)
        except Exception:
            resolved = None
        if resolved:
            notes = find_language_notes(block, resolved)
    return notes


def planner_language_fact(memory, project_state: Dict[str, Any],
                          resolve: Optional[Resolver] = None) -> Dict[str, Any]:
    """The situation as the planner should see it: the active character and
    the location it is currently at. Never raises."""
    block = ((project_state or {}).get("world") or {}).get("languages")
    if not block:
        return language_situation(None, None, [])
    try:
        active_id = project_state.get("active_character")
        character = memory.load_character(active_id) if active_id else None
        location = None
        location_id = getattr(getattr(character, "current_state", None), "location_id", None)
        if location_id:
            location = memory.load_location(location_id)
        pov_people = people_of_character(character) or people_of_location(location)
        others = [("the people here", people_of_location(location))] if location is not None else []
        label = getattr(character, "display_name", "") or ""
        return language_situation(block, pov_people, others, resolve, pov_label=label)
    except Exception:
        return language_situation(None, None, [])
