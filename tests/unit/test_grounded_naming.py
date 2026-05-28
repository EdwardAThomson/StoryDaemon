"""Phase 1 grounded-identity tests: names/entities come from Python, not the LLM."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.vector_store import VectorStore
from novel_agent.tools.name_generator import NameGenerator
from novel_agent.tools.memory_tools import CharacterGenerateTool, LocationGenerateTool

DATA_DIR = Path(__file__).parent.parent.parent / "novel_agent" / "data" / "names"


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 0, "active_character": None}))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def gen():
    return NameGenerator(DATA_DIR)


def test_genre_mapping(gen):
    assert gen._normalize_genre("epic fantasy") == "fantasy"
    assert gen._normalize_genre("space opera scifi") == "scifi"
    assert gen._normalize_genre("noir thriller") == "modern"
    assert gen._normalize_genre(None) == "scifi"


def test_place_names_unique_and_keep_descriptor(gen):
    names = {gen.generate_place_name(descriptor="Spaceport")["full_name"] for _ in range(25)}
    assert len(names) == 25
    assert all(n.endswith("Spaceport") for n in names)


def test_solo_place_name(gen):
    name = gen.generate_place_name()["full_name"]
    assert name and name[0].isupper()


def test_character_name_always_minted(project):
    tool = CharacterGenerateTool(MemoryManager(project), VectorStore(project),
                                 NameGenerator(DATA_DIR), genre="scifi")
    res = tool.execute(role="supporting", description="a guard", name="Bob Smith", gender="male")
    assert res["success"]
    char = MemoryManager(project).load_character(res["character_id"])
    # The LLM-supplied name must be ignored.
    assert char.full_name != "Bob Smith"
    assert "Bob" not in (char.first_name or "")


def test_character_title_hint_applied(project):
    tool = CharacterGenerateTool(MemoryManager(project), VectorStore(project),
                                 NameGenerator(DATA_DIR), genre="scifi")
    res = tool.execute(role="supporting", description="an officer", gender="male", title="Captain")
    char = MemoryManager(project).load_character(res["character_id"])
    assert char.title == "Captain"


def test_unique_role_deduped(project):
    mm, vs = MemoryManager(project), VectorStore(project)
    tool = CharacterGenerateTool(mm, vs, NameGenerator(DATA_DIR), genre="scifi")
    first = tool.execute(role="protagonist", description="the hero")
    second = tool.execute(role="protagonist", description="another hero")
    assert second.get("duplicate") is True
    assert second["character_id"] == first["character_id"]


def test_location_minted_from_descriptor(project):
    tool = LocationGenerateTool(MemoryManager(project), VectorStore(project),
                                NameGenerator(DATA_DIR), genre="scifi")
    res = tool.execute(description="a grand hall", descriptor="Town Hall", name="Ignored Name")
    assert res["success"]
    loc = MemoryManager(project).load_location(res["location_id"])
    assert loc.name.endswith("Town Hall")
    assert loc.name != "Ignored Name"


def test_location_dedup(project):
    # With no generator the fallback name is used, so dedup can be exercised deterministically.
    mm, vs = MemoryManager(project), VectorStore(project)
    tool = LocationGenerateTool(mm, vs, name_generator=None)
    first = tool.execute(description="d", name="The Citadel")
    second = tool.execute(description="d2", name="the citadel")
    assert second.get("duplicate") is True
    assert second["location_id"] == first["location_id"]
