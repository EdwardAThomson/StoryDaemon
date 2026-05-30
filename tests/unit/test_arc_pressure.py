"""Unit tests for arc-pressure (Phase 3 target tension trajectory)."""

from novel_agent.agent.arc_pressure import (
    interpolate_curve,
    compute_target_tension,
    arc_pressure_guidance,
    arc_pressure_guidance_for_writer,
)
from novel_agent.agent.tension_scale import band_for


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


def test_tension_band_boundaries_match_scorer_anchors():
    # Writer bands now equal the scorer's anchors (the calibration fix).
    assert band_for(0).name == "none"
    assert band_for(1).name == "none"
    assert band_for(2).name == "minimal"
    assert band_for(3).name == "minimal"
    assert band_for(4).name == "rising"
    assert band_for(5).name == "rising"
    assert band_for(6).name == "high"
    assert band_for(7).name == "high"
    assert band_for(8).name == "very high"
    assert band_for(9).name == "very high"
    assert band_for(10).name == "peak climax"


def test_shared_scale_renders_all_anchors_and_scorer_rubric():
    from novel_agent.agent.tension_scale import scorer_anchor_block, scale_overview
    from novel_agent.agent.tension_evaluator import TENSION_RUBRIC_PROMPT
    block = scorer_anchor_block()
    for name in ("none", "minimal", "rising", "high", "very high", "peak climax"):
        assert name in block
        assert name in scale_overview()
    # The scorer rubric still renders the six anchors (now from the shared scale).
    rendered = TENSION_RUBRIC_PROMPT.format(anchors=block, scene_text="x")
    assert "Anchors:" in rendered and "peak climax" in rendered


def test_writer_guidance_disabled_when_curve_none():
    cfg = FakeConfig({"coherence.target_tension_curve": None, "coherence.target_story_length": 20})
    assert arc_pressure_guidance_for_writer(5, cfg) == ""


def test_writer_guidance_is_firm_calibrated_and_shows_full_scale():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    # tick 0 -> 0% -> target 3 -> "minimal" band (matches scorer anchor 2-3)
    g = arc_pressure_guidance_for_writer(0, cfg)
    assert "TENSION TARGET FOR THIS SCENE: 3/10 (minimal" in g
    assert "0%" in g
    # The writer is shown the full graded scale used to score the scene afterwards.
    assert "graded 0-10" in g
    assert "very high" in g and "peak climax" in g
    # tick 10 -> 50% -> target 6 -> "high" (scorer anchor 6-7)
    assert "6/10 (high" in arc_pressure_guidance_for_writer(10, cfg)


def test_writer_section_suppressed_when_beat_has_tension_target():
    from novel_agent.agent.writer_context import WriterContextBuilder
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    wcb = WriterContextBuilder.__new__(WriterContextBuilder)  # bypass __init__ (no deps needed)
    wcb.config = cfg
    # Beat with a tension_target -> arc section suppressed (beat governs)
    assert wcb._build_arc_pressure_section({"plot_beat": {"tension_target": 7}}, current_tick=0) == ""
    # No beat -> arc section emitted
    assert wcb._build_arc_pressure_section({}, current_tick=0).startswith("**TENSION TARGET")


def test_writer_template_renders_with_arc_section():
    # Guard against a missing-key KeyError when the new placeholder is added.
    import string
    from novel_agent.agent.prompts import WRITER_PROMPT_TEMPLATE
    keys = {fn for _, fn, _, _ in string.Formatter().parse(WRITER_PROMPT_TEMPLATE) if fn}
    assert "arc_pressure_section" in keys
    rendered = WRITER_PROMPT_TEMPLATE.format(**{k: "x" for k in keys})
    assert "x" in rendered
