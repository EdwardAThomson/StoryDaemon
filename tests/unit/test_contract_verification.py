"""Contracts Slice 1: postconditions feed beat verification (tick step 8.5).

Policy under test: all conditions passing upgrades the verification method to
"contract"; any condition failing downgrades an otherwise-verified beat to the
existing failure routing (keep-pending, or rolling-horizon revision); the gate
off is a strict no-op; and the per-tick counts land in the coherence rubric.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.agent import StoryAgent
from novel_agent.configs.config import Config
from novel_agent.memory.manager import MemoryManager
from novel_agent.plot.manager import PlotOutlineManager
from novel_agent.plot.entities import PlotBeat, PlotOutline


class _FakeLLM:
    """Canned beats payload for horizon regeneration."""

    def generate(self, prompt, max_tokens=1000):
        return json.dumps({"beats": [{"description": "fresh beat"}]})


class _FakeVector:
    def __init__(self, similarity=0.9):
        self.similarity = similarity

    def compute_semantic_similarity(self, a, b):
        return self.similarity


class _AgentShim:
    """Borrow the real StoryAgent verification methods over minimal state."""

    _verify_and_complete_beat = StoryAgent._verify_and_complete_beat
    _evaluate_beat_contract = StoryAgent._evaluate_beat_contract
    _record_contract_results = StoryAgent._record_contract_results
    _mark_beat_complete = StoryAgent._mark_beat_complete
    _revise_horizon = StoryAgent._revise_horizon

    def __init__(self, project_dir, config, similarity=0.9):
        self.config = config
        self.memory = MemoryManager(project_dir)
        self.state = {"current_tick": 3}
        self.plot_manager = PlotOutlineManager(project_dir, _FakeLLM(), config)
        self.vector = _FakeVector(similarity)


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 3, "novel_name": "N"}))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _config(**overrides):
    config = Config()
    config.set("generation.use_contracts", True)
    for key, value in overrides.items():
        config.set(key, value)
    return config


def _seed_beat(shim, postconditions=None, beat_id="PB001"):
    beat = PlotBeat(id=beat_id, description="the beat", status="pending",
                    postconditions=postconditions or [])
    outline = PlotOutline(beats=[beat], created_at=PlotOutline.now_iso(),
                          last_updated=PlotOutline.now_iso())
    shim.plot_manager.save_outline(outline)
    return beat


def _verify(shim, beat, tension_level=7, targeted=True, prose="Joran won."):
    plan = {"beat_target": {"beat_id": beat.id if targeted else "PB999"}}
    return shim._verify_and_complete_beat(beat, plan, prose, "S003", tension_level, 3)


def _reload(shim, beat_id="PB001"):
    return {b.id: b for b in shim.plot_manager.load_outline().beats}[beat_id]


# ---------------------------------------------------------------------------
# Pass: upgrade confidence
# ---------------------------------------------------------------------------

def test_all_conditions_passing_upgrades_method_to_contract(project):
    shim = _AgentShim(project, _config())
    beat = _seed_beat(shim, [{"check": "tension_at_least", "value": 5}])

    payload = _verify(shim, beat, tension_level=7)

    assert payload["is_valid"] is True
    assert payload["checked"] == 1 and payload["failed"] == 0
    stored = _reload(shim)
    assert stored.status == "completed"
    assert stored.verification_method == "contract"
    assert stored.contract_results["is_valid"] is True


def test_semantic_pass_with_contract_pass_also_upgrades(project):
    shim = _AgentShim(project, _config(), similarity=0.9)
    beat = _seed_beat(shim, [{"check": "prose_contains", "any": ["won"]}])

    _verify(shim, beat, targeted=False)

    assert _reload(shim).verification_method == "contract"


def test_beat_without_conditions_keeps_existing_method(project):
    shim = _AgentShim(project, _config())
    beat = _seed_beat(shim)

    payload = _verify(shim, beat)

    assert payload is None
    stored = _reload(shim)
    assert stored.status == "completed"
    assert stored.verification_method == "trusted_planner"
    assert stored.contract_results == {}


# ---------------------------------------------------------------------------
# Fail: route to the existing failure paths
# ---------------------------------------------------------------------------

def test_contract_failure_keeps_verified_beat_pending(project):
    shim = _AgentShim(project, _config())
    beat = _seed_beat(shim, [{"check": "tension_at_least", "value": 9}])

    payload = _verify(shim, beat, tension_level=5)

    assert payload["is_valid"] is False
    assert payload["failed"] == 1
    stored = _reload(shim)
    assert stored.status == "pending"                      # not marked complete
    assert stored.contract_results["is_valid"] is False    # verdict still recorded


def test_contract_failure_with_rolling_horizon_revises(project):
    shim = _AgentShim(project, _config(**{"generation.rolling_horizon": True}))
    beat = _seed_beat(shim, [{"check": "tension_at_least", "value": 9}])

    _verify(shim, beat, tension_level=5)

    beats = {b.id: b for b in shim.plot_manager.load_outline().beats}
    assert beats["PB001"].status == "abandoned"
    assert "failed contract" in beats["PB001"].abandoned_reason
    assert any(b.status == "pending" for b in beats.values())  # fresh horizon


def test_contract_failure_downgrades_auto_completion_too(project):
    # With semantic verification off, contracts are the only gauge; a failing
    # contract must still keep the beat pending.
    shim = _AgentShim(project, _config(**{"generation.verify_beat_execution": False}))
    beat = _seed_beat(shim, [{"check": "tension_at_least", "value": 9}])

    _verify(shim, beat, tension_level=5, targeted=False)

    assert _reload(shim).status == "pending"


def test_semantic_miss_routing_unchanged_by_contracts(project):
    # Contract passing cannot rescue a beat the semantic gauge rejected.
    shim = _AgentShim(project, _config(), similarity=0.1)
    beat = _seed_beat(shim, [{"check": "tension_at_least", "value": 5}])

    payload = _verify(shim, beat, tension_level=7, targeted=False)

    assert payload["is_valid"] is True
    assert _reload(shim).status == "pending"


# ---------------------------------------------------------------------------
# Gate off: strict no-op
# ---------------------------------------------------------------------------

def test_gate_off_ignores_conditions_entirely(project):
    shim = _AgentShim(project, _config(**{"generation.use_contracts": False}))
    beat = _seed_beat(shim, [{"check": "tension_at_least", "value": 9}])

    payload = _verify(shim, beat, tension_level=5)

    assert payload is None
    stored = _reload(shim)
    assert stored.status == "completed"
    assert stored.verification_method == "trusted_planner"
    assert stored.contract_results == {}


def test_evaluation_crash_degrades_to_no_contract(project):
    # A beat whose conditions cannot even be parsed must not kill verification.
    shim = _AgentShim(project, _config())
    beat = _seed_beat(shim, ["not a condition object"])

    payload = _verify(shim, beat)

    assert payload is None
    assert _reload(shim).status == "completed"


# ---------------------------------------------------------------------------
# Coherence rubric fields
# ---------------------------------------------------------------------------

def test_metrics_record_contract_counts(project):
    from novel_agent.agent.coherence_metrics import CoherenceMetrics

    (project / "memory").mkdir(exist_ok=True)
    metrics = CoherenceMetrics(project, MemoryManager(project), _FakeVector(), Config())

    record = metrics.record_tick(tick=3, scene_id="S003",
                                 contract_result={"checked": 2, "failed": 1})
    assert record["contract_conditions_checked"] == 2
    assert record["contract_conditions_failed"] == 1

    record = metrics.record_tick(tick=4, scene_id="S004")
    assert record["contract_conditions_checked"] is None
    assert record["contract_conditions_failed"] is None
