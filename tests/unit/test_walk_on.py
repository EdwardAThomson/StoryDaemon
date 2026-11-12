"""Walk-ons: a minor person the scene needs gets a minted name and a record,
and one role is one person (a live Opus run, 2026-11-06, named three walk-ons
the generator never minted)."""

import json
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.tools.memory_tools import CharacterGenerateTool, WalkOnTool
from novel_agent.tools.name_generator import NameGenerator

NAMES = Path(__file__).parent.parent.parent / "novel_agent" / "data" / "names"


class Vec:
    def index_character(self, c):
        pass


@pytest.fixture
def tool(tmp_path):
    d = tmp_path / "alcyone_1a2b3c4d"
    d.mkdir()
    (d / "state.json").write_text(json.dumps({"current_tick": 1}))
    m = MemoryManager(d)
    return WalkOnTool(CharacterGenerateTool(m, Vec(), NameGenerator(NAMES), genre="historical"))


def test_a_walk_on_is_minted_and_saved(tool):
    out = tool.execute(role="leadsman", gender="male", age_group="young")
    c = tool.memory_manager.load_character(out["character_id"])
    assert c.full_name == out["name"] and c.family_name
    assert (c.gender, c.age_group, c.role) == ("male", "young", "leadsman")
    assert c.metadata["walk_on"] is True and out["existing"] is False


def test_one_role_is_one_person(tool):
    a = tool.execute(role="the leadsman", gender="male", age_group="young")
    b = tool.execute(role="Leadsman", gender="male", age_group="young")
    assert b["character_id"] == a["character_id"] and b["existing"] is True
    c = tool.execute(role="master's mate", gender="male", age_group="adult")
    assert c["character_id"] != a["character_id"]
    assert len(tool.memory_manager.list_characters()) == 2


def test_a_walk_on_without_its_facts_is_refused(tool):
    with pytest.raises(ValueError):
        tool.execute(role="clerk", gender="male")
    with pytest.raises(ValueError):
        tool.execute(role="clerk", age_group="adult")
    with pytest.raises(ValueError):
        tool.execute(role="", gender="male", age_group="adult")
    assert tool.memory_manager.list_characters() == []


def test_the_writer_is_told_to_name_walk_ons_only_from_the_cast():
    from novel_agent.agent.prompts import WRITER_PROMPT_TEMPLATE
    assert 'never give them a name, a surname or a "Mr" of your own' in WRITER_PROMPT_TEMPLATE


def test_the_planner_is_offered_walk_ons(tool):
    from novel_agent.tools.registry import ToolRegistry
    registry = ToolRegistry()
    registry.register(tool)
    assert "character.walk_on" in registry.get_tools_description()
