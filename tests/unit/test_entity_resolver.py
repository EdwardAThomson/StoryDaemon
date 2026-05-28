"""Phase 1 'reference by selection' tests: LLM entity refs resolve to real IDs or get dropped."""

import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Character, Location
from novel_agent.memory.entity_resolver import EntityResolver
from novel_agent.plot.manager import PlotOutlineManager
from novel_agent.plot.entities import PlotBeat


@pytest.fixture
def memory():
    d = Path(tempfile.mkdtemp())
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Joran", family_name="Syxurn",
                                role="supporting", description="a keeper",
                                nicknames=["Jo"]))
    mm.save_character(Character(id="C001", first_name="Elil", family_name="Urnorn",
                                role="protagonist", description="an investigator"))
    mm.save_location(Location(id="L000", name="Vernholt Town Hall", aliases=["Town Hall"]))
    yield mm, d
    shutil.rmtree(d, ignore_errors=True)


def test_resolve_character_by_id_name_nickname(memory):
    mm, _ = memory
    r = EntityResolver(mm)
    assert r.resolve_character("C000") == "C000"
    assert r.resolve_character("Joran") == "C000"
    assert r.resolve_character("joran syxurn") == "C000"
    assert r.resolve_character("Jo") == "C000"
    assert r.resolve_character("Elil") == "C001"


def test_resolve_location_by_id_name_alias(memory):
    mm, _ = memory
    r = EntityResolver(mm)
    assert r.resolve_location("L000") == "L000"
    assert r.resolve_location("Vernholt Town Hall") == "L000"
    assert r.resolve_location("town hall") == "L000"


def test_unresolved_returns_none(memory):
    mm, _ = memory
    r = EntityResolver(mm)
    assert r.resolve_character("C0") is None          # the short-form bug
    assert r.resolve_character("Nobody") is None
    assert r.resolve_location("L7") is None


def test_resolve_beat_drops_phantoms_and_dedups(memory):
    mm, _ = memory
    r = EntityResolver(mm)
    beat = PlotBeat(id="PB001", description="x",
                    characters_involved=["C0", "Elil", "C001", "Ghost"],
                    location="L0")
    dropped_chars, dropped_loc = r.resolve_beat(beat)
    assert beat.characters_involved == ["C001"]       # Elil + C001 dedup to one
    assert beat.location is None
    assert set(dropped_chars) == {"C0", "Ghost"}
    assert dropped_loc == "L0"


def test_add_beats_persists_only_resolved_refs(memory):
    mm, project_dir = memory
    pom = PlotOutlineManager(project_dir, llm_interface=None)
    beat = PlotBeat(id="", description="Joran meets Elil at the hall",
                    characters_involved=["C0", "Joran", "C001"],  # C0 phantom, Joran->C000
                    location="Town Hall")                          # alias -> L000
    pom.add_beats([beat])

    saved = pom.load_outline().beats
    assert len(saved) == 1
    assert saved[0].characters_involved == ["C000", "C001"]
    assert saved[0].location == "L000"
