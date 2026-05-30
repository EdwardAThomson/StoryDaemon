"""Unit tests for arc-pressure (Phase 3 target tension trajectory)."""

from novel_agent.agent.arc_pressure import (
    interpolate_curve,
    compute_target_tension,
    arc_pressure_guidance,
    arc_pressure_guidance_for_writer,
    _tension_band,
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


def test_tension_band_boundaries():
    assert _tension_band(0) == "calm"
    assert _tension_band(2) == "calm"
    assert _tension_band(3) == "low"
    assert _tension_band(4) == "low"
    assert _tension_band(5) == "moderate"
    assert _tension_band(6) == "moderate"
    assert _tension_band(7) == "high"
    assert _tension_band(8) == "high"
    assert _tension_band(9) == "climactic"
    assert _tension_band(10) == "climactic"


def test_writer_guidance_disabled_when_curve_none():
    cfg = FakeConfig({"coherence.target_tension_curve": None, "coherence.target_story_length": 20})
    assert arc_pressure_guidance_for_writer(5, cfg) == ""


def test_writer_guidance_is_firm_and_band_specific():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    # tick 0 -> 0% -> target 3 -> "low" band, with a directive
    low = arc_pressure_guidance_for_writer(0, cfg)
    assert "TENSION TARGET FOR THIS SCENE: 3/10 (low)" in low
    assert "0%" in low
    assert "mild" in low  # the low-band directive
    # tick 10 -> 50% -> target 6 -> "moderate"
    mod = arc_pressure_guidance_for_writer(10, cfg)
    assert "6/10 (moderate)" in mod


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
