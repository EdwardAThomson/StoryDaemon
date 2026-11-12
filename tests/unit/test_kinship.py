"""A relative is created as one: the family name is shared and the link is
recorded with real ids (a live Opus run, 2026-11-05, gave a brother and sister
unrelated surnames and a relationship to "<brother_id>")."""

import json
from pathlib import Path

import pytest

from novel_agent.memory.entities import Character
from novel_agent.memory.manager import MemoryManager
from novel_agent.tools.memory_tools import CharacterGenerateTool, RelationshipCreateTool
from novel_agent.tools.name_generator import NameGenerator

NAMES = Path(__file__).parent.parent.parent / "novel_agent" / "data" / "names"


class Vec:
    def index_character(self, c):
        pass


@pytest.fixture
def memory(tmp_path):
    d = tmp_path / "alcyone_1a2b3c4d"
    d.mkdir()
    (d / "state.json").write_text(json.dumps({"current_tick": 1}))
    m = MemoryManager(d)
    m.save_character(Character(id=m.generate_id("character"), first_name="Avice",
                               family_name="Radlett", gender="female",
                               age_group="adult", role="protagonist"))
    return m


def _tool(memory):
    return CharacterGenerateTool(memory, Vec(), NameGenerator(NAMES), genre="historical")


def test_a_sibling_shares_the_family_name_and_the_link_is_recorded(memory):
    out = _tool(memory).execute(role="her missing brother", description="a naturalist",
                                gender="male", age_group="adult",
                                kin_of="C000", kinship="sibling")
    brother = memory.load_character(out["character_id"])
    assert brother.family_name == "Radlett" and brother.first_name != "Avice"
    assert brother.metadata["kin"] == {"of": "C000", "kinship": "sibling"}
    rel = memory.get_relationship_between("C000", brother.id)
    assert rel is not None and rel.relationship_type == "siblings"
    assert out["kin_of"] == "C000"


def test_a_half_given_or_false_link_is_refused_and_nothing_is_made(memory):
    tool = _tool(memory)
    for kw in ({"kin_of": "C000"}, {"kinship": "sibling"},
               {"kin_of": "<sister_id>", "kinship": "sibling"},
               {"kin_of": "C000", "kinship": "cousin"}):
        with pytest.raises(ValueError):
            tool.execute(role="r", description="d", gender="male", age_group="adult", **kw)
    assert memory.list_characters() == ["C000"]


def test_a_relationship_to_a_placeholder_is_not_stored(memory):
    tool = RelationshipCreateTool(memory)
    for bad in ("<brother_id>", "{captain_id}", "Yusuf", "../state"):
        out = tool.execute("C000", bad, "siblings", "a", "b")
        assert out["success"] is False and "kin_of" in out["error"]
    assert memory.load_relationships() == []


def test_the_planner_is_shown_kinship():
    from novel_agent.tools.registry import ToolRegistry
    registry = ToolRegistry()
    registry.register(CharacterGenerateTool(None, None, None))
    text = registry.get_tools_description()
    assert "kinship (string: one of sibling | parent | child" in text
    assert "kin_of" in text
