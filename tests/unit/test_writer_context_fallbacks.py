"""Missing-entity fallbacks: raw ids (C0/L0) must never reach the writer prompt
as names, or the model uses them as literal character/place names in prose."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.vector_store import VectorStore
from novel_agent.memory.entities import Character
from novel_agent.configs.config import Config
from novel_agent.agent.writer_context import WriterContextBuilder
from novel_agent.agent.prompts import format_writer_prompt


FOUNDATION_STATE = {
    "novel_name": "N",
    "current_tick": 0,
    "story_foundation": {
        "genre": "historical adventure",
        "protagonist_archetype": (
            "Elena Marsh, a naturalist carrying her missing brother's cipher notebook"
        ),
    },
}


@pytest.fixture
def builder():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 0}))
    mm = MemoryManager(d)
    yield WriterContextBuilder(mm, VectorStore(d), Config()), mm
    shutil.rmtree(d, ignore_errors=True)


def test_missing_character_raises_instead_of_substituting(builder):
    """The behaviour this replaced: the name was parsed out of the foundation's
    free text, so the writer got "Elena Marsh" with no entity behind it. Eight
    scenes were written that way. A protagonist is now minted in Python at
    project creation, so reaching here is a real fault and must say so."""
    wcb, _ = builder
    with pytest.raises(ValueError) as e:
        wcb._get_character_details("C0", FOUNDATION_STATE)
    msg = str(e.value)
    assert "No POV character" in msg
    assert "Elena Marsh" in msg          # names the foundation's protagonist
    assert "C0" not in msg.split("Foundation protagonist:")[0]


def test_missing_character_without_foundation_also_raises(builder):
    wcb, _ = builder
    with pytest.raises(ValueError):
        wcb._get_character_details("C0", {})
    with pytest.raises(ValueError):
        wcb._get_character_details("", None)


def test_non_namelike_archetype_also_raises(builder):
    # Previously this quietly became "the protagonist".
    wcb, _ = builder
    state = {"story_foundation": {
        "protagonist_archetype": "a jaded detective haunted by an old case"}}
    with pytest.raises(ValueError):
        wcb._get_character_details("C0", state)


def test_existing_character_still_wins(builder):
    wcb, mm = builder
    mm.save_character(Character(id="C000", first_name="Joran", family_name="Vell",
                                role="protagonist", description="lead"))
    name, details = wcb._get_character_details("C000", FOUNDATION_STATE)
    assert name == "Joran"
    assert "Elena" not in details


def test_missing_location_never_surfaces_id(builder):
    wcb, _ = builder
    name, details = wcb._get_location_details("L0")
    assert "L0" not in name and "L0" not in details


def test_writer_prompt_carries_no_raw_ids(builder):
    """The original point of this file: a raw id reaching the prompt becomes
    the character's literal name in prose. With a real character present the
    prompt carries the name; the missing-character case now raises instead."""
    wcb, mm = builder
    mm.save_character(Character(id="C000", first_name="Joran", family_name="Vell",
                                role="protagonist", description="lead"))
    plan = {"pov_character": "C000", "target_location": "L0",
            "scene_intention": "x", "key_change": "y"}
    ctx = wcb.build_writer_context(plan, {"actions_executed": []}, FOUNDATION_STATE)
    assert ctx["pov_character_name"] == "Joran"
    text = format_writer_prompt(ctx)
    # The id may appear as a labelled field ("**ID:** C000"); what must never
    # happen is the id standing in for the character's NAME.
    assert "C000" not in ctx["pov_character_name"]
    assert "L0" not in text
