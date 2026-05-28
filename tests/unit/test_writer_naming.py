"""Phase 1 writer-naming grounding: writer gets a cast roster + a pool of minted names."""

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
from novel_agent.agent.character_detector import CharacterDetector
from novel_agent.agent.prompts import format_writer_prompt


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 1, "active_character": "C000"}))
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Elil", family_name="Urnorn",
                               role="protagonist", description="the lead", nicknames=["El"]))
    yield d, mm
    shutil.rmtree(d, ignore_errors=True)


def test_cast_and_pool(project):
    d, mm = project
    wcb = WriterContextBuilder(mm, VectorStore(d), Config())
    cast, pool = wcb._build_cast_and_name_pool({"story_foundation": {"genre": "fantasy"}}, "C000")
    assert "Elil" in cast and "(POV)" in cast
    pool_names = [line[2:] for line in pool.splitlines()]
    assert len(pool_names) == 4
    # The minted pool must not reuse an existing character's name.
    assert all(n != "Elil Urnorn" for n in pool_names)


def test_writer_prompt_renders_with_new_keys(project):
    d, mm = project
    wcb = WriterContextBuilder(mm, VectorStore(d), Config())
    plan = {"pov_character": "C000", "scene_intention": "x", "key_change": "y"}
    ctx = wcb.build_writer_context(plan, {"actions_executed": []},
                                   {"novel_name": "N", "current_tick": 1,
                                    "story_foundation": {"genre": "scifi"}})
    text = format_writer_prompt(ctx)  # must not raise KeyError on a missing placeholder
    assert "Cast & Naming" in text
    assert "Elil" in text


def test_stub_skips_existing_character(project):
    d, mm = project
    det = CharacterDetector(mm, {})
    # "El" is a nickname of C000 -> should resolve, not create a duplicate.
    assert det.create_character_stub("El") == "C000"
    assert det.create_character_stub("Elil Urnorn") == "C000"
    # A genuinely new name creates a new entity.
    assert det.create_character_stub("Vexth Renar") != "C000"
