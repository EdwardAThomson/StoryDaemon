"""Mint the protagonist at project creation, in Python, deterministically.

A project used to start with zero characters and no active_character, so the
entire cast of a novel depended on the planner choosing, unprompted, to call
character.generate. When planning degraded, nothing was created and nothing
said so: eight scenes were written about a protagonist who existed only as a
string parsed out of the foundation's free text by a fallback in
writer_context. She had no id, no memory record, no relationships, nothing the
fact extractor could update and nothing the vector store could retrieve.

This is the same principle Phase 1 already applies to every other entity: names
are minted in Python and the LLM only selects. The protagonist was the one
place that never got it. A story now cannot begin without a real protagonist
entity, so the writer is never handed a name with nothing behind it.

The author's own name wins when the foundation gives one; NameGenerator mints
one otherwise. No LLM call either way.
"""

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# "Elena Marsh, a naturalist carrying her brother's notebook" -> "Elena Marsh".
# One to three capitalised words before the first comma reads as a name; the
# check is deliberately strict, because guessing wrong here is what produced a
# phantom protagonist in the first place.
_NAME_WORD = re.compile(r"^[A-Z][\w'\-]*$")


def name_from_archetype(archetype: str) -> Optional[Tuple[str, str]]:
    """(first_name, family_name) if the archetype opens with a proper name."""
    head = (archetype or "").split(",")[0].strip()
    words = head.split()
    if not 1 <= len(words) <= 3:
        return None
    if not all(_NAME_WORD.match(w) for w in words):
        return None
    if len(words) == 1:
        return words[0], ""
    return words[0], words[-1]


def create_protagonist(memory, foundation, name_generator=None):
    """Create and persist the protagonist. Returns the new character id.

    Raises ValueError when no name can be established, which is deliberate: a
    story with no protagonist is not a story that should quietly start.
    """
    archetype = ""
    genre = ""
    if foundation is not None:
        archetype = (getattr(foundation, "protagonist_archetype", "") or "").strip()
        genre = (getattr(foundation, "genre", "") or "").strip()

    named = name_from_archetype(archetype)
    if named:
        first, family = named
    elif name_generator is not None:
        minted = name_generator.generate_name(genre=genre or "scifi")
        first = minted.get("first_name", "")
        family = minted.get("last_name", "") or minted.get("family_name", "")
    else:
        raise ValueError(
            "Cannot create a protagonist: the story foundation does not name "
            "one and no name generator was supplied.")

    if not first:
        raise ValueError("Cannot create a protagonist: minted an empty name.")

    from novel_agent.memory.entities import Character

    char_id = memory.generate_id("character")
    character = Character(
        id=char_id,
        first_name=first,
        family_name=family,
        role="protagonist",
        description=archetype or f"{first} {family}".strip(),
        metadata={"source": "project_creation",
                  "minted": "foundation" if named else "generated"},
    )
    memory.save_character(character)
    if name_generator is not None:
        name_generator.register_used_name(f"{first} {family}".strip())
    logger.info("Created protagonist %s (%s %s)", char_id, first, family)
    return char_id
