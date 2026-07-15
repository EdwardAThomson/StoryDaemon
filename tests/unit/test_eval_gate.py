"""Evaluation gate: a failing verdict with an empty issues list must not abort
the tick (it carries nothing actionable), while concrete issues still do."""

import pytest

from novel_agent.agent.agent import StoryAgent
from novel_agent.agent.evaluator import SceneEvaluator


class _Shim:
    """Minimal stand-in: _gate_on_evaluation touches no agent state."""


def _gate(eval_result):
    StoryAgent._gate_on_evaluation(_Shim(), eval_result)


def test_passed_evaluation_is_silent():
    _gate({"passed": True, "issues": [], "warnings": []})


def test_failed_with_empty_issues_continues():
    # The archived tick-0 failure: passed=False, issues=[] (warnings only).
    _gate({"passed": False, "issues": [], "warnings": ["Possible POV violations"]})


def test_failed_with_missing_issues_continues():
    _gate({"passed": False, "issues": None, "warnings": []})


def test_failed_with_concrete_issues_still_raises():
    with pytest.raises(ValueError, match="Scene evaluation failed"):
        _gate({"passed": False, "issues": ["contradiction with canon"], "warnings": []})


class _FakeMemory:
    """Just enough memory surface for SceneEvaluator's heuristic path."""

    project_path = None

    def load_character(self, cid):
        return None

    def get_recent_scene_qa(self, count=3):
        return []


def test_pov_marker_failure_is_warning_shaped():
    # Documents the trigger: a heuristic check failure produces passed=False
    # with EMPTY issues (warnings only), which the gate must not treat as fatal.
    evaluator = SceneEvaluator(_FakeMemory(), {})
    result = evaluator.evaluate_scene(
        "Meanwhile, across town, the bell rang.",
        {"pov_character_id": "C000"},
    )
    assert result["passed"] is False
    assert result["issues"] == []
    _gate(result)  # must not raise
