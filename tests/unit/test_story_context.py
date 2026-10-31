"""Story-so-far context: planner sees recent scenes, synopsis scales, writer sees canon.

All fakes: no LLM and no embedding model. The vector store is a stub, since
these tests are about what reaches the prompt, not about ranking quality.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.multi_stage_planner import MultiStagePlanner
from novel_agent.agent.story_context import (cast_roster, recent_scene_summaries,
                                             story_so_far)
from novel_agent.agent.writer_context import WriterContextBuilder
from novel_agent.configs.config import Config
from novel_agent.memory.entities import Character, Location, Lore, OpenLoop, Scene
from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.synopsis import load_synopsis, update_synopsis


class StubVector:
    """Lore search returns everything in order; loop ranking prefers 'vault'."""

    def __init__(self, memory=None):
        self.memory = memory

    def search_lore(self, query, n_results=5, **_):
        return [{"id": l.id} for l in self.memory.load_all_lore()][:n_results]

    def rank_by_similarity(self, query, texts):
        return [1.0 if "vault" in t else 0.1 for t in texts]

    def search_scenes(self, query, limit=3):
        return []


class FakeLLM:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        if prompt.startswith("Summarize this stretch"):
            return f"Arc paragraph {len(self.prompts)}."
        return f"Folded synopsis {len(self.prompts)}."


class Tools:
    def get_tools_description(self):
        return "(tools)"


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 12, "active_character": "C000"}))
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Elil", family_name="Urnorn",
                                role="protagonist", description="the lead"))
    mm.save_character(Character(id="C001", first_name="Brann", role="supporting"))
    mm.save_location(Location(id="L000", name="The Vault"))
    for i in range(12):
        mm.save_scene(Scene(id=f"S{i:03d}", tick=i, title=f"Scene {i}",
                            summary=[f"Event number {i} happened.", f"Detail {i}."]))
    yield d, mm
    shutil.rmtree(d, ignore_errors=True)


def test_recent_scene_summaries_are_chronological(project):
    _, mm = project
    text = recent_scene_summaries(mm, 3)
    assert text.index("Event number 9") < text.index("Event number 10") < text.index("Event number 11")
    assert "Event number 8" not in text


def test_strategic_prompt_sees_recent_scenes(project):
    _, mm = project
    planner = MultiStagePlanner(None, mm, StubVector(mm), Tools(), Config())
    prompt = planner._build_strategic_prompt({"current_tick": 12, "active_character": "C000",
                                              "story_foundation": {}})
    assert "## Recent Scenes" in prompt
    assert "Event number 11" in prompt
    assert "continue from where it left off" in prompt


def test_tactical_prompt_has_rosters_and_named_relationships(project):
    _, mm = project
    planner = MultiStagePlanner(None, mm, StubVector(mm), Tools(), Config())

    class Rel:
        character_a, character_b, relationship_type, status = "C000", "C001", "rivals", "strained"

    prompt = planner._build_tactical_prompt(
        "Elil opens the vault", {"relationships": [Rel()]},
        {"current_tick": 12, "active_character": "C000"})
    assert "- C001: Brann (supporting)" in prompt
    assert "- L000: The Vault" in prompt
    assert "Elil (C000) ↔ Brann (C001): rivals (strained)" in prompt
    assert "Event number 11" in prompt


def test_synopsis_folds_full_arcs_and_tail_is_bounded(project):
    _, mm = project
    llm = FakeLLM()
    cfg = Config()
    result = update_synopsis(mm, llm, cfg)
    assert result["arcs_closed"] == 1          # 12 scenes, arc size 8
    data = load_synopsis(mm)
    assert data["arcs"][0]["scene_ids"] == [f"S{i:03d}" for i in range(8)]
    assert data["synopsis"] == "Arc paragraph 1."  # first arc needs no fold
    assert len(llm.prompts) == 1

    # Older-than-window: synopsis + the uncovered tail (S008), not the window.
    text = story_so_far(mm, cfg, 3)
    assert text.startswith("Arc paragraph 1.")
    assert "Event number 8" in text
    assert "Event number 9" not in text and "Event number 3" not in text

    # A second arc folds into the running synopsis.
    for i in range(12, 16):
        mm.save_scene(Scene(id=f"S{i:03d}", tick=i, title=f"Scene {i}", summary=[f"Event number {i}."]))
    assert update_synopsis(mm, llm, cfg)["arcs_closed"] == 1
    assert load_synopsis(mm)["synopsis"].startswith("Folded synopsis")
    assert "Synopsis so far:\nArc paragraph 1." in llm.prompts[-1]


def test_synopsis_failure_leaves_arc_for_next_tick(project):
    _, mm = project

    class Broken:
        def generate(self, prompt, max_tokens=None):
            raise RuntimeError("backend down")

    assert update_synopsis(mm, Broken(), Config()) == {"arcs_closed": 0}
    assert load_synopsis(mm)["arcs"] == []


def test_synopsis_off_renders_nothing(project):
    _, mm = project
    cfg = Config()
    cfg.set("generation.story_synopsis", False)
    assert update_synopsis(mm, FakeLLM(), cfg) == {"arcs_closed": 0}
    assert story_so_far(mm, cfg, 3) == ""


def test_writer_gets_canon_story_so_far_and_search_results(project):
    _, mm = project
    mm.save_lore(Lore(id="LR001", content="Vault doors only open at dawn.", lore_type="rule"))
    mm.save_lore(Lore(id="LR002", content="Disputed claim.", status="disputed"))
    mm.add_open_loop(OpenLoop(id="OL1", description="Who sealed the vault?"))
    mm.add_open_loop(OpenLoop(id="OL2", description="Brann's missing brother"))
    mm.add_open_loop(OpenLoop(id="OL3", description="The unpaid debt"))
    update_synopsis(mm, FakeLLM(), Config())

    cfg = Config()
    cfg.set("generation.writer_canon_loops", 2)  # the pinned loop counts toward it
    wcb = WriterContextBuilder(mm, StubVector(mm), cfg)
    plan = {"pov_character": "C000", "scene_intention": "Elil opens the vault",
            "key_change": "the door gives", "plot_beat": {"description": "x", "advances_loops": ["OL3"]}}
    results = {"actions_executed": [{"tool": "memory.search", "args": {"query": "vault"},
                                     "result": {"results": [{"entity_id": "S002", "entity_type": "scene",
                                                             "name": "", "snippet": "They found the key."}]}}]}
    ctx = wcb.build_writer_context(plan, results, {"current_tick": 12, "story_foundation": {}})

    recent = ctx["recent_context"]
    assert recent.index("## Story So Far") < recent.index("## Established Canon") < recent.index("## Recent Scenes")
    assert "Vault doors only open at dawn." in recent
    assert "Disputed claim." not in recent
    assert "The unpaid debt" in recent          # pinned by the beat
    assert "Who sealed the vault?" in recent    # best-ranked of the rest
    assert "Brann's missing brother" not in recent
    assert "They found the key." in ctx["tool_results_summary"]


def test_synopsis_is_told_which_deaths_are_confirmed(project):
    from novel_agent.memory.entity_status import set_status
    _, mm = project
    cfg = Config()
    llm = FakeLLM()
    update_synopsis(mm, llm, cfg)
    assert "Confirmed changes: none" in llm.prompts[0]

    brann = mm.load_character("C001")
    set_status(brann, "dead", 9, "S009", "Brann did not get out.")
    mm.save_character(brann)
    for i in range(12, 16):
        mm.save_scene(Scene(id=f"S{i:03d}", tick=i, title=f"Scene {i}", summary=[f"Event {i}."]))
    llm.prompts.clear()
    update_synopsis(mm, llm, cfg)
    arc_prompt, fold_prompt = llm.prompts
    for prompt in (arc_prompt, fold_prompt):
        assert "- Brann: dead in S009" in prompt


def test_strategic_intention_budget_and_empty_retry(project):
    _, mm = project

    class Thinker:
        def __init__(self):
            self.budgets = []

        def generate(self, prompt, max_tokens=None):
            self.budgets.append(max_tokens)
            return None if len(self.budgets) == 1 else "Elil opens the vault."

    llm = Thinker()
    planner = MultiStagePlanner(llm, mm, StubVector(mm), Tools(), Config())
    intention = planner._strategic_planning({"current_tick": 12, "active_character": "C000",
                                             "story_foundation": {}})
    assert intention == "Elil opens the vault."
    assert llm.budgets == [1000, 2000]


def test_overlong_summary_is_sent_back_once(project):
    _, mm = project

    class Verbose:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, max_tokens=None):
            self.prompts.append(prompt)
            if prompt.startswith("The text below is"):
                return "Short arc."
            return "word " * 400

    cfg = Config()
    cfg.set("generation.synopsis_max_words", 100)   # arc ceiling 60 words
    llm = Verbose()
    assert update_synopsis(mm, llm, cfg)["arcs_closed"] == 1
    assert load_synopsis(mm)["arcs"][0]["summary"] == "Short arc."
    assert sum(p.startswith("The text below is") for p in llm.prompts) == 1


def test_failed_shortening_keeps_the_original(project):
    _, mm = project

    class NoShorten:
        def generate(self, prompt, max_tokens=None):
            if prompt.startswith("The text below is"):
                raise RuntimeError("down")
            return "word " * 400

    cfg = Config()
    cfg.set("generation.synopsis_max_words", 100)
    assert update_synopsis(mm, NoShorten(), cfg)["arcs_closed"] == 1
    assert len(load_synopsis(mm)["arcs"][0]["summary"].split()) == 400
