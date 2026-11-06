"""The plan's text is held to the roster before the writer sees it.

A premise's "Yusuf" reached the prose 19 times through the planner's
intention with no character behind it (2026-11-03). A name a record already
answers to is replaced by the minted one; a person with no record fails the
tick, because minting them would need a gender nobody stated, and a gender is
never guessed or drawn at random (2026-11-04)."""
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.agent import StoryAgent
from novel_agent.memory.entities import Character
from novel_agent.memory.manager import MemoryManager


@pytest.fixture
def agent():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text("{}")
    memory = MemoryManager(d)
    memory.save_character(Character(id=memory.generate_id("character"), first_name="Theobald",
                                    family_name="Thornbury", gender="female", role="protagonist"))
    a = StoryAgent.__new__(StoryAgent)
    a.memory = memory
    a.state = {"story_foundation": {"premise": "A survey brig, the Alcyone, charts islands.",
                                    "setting": "a survey brig"}}
    yield a
    shutil.rmtree(d, ignore_errors=True)


def test_a_person_with_no_record_fails_the_tick(agent):
    plan = {"scene_intention": "Theobald obtains the log from Yusuf, who warns that he "
                               "replaced one page aboard the Alcyone."}
    with pytest.raises(ValueError, match="Yusuf"):
        agent._hold_plan_to_roster(plan, {"actions_executed": []}, tick=1)
    assert len(agent.memory.list_characters()) == 1  # nobody was minted


def test_a_name_a_record_answers_to_is_replaced_by_the_minted_name(agent):
    cid = agent.memory.generate_id("character")
    agent.memory.save_character(Character(
        id=cid, first_name="Richard", family_name="Huntington", gender="male", role="supporting",
        description="Quartermaster; the intention calls him Yusuf",
        metadata={"unminted_names_in_description": ["Yusuf"]}))
    plan = {"scene_intention": "Theobald obtains the log from Yusuf, who warns her."}
    done = agent._hold_plan_to_roster(plan, {"actions_executed": []}, tick=1)
    assert done[0]["character_id"] == cid
    assert "Richard" in plan["scene_intention"] and "Yusuf" not in plan["scene_intention"]
    assert "Yusuf" not in agent.memory.load_character(cid).description
    assert len(agent.memory.list_characters()) == 2


def test_nothing_happens_when_everyone_has_a_record(agent):
    plan = {"scene_intention": "Theobald sorts soundings aboard the Alcyone."}
    assert agent._hold_plan_to_roster(plan, {"actions_executed": []}, tick=1) == []
