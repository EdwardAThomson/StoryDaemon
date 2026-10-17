"""The language.phrase and language.word tools (novel_agent/tools/language_tools.py)
and the plumbing that carries their results to the writer.

Runs on tests/fixtures/region-small-languages.json: R0 (Quqo) has a phrasebook,
R2 (Gaipo) and the elder tongue do not. No LLM anywhere. The tools are
deterministic lookups in the project's memory/languages.json, so a request
answered once is answered the same way every time.
"""
import json
import pathlib
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.languages_import import bank_file_path, map_languages, persist_languages
from novel_agent.memory.manager import MemoryManager
from novel_agent.tools.language_tools import (
    PHRASE_KINDS,
    LanguageLexicon,
    LanguagePhraseTool,
    LanguageWordTool,
    language_tools_for,
    native_speech_from_results,
    native_speech_section,
)
from novel_agent.tools.name_generator import NameGenerator
from novel_agent.tools.registry import ToolRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "novel_agent" / "data" / "names"
MAIN = pathlib.Path(__file__).resolve().parents[2] / "novel_agent" / "cli" / "main.py"


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    (d / "state.json").write_text(json.dumps({"current_tick": 1, "active_character": "C000"}))
    lang = json.loads((FIXTURES / "region-small-languages.json").read_text(encoding="utf-8"))
    region = json.loads((FIXTURES / "region-small.json").read_text(encoding="utf-8"))
    persist_languages(MemoryManager(d), map_languages(lang, region))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def lexicon(project):
    gen = NameGenerator(DATA_DIR, languages_file=bank_file_path(project))
    return LanguageLexicon(bank_file_path(project), name_generator=gen)


# ============================================================================
# language.phrase
# ============================================================================

def test_phrase_of_each_kind_from_the_phrasebook(lexicon):
    tool = LanguagePhraseTool(lexicon)
    assert tool.name == "language.phrase"
    assert tool.parameters["kind"]["enum"] == list(PHRASE_KINDS)
    greeting = tool.execute(people="Vokekuk Principality", kind="greeting")
    assert greeting == {
        "success": True, "found": True, "kind": "greeting",
        "people": "R0", "people_name": "Vokekuk Principality", "language": "Quqo",
        "text": "Kuyek yele!", "gloss": "greetings friend", "english": "Greetings, friend!",
        "word_only": False,
    }
    for kind in PHRASE_KINDS:
        r = tool.execute(people="R0", kind=kind)
        assert r["found"] and r["kind"] == kind and r["text"] and r["english"], kind
    # the same request always gives the same phrase
    assert tool.execute(people="R0", kind="oath") == tool.execute(people="quqo", kind="oath")
    assert tool.execute(people="R0", kind="oath")["text"] == "Kukeme tekvos!"


def test_phrase_resolves_the_people_sanitize_not_trust(lexicon):
    tool = LanguagePhraseTool(lexicon)
    assert tool.execute(people="Quqo", kind="toast")["people"] == "R0"              # by language
    assert tool.execute(people="vokekuk principalty", kind="toast")["people"] == "R0"  # near miss
    assert tool.execute(people="a Vokekuk Principality guard", kind="toast")["people"] == "R0"
    unknown = tool.execute(people="the Moon Folk", kind="toast")
    assert unknown["success"] is False and unknown["found"] is False
    assert "No imported language for 'the Moon Folk'" in unknown["error"]
    assert "Vokekuk Principality (Quqo)" in unknown["error"]
    assert "text" not in unknown


def test_phrase_kind_near_miss_and_missing_kind(lexicon):
    tool = LanguagePhraseTool(lexicon)
    assert tool.execute(people="R0", kind="greetings")["kind"] == "greeting"
    assert tool.execute(people="R0", kind="Oath")["kind"] == "oath"
    r = tool.execute(people="R0", kind="lullaby")
    assert r["success"] and r["found"] is False and "no lullaby phrase" in r["note"]
    assert "text" not in r


def test_phrase_without_a_phrasebook_is_one_word_and_says_so(lexicon):
    """A pair of lexicon words pasted together ("water fire") is not a
    phrase; the fallback is the single nearest word, flagged."""
    tool = LanguagePhraseTool(lexicon)
    r = tool.execute(people="Principality of Vavarsrai", kind="greeting")
    assert r["found"] and r["word_only"] is True and r["language"] == "Gaipo"
    assert " " not in r["text"]
    assert r["gloss"] == "friend" == r["english"]      # the first KIND_WORDS meaning Gaipo has
    assert "no phrasebook" in r["note"] and "single word" in r["note"]
    curse = tool.execute(people="R2", kind="curse")
    assert curse["found"] and curse["gloss"] in ("death", "blood", "fire", "die") and " " not in curse["text"]
    # a kind nothing in the lexicon is near: found false, never coined
    toast = tool.execute(people="elder", kind="toast")
    assert toast["gloss"] in ("friend", "king", "home")  # the elder lexicon shares the fixture's words
    nothing = LanguageLexicon(None)
    nothing.peoples = {"X": {"people_name": "X", "language": "Xish", "family": None,
                             "family_name": "", "lexicon": [{"english": "zzz", "spelling": "q"}],
                             "phrases": []}}
    r = nothing.phrase("X", "toast")
    assert r["found"] is False and "do not coin" in r["note"]


# ============================================================================
# language.word
# ============================================================================

def test_word_exact_then_nearest_then_not_found(lexicon):
    tool = LanguageWordTool(lexicon)
    assert tool.name == "language.word"
    water = tool.execute(people="R0", english="water")
    assert water == {
        "success": True, "found": True, "english": "water",
        "people": "R0", "people_name": "Vokekuk Principality", "language": "Quqo",
        "word": "numu", "text": "numu", "ipa": "ˈnumu", "pos": "n",
        "matched_english": "water", "gloss": "water", "approximate": False,
    }
    assert tool.execute(people="R0", english="Water")["word"] == "numu"       # case
    near = tool.execute(people="R0", english="rivers")
    assert near["found"] and near["approximate"] is True and near["matched_english"] == "river"
    assert near["word"] == "tuy" and "nearest meaning is 'river'" in near["note"]
    missing = tool.execute(people="R0", english="photosynthesis")
    assert missing["success"] is True and missing["found"] is False
    assert "no word for 'photosynthesis'" in missing["note"] and "do not coin" in missing["note"]
    assert "word" not in missing and "text" not in missing
    empty = tool.execute(people="R0", english="")
    assert empty["found"] is False and empty["note"] == "No meaning given."


def test_word_unknown_people_and_a_bank_without_lexicon(lexicon, project):
    tool = LanguageWordTool(lexicon)
    r = tool.execute(people="Atlantis", english="water")
    assert r["success"] is False and r["found"] is False and "Atlantis" in r["error"]
    # a bank written before lexicons were kept: tolerated, nothing registered
    bank = json.loads(bank_file_path(project).read_text(encoding="utf-8"))
    for people in bank["peoples"].values():
        people.pop("lexicon", None)
        people.pop("phrases", None)
    old = project / "memory" / "old-languages.json"
    old.write_text(json.dumps(bank), encoding="utf-8")
    assert LanguageLexicon(old).has_words is False
    assert language_tools_for(old) == []
    r = LanguageLexicon(old).word("R0", "water")
    assert r["found"] is False and "no lexicon" in r["note"]


def test_tools_never_raise(lexicon):
    phrase, word = LanguagePhraseTool(lexicon), LanguageWordTool(lexicon)
    assert phrase.execute(people=None, kind=None)["success"] is False
    assert word.execute(people=None, english=None)["success"] is False
    lexicon.peoples["R0"]["lexicon"] = [{"english": 5, "spelling": "x"}]   # corrupt data: an error result, not an exception
    assert word.execute(people="R0", english="water")["success"] is False


# ============================================================================
# Registration and plumbing
# ============================================================================

def test_language_tools_are_offered_only_when_languages_were_imported(project):
    gen = NameGenerator(DATA_DIR, languages_file=bank_file_path(project))
    tools = language_tools_for(bank_file_path(project), gen)
    assert [t.name for t in tools] == ["language.phrase", "language.word"]
    assert language_tools_for(None) == []
    assert language_tools_for(project / "memory" / "absent.json") == []
    registry = ToolRegistry()
    for t in tools:
        registry.register(t)
    description = registry.get_tools_description()
    assert "**language.phrase**" in description and "people (string), kind (string)" in description
    assert "**language.word**" in description and "people (string), english (string)" in description
    # the planner is told which peoples it may name
    assert "Vokekuk Principality (Quqo)" in tools[0].parameters["people"]["description"]


def test_tick_and_run_both_register_the_language_tools():
    src = MAIN.read_text()
    for fn in ("tick", "run"):
        i = src.index(f"\ndef {fn}(")
        nxt = src.find("\ndef ", i + 5)
        body = src[i:nxt if nxt > 0 else len(src)]
        assert re.search(r"for language_tool in language_tools_for\(.*\):\s*\n\s*tool_registry\.register\(language_tool\)", body), fn


def test_native_speech_from_results_keeps_only_what_was_found():
    results = {"actions_executed": [
        {"tool": "language.phrase", "args": {"people": "R0", "kind": "greeting"}, "success": True,
         "result": {"success": True, "found": True, "kind": "greeting", "language": "Quqo",
                    "text": "Kuyek yele!", "gloss": "greetings friend", "english": "Greetings, friend!",
                    "word_only": False}},
        {"tool": "language.word", "args": {"people": "R0", "english": "water"}, "success": True,
         "result": {"success": True, "found": True, "language": "Quqo", "text": "numu", "word": "numu",
                    "ipa": "ˈnumu", "gloss": "water", "english": "water"}},
        {"tool": "language.word", "args": {"people": "R0", "english": "zzz"}, "success": True,
         "result": {"success": True, "found": False, "language": "Quqo", "english": "zzz"}},
        {"tool": "language.phrase", "args": {"people": "Mars", "kind": "oath"}, "success": True,
         "result": {"success": False, "found": False, "error": "x"}},
        {"tool": "language.phrase", "args": {"people": "R0", "kind": "greeting"}, "success": True,
         "result": {"success": True, "found": True, "kind": "greeting", "language": "Quqo",
                    "text": "Kuyek yele!", "english": "Greetings, friend!"}},        # duplicate
        {"tool": "character.generate", "args": {}, "success": True, "result": {"success": True}},
        {"tool": "language.word", "args": {}, "success": False, "error": "boom"},
    ]}
    items = native_speech_from_results(results)
    assert [i["text"] for i in items] == ["Kuyek yele!", "numu"]
    assert items[0] == {"text": "Kuyek yele!", "meaning": "Greetings, friend!", "gloss": "greetings friend",
                        "ipa": "", "language": "Quqo", "kind": "greeting"}
    assert items[1]["kind"] == "word" and items[1]["ipa"] == "ˈnumu"
    section = native_speech_section(items)
    assert section.startswith("**Native speech available this scene**")
    assert "“Kuyek yele!” — Greetings, friend! (Quqo greeting)" in section
    assert "“numu” — water /ˈnumu/ (Quqo word)" in section
    assert native_speech_from_results(None) == [] and native_speech_from_results({}) == []
    assert native_speech_section([]) == ""
