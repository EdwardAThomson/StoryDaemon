"""Tests for the worldgen world importer (novel_agent/world_import.py).

The mapping tests run on the small fixtures under tests/fixtures/ and need
neither ChromaDB nor an LLM. The persistence tests use a real MemoryManager
on a temporary directory; the one that touches the vector index skips when
chromadb is not installed, and the CLI test skips when the llm-backends
package is not importable (novel_agent.cli.main needs it at import time).
"""
import json
import tempfile
from pathlib import Path

import pytest

from novel_agent.world_import import (
    REGION_SCHEMA,
    SECTOR_SCHEMA,
    UnknownWorldSchemaError,
    WorldEntities,
    describe_magic,
    faction_org_type,
    load_world,
    map_region,
    map_sector,
    map_world,
    persist_world,
    world_state_record,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def region_data():
    return json.loads((FIXTURES / "region-small.json").read_text(encoding="utf-8"))


@pytest.fixture
def sector_data():
    return json.loads((FIXTURES / "sector-small.json").read_text(encoding="utf-8"))


# ============================================================================
# Loading and dispatch
# ============================================================================

def test_load_world_reads_both_fixtures():
    assert load_world(str(FIXTURES / "region-small.json"))["schema"] == REGION_SCHEMA
    assert load_world(str(FIXTURES / "sector-small.json"))["schema"] == SECTOR_SCHEMA


def test_unknown_schema_raises_on_map_and_load():
    with pytest.raises(UnknownWorldSchemaError, match="worldgen/nebula@9"):
        map_world({"schema": "worldgen/nebula@9"})
    with pytest.raises(UnknownWorldSchemaError):
        map_world({"realms": []})  # no schema at all
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "odd.json"
        path.write_text(json.dumps({"schema": "something/else@0.1"}), encoding="utf-8")
        with pytest.raises(UnknownWorldSchemaError):
            load_world(str(path))
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(UnknownWorldSchemaError):
            load_world(str(path))


def test_map_world_dispatches_on_schema(region_data, sector_data):
    assert map_world(region_data).kind == "region"
    assert map_world(sector_data).kind == "sector"


def test_mapper_assigns_no_ids(region_data, sector_data):
    """Ids are MemoryManager's job; the mapper must never hand one out."""
    for entities in (map_world(region_data), map_world(sector_data)):
        for spec in entities.locations + entities.factions + entities.lore:
            assert "id" not in spec
            assert "created_at" not in spec


# ============================================================================
# Region
# ============================================================================

def test_region_factions_are_realms(region_data):
    e = map_region(region_data)
    assert e.genre == "fantasy"
    assert [f["name"] for f in e.factions] == [
        "Vokekuk Principality", "Principality of Vavarsrai"]
    first = e.factions[0]
    assert first["org_type"] == "government"
    assert first["importance"] == "high"
    summary = first["summary"]
    # ruler, succession and gender law, size, coast, magic tradition
    assert "Prince Vok Tektosngo" in summary
    assert "primogeniture" in summary and "male-only" in summary
    assert "90,000 people" in summary and "2,400 km²" in summary
    assert "with a coast" in summary
    assert "the Ukrekes way" in summary and "alchemical preparation" in summary
    assert "ruled from Esuk up Qokesvok" in summary
    assert first["metadata"]["worldgen"]["id"] == "R0"
    assert "realm" in first["tags"]
    # the landlocked realm says so, and carries its own tradition
    second = e.factions[1]["summary"]
    assert "landlocked" in second and "the Zhosske way" in second
    assert "Princess Saipyada Vai" in second


def test_region_locations_cities_and_largest_towns(region_data):
    e = map_region(region_data)
    names = [l["name"] for l in e.locations]
    # 3 cities (largest first), then towns at/above the 3,000 floor, largest first.
    # Aqik (1,152) and Uktokes (559) fall under the floor.
    assert names == ["Staysha", "Esuk up Qokesvok", "Swanhin", "Opes", "Utop", "Coqêffeq"]


def test_region_town_cap_and_floor(region_data):
    capped = map_region(region_data, max_towns=1)
    assert [l["name"] for l in capped.locations] == [
        "Staysha", "Esuk up Qokesvok", "Swanhin", "Opes"]
    everything = map_region(region_data, max_towns=50, town_population_min=0)
    assert len(everything.locations) == 8
    unclaimed = next(l for l in everything.locations if l["name"] == "Uktokes")
    assert "no realm" in unclaimed["description"]
    assert unclaimed["significance"] == "Unclaimed town"
    assert unclaimed["metadata"]["worldgen"]["realm_id"] is None
    none_at_all = map_region(region_data, max_towns=0)
    assert len(none_at_all.locations) == 3


def test_region_location_details(region_data):
    e = map_region(region_data)
    esuk = next(l for l in e.locations if l["name"] == "Esuk up Qokesvok")
    assert esuk["significance"] == "Capital of Vokekuk Principality"
    desc = esuk["description"]
    assert "city of 20,897 people" in desc
    assert "temperate grassland" in desc     # biome of its cell
    assert "river mouth" in desc and "coast" in desc
    wg = esuk["metadata"]["worldgen"]
    assert wg["realm_id"] == "R0" and wg["realm_name"] == "Vokekuk Principality"
    assert wg["biome"] == "temperate grassland"
    assert wg["river"] is True and wg["coast"] is True and wg["capital"] is True
    # a town whose site says nothing about water still reads the river layer
    opes = next(l for l in e.locations if l["name"] == "Opes")
    assert "town of 6,803 people in Vokekuk Principality" in opes["description"]
    assert opes["metadata"]["worldgen"]["river"] is True
    utop = next(l for l in e.locations if l["name"] == "Utop")
    assert utop["metadata"]["worldgen"]["river"] is False
    assert "defensible" in utop["features"]


def test_region_lore_items(region_data):
    e = map_region(region_data)
    by_cat = {}
    for item in e.lore:
        by_cat.setdefault(item["category"], []).append(item)
    assert len(by_cat["magic"]) == 1
    magic = by_cat["magic"][0]
    assert magic["lore_type"] == "rule" and magic["importance"] == "critical"
    assert "The Cosisae" in magic["content"]
    assert "worldgen" in magic["tags"]
    assert len(by_cat["calendar"]) == 1
    cal = by_cat["calendar"][0]["content"]
    assert "345 days; drop a day every 161 years" in cal
    assert "Sŷgw" in cal and "Siacesisia" in cal and "align every 94 days" in cal
    # one range and two rivers, as geography lore rather than locations
    geo = by_cat["geography"]
    assert len(geo) == 3
    rng = next(g for g in geo if "range" in g["tags"])
    assert "Cetcotdot Gaen" in rng["content"] and "2,800 m" in rng["content"]
    assert "Principality of Vavarsrai" in rng["content"]
    river = next(g for g in geo if "RV0" in g["tags"])
    assert "Gainaistai" in river["content"]
    assert "420 m³/s" in river["content"]
    assert "Vokekuk Principality" in river["content"]
    assert "Esuk up Qokesvok, Swanhin and Opes" in river["content"]
    # every hook, tagged as one
    hooks = by_cat["story_hook"]
    assert len(hooks) == 3
    assert all("hook" in h["tags"] for h in hooks)
    assert {h["tags"][2] for h in hooks} == {"mountain-pass", "river-border", "wilds"}
    assert all(h["importance"] == "important" for h in hooks)
    assert len(e.lore) == 1 + 1 + 3 + 3
    # nothing from the world is attributed to a scene
    assert all(item["source_scene_id"] == "" and item["tick"] == 0 for item in e.lore)


def test_region_setting_summary(region_data):
    e = map_region(region_data)
    assert "2 realms" in e.setting
    assert "Vokekuk Principality and Principality of Vavarsrai" in e.setting
    assert "3 cities and 5 towns" in e.setting
    assert "the Cosisae" in e.setting
    assert e.title == "The realms of Vokekuk and Vavarsrai"


def test_region_tolerates_missing_layers(region_data):
    """A trimmed or hand-edited world still maps; nothing optional is required."""
    data = dict(region_data)
    data.pop("cells")
    data.pop("rivers")
    data.pop("ranges")
    data.pop("hooks")
    data["magic"] = {}
    data["calendar"] = {}
    e = map_region(data)
    assert len(e.factions) == 2
    assert len(e.locations) == 6
    assert e.lore == []
    assert "biome" not in e.locations[0]["description"]


# ============================================================================
# Sector
# ============================================================================

def test_sector_factions(sector_data):
    e = map_sector(sector_data)
    assert e.genre == "science fiction"
    names = [f["name"] for f in e.factions]
    assert names == ["Pefsnuv Imperium", "Pekfus Exchange"]
    imperium, exchange = e.factions
    assert imperium["org_type"] == "government"
    assert exchange["org_type"] == "consortium"
    s = imperium["summary"]
    assert "militaristic empire" in s
    assert "Tech level: Interstellar" in s
    assert "Capital: the Tânvoum system, homeworld Nanstif" in s
    assert "15,364 million people" in s
    assert "133 ships" in s and "Home Fleet (home defence) at Tânvoum" in s
    assert "the Zatveš way" in s            # psionic tradition
    assert imperium["assets_resources"] == ["Home Fleet"]
    assert imperium["metadata"]["worldgen"]["tech_level_name"] == "Interstellar"
    assert imperium["metadata"]["worldgen"]["id"] == "F0"


def test_faction_org_type_mapping():
    assert faction_org_type("Trade Federation") == "consortium"
    assert faction_org_type("Hive Collective") == "ai_collective"
    assert faction_org_type("Spiritual Sect") == "cult"
    assert faction_org_type("Militaristic Empire") == "government"
    assert faction_org_type("Crime Syndicate") == "criminal"
    assert faction_org_type("Mining Corporation") == "corporate"
    assert faction_org_type("") == "government"


def test_sector_locations_capitals_and_temperate_worlds(sector_data):
    e = map_sector(sector_data)
    names = [l["name"] for l in e.locations]
    # homeworlds first, then colonies by population, then the unclaimed world
    assert names == ["Nemramgiap", "Nanstif", "Hiehhin", "Bihgob d"]
    nanstif = next(l for l in e.locations if l["name"] == "Nanstif")
    assert nanstif["significance"] == "Homeworld and capital of Pefsnuv Imperium"
    assert nanstif["aliases"] == ["Tânvoum c"]
    d = nanstif["description"]
    assert "K2V star" in d
    assert "Gravity 0.44 g" in d
    assert "°C" in d
    assert "The day is 30.5 hours" in d
    assert "The year is 211 Earth days (165 days local;" in d
    assert "red-orange to Earth-like" in d
    assert "Colonial Prefect Dezvim It Pifhěz" in d
    wg = nanstif["metadata"]["worldgen"]
    assert wg["system_id"] == "S2.0.0" and wg["owner_faction_id"] == "F0"
    assert wg["colony_kind"] == "homeworld"
    hiehhin = next(l for l in e.locations if l["name"] == "Hiehhin")
    assert "tidally locked" in hiehhin["description"]
    assert "tidally locked" in hiehhin["features"]
    assert hiehhin["significance"] == "Colony of Pekfus Exchange"
    bihgob = next(l for l in e.locations if l["name"] == "Bihgob d")
    assert bihgob["significance"] == "An unclaimed temperate world"
    assert "Claimed by no faction" in bihgob["description"]
    assert bihgob["aliases"] == []


def test_sector_world_cap(sector_data):
    e = map_sector(sector_data, max_worlds=2)
    assert [l["name"] for l in e.locations] == ["Nemramgiap", "Nanstif"]


def test_sector_capital_without_named_homeworld(sector_data):
    """With no homeworldId the capital's most habitable planet stands in."""
    data = json.loads(json.dumps(sector_data))
    data["factions"][0]["homeworldId"] = None
    e = map_sector(data)
    assert "Nanstif" in [l["name"] for l in e.locations]
    assert "main world Nanstif" in e.factions[0]["summary"]
    assert "homeworld" not in e.factions[0]["summary"]


def test_sector_lore_items(sector_data):
    e = map_sector(sector_data)
    by_cat = {}
    for item in e.lore:
        by_cat.setdefault(item["category"], []).append(item)
    psi = by_cat["psionics"][0]
    assert psi["lore_type"] == "rule" and psi["importance"] == "critical"
    assert "The Mibstaz draws on a mutation (hard)" in psi["content"]
    assert "Telekinesis" in psi["content"]
    ftl = by_cat["technology"][0]
    assert "jump lanes" in ftl["content"] and "7" in ftl["content"]
    # the one chokepoint lane is one item, merged with its hook: no duplicate
    chokepoints = by_cat["starlanes"]
    assert len(chokepoints) == 1
    c = chokepoints[0]
    assert "Mouzmouz–Pizchih" in c["content"]
    assert "Pekfus Exchange holds both ends" in c["content"]   # from the hook
    assert "5.5 ly" in c["content"]                             # from the lane
    assert {"chokepoint", "hook", "L121"} <= set(c["tags"])
    hooks = by_cat["story_hook"]
    kinds = sorted(h["tags"][2] for h in hooks)
    assert kinds == ["contested-world", "double-moon", "dying-star", "unguarded-chokepoint"]
    assert "chokepoint" not in kinds
    assert len(e.lore) == 1 + 1 + 1 + 4


def test_sector_setting_summary(sector_data):
    e = map_sector(sector_data)
    assert "5 star systems" in e.setting
    assert "jump lanes (up to 7 ly, 4 days per jump)" in e.setting
    assert "Pefsnuv Imperium and Pekfus Exchange" in e.setting
    assert "4 temperate worlds and 1 chokepoint lane." in e.setting
    assert "the Mibstaz" in e.setting


# ============================================================================
# describe_magic
# ============================================================================

def test_describe_magic_full(region_data):
    text = describe_magic(region_data["magic"])
    assert text.startswith("The Cosisae draws on a substance the user consumes (mostly hard).")
    assert "Anyone who studies can use it; users are very rare, and learn through a religious order." in text
    assert "Its workings pair a verb (Perceive, Create, Unravel, Bind) with a subject (Shadow, Mind, Air, Plants)." in text
    assert "It cannot affect the user's own body or raise the dead." in text
    assert "It costs a measured quantity of a named material per working." in text
    assert "When it goes wrong: fizzles harmlessly." in text
    assert "Why users don't rule: there are too few of them." in text
    assert "Known workings include" in text


def test_describe_magic_discrete_powers_and_sparse():
    assert "Its powers: Telekinesis, Clairvoyance." in describe_magic({
        "name": "the Gift", "source": "mutation",
        "grammar": {"kind": "discrete powers", "powers": ["Telekinesis", "Clairvoyance"]},
    })
    sparse = describe_magic({"name": "the Art"})
    assert sparse == "The Art draws on an unknown source."
    assert describe_magic({}) .startswith("The magic draws on")


# ============================================================================
# Persistence through MemoryManager
# ============================================================================

def _project_dir(tmpdir: str) -> Path:
    project = Path(tmpdir)
    (project / "memory").mkdir()
    return project


def test_persist_world_assigns_ids_and_writes_files(region_data):
    from novel_agent.memory.manager import MemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        project = _project_dir(tmpdir)
        memory = MemoryManager(project)
        entities = map_region(region_data)
        created = persist_world(memory, entities, vector_store=None)

        assert created["locations"] == ["L000", "L001", "L002", "L003", "L004", "L005"]
        assert created["factions"] == ["F0", "F1"]
        assert created["lore"] == [f"L{n:03d}" for n in range(1, 9)]
        assert created["skipped_locations"] == []

        loc = memory.load_location("L001")
        assert loc.name == "Esuk up Qokesvok"
        assert loc.metadata["worldgen"]["id"] == "T0"
        assert loc.created_at and loc.updated_at
        fac = memory.load_faction("F0")
        assert fac.name == "Vokekuk Principality"
        assert fac.org_type == "government"
        assert fac.metadata["worldgen"]["ruler"]["name"] == "Vok Tektosngo"
        lore = memory.load_all_lore()
        assert len(lore) == 8
        assert lore[0].category == "magic" and lore[0].status == "active"
        assert (project / "memory" / "locations" / "L005.json").exists()
        assert (project / "memory" / "factions" / "F1.json").exists()
        # counters moved on, so the ticks keep minting after the world
        assert memory.generate_id("location") == "L006"
        assert memory.generate_id("faction") == "F2"
        assert memory.generate_lore_id() == "L009"


def test_persist_world_skips_duplicate_location_names(sector_data):
    from novel_agent.memory.manager import MemoryManager
    from novel_agent.memory.entities import Location

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = MemoryManager(_project_dir(tmpdir))
        memory.save_location(Location(id=memory.generate_id("location"), name="nanstif"))
        created = persist_world(memory, map_sector(sector_data))
        assert created["skipped_locations"] == ["Nanstif"]
        assert len(created["locations"]) == 3
        names = {memory.load_location(lid).name for lid in memory.list_locations()}
        assert names == {"nanstif", "Nemramgiap", "Hiehhin", "Bihgob d"}


class _RecordingStore:
    """Stands in for VectorStore: records calls, and can fail on demand."""

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def _record(self, method, entity):
        if self.fail_on == method:
            raise RuntimeError("index down")
        self.calls.append((method, entity.id))

    def index_location(self, location):
        self._record("index_location", location)

    def index_faction(self, faction):
        self._record("index_faction", faction)

    def index_lore(self, lore):
        self._record("index_lore", lore)


def test_persist_world_indexes_every_entity(sector_data):
    from novel_agent.memory.manager import MemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = MemoryManager(_project_dir(tmpdir))
        store = _RecordingStore()
        created = persist_world(memory, map_sector(sector_data), store)
        methods = [m for m, _ in store.calls]
        assert methods.count("index_location") == len(created["locations"]) == 4
        assert methods.count("index_faction") == len(created["factions"]) == 2
        assert methods.count("index_lore") == len(created["lore"]) == 7


def test_persist_world_survives_index_failure(region_data):
    """An index failure must not cost the entity: it stays on disk."""
    from novel_agent.memory.manager import MemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = MemoryManager(_project_dir(tmpdir))
        store = _RecordingStore(fail_on="index_lore")
        created = persist_world(memory, map_region(region_data), store)
        assert len(created["lore"]) == 8
        assert len(memory.load_all_lore()) == 8
        assert sum(1 for m, _ in store.calls if m == "index_location") == 6


def test_persist_world_with_real_vector_store(region_data):
    pytest.importorskip("chromadb")
    from novel_agent.memory.manager import MemoryManager
    from novel_agent.memory.vector_store import VectorStore

    with tempfile.TemporaryDirectory() as tmpdir:
        project = _project_dir(tmpdir)
        memory = MemoryManager(project)
        store = VectorStore(project)
        created = persist_world(memory, map_region(region_data), store)
        counts = store.get_collection_counts()
        assert counts["locations"] == len(created["locations"]) == 6
        assert counts["factions"] == len(created["factions"]) == 2
        assert counts["lore"] == len(created["lore"]) == 8


def test_world_state_record(region_data):
    e = map_region(region_data)
    record = world_state_record("tests/fixtures/region-small.json", e,
                                {"locations": ["L000"], "factions": ["F0"], "lore": ["L001"]})
    assert record["schema"] == REGION_SCHEMA
    assert record["kind"] == "region"
    assert Path(record["source"]).is_absolute()
    assert record["counts"] == {"locations": 6, "factions": 2, "lore": 8}
    assert record["entity_ids"]["factions"] == ["F0"]
    assert record["imported_at"]


# ============================================================================
# CLI: novel new --world
# ============================================================================

def test_novel_new_with_world_non_interactive():
    pytest.importorskip("llm_backends")
    pytest.importorskip("chromadb")
    from typer.testing import CliRunner
    from novel_agent.cli import main as cli_main
    from novel_agent.memory.manager import MemoryManager

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(cli_main.app, [
            "new", "world-novel", "--dir", tmpdir, "--no-interactive",
            "--world", str(FIXTURES / "sector-small.json"),
            "--premise", "A courier carries a secret through the chokepoint.",
        ])
        assert result.exit_code == 0, result.output
        assert "Imported world: 2 factions, 4 locations, 7 lore items" in result.output

        project = next(Path(tmpdir).glob("world-novel_*"))
        state = json.loads((project / "state.json").read_text(encoding="utf-8"))
        foundation = state["story_foundation"]
        # genre and setting from the world; the premise the author gave
        assert foundation["genre"] == "science fiction"
        assert "Pefsnuv Imperium and Pekfus Exchange" in foundation["setting"]
        assert foundation["premise"] == "A courier carries a secret through the chokepoint."
        assert state["world"]["schema"] == SECTOR_SCHEMA
        assert state["world"]["source"].endswith("sector-small.json")
        assert state["world"]["counts"] == {"locations": 4, "factions": 2, "lore": 7}
        # the protagonist minted at creation is untouched and still active
        assert state["active_character"] == "C000"

        memory = MemoryManager(project)
        assert sorted(memory.list_factions()) == ["F0", "F1"]
        assert len(memory.list_locations()) == 4
        assert len(memory.load_all_lore()) == 7


def test_novel_new_with_user_genre_and_setting_keeps_them():
    pytest.importorskip("llm_backends")
    pytest.importorskip("chromadb")
    from typer.testing import CliRunner
    from novel_agent.cli import main as cli_main

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(cli_main.app, [
            "new", "world-novel", "--dir", tmpdir,
            "--world", str(FIXTURES / "region-small.json"),
            "--genre", "grimdark fantasy", "--setting", "The border marches.",
            "--premise", "p", "--protagonist", "a", "--tone", "t",
        ])
        assert result.exit_code == 0, result.output
        project = next(Path(tmpdir).glob("world-novel_*"))
        state = json.loads((project / "state.json").read_text(encoding="utf-8"))
        assert state["story_foundation"]["genre"] == "grimdark fantasy"
        assert state["story_foundation"]["setting"] == "The border marches."
        assert state["world"]["kind"] == "region"


def test_novel_new_rejects_unknown_world_before_creating_anything():
    pytest.importorskip("llm_backends")
    from typer.testing import CliRunner
    from novel_agent.cli import main as cli_main

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        bad = Path(tmpdir) / "bad.json"
        bad.write_text(json.dumps({"schema": "worldgen/nebula@9"}), encoding="utf-8")
        result = runner.invoke(cli_main.app, [
            "new", "world-novel", "--dir", tmpdir, "--no-interactive", "--world", str(bad)])
        assert result.exit_code == 1
        assert "Unknown world schema" in result.output
        assert not list(Path(tmpdir).glob("world-novel_*"))
        result = runner.invoke(cli_main.app, [
            "new", "world-novel", "--dir", tmpdir, "--no-interactive",
            "--world", str(Path(tmpdir) / "missing.json")])
        assert result.exit_code == 1
        assert "not found" in result.output
