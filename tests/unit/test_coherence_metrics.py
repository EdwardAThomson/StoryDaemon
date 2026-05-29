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


def test_goal_relevance_present_and_absent(project):
    cm = _metrics(project, FakeVector(value=0.5))
    with_goal = cm.record_tick(tick=1, scene_id="S001", scene_text="prose",
                               tension_result=None, goal_description="defeat the empire")
    assert with_goal["goal_relevance"] == 0.5

    without_goal = cm.record_tick(tick=2, scene_id="S002", scene_text="prose", tension_result=None)
    assert without_goal["goal_relevance"] is None


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


def test_read_metrics_missing_file(project):
    assert read_metrics(project / "memory" / "nope.jsonl") == []
