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


def test_missing_character_falls_back_to_foundation_protagonist(builder):
    wcb, _ = builder
    name, details = wcb._get_character_details("C0", FOUNDATION_STATE)
    assert name == "Elena Marsh"
    assert "C0" not in name and "C0" not in details
    assert "naturalist" in details


def test_missing_character_without_foundation_is_neutral(builder):
    wcb, _ = builder
    name, details = wcb._get_character_details("C0", {})
    assert name == "the protagonist"
    assert "C0" not in details

    # No id at all takes the same fallback.
    name, details = wcb._get_character_details("", None)
    assert name == "the protagonist"


def test_non_namelike_archetype_keeps_neutral_name(builder):
    wcb, _ = builder
    state = {"story_foundation": {
        "protagonist_archetype": "a jaded detective haunted by an old case"
    }}
    name, details = wcb._get_character_details("C0", state)
    assert name == "the protagonist"
    assert "jaded detective" in details


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
    wcb, _ = builder
    plan = {"pov_character": "C0", "target_location": "L0",
            "scene_intention": "x", "key_change": "y"}
    ctx = wcb.build_writer_context(plan, {"actions_executed": []}, FOUNDATION_STATE)
    assert ctx["pov_character_name"] == "Elena Marsh"
    text = format_writer_prompt(ctx)
    assert "C0" not in text
    assert "L0" not in text
