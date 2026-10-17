"""Tests for the worldgen languages importer (novel_agent/languages_import.py).

The mapping tests run on tests/fixtures/region-small-languages.json, a small
synthetic languages file keyed to region-small.json's realms (R0, R2) plus an
unaffiliated "elder" tongue; R0 carries a ``phrases`` array, the others do
not. No LLM anywhere. The language tools and the scene's language situation
have their own files (test_language_tools.py, test_language_situation.py). The persistence and writer tests
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
    # the whole lexicon and the phrasebook travel to the bank, in file order
    assert len(quqo.lexicon) == 39
    assert quqo.lexicon[0] == {"english": "person", "pos": "n", "spelling": "kuq", "ipa": "ˈkuq", "tier": 1}
    assert len(quqo.phrases) == 9
    assert quqo.phrases[0] == {"english": "Greetings, friend!", "text": "Kuyek yele!",
                               "gloss": "greetings friend", "kind": "greeting"}

    elder = entities.languages[2]
    assert elder.in_world is False
    assert elder.people_name == "the old tongue of the wilds"
    assert elder.relatives == [] and elder.family is None
    assert elder.word_order.startswith("subject, object, verb")
    assert "5 noun cases" in elder.morphology
    assert elder.phrases == [] and len(elder.lexicon) == 39     # no phrasebook: tolerated


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


def test_no_lore_is_written_for_a_language(entities, project):
    """A language is texture, not a fact: the lore items an earlier version
    wrote were re-extracted into every scene as paragraphs about the tongue."""
    assert not hasattr(entities, "lore")
    assert "lore" not in entities.counts()
    memory = MemoryManager(project)
    created = persist_languages(memory, entities)
    assert "lore" not in created
    assert memory.load_all_lore() == []
    record = languages_state_record("x", entities, created)
    assert "entity_ids" not in record


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
    assert bank["peoples"]["R0"]["family"] == "RF0" and bank["peoples"]["elder"]["family"] is None
    assert len(bank["peoples"]["R0"]["lexicon"]) == 39 and len(bank["peoples"]["R0"]["phrases"]) == 9
    assert bank["peoples"]["elder"]["phrases"] == []
    # the state block stays small: no lexicon or phrasebook in state.json
    assert "lexicon" not in block["peoples"][0] and "phrases" not in block["peoples"][0]
    assert entities.setting_sentence() == (
        "2 tongues are spoken: Quqo (Vokekuk Principality) and Gaipo (Principality of Vavarsrai).")
    assert entities.counts() == {"languages": 3, "families": 1, "names": 24, "words": 117, "phrases": 9}


def test_map_without_world_uses_the_files_own_names(lang_data):
    entities = map_languages(lang_data)
    assert entities.languages[0].people_name == "Vokekuk Principality"
    assert entities.languages[0].in_world is False


# ============================================================================
# The writer's line
# ============================================================================

def test_languages_line_is_one_short_line(entities):
    """No word list, no grammar: the words reach the writer only through the
    language tools when the plan asks, and a prompt that listed them was
    answered with a paragraph about the language."""
    block = entities.notes_block()
    assert languages_line(block, "R0") == "**Language:** speaks Quqo (related to Gaipo)."
    assert languages_line(block, "elder") == "**Language:** speaks Cocqor."
    assert "Everyday words" not in languages_line(block, "R0") and "Order:" not in languages_line(block, "R0")
    # by name as well as id; nothing for an unknown people or an empty block
    assert languages_line(block, "Principality of Vavarsrai") == "**Language:** speaks Gaipo (related to Quqo)."
    assert find_language_notes(block, "gaipo")["people"] == "R2"
    assert languages_line(block, "R9") == ""
    assert languages_line(None, "R0") == "" and languages_line(block, None) == ""


# ============================================================================
# Persistence and the name banks
# ============================================================================

def test_persist_languages_writes_the_bank_file(entities, project):
    memory = MemoryManager(project)
    created = persist_languages(memory, entities)
    assert Path(created["bank_file"]) == bank_file_path(project)
    bank = json.loads(bank_file_path(project).read_text(encoding="utf-8"))
    assert bank["schema"] == "storydaemon/language-banks@0.1"
    assert bank["peoples"]["R0"]["places"][0]["name"] == "Puyeyukok"
    assert bank["peoples"]["R0"]["phrases"][0]["text"] == "Kuyek yele!"

    record = languages_state_record("/tmp/x-languages.json", entities, created, auto_detected=True)
    assert record["auto_detected"] is True
    assert record["bank_file"] == created["bank_file"]
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
    assert ctx["languages_section"] == "**Language:** speaks Gaipo (related to Quqo)."
    assert ctx["languages_section"] in ctx["pov_character_details"]
    assert ctx["languages_imported"] is True
    text = format_writer_prompt(ctx)
    assert "speaks Gaipo" in text
    assert "LANGUAGE RULES" in text
    # half the approved pool comes from that people
    pool = [line[2:] for line in ctx["approved_new_names"].splitlines()]
    gaipo_names = {p["name"] for p in entities.languages[1].persons}
    assert len(pool) == 4 and len([n for n in pool if n in gaipo_names]) == 2

    # a character with no people falls back to the location's realm
    plan = {"pov_character": "C000", "target_location": "L000", "scene_intention": "x", "key_change": "y"}
    ctx = wcb.build_writer_context(plan, {"actions_executed": []}, state)
    assert ctx["pov_people"] == "R0"
    assert "speaks Quqo" in ctx["languages_section"]

    # no languages block: nothing is added and nothing breaks
    ctx = wcb.build_writer_context(plan, {"actions_executed": []},
                                   {"novel_name": "N", "current_tick": 1,
                                    "story_foundation": {"genre": "fantasy"}})
    assert ctx["languages_section"] == ""
    assert ctx["languages_imported"] is False
    assert "**Language:**" not in ctx["pov_character_details"]
    assert "LANGUAGE RULES" not in format_writer_prompt(ctx)


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
        assert ("Imported languages: 3 languages, 117 words, 9 phrases, 24 names "
                "in memory/languages.json") in result.output

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
        # no language lore: the world's own lore is all there is
        assert [l for l in memory.load_all_lore() if l.category == "language"] == []
        assert len(memory.load_all_lore()) > 0
        assert sorted(memory.list_factions()) == ["F0", "F1"]
        bank = json.loads(bank_file_path(project).read_text(encoding="utf-8"))
        assert len(bank["peoples"]["R0"]["phrases"]) == 9


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
