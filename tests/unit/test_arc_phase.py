"""Unit tests for the Phase 3 arc-phase planner mandate (escalate / confront / resolve)."""

from novel_agent.agent.agent import StoryAgent
from novel_agent.agent.arc_pressure import (
    ARC_PHASE_MANDATES,
    arc_phase_mandate,
    arc_pressure_guidance_for_planner,
    compute_arc_phase,
    derive_arc_phase,
    rewrite_futile,
)
from novel_agent.configs.config import Config


class FakeConfig:
    """Minimal dot-notation config for testing."""

    def __init__(self, values):
        self._v = values

    def get(self, key, default=None):
        return self._v.get(key, default)


# The repo's default-shaped curve: climb to a late peak at 0.9, resolution tail to 4.
DEFAULT_CURVE = [[0.0, 3], [0.25, 5], [0.5, 6], [0.75, 8], [0.9, 9], [1.0, 4]]
# An earlier peak leaves room for a mid-story "falling" stretch before the tail.
EARLY_PEAK_CURVE = [[0.0, 3], [0.5, 9], [1.0, 2]]


# ---- phase derivation (pure) ------------------------------------------------

def test_phase_rising_on_the_climb():
    assert derive_arc_phase(0.0, DEFAULT_CURVE) == "rising"
    assert derive_arc_phase(0.5, DEFAULT_CURVE) == "rising"
    assert derive_arc_phase(0.8, DEFAULT_CURVE) == "rising"


def test_phase_peak_near_curve_maximum():
    assert derive_arc_phase(0.9, DEFAULT_CURVE) == "peak"    # the peak control point
    assert derive_arc_phase(0.88, DEFAULT_CURVE) == "peak"   # within the peak margin


def test_phase_falling_mid_story_after_early_peak():
    # Past the peak but before the resolution tail: wind down, don't end the book.
    assert derive_arc_phase(0.7, EARLY_PEAK_CURVE) == "falling"


def test_phase_resolution_in_final_tail():
    assert derive_arc_phase(0.95, DEFAULT_CURVE) == "resolution"
    assert derive_arc_phase(1.0, DEFAULT_CURVE) == "resolution"
    assert derive_arc_phase(0.9, EARLY_PEAK_CURVE) == "resolution"


def test_phase_descent_before_resolution_start_is_falling():
    # Immediately past the DEFAULT_CURVE peak (0.9) the tail starts at 0.85+, so it's
    # resolution; a custom resolution_start pushes the same position back to falling.
    assert derive_arc_phase(0.92, DEFAULT_CURVE, resolution_start=0.99) == "falling"


def test_phase_mid_story_dip_before_final_peak_is_falling_not_resolution():
    # A curve ending on its highest peak: the dip de-escalates but never resolves.
    dip_curve = [[0.0, 3], [0.3, 7], [0.6, 4], [1.0, 9]]
    assert derive_arc_phase(0.45, dip_curve) == "falling"
    assert derive_arc_phase(0.9, dip_curve) == "rising"
    assert derive_arc_phase(0.97, dip_curve) == "peak"     # ends high: never resolution


def test_phase_progress_clamped():
    assert derive_arc_phase(-1.0, DEFAULT_CURVE) == "rising"
    assert derive_arc_phase(5.0, DEFAULT_CURVE) == "resolution"


def test_phase_none_for_flat_or_missing_curve():
    assert derive_arc_phase(0.5, [[0.0, 5], [1.0, 5]]) is None  # flat: no arc shape
    assert derive_arc_phase(0.5, []) is None
    assert derive_arc_phase(0.5, None) is None
    assert derive_arc_phase(0.5, [["x", "y"]]) is None          # malformed points dropped


def test_compute_arc_phase_from_config():
    cfg = FakeConfig({"coherence.target_tension_curve": DEFAULT_CURVE,
                      "coherence.target_story_length": 20})
    assert compute_arc_phase(0, cfg) == "rising"
    assert compute_arc_phase(18, cfg) == "peak"        # 90%
    assert compute_arc_phase(19, cfg) == "resolution"  # 95%


def test_compute_arc_phase_disabled_when_curve_none():
    cfg = FakeConfig({"coherence.target_tension_curve": None})
    assert compute_arc_phase(10, cfg) is None


# ---- mandate text selection --------------------------------------------------

def test_mandate_texts_are_event_level():
    assert "Escalate" in arc_phase_mandate("rising")
    assert "Confront" in arc_phase_mandate("peak")
    falling = arc_phase_mandate("falling")
    assert "aftermath" in falling and "open loop" in falling and "time-skip" in falling
    assert "Do NOT introduce new threats" in falling
    resolution = arc_phase_mandate("resolution")
    assert "denouement" in resolution and "closure" in resolution
    assert "Do NOT introduce new threats" in resolution


def test_mandate_empty_for_unknown_phase():
    assert arc_phase_mandate(None) == ""
    assert arc_phase_mandate("sideways") == ""
    assert set(ARC_PHASE_MANDATES) == {"rising", "peak", "falling", "resolution"}


# ---- planner guidance injection + config gate ---------------------------------

def test_planner_guidance_carries_phase_mandate():
    cfg = FakeConfig({"coherence.target_tension_curve": EARLY_PEAK_CURVE,
                      "coherence.target_story_length": 20})
    g = arc_pressure_guidance_for_planner(19, cfg)  # 95% -> resolution
    assert "Arc phase: RESOLUTION" in g and "denouement" in g
    assert "EVENTS" in g  # the numeric target line is still present


def test_planner_guidance_mandate_gated_off():
    cfg = FakeConfig({"coherence.target_tension_curve": EARLY_PEAK_CURVE,
                      "coherence.target_story_length": 20,
                      "coherence.arc_phase_mandate": False})
    g = arc_pressure_guidance_for_planner(19, cfg)
    assert "Arc phase" not in g
    assert "EVENTS" in g  # pre-mandate guidance intact


def test_planner_guidance_empty_when_curve_none():
    cfg = FakeConfig({"coherence.target_tension_curve": None})
    assert arc_pressure_guidance_for_planner(19, cfg) == ""


# ---- plot-first (beat-first) planning path ------------------------------------
# plan_for_beat bypasses Stage 1 (where arc-pressure guidance lands), so the phase
# mandate is threaded into the Stage 3 tactical prompt instead.

class _PlannerLLM:
    def __init__(self):
        self.prompt = None

    def generate(self, prompt, max_tokens=2000):
        self.prompt = prompt
        return '{"scene_intention": "x", "actions": []}'


class _PlannerMemory:
    def load_character(self, cid):
        return None

    def load_open_loops(self):
        return []

    def load_all_lore(self):
        return []

    def get_active_character(self):
        return None


class _PlannerVector:
    def search_scenes(self, query, limit=3):
        return []


class _PlannerTools:
    def get_tools_description(self):
        return "(tools)"


def _beat_planner(cfg):
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner
    llm = _PlannerLLM()
    planner = MultiStagePlanner(llm, _PlannerMemory(), _PlannerVector(), _PlannerTools(), cfg)
    return planner, llm


def _resolution_cfg(**extra):
    values = {"coherence.target_tension_curve": EARLY_PEAK_CURVE,
              "coherence.target_story_length": 20}
    values.update(extra)
    return FakeConfig(values)


def test_beat_first_plan_carries_phase_mandate():
    planner, llm = _beat_planner(_resolution_cfg())
    plan = planner.plan_for_beat({"current_tick": 19}, {"id": "B001", "description": "the aftermath"})
    assert "Arc phase: RESOLUTION" in llm.prompt and "denouement" in llm.prompt
    assert plan["beat_target"]["beat_id"] == "B001"


def test_beat_first_mandate_suppressed_by_beat_tension_target():
    # An explicit beat tension_target governs, mirroring the writer-side precedence.
    planner, llm = _beat_planner(_resolution_cfg())
    planner.plan_for_beat({"current_tick": 19},
                          {"id": "B001", "description": "the aftermath", "tension_target": 7})
    assert "Arc phase" not in llm.prompt


def test_beat_first_mandate_gated_off():
    planner, llm = _beat_planner(_resolution_cfg(**{"coherence.arc_phase_mandate": False}))
    planner.plan_for_beat({"current_tick": 19}, {"id": "B001", "description": "the aftermath"})
    assert "Arc phase" not in llm.prompt


# ---- rewrite-skip for big downward moves --------------------------------------

def test_rewrite_futile():
    assert rewrite_futile(8, 4, 3) is True    # drop 4 >= step 3
    assert rewrite_futile(8, 5, 3) is True    # drop 3 == step
    assert rewrite_futile(8, 6, 3) is False   # drop 2 < step
    assert rewrite_futile(2, 8, 3) is False   # upward move: rewrite can raise
    assert rewrite_futile(None, 4, 3) is False
    assert rewrite_futile(8, None, 3) is False


class FakeWriter:
    def __init__(self, revised):
        self.revised = revised
        self.called = False

    def revise_for_tension(self, text, target, current, writer_context=None, prev_tension=None):
        self.called = True
        return self.revised


class FakeTension:
    def __init__(self, score):
        self.score = score

    def evaluate_tension(self, text, ctx):
        return {"enabled": True, "tension_level": self.score, "tension_category": "x"}


class FakeMemory:
    """No prior scenes -> last_scene_tension returns None."""
    def list_scenes(self):
        return []


def _agent(config, writer, tension):
    a = StoryAgent.__new__(StoryAgent)  # bypass __init__; method only uses these attrs
    a.config = config
    a.writer = writer
    a.tension_evaluator = tension
    a.memory = FakeMemory()
    return a


# At tick 0 with the default curve+length, the target is 3.
def _tr(level):
    return {"enabled": True, "tension_level": level, "tension_category": "high"}


def test_rewrite_skipped_for_big_downward_move():
    writer = FakeWriter("calmer prose")
    agent = _agent(Config(), writer, FakeTension(4))
    # current 8 vs target 3: drop 5 >= step 3 -> events set the floor, skip entirely
    scene, tr = agent._maybe_rewrite_for_tension({"text": "tense", "word_count": 1}, _tr(8), 0, {})
    assert not writer.called
    assert scene["text"] == "tense" and tr["tension_level"] == 8


def test_rewrite_still_fires_for_big_upward_move():
    writer = FakeWriter("tenser prose")
    agent = _agent(Config(), writer, FakeTension(2))
    # current 0 vs target 3: off by 3 > threshold, but the gap is upward -> rewrite runs
    scene, tr = agent._maybe_rewrite_for_tension({"text": "calm", "word_count": 1}, _tr(0), 0, {})
    assert writer.called
    assert tr["tension_level"] == 2 and tr["rewritten"] is True


def test_rewrite_skip_gated_off_restores_old_behavior():
    cfg = Config()
    cfg.set("coherence.arc_phase_mandate", False)
    writer = FakeWriter("calmer prose")
    agent = _agent(cfg, writer, FakeTension(4))
    scene, tr = agent._maybe_rewrite_for_tension({"text": "tense", "word_count": 1}, _tr(8), 0, {})
    assert writer.called  # pre-mandate behavior: the (futile) revision pass still runs
    assert tr["tension_level"] == 4 and tr["rewritten"] is True
