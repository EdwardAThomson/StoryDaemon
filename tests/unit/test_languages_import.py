"""Tests for the worldgen languages importer (novel_agent/languages_import.py).

The mapping tests run on tests/fixtures/region-small-languages.json, a small
synthetic languages file keyed to region-small.json's realms (R0, R2) plus an
unaffiliated "elder" tongue. No LLM anywhere. The persistence and writer tests
use a real MemoryManager on a temporary directory; the ones that touch the
vector index or the CLI skip when chromadb or llm-backends is missing.
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.languages_import import (
    LANGUAGES_SCHEMA,
    LanguagesMismatchError,
    UnknownLanguagesSchemaError,
    bank_file_path,
    check_people_match,
    default_languages_path,
    everyday_words,
    find_language_notes,
    languages_line,
    languages_state_record,
    load_languages,
    map_languages,
    persist_languages,
    world_people,
)
from novel_agent.memory.manager import MemoryManager
from novel_agent.tools.name_generator import NameGenerator, NameGeneratorTool

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "novel_agent" / "data" / "names"


@pytest.fixture
def region_data():
    return json.loads((FIXTURES / "region-small.json").read_text(encoding="utf-8"))


@pytest.fixture
def sector_data():
    return json.loads((FIXTURES / "sector-small.json").read_text(encoding="utf-8"))


@pytest.fixture
def lang_data():
    return json.loads((FIXTURES / "region-small-languages.json").read_text(encoding="utf-8"))


@pytest.fixture
def entities(lang_data, region_data):
    return map_languages(lang_data, region_data)


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    (d / "state.json").write_text(json.dumps({"current_tick": 1, "active_character": "C000"}))
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ============================================================================
# Loading and validation
# ============================================================================

def test_load_languages_checks_schema():
    assert load_languages(str(FIXTURES / "region-small-languages.json"))["schema"] == LANGUAGES_SCHEMA
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "odd.json"
        path.write_text(json.dumps({"schema": "worldgen/region@0.1"}), encoding="utf-8")
        with pytest.raises(UnknownLanguagesSchemaError, match="worldgen/region@0.1"):
            load_languages(str(path))
        path.write_text(json.dumps([1]), encoding="utf-8")
        with pytest.raises(UnknownLanguagesSchemaError):
            load_languages(str(path))
    with pytest.raises(UnknownLanguagesSchemaError):
        map_languages({"languages": []})


def test_default_languages_path_sits_beside_the_world_file():
    assert default_languages_path("/x/region-demo.json") == Path("/x/region-demo-languages.json")
    assert default_languages_path(FIXTURES / "region-small.json").exists()


def test_world_people_region_and_sector(region_data, sector_data):
    realms = world_people(region_data)
    assert set(realms) == {"R0", "R2"}
    assert realms["R0"]["full_name"] == "Vokekuk Principality"
    factions = world_people(sector_data)
    assert set(factions) == {"F0", "F2"}
    assert factions["F2"]["name"] == "Pekfus Exchange"


def test_mismatched_people_ids_raise(lang_data, region_data, sector_data):
    # the region file's realms are R0 and R2; a languages file for R1 is another world
    lang_data["languages"][1]["people"] = "R1"
    with pytest.raises(LanguagesMismatchError, match="R1"):
        check_people_match(lang_data, region_data)
    with pytest.raises(LanguagesMismatchError):
        map_languages(lang_data, region_data)
    # a region's languages against a sector: nothing matches
    with pytest.raises(LanguagesMismatchError):
        check_people_match(lang_data, sector_data)


def test_unaffiliated_tongues_need_no_match(lang_data, region_data):
    """``elder`` is not a realm id and must not be reported as missing."""
    check_people_match(lang_data, region_data)
    only_elder = {**lang_data, "languages": [lang_data["languages"][2]]}
    with pytest.raises(LanguagesMismatchError, match="none of the world's peoples"):
        check_people_match(only_elder, region_data)


# ============================================================================
# Mapping
# ============================================================================

def test_notes_per_people(entities, lang_data):
    assert [n.people for n in entities.languages] == ["R0", "R2", "elder"]
    quqo = entities.languages[0]
    assert quqo.name == "Quqo"
    assert quqo.people_name == "Vokekuk Principality"      # the world's full name wins
    assert quqo.family == "RF0" and quqo.family_name == "the Vokic family"
    assert quqo.relatives == ["Gaipo (Principality of Vavarsrai)"]
    assert quqo.word_order == "subject, verb, object, as in English; adjectives before the noun"
    assert quqo.morphology == "words do not inflect"
    assert quqo.script == "written in an abjad (consonants only), left to right"
    assert quqo.in_world is True
    assert len(quqo.places) == 4 and quqo.places[0] == {"name": "Puyeyukok", "meaning": "Deep Field"}
    assert len(quqo.persons) == 4 and quqo.persons[0]["name"] == "Tukkuye"

    elder = entities.languages[2]
    assert elder.in_world is False
    assert elder.people_name == "the old tongue of the wilds"
    assert elder.relatives == [] and elder.family is None
    assert elder.word_order.startswith("subject, object, verb")
    assert "5 noun cases" in elder.morphology


def test_everyday_words_are_a_dozen_tier_1_and_2_nouns_and_verbs(entities, lang_data):
    quqo = entities.languages[0]
    assert len(quqo.words) == 12
    lexicon = {w["english"]: w for w in lang_data["languages"][0]["language"]["lexicon"]}
    for english, native in quqo.words.items():
        assert lexicon[english]["spelling"] == native
        assert lexicon[english]["tier"] in (1, 2)
        assert lexicon[english]["pos"] in ("n", "v")
    assert "water" in quqo.words and "king" in quqo.words and "sword" in quqo.words
    assert "see" in quqo.words and "give" in quqo.words
    assert "fortress" not in quqo.words and "teacher" not in quqo.words   # tiers 3 and 0
    # the same English words for every language of the world
    assert list(entities.languages[1].words) == list(quqo.words)
    # the count is a knob
    assert len(everyday_words(lang_data["languages"][0]["language"]["lexicon"], 6)) == 6
    assert everyday_words([], 12) == {}


def test_mapping_is_deterministic(lang_data, region_data):
    a = map_languages(lang_data, region_data)
    b = map_languages(lang_data, region_data)
    assert a.notes_block() == b.notes_block()
    assert a.bank_file() == b.bank_file()
    assert a.lore == b.lore


def test_one_lore_item_per_language(entities):
    assert len(entities.lore) == 3
    quqo = entities.lore[0]
    assert quqo["category"] == "language" and quqo["lore_type"] == "fact"
    assert "id" not in quqo
    assert quqo["tags"][:2] == ["worldgen", "language"] and "R0" in quqo["tags"]
    content = quqo["content"]
    assert content.startswith("The people of Vokekuk Principality speak Quqo, a tongue of the Vokic family "
                              "related to Gaipo (Principality of Vavarsrai).")
    assert "Their word for water is" in content and "king is" in content
    assert "Puyeyukok (Deep Field)" in content
    elder = entities.lore[2]["content"]
    assert elder.startswith("The old tongue of the wilds is Cocqor, related to no other living tongue.")


def test_blocks_and_setting_sentence(entities):
    block = entities.notes_block()
    assert block["schema"] == LANGUAGES_SCHEMA
    assert [p["people"] for p in block["peoples"]] == ["R0", "R2", "elder"]
    assert block["families"] == [{"id": "RF0", "name": "the Vokic family", "members": ["R0", "R2"]}]
    assert block["peoples"][0]["words"]["king"]
    bank = entities.bank_file()
    assert bank["schema"] == "storydaemon/language-banks@0.1"
    assert set(bank["peoples"]) == {"R0", "R2", "elder"}
    assert bank["peoples"]["R2"]["language"] == "Gaipo"
    assert bank["peoples"]["R2"]["people"][0] == {"name": "Zhailo", "meaning": "Bright Star"}
    assert entities.setting_sentence() == (
        "2 tongues are spoken: Quqo (Vokekuk Principality) and Gaipo (Principality of Vavarsrai).")
    assert entities.counts() == {"languages": 3, "families": 1, "lore": 3, "names": 24}


def test_map_without_world_uses_the_files_own_names(lang_data):
    entities = map_languages(lang_data)
    assert entities.languages[0].people_name == "Vokekuk Principality"
    assert entities.languages[0].in_world is False


# ============================================================================
# The writer's line
# ============================================================================

def test_languages_line_is_one_language_and_compact(entities):
    block = entities.notes_block()
    line = languages_line(block, "R0")
    assert line.startswith("**Language:** The people of Vokekuk Principality speak Quqo (kin to Gaipo")
    assert "Order: subject, verb, object, as in English; adjectives before the noun; words do not inflect." in line
    assert "water *" in line and "king *" in line
    assert "Gaipo" not in line.split("Everyday words")[1]       # the other realm's words are absent
    assert "never invent words" in line
    assert len(line) < 700
    assert "(kin to Gaipo)" in line
    assert languages_line(block, "R0", max_words=3).count("*") == 4 + 6   # the bold label, three words
    # by name as well as id; nothing for an unknown people or an empty block
    assert languages_line(block, "Principality of Vavarsrai").startswith("**Language:** The people of Principality of Vavarsrai speak Gaipo")
    assert find_language_notes(block, "gaipo")["people"] == "R2"
    assert languages_line(block, "R9") == ""
    assert languages_line(None, "R0") == "" and languages_line(block, None) == ""


# ============================================================================
# Persistence and the name banks
# ============================================================================

def test_persist_languages_writes_lore_and_bank_file(entities, project):
    memory = MemoryManager(project)
    created = persist_languages(memory, entities)
    assert len(created["lore"]) == 3 and len(set(created["lore"])) == 3
    assert Path(created["bank_file"]) == bank_file_path(project)
    lore = {l.id: l for l in memory.load_all_lore()}
    first = lore[created["lore"][0]]
    assert first.category == "language"
    assert "speak Quqo" in first.content
    bank = json.loads(bank_file_path(project).read_text(encoding="utf-8"))
    assert bank["schema"] == "storydaemon/language-banks@0.1"
    assert bank["peoples"]["R0"]["places"][0]["name"] == "Puyeyukok"

    record = languages_state_record("/tmp/x-languages.json", entities, created, auto_detected=True)
    assert record["auto_detected"] is True
    assert record["entity_ids"]["lore"] == created["lore"]
    assert record["peoples"][0]["name"] == "Quqo"
    assert record["counts"]["languages"] == 3


def test_name_generator_draws_from_a_peoples_bank(entities, project):
    memory = MemoryManager(project)
    persist_languages(memory, entities)
    gen = NameGenerator(DATA_DIR, languages_file=bank_file_path(project))
    assert set(gen.language_banks) == {"R0", "R2", "elder"}
    assert gen.peoples_roster()[0] == "Vokekuk Principality (Quqo)"

    # resolution: id, people name, language name, near miss, embedded name; else None
    assert gen.resolve_people("R0") == "R0"
    assert gen.resolve_people("vokekuk principality") == "R0"
    assert gen.resolve_people("Gaipo") == "R2"
    assert gen.resolve_people("Principality of Vavarsai") == "R2"
    assert gen.resolve_people("a Vokekuk Principality guardsman") == "R0"
    assert gen.resolve_people("the Moon Court") is None
    assert gen.resolve_people("") is None

    quqo_names = {p["name"] for p in entities.languages[0].persons}
    drawn = gen.generate_name(gender="female", genre="fantasy", affiliation="Vokekuk Principality")
    assert drawn["first_name"] in quqo_names and drawn["last_name"] == ""
    assert drawn["full_name"] == drawn["first_name"]
    assert drawn["people"] == "R0" and drawn["language"] == "Quqo" and drawn["meaning"]
    # a title still applies, and no name repeats while any is unused
    titled = gen.generate_name(gender="male", genre="fantasy", title="Lord", affiliation="R0")
    assert titled["full_name"].startswith("Lord ") and titled["first_name"] != drawn["first_name"]
    seen = {drawn["first_name"], titled["first_name"]}
    for _ in range(2):
        seen.add(gen.generate_name(gender="male", genre="fantasy", affiliation="R0")["first_name"])
    assert seen == quqo_names
    # exhausted mononyms pair up rather than failing
    paired = gen.generate_name(gender="male", genre="fantasy", affiliation="R0")
    assert paired["first_name"] in quqo_names and paired["last_name"] in quqo_names

    # no affiliation, or an unknown one: the genre bank exactly as before
    plain = gen.generate_name(gender="male", genre="fantasy")
    assert "people" not in plain and plain["first_name"] not in quqo_names
    other = gen.generate_name(gender="male", genre="fantasy", affiliation="the Moon Court")
    assert "people" not in other

    # places: the people's own names first, then coined
    place_names = {p["name"] for p in entities.languages[1].places}
    place = gen.generate_place_name(descriptor="harbour", genre="fantasy", affiliation="Gaipo")
    assert place["root"] in place_names and place["full_name"] == f"{place['root']} harbour"
    assert place["people"] == "R2" and place["meaning"]
    for _ in range(3):
        gen.generate_place_name(genre="fantasy", affiliation="R2")
    coined = gen.generate_place_name(genre="fantasy", affiliation="R2")
    assert coined["root"] not in place_names


def test_name_generator_without_languages_is_unchanged(project):
    gen = NameGenerator(DATA_DIR)
    assert gen.language_banks == {} and gen.resolve_people("R0") is None
    assert NameGenerator(DATA_DIR, languages_file=project / "memory" / "languages.json").language_banks == {}
    (project / "memory" / "languages.json").write_text(json.dumps({"schema": "something/else"}))
    with pytest.raises(ValueError, match="language-bank"):
        NameGenerator(DATA_DIR, languages_file=project / "memory" / "languages.json")


def test_name_generate_tool_advertises_and_uses_affiliation(entities, project):
    memory = MemoryManager(project)
    persist_languages(memory, entities)
    tool = NameGeneratorTool(DATA_DIR, genre="fantasy", languages_file=bank_file_path(project))
    assert "affiliation" in tool.parameters
    assert "Vokekuk Principality (Quqo)" in tool.parameters["affiliation"]["description"]
    assert "own language" in tool.description
    result = tool.execute(gender="female", affiliation="Principality of Vavarsrai")
    assert result["success"] and result["people"] == "R2"
    assert result["first_name"] in {p["name"] for p in entities.languages[1].persons}
    # without language banks the parameter is not offered, as before
    plain = NameGeneratorTool(DATA_DIR, genre="fantasy")
    assert "affiliation" not in plain.parameters


def test_character_generate_records_the_people(entities, project):
    pytest.importorskip("chromadb")
    from novel_agent.memory.vector_store import VectorStore
    from novel_agent.tools.memory_tools import CharacterGenerateTool, LocationGenerateTool

    memory = MemoryManager(project)
    persist_languages(memory, entities)
    gen = NameGenerator(DATA_DIR, languages_file=bank_file_path(project))
    store = VectorStore(project)
    tool = CharacterGenerateTool(memory, store, gen, genre="fantasy")
    assert "affiliation" in tool.parameters
    result = tool.execute(role="supporting", description="a ferryman", gender="male",
                          affiliation="Vokekuk Principality")
    character = memory.load_character(result["character_id"])
    assert character.first_name in {p["name"] for p in entities.languages[0].persons}
    assert character.metadata["worldgen"]["people"] == "R0"
    assert character.metadata["worldgen"]["language"] == "Quqo"
    assert character.metadata["affiliation"] == "Vokekuk Principality"

    loc_tool = LocationGenerateTool(memory, store, gen, genre="fantasy")
    result = loc_tool.execute(description="a ford", descriptor="ford", affiliation="Gaipo")
    location = memory.load_location(result["location_id"])
    assert location.metadata["worldgen"]["realm_id"] == "R2"
    assert location.name.endswith(" ford")


# ============================================================================
# The writer sees it
# ============================================================================

def test_writer_context_carries_the_pov_language(entities, project):
    pytest.importorskip("chromadb")
    from novel_agent.agent.prompts import format_writer_prompt
    from novel_agent.agent.writer_context import WriterContextBuilder
    from novel_agent.configs.config import Config
    from novel_agent.memory.entities import Character, Location
    from novel_agent.memory.vector_store import VectorStore

    memory = MemoryManager(project)
    created = persist_languages(memory, entities)
    state = {"novel_name": "N", "current_tick": 1, "story_foundation": {"genre": "fantasy"},
             "world": {"languages": languages_state_record("x", entities, created)}}
    memory.save_character(Character(id="C000", first_name="Elil", family_name="Urnorn",
                                    role="protagonist", description="the lead"))
    memory.save_character(Character(id="C001", first_name="Zhailo", role="supporting",
                                    description="a captain",
                                    metadata={"worldgen": {"people": "R2", "language": "Gaipo"}}))
    memory.save_location(Location(id="L000", name="Swanhin", description="a city",
                                  metadata={"worldgen": {"realm_id": "R0"}}))
    wcb = WriterContextBuilder(memory, VectorStore(project), Config())

    # the POV character's own people wins
    plan = {"pov_character": "C001", "target_location": "L000", "scene_intention": "x", "key_change": "y"}
    ctx = wcb.build_writer_context(plan, {"actions_executed": []}, state)
    assert ctx["pov_people"] == "R2"
    assert ctx["languages_section"].startswith("**Language:** The people of Principality of Vavarsrai speak Gaipo")
    assert ctx["languages_section"] in ctx["pov_character_details"]
    assert "Quqo" not in ctx["languages_section"].split("Everyday words")[1]
    text = format_writer_prompt(ctx)
    assert "speak Gaipo" in text
    # half the approved pool comes from that people
    pool = [line[2:] for line in ctx["approved_new_names"].splitlines()]
    gaipo_names = {p["name"] for p in entities.languages[1].persons}
    assert len(pool) == 4 and len([n for n in pool if n in gaipo_names]) == 2

    # a character with no people falls back to the location's realm
    plan = {"pov_character": "C000", "target_location": "L000", "scene_intention": "x", "key_change": "y"}
    ctx = wcb.build_writer_context(plan, {"actions_executed": []}, state)
    assert ctx["pov_people"] == "R0"
    assert "speak Quqo" in ctx["languages_section"]

    # no languages block: nothing is added and nothing breaks
    ctx = wcb.build_writer_context(plan, {"actions_executed": []},
                                   {"novel_name": "N", "current_tick": 1,
                                    "story_foundation": {"genre": "fantasy"}})
    assert ctx["languages_section"] == ""
    assert "**Language:**" not in ctx["pov_character_details"]


# ============================================================================
# CLI: novel new --world --languages
# ============================================================================

def _cli():
    pytest.importorskip("llm_backends")
    pytest.importorskip("chromadb")
    from typer.testing import CliRunner
    from novel_agent.cli import main as cli_main
    return CliRunner(), cli_main.app


def test_novel_new_auto_detects_languages_beside_the_world():
    runner, app = _cli()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, [
            "new", "lang-novel", "--dir", tmpdir, "--no-interactive",
            "--world", str(FIXTURES / "region-small.json"),
        ])
        assert result.exit_code == 0, result.output
        assert "region-small-languages.json (found beside the world file)" in result.output
        assert "3 languages: Quqo, Gaipo, Cocqor" in result.output
        assert "Imported languages: 3 languages, 3 lore items, 24 names in memory/languages.json" in result.output

        project = next(Path(tmpdir).glob("lang-novel_*"))
        state = json.loads((project / "state.json").read_text(encoding="utf-8"))
        languages = state["world"]["languages"]
        assert languages["auto_detected"] is True
        assert languages["source"].endswith("region-small-languages.json")
        assert [p["people"] for p in languages["peoples"]] == ["R0", "R2", "elder"]
        assert languages["peoples"][0]["words"]["water"]
        assert state["story_foundation"]["setting"].endswith(
            "2 tongues are spoken: Quqo (Vokekuk Principality) and Gaipo (Principality of Vavarsrai).")
        assert bank_file_path(project).exists()

        memory = MemoryManager(project)
        language_lore = [l for l in memory.load_all_lore() if l.category == "language"]
        assert len(language_lore) == 3
        # the world's own lore is still there alongside
        assert len(memory.load_all_lore()) > 3
        assert sorted(memory.list_factions()) == ["F0", "F1"]


def test_novel_new_with_explicit_languages_file():
    runner, app = _cli()
    with tempfile.TemporaryDirectory() as tmpdir:
        # the world under another name, so nothing sits beside it to auto-detect
        world = Path(tmpdir) / "my-world.json"
        world.write_text((FIXTURES / "region-small.json").read_text(encoding="utf-8"), encoding="utf-8")
        result = runner.invoke(app, [
            "new", "lang-novel", "--dir", tmpdir, "--no-interactive", "--world", str(world),
            "--languages", str(FIXTURES / "region-small-languages.json"),
            "--setting", "The marches.",
        ])
        assert result.exit_code == 0, result.output
        assert "found beside" not in result.output
        project = next(Path(tmpdir).glob("lang-novel_*"))
        state = json.loads((project / "state.json").read_text(encoding="utf-8"))
        assert state["world"]["languages"]["auto_detected"] is False
        assert state["story_foundation"]["setting"] == "The marches."   # the author's text is kept

        # without --languages and nothing beside the world: no languages, no complaint
        result = runner.invoke(app, [
            "new", "plain-novel", "--dir", tmpdir, "--no-interactive", "--world", str(world)])
        assert result.exit_code == 0, result.output
        assert "Languages" not in result.output
        project = next(Path(tmpdir).glob("plain-novel_*"))
        state = json.loads((project / "state.json").read_text(encoding="utf-8"))
        assert "languages" not in state["world"]
        assert not bank_file_path(project).exists()


def test_novel_new_rejects_bad_languages_before_creating_anything(sector_data):
    runner, app = _cli()
    with tempfile.TemporaryDirectory() as tmpdir:
        # mismatched: a region's languages against a sector world
        sector = Path(tmpdir) / "sector.json"
        sector.write_text(json.dumps(sector_data), encoding="utf-8")
        result = runner.invoke(app, [
            "new", "lang-novel", "--dir", tmpdir, "--no-interactive", "--world", str(sector),
            "--languages", str(FIXTURES / "region-small-languages.json")])
        assert result.exit_code == 1
        assert "which the world file does not have" in result.output
        assert not list(Path(tmpdir).glob("lang-novel_*"))
        # wrong schema
        bad = Path(tmpdir) / "bad.json"
        bad.write_text(json.dumps({"schema": "worldgen/region@0.1"}), encoding="utf-8")
        result = runner.invoke(app, [
            "new", "lang-novel", "--dir", tmpdir, "--no-interactive",
            "--world", str(FIXTURES / "region-small.json"), "--languages", str(bad)])
        assert result.exit_code == 1
        assert "Unknown languages schema" in result.output
        # --languages needs --world
        result = runner.invoke(app, [
            "new", "lang-novel", "--dir", tmpdir, "--no-interactive",
            "--languages", str(FIXTURES / "region-small-languages.json")])
        assert result.exit_code == 1
        assert "--languages needs --world" in result.output
        assert not list(Path(tmpdir).glob("lang-novel_*"))
