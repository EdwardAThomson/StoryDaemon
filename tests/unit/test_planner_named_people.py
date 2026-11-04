"""A person the plan names without a record is minted through the generator
before the writer sees the plan (2026-11-03: a premise's "Yusuf" reached the
prose 19 times through the planner's intention, with no character behind it)."""
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.agent import StoryAgent
from novel_agent.memory.entities import Character
from novel_agent.memory.manager import MemoryManager


class Tool:
    def __init__(self, memory):
        self.memory, self.calls = memory, []

    def execute(self, role, description, gender=None, **_):
        self.calls.append((role, description, gender))
        cid = self.memory.generate_id("character")
        self.memory.save_character(Character(id=cid, first_name="Septimus", family_name="Percy",
                                             gender=gender or "male", role=role,
                                             description=description))
        return {"success": True, "character_id": cid, "name": "Septimus Percy"}


class Registry:
    def __init__(self, tool):
        self.tool = tool

    def get_tool(self, name):
        return self.tool if name == "character.generate" else None


@pytest.fixture
def agent():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text("{}")
    memory = MemoryManager(d)
    memory.save_character(Character(id=memory.generate_id("character"), first_name="Theobald",
                                    family_name="Thornbury", gender="female", role="protagonist"))
    a = StoryAgent.__new__(StoryAgent)
    a.memory = memory
    a.tools = Registry(Tool(memory))
    a.state = {"story_foundation": {"premise": "A survey brig, the Alcyone, charts islands.",
                                    "setting": "a survey brig"}}
    yield a
    shutil.rmtree(d, ignore_errors=True)


def test_an_unrecorded_person_is_minted_and_the_plan_uses_the_minted_name(agent):
    plan = {"scene_intention": "Theobald obtains the log from Yusuf, who warns that he "
                               "replaced one page aboard the Alcyone.",
            "key_change": "Yusuf hands over the log."}
    results = {"actions_executed": []}
    done = agent._mint_planner_named_people(plan, results, tick=1)
    assert [d["named_in_plan"] for d in done] == ["Yusuf"]
    assert "Yusuf" not in plan["scene_intention"] and "Yusuf" not in plan["key_change"]
    assert "Septimus" in plan["scene_intention"]
    assert agent.tools.tool.calls[0][2] == "male"          # "he" in the sentence
    assert results["actions_executed"][0]["tool"] == "character.generate"
    assert len(agent.memory.list_characters()) == 2


def test_a_name_already_claimed_by_a_record_is_not_minted_twice(agent):
    cid = agent.memory.generate_id("character")
    agent.memory.save_character(Character(
        id=cid, first_name="Richard", family_name="Huntington", gender="male", role="supporting",
        description="Quartermaster; the intention calls him Yusuf",
        metadata={"unminted_names_in_description": ["Yusuf"]}))
    plan = {"scene_intention": "Theobald obtains the log from Yusuf, who warns her."}
    done = agent._mint_planner_named_people(plan, {"actions_executed": []}, tick=1)
    assert done[0]["character_id"] == cid and done[0]["existing"]
    assert agent.tools.tool.calls == []
    assert "Richard" in plan["scene_intention"]
    assert "Yusuf" not in agent.memory.load_character(cid).description


def test_nothing_happens_when_everyone_has_a_record(agent):
    plan = {"scene_intention": "Theobald sorts soundings aboard the Alcyone."}
    assert agent._mint_planner_named_people(plan, {"actions_executed": []}, tick=1) == []
    assert agent.tools.tool.calls == []
