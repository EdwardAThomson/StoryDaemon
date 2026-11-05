"""Mint the protagonist at project creation, in Python, deterministically.

A project used to start with zero characters and no active_character, so the
entire cast of a novel depended on the planner choosing, unprompted, to call
character.generate. When planning degraded, nothing was created and nothing
said so: eight scenes were written about a protagonist who existed only as a
string a regex had mined out of the foundation's prose. She had no id, no
memory record, nothing the fact extractor could update or the vector store
retrieve.

The name now comes from an explicit field or from the generator. Nothing here
parses prose. The parser this replaced split the archetype on its first comma
and accepted one to three capitalised words, which produced:

    "Captain Ahab"                        -> first name "Captain"
    "Doctor Miriam Vale, a field surgeon" -> first name "Doctor", Miriam lost
    "The Nameless One, a wanderer"        -> first name "The"
    "Detective Sergeant Ruth Kade"        -> rejected, real name discarded

and it was the compensation that hid a deeper mistake: the wizard asks for an
archetype ("personality/role") and our projects had a name written into it, so
the field was being filled wrongly and the code quietly covered for it.
"""

import logging
from typing import Optional, Tuple

from novel_agent.agent.name_hygiene import (name_shaped_head, require_consistent,
                                            require_gender, strip_name_head)

logger = logging.getLogger(__name__)


def split_name(full_name: str) -> Tuple[str, str]:
    """Split an explicitly given name into (first, family).

    Splitting a name the author typed into a name field is not guessing: every
    word is part of the name. A single word is a mononym and keeps an empty
    family name.
    """
    words = (full_name or "").split()
    if not words:
        return "", ""
    if len(words) == 1:
        return words[0], ""
    return words[0], " ".join(words[1:])


def create_protagonist(memory, foundation, name_generator=None, gender=None, age_group=None):
    """Create and persist the protagonist. Returns the new character id.

    The name is taken from foundation.protagonist_name when the author gave
    one, and minted otherwise. Raises ValueError when neither is possible,
    which is deliberate: a story with no protagonist should not quietly start.
    """
    archetype = ""
    genre = ""
    given = ""
    if foundation is not None:
        archetype = (getattr(foundation, "protagonist_archetype", "") or "").strip()
        genre = (getattr(foundation, "genre", "") or "").strip()
        given = (getattr(foundation, "protagonist_name", "") or "").strip()

    # The gender is a fact recorded with the name. It must be stated, in the
    # foundation's protagonist_gender or the explicit argument; it is never
    # read off the archetype's pronouns, never defaulted (the generator's old
    # default made every protagonist male) and never drawn at random. A
    # missing gender, or an archetype that states the other one, raises.
    who = "the protagonist"
    if gender is None and foundation is not None:
        gender = getattr(foundation, "protagonist_gender", None)
    gender = require_gender(gender, who)
    require_consistent(archetype, gender, "The protagonist", "archetype")
    # The age group is the same kind of fact: stated, never read off the text.
    from novel_agent.agent.name_hygiene import require_age_group
    if age_group is None and foundation is not None:
        age_group = getattr(foundation, "protagonist_age", None)
    age_group = require_age_group(age_group, who)

    if given:
        first, family = split_name(given)
        source = "foundation"
    elif name_generator is not None:
        minted = name_generator.generate_name(gender=gender, genre=genre or "scifi")
        first = minted.get("first_name", "")
        family = minted.get("last_name", "") or minted.get("family_name", "")
        source = "generated"
        _warn_if_archetype_looks_like_a_name(archetype, f"{first} {family}".strip())
    else:
        raise ValueError(
            "Cannot create a protagonist: the story foundation has no "
            "protagonist_name and no name generator was supplied.")

    if not first:
        raise ValueError("Cannot create a protagonist: the name is empty.")

    from novel_agent.memory.entities import Character

    # The record describes a role, never a second name. An archetype that
    # opens with a name ("Elena Marsh, a determined naturalist") used to be
    # copied whole, so the minted protagonist carried that name into every
    # writer prompt and the prose used it (2026-11-02 diagnosis). The author's
    # own protagonist_name is kept: that is the name the record already has.
    description, dropped = archetype, ""
    if not given:
        description, dropped = strip_name_head(archetype)
    metadata = {"source": "project_creation", "minted": source}
    if dropped:
        metadata["archetype_name_dropped"] = dropped

    char_id = memory.generate_id("character")
    from novel_agent.agent.personas import persona_for
    character = Character(
        id=char_id,
        first_name=first,
        family_name=family,
        gender=gender,
        age_group=age_group,
        persona=persona_for(memory.project_path.name, char_id, age_group,
                            [c.persona for c in map(memory.load_character, memory.list_characters())
                             if c is not None and c.persona]),
        role="protagonist",
        description=description or f"{first} {family}".strip(),
        metadata=metadata,
    )
    memory.save_character(character)
    if name_generator is not None:
        name_generator.register_used_name(f"{first} {family}".strip())
    logger.info("Created protagonist %s (%s %s, %s, %s)", char_id, first, family, gender, source)
    return char_id


def _warn_if_archetype_looks_like_a_name(archetype: str, minted: str) -> None:
    """Say so when a name was probably meant but not given.

    Surfacing it beats silently mining it: a legacy foundation with a name
    buried in its archetype now gets a generated protagonist AND a message
    saying which field to fill, instead of a regex deciding on the author's
    behalf.
    """
    head = name_shaped_head(archetype)
    if head:
        logger.warning(
            "The protagonist archetype starts with %r, which reads like a "
            "name, but protagonist_name was empty so %r was generated instead "
            "and %r was dropped from the character's description. "
            "Set protagonist_name in the story foundation if a specific name "
            "was intended.", head, minted, head)
