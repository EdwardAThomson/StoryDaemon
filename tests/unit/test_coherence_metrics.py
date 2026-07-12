"""Unit tests for the Phase 3 coherence rubric (instrumentation only)."""
import json
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import OpenLoop, Lore
from novel_agent.configs.config import Config
from novel_agent.agent.coherence_metrics import CoherenceMetrics, read_metrics


class FakeVector:
    """Stand-in VectorStore: constant similarity, no embeddings."""

    def __init__(self, value=0.5, raises=False):
        self.value = value
        self.raises = raises

    def compute_semantic_similarity(self, a, b):
        if self.raises:
            raise RuntimeError("embedding backend down")
        return self.value


class FakeLLM:
    """Stand-in LLM: returns a canned response, or raises, and records the prompt."""

    def __init__(self, out=None, raises=False):
        self.out = out
        self.raises = raises
        self.prompt = None
        self.calls = 0

    def generate(self, prompt, max_tokens=200):
        self.calls += 1
        self.prompt = prompt
        if self.raises:
            raise RuntimeError("llm backend down")
        return self.out


def _metrics_llm(project_dir, llm, vector=None, config=None):
    return CoherenceMetrics(project_dir, MemoryManager(project_dir), vector or FakeVector(),
                            config or Config(), llm)


@pytest.fixture
def project():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "memory").mkdir()
        yield project_dir


def _metrics(project_dir, vector=None):
    return CoherenceMetrics(project_dir, MemoryManager(project_dir), vector or FakeVector(), Config())


def test_empty_first_tick(project):
    cm = _metrics(project)
    rec = cm.record_tick(tick=0, scene_id="S000", scene_text="prose", word_count=120, tension_result=None)

    assert rec["loops_opened"] == 0
    assert rec["loops_closed"] == 0
    assert rec["open_loops_total"] == 0
    assert rec["contradictions_detected"] == 0
    assert rec["tension_level"] is None
    assert rec["tension_category"] is None
    assert rec["goal_relevance"] is None  # no goal_description passed
    assert rec["word_count"] == 120
    # exactly one JSONL line written
    assert cm.metrics_file.read_text().strip().count("\n") == 0
    assert len(cm.load_metrics()) == 1


def test_loops_opened_and_closed(project):
    mem = MemoryManager(project)
    mem.add_open_loop(OpenLoop(id="OL1", created_in_scene="S001", description="a"))
    mem.add_open_loop(OpenLoop(id="OL2", created_in_scene="S001", description="b"))
    mem.resolve_open_loop("OL1", "S001", "resolved here")

    cm = CoherenceMetrics(project, mem, FakeVector(), Config())
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="x", word_count=10, tension_result=None)

    assert rec["loops_opened"] == 2
    assert rec["loops_closed"] == 1
    assert rec["open_loops_total"] == 1


def test_contradictions_deduped_by_pair(project):
    mem = MemoryManager(project)
    # As the real detector records it: both sides carry a detail, each stamped with its own tick.
    mem.save_lore(Lore(id="L001", tick=1, content="passive",
                       contradiction_details=[{"with": "L002", "canon": "L001", "reason": "r",
                                               "detected_tick": 1, "method": "llm"}]))
    mem.save_lore(Lore(id="L002", tick=2, content="destroys",
                       contradiction_details=[{"with": "L001", "canon": "L001", "reason": "r",
                                               "detected_tick": 2, "method": "llm"}]))
    cm = CoherenceMetrics(project, mem, FakeVector(), Config())

    # Detected on tick 2 (the fresh side) — counted once, not twice.
    assert cm.record_tick(tick=2, scene_id="S002", tension_result=None)["contradictions_detected"] == 1
    # The older side carries detected_tick == 1.
    assert cm.record_tick(tick=1, scene_id="S001", tension_result=None)["contradictions_detected"] == 1
    # A tick with no detections.
    assert cm.record_tick(tick=3, scene_id="S003", tension_result=None)["contradictions_detected"] == 0


def test_goal_relevance_embedding_fallback_when_no_llm(project):
    # No LLM wired in -> embedding gauge, scaled from 0-1 to the 0-10 scale.
    cm = _metrics(project, FakeVector(value=0.5))
    with_goal = cm.record_tick(tick=1, scene_id="S001", scene_text="prose",
                               tension_result=None, goal_description="defeat the empire")
    assert with_goal["goal_relevance"] == 5.0
    assert with_goal["goal_relevance_method"] == "embedding"

    without_goal = cm.record_tick(tick=2, scene_id="S002", scene_text="prose", tension_result=None)
    assert without_goal["goal_relevance"] is None
    assert without_goal["goal_relevance_method"] is None


def test_tension_passthrough(project):
    cm = _metrics(project)
    enabled = cm.record_tick(tick=1, scene_id="S001",
                             tension_result={"enabled": True, "tension_level": 7, "tension_category": "high"})
    assert enabled["tension_level"] == 7
    assert enabled["tension_category"] == "high"

    # enabled=False must not populate tension
    disabled = cm.record_tick(tick=2, scene_id="S002",
                              tension_result={"enabled": False, "tension_level": 3})
    assert disabled["tension_level"] is None


def test_tension_recorded_when_rewrite_disabled(project):
    # Regression (2026-07 sunshine test): with coherence.tension_rewrite off,
    # _maybe_rewrite_for_tension returns the scored result untouched, and the
    # rubric must still record it. The rewrite-produced fields keep the same
    # convention as an enabled-but-not-fired tick: rewritten False,
    # tension_pre_rewrite null.
    from novel_agent.agent.agent import StoryAgent

    cfg = Config()
    cfg.set("coherence.tension_rewrite", False)
    agent = StoryAgent.__new__(StoryAgent)  # the gate-off path reads only agent.config
    agent.config = cfg

    scored = {"enabled": True, "tension_level": 4, "tension_category": "rising"}
    _, tension_result = agent._maybe_rewrite_for_tension(
        {"text": "calm prose", "word_count": 2}, scored, 16, {}
    )

    rec = _metrics(project).record_tick(tick=16, scene_id="S016", tension_result=tension_result)
    assert rec["tension_level"] == 4
    assert rec["tension_category"] == "rising"
    assert rec["tension_rewritten"] is False
    assert rec["tension_pre_rewrite"] is None


def test_tension_recorded_without_enabled_flag(project):
    # A tension result that never set the 'enabled' flag still carries the scored
    # level; the recorder must not drop it. Only an explicit enabled=False
    # (tension tracking off) means null, per test_tension_passthrough.
    cm = _metrics(project)
    rec = cm.record_tick(tick=3, scene_id="S003",
                         tension_result={"tension_level": 6, "tension_category": "rising"})
    assert rec["tension_level"] == 6
    assert rec["tension_category"] == "rising"


def test_append_and_last_wins(project):
    cm = _metrics(project)
    cm.record_tick(tick=0, scene_id="S000", word_count=100, tension_result=None)
    cm.record_tick(tick=1, scene_id="S001", word_count=200, tension_result=None)
    cm.record_tick(tick=1, scene_id="S001", word_count=250, tension_result=None)  # re-run of tick 1

    series = cm.load_metrics()
    assert [r["tick"] for r in series] == [0, 1]  # de-duped, sorted
    tick1 = next(r for r in series if r["tick"] == 1)
    assert tick1["word_count"] == 250  # latest wins


def test_graceful_degradation_on_similarity_failure(project):
    cm = _metrics(project, FakeVector(raises=True))
    # Similarity raises, but the record still persists with goal_relevance=None.
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="prose",
                         tension_result=None, goal_description="some goal")
    assert rec["goal_relevance"] is None
    assert rec["word_count"] == 0
    assert len(cm.load_metrics()) == 1


def test_corrupt_line_skipped_on_read(project):
    cm = _metrics(project)
    cm.record_tick(tick=0, scene_id="S000", tension_result=None)
    with open(cm.metrics_file, "a", encoding="utf-8") as f:
        f.write("this is not json\n")
        f.write("\n")
    series = cm.load_metrics()
    assert len(series) == 1
    assert series[0]["tick"] == 0


def test_records_arc_target_and_delta(project):
    # Real Config() has the default arc curve (length 40). Progress 10/40 = 0.25,
    # which hits the [0.25, 5] control point exactly.
    cm = _metrics(project)
    rec = cm.record_tick(tick=10, scene_id="S010",
                         tension_result={"enabled": True, "tension_level": 8, "tension_category": "high"})
    assert rec["target_tension"] == 5
    assert rec["tension_delta"] == 3.0  # actual 8 - target 5


def test_arc_target_without_tension_has_no_delta(project):
    cm = _metrics(project)
    rec = cm.record_tick(tick=10, scene_id="S010", tension_result=None)
    assert rec["target_tension"] == 5
    assert rec["tension_delta"] is None


def test_records_arc_phase(project):
    # Default curve peaks at 0.9; progress 10/40 = 0.25 is on the climb.
    cm = _metrics(project)
    rec = cm.record_tick(tick=10, scene_id="S010", tension_result=None)
    assert rec["arc_phase"] == "rising"
    # Progress 39/40 = 0.975 is past the peak, in the resolution tail.
    assert cm.record_tick(tick=39, scene_id="S039", tension_result=None)["arc_phase"] == "resolution"


def test_arc_phase_none_when_curve_disabled(project):
    cfg = Config()
    cfg.set("coherence.target_tension_curve", None)
    cm = CoherenceMetrics(project, MemoryManager(project), FakeVector(), cfg)
    rec = cm.record_tick(tick=10, scene_id="S010", tension_result=None)
    assert rec["arc_phase"] is None
    assert rec["target_tension"] is None


def test_read_metrics_missing_file(project):
    assert read_metrics(project / "memory" / "nope.jsonl") == []


# ---- LLM goal-relevance judge ---------------------------------------------

def test_llm_goal_relevance_judge_used_when_llm_present(project):
    llm = FakeLLM('{"relevance": 8, "rationale": "the heist advances"}')
    cm = _metrics_llm(project, llm, FakeVector(value=0.1))  # embedding would give 1.0
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="the team cracks the vault",
                         tension_result=None, goal_description="pull off the heist")
    assert rec["goal_relevance"] == 8  # LLM judge, not the embedding 1.0
    assert rec["goal_relevance_method"] == "llm"
    assert rec["goal_relevance_rationale"] == "the heist advances"
    # The goal and the scene both reach the judge.
    assert "pull off the heist" in llm.prompt and "cracks the vault" in llm.prompt
    assert llm.calls == 1


def test_llm_goal_relevance_clamped(project):
    llm = FakeLLM('{"relevance": 99}')
    cm = _metrics_llm(project, llm)
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="x",
                         tension_result=None, goal_description="g")
    assert rec["goal_relevance"] == 10
    assert rec["goal_relevance_method"] == "llm"


def test_llm_goal_relevance_disabled_falls_back_to_embedding(project):
    cfg = Config()
    cfg.set("coherence.use_llm_goal_relevance", False)
    llm = FakeLLM('{"relevance": 8}')
    cm = _metrics_llm(project, llm, FakeVector(value=0.3), cfg)
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="x",
                         tension_result=None, goal_description="g")
    assert rec["goal_relevance"] == 3.0  # embedding 0.3 -> 3.0
    assert rec["goal_relevance_method"] == "embedding"
    assert llm.calls == 0  # judge never consulted


def test_llm_goal_relevance_malformed_falls_back(project):
    llm = FakeLLM("sorry, I cannot rate this")  # no JSON
    cm = _metrics_llm(project, llm, FakeVector(value=0.4))
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="x",
                         tension_result=None, goal_description="g")
    assert rec["goal_relevance"] == 4.0  # embedding fallback
    assert rec["goal_relevance_method"] == "embedding"
    assert llm.calls == 2  # retried once before giving up


def test_llm_goal_relevance_raises_falls_back(project):
    llm = FakeLLM(raises=True)
    cm = _metrics_llm(project, llm, FakeVector(value=0.2))
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="x",
                         tension_result=None, goal_description="g")
    assert rec["goal_relevance"] == 2.0
    assert rec["goal_relevance_method"] == "embedding"
    assert llm.calls == 2


# ---- write-until-concluded scene loop fields (Phase 3 segment plumbing) ------

def test_scene_segment_fields_recorded(project):
    cm = _metrics(project)
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="x", word_count=5,
                         tension_result=None, scene_segments=2, scene_truncated=False)
    assert rec["scene_segments"] == 2
    assert rec["scene_truncated"] is False


def test_scene_truncated_true_when_trim_fired(project):
    cm = _metrics(project)
    rec = cm.record_tick(tick=1, scene_id="S001", scene_text="x", word_count=5,
                         tension_result=None, scene_segments=3, scene_truncated=True)
    assert rec["scene_segments"] == 3
    assert rec["scene_truncated"] is True


def test_scene_segment_fields_default_none(project):
    # None (not 0/False) when the writer did not report, the usual convention.
    cm = _metrics(project)
    rec = cm.record_tick(tick=1, scene_id="S001", tension_result=None)
    assert rec["scene_segments"] is None
    assert rec["scene_truncated"] is None


# ---- construction-pressure detector fields (Phase 3, interleaving Slice T4a) --

def test_construction_fields_recorded_on_would_fire(project):
    cm = _metrics(project)
    rec = cm.record_tick(tick=6, scene_id="S006", tension_result=None,
                         construction_result={"would_fire": True, "trigger": "diversity",
                                              "reason": "diversity (1 thread at 40 percent)",
                                              "story_fraction": 0.4, "thread_count": 1,
                                              "runway": 9})
    assert rec["construction_would_fire"] is True
    assert rec["construction_trigger"] == "diversity"


def test_construction_fields_on_no_fire_tick(project):
    # Ran-but-would-not-fire: would_fire False, trigger None (distinguishable
    # from "did not run", where would_fire itself is None).
    cm = _metrics(project)
    rec = cm.record_tick(tick=1, scene_id="S001", tension_result=None,
                         construction_result={"would_fire": False, "trigger": None,
                                              "reason": "before the construction floor",
                                              "story_fraction": 0.067, "thread_count": 1,
                                              "runway": 14})
    assert rec["construction_would_fire"] is False
    assert rec["construction_trigger"] is None


def test_construction_fields_default_none(project):
    # None when the detector did not run (gate off, hook failure), the
    # None-when-unavailable convention.
    cm = _metrics(project)
    rec = cm.record_tick(tick=1, scene_id="S001", tension_result=None)
    assert rec["construction_would_fire"] is None
    assert rec["construction_trigger"] is None
