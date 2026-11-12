"""Style profiles (generation.style_profile): measured habits as writer targets.

No model calls: the counts are pure Python and the writer runs on a fake LLM.
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent import style_profile as sp
from novel_agent.configs.config import Config


class Cfg:
    def __init__(self, **kw):
        self.kw = kw

    def get(self, key, default=None):
        if key in self.kw:
            return self.kw[key]
        return Config().get(key, default)


# ---- measuring ---------------------------------------------------------------

TEXT = """She came in; he rose. "I cannot stay," said she, "and I won't."

He bowed--and was silent; the clock ticked on through the long grey afternoon while the two of them sat and neither of them found anything at all to say to the other."""


def test_measure_counts_punctuation_speech_and_contractions():
    m = sp.measure(TEXT)
    words = len(sp._words(TEXT))
    assert m["semicolons_per_1k"] == round(1000 * 2 / words, 1)
    assert m["dashes_per_1k"] == round(1000 * 1 / words, 1)
    assert m["contractions_per_1k"] == round(1000 * 1 / words, 1)     # won't
    assert m["said_share"] == 1.0
    assert 0 < m["speech_word_pct"] < 30
    assert m["long_sentence_pct"] > 0                                  # the last sentence
    assert set(sp.TARGET_KEYS) <= set(m)


def test_measure_refuses_an_empty_text():
    with pytest.raises(ValueError):
        sp.measure("  \n ")


def _chapter(word, n=250):
    return " ".join([word] * n) + "."


BOOK = f"""The Project Gutenberg eBook header
*** START OF THE PROJECT GUTENBERG EBOOK A NOVEL ***

A NOVEL. {_chapter('preface')}

CHAPTER I.

    An epigraph, indented.

{_chapter('alpha')} _Indeed_ she said.

[Illustration: a lady at a window]

CHAPTER II.

{_chapter('beta')} the test passage is here.

CHAPTER III.

{_chapter('gamma')}

*** END OF THE PROJECT GUTENBERG EBOOK A NOVEL ***
licence text {_chapter('licence')}"""


def test_book_chapters_keeps_only_the_story():
    chapters = sp.book_chapters(BOOK, leave_out=["the test passage"], drop_indented=True)
    assert len(chapters) == 2
    joined = "\n".join(chapters)
    assert "alpha" in joined and "gamma" in joined
    assert "preface" not in joined                  # front matter
    assert "licence" not in joined                  # Gutenberg footer
    assert "beta" not in joined                     # left out
    assert "epigraph" not in joined and "Illustration" not in joined
    assert "Indeed" in joined and "_Indeed_" not in joined


def test_book_chapters_keeps_indented_paragraphs_unless_asked():
    assert "epigraph" in "\n".join(sp.book_chapters(BOOK))


# ---- loading -------------------------------------------------------------------

def test_shipped_profiles_load():
    assert {"marriage", "pride"} <= set(sp.available_profiles())
    m = sp.load_profile("marriage")
    assert m["sentence_mean_words"] > 20 and m["semicolons_per_1k"] > 10


def test_unknown_profile_raises_with_the_choices():
    with pytest.raises(ValueError, match="marriage"):
        sp.load_profile("marriagge")


def test_profile_missing_a_count_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"sentence_mean_words": 20}))
    with pytest.raises(ValueError, match="lacks"):
        sp.load_profile(str(bad))


def test_profile_from_config():
    assert sp.profile_from_config(Config()) is None             # default unset
    assert sp.profile_from_config(Cfg(**{"generation.style_profile": "none"})) is None
    assert sp.profile_from_config(Cfg(**{"generation.style_profile": "pride"}))["name"] == "pride"


# ---- the section ---------------------------------------------------------------

def test_targets_scale_with_scene_length():
    p = sp.load_profile("marriage")
    short = sp.style_targets_section(p, 1000)
    long = sp.style_targets_section(p, 2000)
    semis = round(p["semicolons_per_1k"])
    assert f"Semicolons: about {semis} in this scene" in short
    assert f"Semicolons: about {round(p['semicolons_per_1k'] * 2)} in this scene" in long
    assert "Contractions only in speech" in short               # Ferrier uses a few


def test_no_contractions_line_for_an_author_without_them():
    text = sp.style_targets_section(sp.load_profile("pride"), 1000)
    assert "No contractions anywhere" in text


# ---- the writer ----------------------------------------------------------------

@pytest.fixture
def project():
    from novel_agent.memory.entities import Character
    from novel_agent.memory.manager import MemoryManager
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 1, "active_character": "C000"}))
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Elil", family_name="Urnorn",
                                role="protagonist", description="the lead",
                                gender="female", age_group="adult"))
    yield d, mm
    shutil.rmtree(d, ignore_errors=True)


def _writer_context(project, **config):
    from novel_agent.agent.writer_context import WriterContextBuilder
    from novel_agent.memory.vector_store import VectorStore
    d, mm = project
    plan = {"pov_character": "C000", "scene_intention": "x", "key_change": "y"}
    return WriterContextBuilder(mm, VectorStore(d), Cfg(**config)).build_writer_context(
        plan, {"actions_executed": []}, {"current_tick": 1, "story_foundation": {}})


def test_writer_prompt_has_no_targets_by_default(project):
    from novel_agent.agent.prompts import format_writer_prompt
    ctx = _writer_context(project)
    assert ctx["style_profile"] is None
    assert "Style targets" not in format_writer_prompt(ctx)


def test_writer_prompt_carries_targets_for_the_scene_length(project):
    from novel_agent.agent.prompts import format_writer_prompt
    ctx = _writer_context(project, **{"generation.style_profile": "marriage"})
    text = format_writer_prompt(ctx)
    p = sp.load_profile("marriage")
    expected = round(p["semicolons_per_1k"] * ctx["word_target"] / 1000)
    assert "Style targets" in text
    assert f"Semicolons: about {expected} in this scene" in text


def test_a_misspelled_profile_stops_the_writer(project):
    with pytest.raises(ValueError):
        _writer_context(project, **{"generation.style_profile": "marriagge"})


def test_each_section_gets_targets_for_its_own_length():
    from tests.unit.test_sectioned_writing import ON, FakeLLM, _ctx
    from novel_agent.agent.writer import SceneWriter
    ctx = _ctx(["DIALOGUE"] * 25)
    ctx["style_profile"] = sp.load_profile("marriage")
    llm = FakeLLM(["[1] Opening line.", "[11] Second part."])
    SceneWriter(llm, Cfg(**ON)).write_scene(ctx)
    assert len(llm.prompts) == 2
    assert all("Style targets" in p for p in llm.prompts)
