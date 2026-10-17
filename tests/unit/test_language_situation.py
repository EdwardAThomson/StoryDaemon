"""The scene's language situation (agent/language_situation.py), its line in
the writer and planner contexts, the writer's language rules, and the
executor-to-writer plumbing for requested native speech.

Pure-Python tests on a hand-built notes block, then the real builders over a
MemoryManager on a temporary directory (those skip without chromadb).
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.language_situation import (
    FOREIGN, RELATED, SHARED, UNKNOWN,
    language_situation, people_of_character, people_of_location, planner_language_fact,
    situation_line,
)
from novel_agent.agent.prompts import craft_rules, format_writer_prompt, language_rules
from novel_agent.languages_import import (
    bank_file_path, languages_state_record, map_languages, persist_languages,
)
from novel_agent.memory.entities import Character, Location
from novel_agent.memory.manager import MemoryManager

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

BLOCK = {
    "families": [{"id": "RF0", "name": "the Vokic family", "members": ["R0", "R2"]}],
    "peoples": [
        {"people": "R0", "people_name": "Vokekuk Principality", "name": "Quqo",
         "family": "RF0", "family_name": "the Vokic family"},
        {"people": "R2", "people_name": "Principality of Vavarsrai", "name": "Gaipo",
         "family": "RF0", "family_name": "the Vokic family"},
        {"people": "elder", "people_name": "the old tongue of the wilds", "name": "Cocqor",
         "family": None, "family_name": ""},
    ],
}


# ============================================================================
# The four verdicts
# ============================================================================

def test_shared_when_everyone_speaks_the_one_tongue():
    s = language_situation(BLOCK, "R0", [("the people here", "R0"), ("Tukkuye", "Vokekuk Principality")])
    assert s["status"] == SHARED and s["pov_language"] == "Quqo" and s["others"] == []
    assert s["line"] == "Language situation: everyone present speaks Quqo."


def test_related_when_the_other_tongue_is_of_the_same_family():
    s = language_situation(BLOCK, "R0", [("the innkeeper", "R2")], pov_label="Tukkuye")
    assert s["status"] == RELATED
    assert s["others"] == [{"label": "the innkeeper", "people": "R2",
                            "people_name": "Principality of Vavarsrai", "language": "Gaipo",
                            "family_name": "the Vokic family", "relation": RELATED}]
    assert s["line"] == ("Language situation: Tukkuye speaks Quqo; the innkeeper speaks Gaipo, related "
                         "to Quqo (the Vokic family); they can follow each other with effort, not "
                         "fluently: slow speech, familiar words, misheard ones.")


def test_foreign_when_no_tongue_is_shared_including_a_mix():
    s = language_situation(BLOCK, "R0", [("the people here", "elder")], pov_label="Tukkuye")
    assert s["status"] == FOREIGN
    assert s["line"] == ("Language situation: Tukkuye speaks Quqo; the people here speak Cocqor, which "
                         "shares nothing with Quqo; what is said in it reaches Tukkuye as sound, not "
                         "meaning, unless someone translates or a few learned words carry it.")
    # one related party and one foreign: someone present shares no tongue
    mixed = language_situation(BLOCK, "R0", [("Zhailo", "R2"), ("the guide", "elder")])
    assert mixed["status"] == FOREIGN
    assert [o["relation"] for o in mixed["others"]] == [RELATED, FOREIGN]
    assert "Zhailo speaks Gaipo, related to Quqo" in mixed["line"]
    assert "the guide speaks Cocqor, which shares nothing with Quqo" in mixed["line"]
    assert "the POV character speaks Quqo" in mixed["line"]      # no label given
    # a tongue with no family is foreign to everyone, even another familyless one
    assert language_situation(BLOCK, "elder", [("x", "R0")])["status"] == FOREIGN


def test_unknown_without_data():
    assert language_situation(None, "R0", [("x", "R2")])["status"] == UNKNOWN
    assert language_situation({}, "R0", [("x", "R2")])["status"] == UNKNOWN
    assert language_situation(BLOCK, None, [("x", "R2")])["status"] == UNKNOWN
    assert language_situation(BLOCK, "R9", [("x", "R2")])["status"] == UNKNOWN
    # the POV is known but nobody else is: nothing to say
    alone = language_situation(BLOCK, "R0", [])
    assert alone["status"] == UNKNOWN and alone["pov_language"] == "Quqo" and alone["line"] == ""
    assert language_situation(BLOCK, "R0", [("x", None), ("y", "nobody")])["status"] == UNKNOWN
    assert situation_line({"status": UNKNOWN}) == ""


def test_resolver_and_duplicates():
    calls = []

    def resolve(people):
        calls.append(people)
        return {"the vokekuk": "R0", "vavarsrai folk": "R2"}.get((people or "").lower())

    s = language_situation(BLOCK, "the Vokekuk", [("a", "Vavarsrai folk"), ("a", "Vavarsrai folk"),
                                                    ("b", "gaipo")], resolve=resolve)
    assert s["status"] == RELATED and calls == ["the Vokekuk", "Vavarsrai folk", "Vavarsrai folk"]
    assert [o["label"] for o in s["others"]] == ["a", "b"]      # same label+people once; "gaipo" by name


def test_people_of_character_and_location():
    assert people_of_character(Character(id="C1", first_name="A", metadata={"worldgen": {"people": "R2"}})) == "R2"
    assert people_of_character(Character(id="C1", first_name="A", metadata={"affiliation": "Vokekuk"})) == "Vokekuk"
    assert people_of_character(Character(id="C1", first_name="A")) is None
    assert people_of_character(None) is None
    assert people_of_location(Location(id="L1", name="x", metadata={"worldgen": {"realm_id": "R0"}})) == "R0"
    assert people_of_location(Location(id="L1", name="x", metadata={"worldgen": {"owner_faction_id": "F1"}})) == "F1"
    assert people_of_location(Location(id="L1", name="x", metadata={"affiliation": "elder"})) == "elder"
    assert people_of_location(Location(id="L1", name="x")) is None


# ============================================================================
# The writer's language rules
# ============================================================================

def test_language_rules_only_when_languages_were_imported():
    assert language_rules({}) == ""
    assert language_rules({"pov_character_name": "Elil"}) == ""
    assert "LANGUAGE RULES" not in craft_rules({"pov_character_name": "Elil"})
    rules = language_rules({"languages_imported": True, "pov_character_name": "Elil"})
    assert rules.startswith("\n**LANGUAGE RULES**")
    for must in ("NEVER explain, describe or comment on a language",
                 "At most ONE native word or phrase in the scene",
                 "Native speech available this scene",
                 "NEVER gloss a word in narration",
                 "Untranslated speech only when Elil would not understand it",
                 "Never coin a word"):
        assert must in rules, must
    # the Language line alone is enough for a hand-built context
    assert language_rules({"languages_section": "**Language:** speaks Quqo."})
    # and the rules ride craft_rules, so every writing call carries them
    with_rules = craft_rules({"languages_imported": True, "pov_character_name": "Elil"})
    assert with_rules.startswith("**WRITING RULES:**") and "LANGUAGE RULES" in with_rules
    assert "FOCUS ON" not in with_rules


# ============================================================================
# The builders: writer and planner contexts
# ============================================================================

@pytest.fixture
def world():
    pytest.importorskip("chromadb")
    from novel_agent.memory.vector_store import VectorStore
    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    (d / "state.json").write_text(json.dumps({"current_tick": 1, "active_character": "C000"}))
    lang = json.loads((FIXTURES / "region-small-languages.json").read_text(encoding="utf-8"))
    region = json.loads((FIXTURES / "region-small.json").read_text(encoding="utf-8"))
    entities = map_languages(lang, region)
    memory = MemoryManager(d)
    created = persist_languages(memory, entities)
    state = {"novel_name": "N", "current_tick": 1, "active_character": "C000",
             "story_foundation": {"genre": "fantasy"},
             "world": {"languages": languages_state_record("x", entities, created)}}
    memory.save_character(Character(id="C000", first_name="Tukkuye", role="protagonist",
                                    description="the lead",
                                    metadata={"worldgen": {"people": "R0", "language": "Quqo"}}))
    memory.save_character(Character(id="C001", first_name="Zhailo", role="supporting",
                                    description="an innkeeper",
                                    metadata={"worldgen": {"people": "R2", "language": "Gaipo"}}))
    memory.save_character(Character(id="C002", first_name="Elil", family_name="Urnorn",
                                    role="supporting", description="a stranger"))
    memory.save_location(Location(id="L000", name="Swanhin", description="a Quqo city",
                                  metadata={"worldgen": {"realm_id": "R0"}}))
    memory.save_location(Location(id="L001", name="Vavar", description="a Gaipo town",
                                  metadata={"worldgen": {"realm_id": "R2"}}))
    memory.save_location(Location(id="L002", name="The wilds", description="old forest",
                                  metadata={"worldgen": {"realm_id": "elder"}}))
    memory.save_location(Location(id="L003", name="Nowhere", description="unplaced"))
    yield memory, VectorStore(d), state
    shutil.rmtree(d, ignore_errors=True)


def _plan(pov="C000", location="L000", **extra):
    return {"pov_character": pov, "target_location": location,
            "scene_intention": "x", "key_change": "y", **extra}


def test_writer_context_language_situation(world):
    from novel_agent.agent.writer_context import WriterContextBuilder
    from novel_agent.configs.config import Config
    memory, vector, state = world
    wcb = WriterContextBuilder(memory, vector, Config())
    none = {"actions_executed": []}

    # at home: shared
    ctx = wcb.build_writer_context(_plan(), none, state)
    assert ctx["language_situation"]["status"] == SHARED
    assert "Language situation: everyone present speaks Quqo." in ctx["pov_character_details"]
    assert ctx["pov_character_details"].index("**Language:** speaks Quqo (related to Gaipo).") \
        < ctx["pov_character_details"].index("Language situation:")

    # in the related realm's town, talking to its innkeeper (named in dialogue_targets)
    ctx = wcb.build_writer_context(
        _plan(location="L001", dialogue_targets={"min_exchanges": 3, "participants": ["Zhailo"]}), none, state)
    s = ctx["language_situation"]
    assert s["status"] == RELATED
    assert [o["label"] for o in s["others"]] == ["the people here", "Zhailo"]
    assert "Tukkuye speaks Quqo; the people here speak Gaipo, related to Quqo" in s["line"]
    assert s["line"] in ctx["pov_character_details"]
    assert "Language situation" in format_writer_prompt(ctx)

    # in the wilds: foreign; a participant given by id; a character without a people is skipped
    ctx = wcb.build_writer_context(
        _plan(location="L002", dialogue_targets={"participants": "C001, C002"}), none, state)
    s = ctx["language_situation"]
    assert s["status"] == FOREIGN
    assert [(o["label"], o["relation"]) for o in s["others"]] == [("the people here", FOREIGN), ("Zhailo", RELATED)]

    # a character created by this tick's plan is in the room
    created = {"actions_executed": [{"tool": "character.generate", "args": {}, "success": True,
                                     "result": {"success": True, "character_id": "C001", "name": "Zhailo"}}]}
    ctx = wcb.build_writer_context(_plan(location="L003"), created, state)
    assert ctx["language_situation"]["status"] == RELATED
    assert [o["label"] for o in ctx["language_situation"]["others"]] == ["Zhailo"]

    # location fallback: a POV with no people takes the location's realm
    ctx = wcb.build_writer_context(_plan(pov="C002", location="L001"), none, state)
    assert ctx["pov_people"] == "R2" and ctx["languages_section"] == "**Language:** speaks Gaipo (related to Quqo)."
    assert ctx["language_situation"]["status"] == SHARED

    # nothing known: unknown, no line, but the rules still apply (languages exist)
    ctx = wcb.build_writer_context(_plan(pov="C002", location="L003"), none, state)
    assert ctx["language_situation"]["status"] == UNKNOWN and ctx["language_situation"]["line"] == ""
    assert "Language situation" not in ctx["pov_character_details"]
    assert ctx["languages_imported"] is True and "LANGUAGE RULES" in format_writer_prompt(ctx)

    # no languages imported: unknown, no block, no rules
    plain = {"novel_name": "N", "current_tick": 1, "story_foundation": {"genre": "fantasy"}}
    ctx = wcb.build_writer_context(_plan(), none, plain)
    assert ctx["language_situation"]["status"] == UNKNOWN and ctx["languages_imported"] is False
    assert ctx["native_speech"] == [] and "LANGUAGE RULES" not in format_writer_prompt(ctx)


def test_requested_native_speech_reaches_the_writer(world):
    """The executor's language.* results become the 'native speech available
    this scene' list, so the writer uses exactly what the planner asked for."""
    from novel_agent.agent.runtime import PlanExecutor
    from novel_agent.agent.writer_context import WriterContextBuilder
    from novel_agent.configs.config import Config
    from novel_agent.tools.language_tools import language_tools_for
    from novel_agent.tools.name_generator import NameGenerator
    from novel_agent.tools.registry import ToolRegistry
    memory, vector, state = world
    data_dir = Path(__file__).resolve().parent.parent.parent / "novel_agent" / "data" / "names"
    gen = NameGenerator(data_dir, languages_file=bank_file_path(memory.project_path))
    registry = ToolRegistry()
    for tool in language_tools_for(bank_file_path(memory.project_path), gen):
        registry.register(tool)
    plan = _plan(actions=[
        {"tool": "language.phrase", "args": {"people": "Vokekuk Principality", "kind": "greeting"}},
        {"tool": "language.word", "args": {"people": "Quqo", "english": "water"}},
        {"tool": "language.word", "args": {"people": "Quqo", "english": "photosynthesis"}},
        {"tool": "language.phrase", "args": {"people": "the Moon Folk", "kind": "oath"}},
    ])
    results = PlanExecutor(registry, memory, vector).execute_plan(plan, tick=1)
    assert results["success"] is True and len(results["actions_executed"]) == 4   # nothing halted the tick

    wcb = WriterContextBuilder(memory, vector, Config())
    ctx = wcb.build_writer_context(plan, results, state)
    assert [i["text"] for i in ctx["native_speech"]] == ["Kuyek yele!", "numu"]
    details = ctx["pov_character_details"]
    assert "**Native speech available this scene**" in details
    assert "“Kuyek yele!” — Greetings, friend! (Quqo greeting)" in details
    assert "“numu” — water /ˈnumu/ (Quqo word)" in details
    assert "photosynthesis" not in details and "Moon Folk" not in details
    prompt = format_writer_prompt(ctx)
    assert "Native speech requested: “Kuyek yele!” (Greetings, friend!, Quqo)" in ctx["tool_results_summary"]
    assert "found nothing usable" in ctx["tool_results_summary"]
    assert "Kuyek yele!" in prompt and "LANGUAGE RULES" in prompt

    # a plan that requested nothing offers nothing, and the rules say so
    ctx = wcb.build_writer_context(_plan(), {"actions_executed": []}, state)
    assert ctx["native_speech"] == [] and "Native speech available" not in ctx["pov_character_details"]
    assert "If nothing is listed, the scene has no native words at all" in format_writer_prompt(ctx)


def test_planner_context_carries_the_language_fact(world):
    from novel_agent.agent.context import ContextBuilder
    from novel_agent.tools.registry import ToolRegistry
    memory, vector, state = world
    tukkuye = memory.load_character("C000")
    tukkuye.current_state.location_id = "L001"
    memory.save_character(tukkuye)

    fact = planner_language_fact(memory, state)
    assert fact["status"] == RELATED
    assert fact["line"].startswith("Language situation: Tukkuye speaks Quqo; the people here speak Gaipo, related to Quqo")
    assert planner_language_fact(memory, {"active_character": "C000"})["status"] == UNKNOWN
    assert planner_language_fact(memory, {**state, "active_character": "C999"})["status"] == UNKNOWN

    from novel_agent.configs.config import Config
    cb = ContextBuilder(memory, vector, ToolRegistry(), Config())
    context = cb.build_planner_context(state)
    assert context["language_situation"]["status"] == RELATED
    assert context["active_character_details"].rstrip().endswith(fact["line"])
    plain = cb.build_planner_context({**state, "world": {}})
    assert plain["language_situation"]["status"] == UNKNOWN
    assert "Language situation" not in plain["active_character_details"]


def test_multi_stage_tactical_prompt_carries_the_language_fact(world):
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner
    from novel_agent.configs.config import Config
    from novel_agent.tools.registry import ToolRegistry
    memory, vector, state = world
    tukkuye = memory.load_character("C000")
    tukkuye.current_state.location_id = "L002"
    memory.save_character(tukkuye)
    planner = MultiStagePlanner(None, memory, vector, ToolRegistry(), Config())
    prompt = planner._build_tactical_prompt("x", {}, state)
    assert "## Language Situation" in prompt
    assert "the people here speak Cocqor, which shares nothing with Quqo" in prompt
    assert "Request at most one native phrase or word" in prompt
    assert "## Language Situation" not in planner._build_tactical_prompt("x", {}, {**state, "world": {}})
