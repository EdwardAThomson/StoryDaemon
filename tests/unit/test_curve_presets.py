"""Unit tests for tension-curve presets (Phase 3, interleaving Slice T4a).

The default preset ("house") must resolve to exactly the shipped default curve
(byte-identical behavior); the named presets from the masters study are opt-in;
an explicitly customized curve always wins; curve None still disables.
"""

from novel_agent.agent.arc_pressure import (
    CURVE_PRESETS,
    HOUSE_CURVE,
    beat_tension_schedule,
    compute_arc_phase,
    compute_target_tension,
    interpolate_curve,
    resolve_tension_curve,
)
from novel_agent.agent.finale import finale_target_tension, finale_tension_cap
from novel_agent.configs.config import Config, DEFAULT_CONFIG


class FakeConfig:
    """Minimal dot-notation config for testing."""

    def __init__(self, values=None):
        self._v = dict(values or {})

    def get(self, key, default=None):
        return self._v.get(key, default)


def _cfg(preset=None, curve=HOUSE_CURVE, length=20, **extra):
    values = {
        "coherence.target_tension_curve": curve,
        "coherence.target_story_length": length,
    }
    if preset is not None:
        values["coherence.curve_preset"] = preset
    values.update(extra)
    return FakeConfig(values)


# ---- drift guards and byte-identical default ---------------------------------

def test_house_curve_matches_shipped_default():
    # arc_pressure.HOUSE_CURVE and DEFAULT_CONFIG keep the same literal; this
    # is the drift guard the module comment promises.
    assert DEFAULT_CONFIG["coherence"]["target_tension_curve"] == HOUSE_CURVE
    assert DEFAULT_CONFIG["coherence"]["curve_preset"] == "house"
    assert CURVE_PRESETS["house"] is HOUSE_CURVE


def test_default_config_resolves_to_house():
    cfg = Config()
    assert resolve_tension_curve(cfg) == HOUSE_CURVE


def test_default_behavior_byte_identical_to_direct_interpolation():
    # The house preset must reproduce today's targets exactly at every tick of
    # the default 40-tick story.
    cfg = Config()
    for tick in range(0, 45):
        expected = interpolate_curve(min(1.0, tick / 40.0),
                                     DEFAULT_CONFIG["coherence"]["target_tension_curve"])
        assert compute_target_tension(tick, cfg) == round(expected, 1)


def test_finale_target_unchanged_under_house_default():
    assert finale_target_tension(Config()) == 4.0
    assert finale_tension_cap(Config()) == 5.0


# ---- named presets resolve (opt-in) -------------------------------------------

def test_named_preset_resolves():
    cfg = _cfg(preset="thriller-register")
    assert resolve_tension_curve(cfg) == CURVE_PRESETS["thriller-register"]
    # The thriller opens AT register (Steps d0 8.0), not cold.
    assert compute_target_tension(0, cfg) == 8


def test_preset_name_normalized():
    cfg = _cfg(preset="  Thriller-Register ")
    assert resolve_tension_curve(cfg) == CURVE_PRESETS["thriller-register"]


def test_wind_down_descends_to_denouement_tail():
    cfg = _cfg(preset="wind-down")
    # Spike 9 at 0.9 (tick 18 of 20), then the short committed descent to 2.
    assert compute_target_tension(18, cfg) == 9
    assert compute_target_tension(20, cfg) == 2
    assert finale_target_tension(cfg) == 2.0


def test_thriller_holds_climax_to_the_last_page():
    cfg = _cfg(preset="thriller-register")
    assert compute_target_tension(20, cfg) == 9
    assert finale_target_tension(cfg) == 9.0
    assert finale_tension_cap(cfg) == 10.0
    # A thriller ENDS at its peak (masters: Dracula's final chapter is a 9).
    assert compute_arc_phase(20, cfg) == "peak"


def test_domestic_arc_register_and_ending():
    cfg = _cfg(preset="domestic-arc")
    # Peak 8 at 0.75 (tick 15 of 20), ending in the 1-3 denouement band.
    assert compute_target_tension(15, cfg) == 8
    assert compute_target_tension(20, cfg) == 1.5
    # Past the peak in the final tail: resolution phase.
    assert compute_arc_phase(20, cfg) == "resolution"


def test_beat_schedule_follows_preset():
    cfg = _cfg(preset="wind-down")
    schedule = beat_tension_schedule(19, 1, cfg)  # the slot at tick 20 = progress 1.0
    assert schedule[0]["target"] == 2
    assert schedule[0]["final"] is True


# ---- precedence ----------------------------------------------------------------

def test_explicit_curve_wins_over_preset():
    explicit = [[0.0, 1], [1.0, 2]]
    cfg = _cfg(preset="thriller-register", curve=explicit)
    assert resolve_tension_curve(cfg) == explicit
    assert compute_target_tension(0, cfg) == 1


def test_none_curve_disables_even_with_preset():
    cfg = _cfg(preset="thriller-register", curve=None)
    assert resolve_tension_curve(cfg) is None
    assert compute_target_tension(5, cfg) is None
    assert compute_arc_phase(5, cfg) is None


def test_unknown_preset_falls_back_to_house():
    cfg = _cfg(preset="grimdark")
    assert resolve_tension_curve(cfg) == HOUSE_CURVE   # warned, degraded, no raise
    assert compute_target_tension(0, cfg) == 3


def test_blank_preset_falls_back_to_house():
    for preset in ("", "   ", None, 7):
        cfg = _cfg(preset=preset)
        assert resolve_tension_curve(cfg) == HOUSE_CURVE


# ---- preset well-formedness -----------------------------------------------------

def test_all_presets_well_formed():
    for name, points in CURVE_PRESETS.items():
        fractions = [p[0] for p in points]
        levels = [p[1] for p in points]
        assert fractions == sorted(fractions), name
        assert fractions[0] == 0.0 and fractions[-1] == 1.0, name
        assert all(0.0 <= f <= 1.0 for f in fractions), name
        assert all(0 <= lvl <= 10 for lvl in levels), name
        # Every preset must interpolate cleanly across the whole story.
        assert interpolate_curve(0.5, points) is not None, name


def test_no_preset_targets_ten():
    # 149 master chapters produced no 10 (the rubric reserves it); presets
    # follow suit, peaking at the observed ceiling of 9.
    for name, points in CURVE_PRESETS.items():
        assert max(p[1] for p in points) <= 9, name
