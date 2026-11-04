"""Personas: picked by Python from the id, shown to the writer only when on."""

import json
from pathlib import Path

import pytest

from novel_agent.agent import personas
from novel_agent.configs.config import Config
from novel_agent.memory.entities import Character
from novel_agent.memory.manager import MemoryManager

NAMES = Path(__file__).parent.parent.parent / "novel_agent" / "data" / "names"


@pytest.fixture
def memory(tmp_path):
    d = tmp_path / "alcyone_1a2b3c4d"
    d.mkdir()
    (d / "state.json").write_text(json.dumps({"current_tick": 1}))
    return MemoryManager(d)


def test_every_persona_has_one_known_manner():
    t = personas.table()
    assert set(personas.names()) == {"grumbler", "worrier", "gossip", "dreamer", "oldtimer"}
    for name, p in t["personas"].items():
        assert p["manner"] in t["manners"]
        assert personas.describe(name).startswith(personas.label(name))


def test_the_persona_is_a_fixed_function_of_the_novel_and_the_id():
    a = personas.persona_for("alcyone_1a2b3c4d", "C001")
    assert all(personas.persona_for("alcyone_1a2b3c4d", "C001") == a for _ in range(5))
    picks = {personas.persona_for(f"novel_{i}", "C000") for i in range(40)}
    assert picks == set(personas.names())  # novels differ, and every persona is reachable
    with pytest.raises(ValueError):
        personas.persona_for("alcyone", "")


def test_a_generated_character_is_given_its_persona(memory):
    from novel_agent.tools.memory_tools import CharacterGenerateTool
    from novel_agent.tools.name_generator import NameGenerator

    class Vec:
        def index_character(self, c):
            pass

    tool = CharacterGenerateTool(memory, Vec(), NameGenerator(NAMES), genre="historical")
    out = tool.execute(role="minor", description="a quartermaster", gender="male")
    c = memory.load_character(out["character_id"])
    assert c.persona == personas.persona_for(memory.project_path.name, c.id)


def test_the_protagonist_is_given_its_persona(memory):
    from novel_agent.cli.protagonist import create_protagonist
    from novel_agent.cli.foundation import StoryFoundation
    from novel_agent.tools.name_generator import NameGenerator
    f = StoryFoundation(genre="historical adventure", premise="p",
                        protagonist_archetype="a junior surveyor", setting="s",
                        tone="t", protagonist_gender="female")
    cid = create_protagonist(memory, f, NameGenerator(NAMES))
    c = memory.load_character(cid)
    assert c.persona == personas.persona_for(memory.project_path.name, cid)


def _cast(memory):
    memory.save_character(Character(id="C000", first_name="Ada", family_name="Vane",
                                    gender="female", role="protagonist", persona="worrier"))
    memory.save_character(Character(id="C001", first_name="Tom", family_name="Hale",
                                    gender="male", role="supporting", persona="grumbler"))


def test_the_writer_sees_personas_only_when_they_are_on(memory):
    from novel_agent.agent.writer_context import WriterContextBuilder
    _cast(memory)
    off = WriterContextBuilder(memory, None, Config())
    cast, _ = off._build_cast_and_name_pool({}, "C000")
    _, details = off._get_character_details("C000")
    assert "persona" not in cast.lower() and "Persona" not in details

    cfg = Config()
    cfg.set("generation.character_personas", True)
    on = WriterContextBuilder(memory, None, cfg)
    cast, _ = on._build_cast_and_name_pool({}, "C000")
    _, details = on._get_character_details("C000")
    assert "- Tom: grumbler, plain manner" in cast
    assert "- Ada: worrier, plain manner" in cast
    assert "never through misspelt or dialect words, a catchphrase" in cast
    assert "**Persona:** worrier, plain manner" in details


def test_older_records_get_their_persona_at_the_start_of_a_tick(memory):
    from novel_agent.agent.agent import StoryAgent
    memory.save_character(Character(id="C000", first_name="Ada", gender="female"))
    agent = StoryAgent.__new__(StoryAgent)
    agent.memory = memory
    agent.config = Config()
    agent._backfill_character_personas()
    assert memory.load_character("C000").persona == ""  # off: untouched

    agent.config.set("generation.character_personas", True)
    agent._backfill_character_personas()
    c = memory.load_character("C000")
    assert c.persona == personas.persona_for(memory.project_path.name, "C000")
    assert c.metadata["persona_source"] == "backfill"
