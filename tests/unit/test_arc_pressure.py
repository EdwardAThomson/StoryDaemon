"""Unit tests for arc-pressure (Phase 3 target tension trajectory)."""

from novel_agent.agent.arc_pressure import (
    interpolate_curve,
    compute_target_tension,
    arc_pressure_guidance,
)


class FakeConfig:
    """Minimal dot-notation config for testing."""

    def __init__(self, values):
        self._v = values

    def get(self, key, default=None):
        return self._v.get(key, default)


CURVE = [[0.0, 3], [0.5, 6], [1.0, 4]]


def test_interpolate_endpoints_and_midpoint():
    assert interpolate_curve(0.0, CURVE) == 3
    assert interpolate_curve(0.5, CURVE) == 6
    assert interpolate_curve(1.0, CURVE) == 4
    # midway between 0.0 (3) and 0.5 (6) -> 4.5
    assert interpolate_curve(0.25, CURVE) == 4.5


def test_interpolate_clamps_outside_range():
    assert interpolate_curve(-1.0, CURVE) == 3   # below first point
    assert interpolate_curve(5.0, CURVE) == 4     # above last point


def test_interpolate_unsorted_and_malformed():
    assert interpolate_curve(0.25, [[1.0, 4], [0.0, 3], [0.5, 6]]) == 4.5  # sorts internally
    assert interpolate_curve(0.5, []) is None
    assert interpolate_curve(0.5, None) is None


def test_compute_target_tension_progress():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    assert compute_target_tension(0, cfg) == 3      # 0% -> first point
    assert compute_target_tension(10, cfg) == 6     # 50% -> midpoint
    assert compute_target_tension(20, cfg) == 4     # 100%
    assert compute_target_tension(40, cfg) == 4     # >100% clamps to end


def test_disabled_when_curve_none():
    cfg = FakeConfig({"coherence.target_tension_curve": None, "coherence.target_story_length": 20})
    assert compute_target_tension(5, cfg) is None
    assert arc_pressure_guidance(5, cfg) == ""


def test_guidance_text_contains_position_and_target():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    text = arc_pressure_guidance(10, cfg)  # 50% -> target 6
    assert "50%" in text
    assert "6/10" in text
    assert text.startswith("\nArc Target:")
