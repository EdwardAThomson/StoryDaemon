"""Personas: each character's way of speaking, picked by Python, never the model.

Judge v2 scored every model chapter lowest on voices (Opus 5.5 3.5, Luna 2.3,
masters 4.5): everyone speaks in one formal, procedural register. The design
comes from Voxelholm's townsfolk personas (EdwardAThomson/voxelholm PR #214):
five personas, each with exactly one manner, picked from the person's number.
Here the number is the character's id, hashed with the novel's directory name
so two novels do not hand out personas in the same order.

A persona changes what a character notices and how they treat people, never
their spelling: the author's caution is that niche speech patterns jar the
reader, so the writer rules forbid dialect spellings, catchphrases and a
complaint repeated in every line.

Pure: the table is ``novel_agent/data/personas.json``; nothing here does I/O
beyond reading it once.
"""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "personas.json"


@lru_cache(maxsize=1)
def table():
    return json.loads(DATA.read_text(encoding="utf-8"))


def names():
    return list(table()["personas"])


def persona_for(seed: str, character_id: str) -> str:
    """The persona for a character: a fixed function of the novel and the id,
    so it is the same every time it is asked and needs no stored randomness."""
    if not character_id:
        raise ValueError("A persona is picked from the character's id; the id is empty.")
    digest = hashlib.sha256(f"{seed}:{character_id}".encode("utf-8")).digest()
    keys = names()
    return keys[int.from_bytes(digest[:4], "big") % len(keys)]


def label(persona: str) -> str:
    p = table()["personas"].get(persona) or {}
    return p.get("label", persona)


def manner(persona: str) -> str:
    return (table()["personas"].get(persona) or {}).get("manner", "")


def describe(persona: str) -> str:
    """One plain line: 'grumbler, plain manner: notices ...; with others ...'."""
    t = table()
    p = t["personas"].get(persona)
    if not p:
        return ""
    m = p["manner"]
    return (f"{label(persona)}, {m} manner ({t['manners'][m]}). Notices {p['notices']}. "
            f"With others: {p['with_others']}.")


VOICE_RULES = (
    "Each speaker's persona shapes what they notice, what they bring up and how "
    "they treat the others, so their lines could not be swapped. Show it through "
    "the substance of what they say, in ordinary English: never through misspelt "
    "or dialect words, a catchphrase, or the same complaint or worry in every "
    "line. Let it colour some lines, not all of them; the scene's business comes "
    "first."
)


def voices_section(characters) -> str:
    """The writer's 'How each one talks' block for ``characters`` (records with
    ``display_name`` and ``persona``), or '' when none has a persona."""
    lines = [f"- {c.display_name}: {describe(c.persona)}"
             for c in characters if getattr(c, "persona", "") and describe(c.persona)]
    if not lines:
        return ""
    return "\n\nHow each one talks (persona):\n" + "\n".join(lines) + "\n" + VOICE_RULES
