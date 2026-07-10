"""Unit tests for arc-pressure (Phase 3 target tension trajectory)."""

from types import SimpleNamespace

from novel_agent.agent.arc_pressure import (
    interpolate_curve,
    compute_target_tension,
    arc_pressure_guidance,
    arc_pressure_guidance_for_writer,
    arc_pressure_guidance_for_planner,
    beat_target_is_stale,
    last_scene_tension,
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


def _writer_context_builder(cfg):
    from novel_agent.agent.writer_context import WriterContextBuilder
    wcb = WriterContextBuilder.__new__(WriterContextBuilder)  # bypass __init__ (no deps needed)
    wcb.config = cfg
    return wcb


def test_writer_section_suppressed_when_beat_has_fresh_tension_target():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    wcb = _writer_context_builder(cfg)
    # Beat with a fresh tension_target (near the tick-0 curve target 3) -> arc
    # section suppressed (the beat governs)
    assert wcb._build_arc_pressure_section({"plot_beat": {"tension_target": 4}}, current_tick=0) == ""
    # No beat -> arc section emitted
    assert wcb._build_arc_pressure_section({}, current_tick=0).startswith("**TENSION TARGET")


def test_writer_section_rendered_when_beat_tension_target_is_stale():
    # The 2026-07-10 addendum's wedge shape: a peak beat (tension_target 8.8)
    # consumed at the tick whose curve target is 4; the stale target yields and
    # the schedule's arc section renders.
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    wcb = _writer_context_builder(cfg)
    section = wcb._build_arc_pressure_section(
        {"plot_beat": {"tension_target": 8.8}}, current_tick=20
    )
    assert section.startswith("**TENSION TARGET FOR THIS SCENE: 4/10")


# ---- stale beat targets yield to the schedule (2026-07-10 addendum backstop) ----

def _curve_cfg(**extra):
    values = {"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20}
    values.update(extra)
    return FakeConfig(values)


def test_beat_target_fresh_near_curve_target():
    # tick 20 -> curve target 4; a target within the transition step is fresh
    cfg = _curve_cfg()
    assert beat_target_is_stale(4, 20, cfg) is False
    assert beat_target_is_stale(6, 20, cfg) is False   # deviation 2 < step 3


def test_beat_target_stale_at_step_or_more():
    cfg = _curve_cfg()
    # the observed wedge: peak target 8.8 carried into a slot whose target is 4
    assert beat_target_is_stale(8.8, 20, cfg) is True
    assert beat_target_is_stale(7, 20, cfg) is True    # deviation 3 == step
    assert beat_target_is_stale(1, 20, cfg) is True    # staleness is symmetric


def test_beat_target_stale_honors_configured_step():
    cfg = _curve_cfg(**{"coherence.tension_step_for_transition": 2})
    assert beat_target_is_stale(6, 20, cfg) is True    # deviation 2 >= step 2


def test_beat_target_stale_graceful_when_missing_or_disabled():
    cfg = _curve_cfg()
    assert beat_target_is_stale(None, 20, cfg) is False      # no target: fresh precedence
    assert beat_target_is_stale("loud", 20, cfg) is False    # non-numeric target
    off = FakeConfig({"coherence.target_tension_curve": None})
    assert beat_target_is_stale(8.8, 20, off) is False       # curve off: no schedule to yield to


def test_writer_template_renders_with_arc_section():
    # Guard against a missing-key KeyError when the new placeholder is added.
    import string
    from novel_agent.agent.prompts import WRITER_PROMPT_TEMPLATE
    keys = {fn for _, fn, _, _ in string.Formatter().parse(WRITER_PROMPT_TEMPLATE) if fn}
    assert "arc_pressure_section" in keys
    rendered = WRITER_PROMPT_TEMPLATE.format(**{k: "x" for k in keys})
    assert "x" in rendered


# ---- option (c): continuity-aware planner guidance + previous-tension lookup ----

def test_planner_guidance_disabled_when_curve_none():
    cfg = FakeConfig({"coherence.target_tension_curve": None, "coherence.target_story_length": 20})
    assert arc_pressure_guidance_for_planner(5, cfg, prev_tension=9) == ""


def test_planner_guidance_big_drop_stages_transition():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    # tick 0 -> target 3; prev 9 -> drop 6 >= step(3) -> transition + low-stakes
    g = arc_pressure_guidance_for_planner(0, cfg, prev_tension=9)
    assert "EVENTS" in g and "3/10" in g
    assert "transition" in g.lower() and "low-stakes" in g.lower()
    assert "9/10" in g


def test_planner_guidance_big_rise_escalates():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    # tick 10 -> target 6; prev 3 -> rise 3 >= step -> escalate
    g = arc_pressure_guidance_for_planner(10, cfg, prev_tension=3)
    assert "Escalate" in g


def test_planner_guidance_small_step_is_gradual():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    g = arc_pressure_guidance_for_planner(10, cfg, prev_tension=5)  # target 6, diff 1 < 3
    assert "gradually" in g.lower()
    assert "transition" not in g.lower()


def test_planner_guidance_no_prev_just_targets():
    cfg = FakeConfig({"coherence.target_tension_curve": CURVE, "coherence.target_story_length": 20})
    g = arc_pressure_guidance_for_planner(0, cfg, prev_tension=None)
    assert "EVENTS" in g
    assert "previous scene" not in g.lower()


class _FakeMem:
    def __init__(self, scenes):  # scenes: {id: tension_level}
        self._scenes = scenes

    def list_scenes(self):
        return list(self._scenes.keys())

    def load_scene(self, sid):
        return SimpleNamespace(tension_level=self._scenes[sid])


def test_last_scene_tension():
    assert last_scene_tension(_FakeMem({})) is None
    # latest by sorted id (S002 > S001)
    assert last_scene_tension(_FakeMem({"S001": 5, "S002": 8})) == 8
