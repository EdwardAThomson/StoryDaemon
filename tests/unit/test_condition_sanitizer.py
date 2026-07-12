"""Contracts Slice 1: sanitize-not-trust for LLM-authored beat conditions.

The shared helper (novel_agent/contracts/authoring.py) drops unknown checks and
phantom refs with a warning (never failing beat generation), caps conditions per
beat, and keeps tension conditions consistent with the beat's own tension_target.
"""

import pytest

from novel_agent.configs.config import Config
from novel_agent.contracts.authoring import (
    MAX_CONDITIONS_PER_BEAT,
    TENSION_FLOOR_CAP,
    sanitize_beat_conditions,
)
from novel_agent.plot.entities import PlotBeat


class FakeLoop:
    def __init__(self, loop_id):
        self.id = loop_id


class FakeMemory:
    """Duck-typed roster surface the sanitizer reads."""

    def __init__(self, characters=("C000",), locations=("L000",), loops=("OL001",),
                 broken=False):
        self._characters = list(characters)
        self._locations = list(locations)
        self._loops = [FakeLoop(l) for l in loops]
        self._broken = broken

    def list_characters(self):
        if self._broken:
            raise RuntimeError("roster unavailable")
        return list(self._characters)

    def list_locations(self):
        if self._broken:
            raise RuntimeError("roster unavailable")
        return list(self._locations)

    def load_open_loops(self):
        if self._broken:
            raise RuntimeError("roster unavailable")
        return list(self._loops)


def _config(use_contracts=True, threshold=2):
    config = Config()
    config.set("generation.use_contracts", use_contracts)
    config.set("coherence.tension_rewrite_threshold", threshold)
    return config


def _beat(postconditions=None, preconditions=None, tension_target=None, beat_id="PB001"):
    return PlotBeat(
        id=beat_id,
        description="a beat",
        tension_target=tension_target,
        preconditions=preconditions or [],
        postconditions=postconditions or [],
    )


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def test_gate_off_is_a_noop():
    conditions = [{"check": "totally_bogus"}]
    beat = _beat(postconditions=list(conditions), tension_target=8)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config(use_contracts=False))
    assert warnings == []
    assert beat.postconditions == conditions  # untouched, nothing derived


# ---------------------------------------------------------------------------
# Vocabulary and reference sanitization
# ---------------------------------------------------------------------------

def test_unknown_check_dropped_with_warning():
    beat = _beat(postconditions=[
        {"check": "scene_has_vibes"},
        {"check": "char_in_prose", "char": "C000"},
    ])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions[0] == {"check": "char_in_prose", "char": "C000"}
    assert any("unknown check 'scene_has_vibes'" in w for w in warnings)


def test_phantom_entity_refs_dropped():
    beat = _beat(postconditions=[
        {"check": "char_in_prose", "char": "C999"},
        {"check": "entity_exists", "id": "L999"},
        {"check": "entity_exists", "id": "X001"},
        {"check": "entity_exists", "id": "C000"},
    ])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "entity_exists", "id": "C000"}]
    assert len(warnings) == 3
    assert any("C999" in w for w in warnings)
    assert any("L999" in w for w in warnings)
    assert any("X001" in w for w in warnings)


def test_resolvable_refs_kept():
    conditions = [
        {"check": "entity_exists", "id": "C000"},
        {"check": "char_in_prose", "char": "C000"},
        {"check": "prose_contains", "any": ["Skyvault"]},
    ]
    beat = _beat(postconditions=list(conditions))
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == conditions
    assert warnings == []


def test_gated_checks_dropped_even_with_resolvable_refs():
    # char_at_location is structurally unsatisfiable today (2026-07-10 run:
    # nothing writes location state): authored conditions on it are dropped by
    # the gate regardless of whether their refs resolve. loop_resolved was
    # un-gated 2026-07-12 (77.8 percent claim precision cleared the bar) and
    # rides through with a resolvable ref.
    beat = _beat(postconditions=[
        {"check": "char_at_location", "char": "C000", "location": "L000"},
        {"check": "loop_resolved", "loop": "OL001"},
    ])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "loop_resolved", "loop": "OL001"}]
    assert len(warnings) == 1
    assert "gated from authoring" in warnings[0] and "char_at_location" in warnings[0]


def test_loop_resolved_phantom_ref_still_dropped():
    # Un-gated does not mean unvalidated: a loop_resolved condition referencing
    # a loop that does not exist is dropped by the ref check, exactly like
    # every other checker's phantom refs.
    beat = _beat(postconditions=[{"check": "loop_resolved", "loop": "OL999"}])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == []
    assert any("unresolvable loop ref" in w for w in warnings)


def test_malformed_params_dropped():
    beat = _beat(postconditions=[
        {"check": "prose_contains"},                      # no terms
        {"check": "tension_at_least", "value": "loud"},   # non-numeric
        {"check": "tension_at_most", "value": 14},        # out of range
        "not even an object",
    ])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == []
    assert len(warnings) == 4


def test_conditions_capped_per_beat():
    beat = _beat(postconditions=[
        {"check": "prose_contains", "any": [f"term{i}"]} for i in range(5)
    ])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert len(beat.postconditions) == MAX_CONDITIONS_PER_BEAT
    assert any("keeping the first 3" in w for w in warnings)


def test_preconditions_sanitized_too():
    beat = _beat(preconditions=[
        {"check": "entity_exists", "id": "C000"},
        {"check": "bogus"},
    ])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.preconditions == [{"check": "entity_exists", "id": "C000"}]
    assert any("precondition" in w for w in warnings)


def test_unreadable_roster_skips_existence_checks():
    # A roster failure degrades to vocabulary-only checking rather than
    # dropping everything (graceful degradation, house rule).
    beat = _beat(postconditions=[{"check": "char_in_prose", "char": "C123"}])
    warnings = sanitize_beat_conditions([beat], FakeMemory(broken=True), _config())
    assert beat.postconditions == [{"check": "char_in_prose", "char": "C123"}]
    assert warnings == []


# ---------------------------------------------------------------------------
# Finale exemption (Phase 3, 2026-07-12 un-gating: the story's final slot must
# not carry loop_resolved postconditions, the finale over-claim species)
# ---------------------------------------------------------------------------

_LOOP_CLAIM = {"check": "loop_resolved", "loop": "OL001"}


def _length_config(length=15):
    config = _config()
    config.set("coherence.target_story_length", length)
    return config


def test_final_slot_beat_loses_loop_resolved_with_warning():
    # Batch authored at tick 11 of a 15-tick story: positions 1-4 land on ticks
    # 12-15, so position 4 is the finale slot (the triple run's PB014 shape).
    beats = [_beat(beat_id=f"PB{i:03d}", postconditions=[dict(_LOOP_CLAIM)])
             for i in range(1, 5)]
    warnings = sanitize_beat_conditions(beats, FakeMemory(), _length_config(15),
                                        current_tick=11)
    for beat in beats[:3]:
        assert beat.postconditions == [_LOOP_CLAIM]  # non-finale beats keep theirs
    assert beats[3].postconditions == []
    assert any("final slot" in w and "PB004" in w for w in warnings)


def test_final_slot_keeps_other_postconditions():
    beat = _beat(postconditions=[
        dict(_LOOP_CLAIM),
        {"check": "char_in_prose", "char": "C000"},
    ])
    sanitize_beat_conditions([beat], FakeMemory(), _length_config(15), current_tick=14)
    assert beat.postconditions == [{"check": "char_in_prose", "char": "C000"}]


def test_final_slot_preconditions_untouched():
    # The exemption targets the over-claim species (postconditions); a
    # loop_resolved PREcondition states a dependency, not a claim.
    beat = _beat(preconditions=[dict(_LOOP_CLAIM)])
    sanitize_beat_conditions([beat], FakeMemory(), _length_config(15), current_tick=14)
    assert beat.preconditions == [_LOOP_CLAIM]


def test_beats_past_the_runway_also_stripped():
    # An uncapped batch overshooting the story's end: the final slot AND the
    # overshoot land at/past target_story_length, so both are stripped.
    beats = [_beat(beat_id=f"PB{i:03d}", postconditions=[dict(_LOOP_CLAIM)])
             for i in range(1, 4)]
    sanitize_beat_conditions(beats, FakeMemory(), _length_config(15), current_tick=13)
    assert beats[0].postconditions == [_LOOP_CLAIM]   # tick 14
    assert beats[1].postconditions == []              # tick 15, the finale slot
    assert beats[2].postconditions == []              # tick 16, past the end


def test_no_current_tick_skips_the_exemption():
    beat = _beat(postconditions=[dict(_LOOP_CLAIM)])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _length_config(15))
    assert beat.postconditions == [_LOOP_CLAIM]
    assert warnings == []


def test_no_story_length_skips_the_exemption():
    config = _config()
    config.set("coherence.target_story_length", None)
    beat = _beat(postconditions=[dict(_LOOP_CLAIM)])
    sanitize_beat_conditions([beat], FakeMemory(), config, current_tick=14)
    assert beat.postconditions == [_LOOP_CLAIM]


def test_overtime_keeps_existing_behavior():
    # At or past the intended end the runway is exhausted (remaining 0): the
    # exemption stands down, same overtime rule as cap_beat_count.
    beat = _beat(postconditions=[dict(_LOOP_CLAIM)])
    sanitize_beat_conditions([beat], FakeMemory(), _length_config(15), current_tick=15)
    assert beat.postconditions == [_LOOP_CLAIM]


# ---------------------------------------------------------------------------
# Tension consistency (sketch section 6, rule 3)
# ---------------------------------------------------------------------------

def test_consistent_tension_condition_kept_as_authored():
    beat = _beat(postconditions=[{"check": "tension_at_least", "value": 7}],
                 tension_target=8)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_least", "value": 7}]
    assert warnings == []


def test_contradictory_tension_at_least_reconciled_down():
    # tension_at_least 10 against target 5 (band 2) demands more tension than the
    # beat even aims for; reconciled to target - band.
    beat = _beat(postconditions=[{"check": "tension_at_least", "value": 10}],
                 tension_target=5)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_least", "value": 3}]
    assert any("contradicts tension_target" in w for w in warnings)


def test_contradictory_tension_at_most_reconciled_up():
    beat = _beat(postconditions=[{"check": "tension_at_most", "value": 1}],
                 tension_target=5)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_most", "value": 7}]
    assert any("contradicts tension_target" in w for w in warnings)


def test_derives_tension_at_least_for_high_target():
    # Sketch example: target 8 yields tension_at_least 6.
    beat = _beat(postconditions=[{"check": "char_in_prose", "char": "C000"}],
                 tension_target=8)
    sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert {"check": "tension_at_least", "value": 6} in beat.postconditions


def test_derives_tension_at_most_for_low_target():
    beat = _beat(tension_target=2)
    sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_most", "value": 4}]


def test_no_derivation_without_target():
    beat = _beat(postconditions=[{"check": "char_in_prose", "char": "C000"}])
    sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "char_in_prose", "char": "C000"}]


def test_authored_tension_condition_suppresses_derivation():
    beat = _beat(postconditions=[{"check": "tension_at_most", "value": 5}],
                 tension_target=4)
    sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_most", "value": 5}]


# ---------------------------------------------------------------------------
# Tension floor cap (the scorer's practical ceiling, 2026-07-10 addendum)
# ---------------------------------------------------------------------------

def test_authored_floor_of_8_clamped_to_cap():
    # The clean re-run's wedge shape: authored tension_at_least 8 on the peak
    # beat (target 8.8) is consistent with the target, and unsatisfiable in
    # practice (the scorer almost never grants 8+).
    beat = _beat(postconditions=[{"check": "tension_at_least", "value": 8}],
                 tension_target=8.8)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [
        {"check": "tension_at_least", "value": TENSION_FLOOR_CAP}
    ]
    assert any("practical ceiling" in w for w in warnings)


def test_authored_floor_of_9_clamped_to_cap():
    beat = _beat(postconditions=[{"check": "tension_at_least", "value": 9}],
                 tension_target=9)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_least", "value": 7}]
    assert any("practical ceiling" in w for w in warnings)


def test_floor_at_cap_or_below_untouched():
    for value in (7, 6):
        beat = _beat(postconditions=[{"check": "tension_at_least", "value": value}],
                     tension_target=8)
        warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
        assert beat.postconditions == [{"check": "tension_at_least", "value": value}]
        assert warnings == []


def test_tension_at_most_never_capped():
    # Ceilings are satisfiable; the failure mode is floors, so tension_at_most
    # values above the cap pass through untouched.
    beat = _beat(postconditions=[{"check": "tension_at_most", "value": 9}],
                 tension_target=8.8)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_most", "value": 9}]
    assert warnings == []


def test_derived_floor_within_cap_unchanged():
    # target 8.8 derives round(8.8 - band 2) = 7: at the cap already, no clamp.
    beat = _beat(tension_target=8.8)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_least", "value": 7}]
    assert warnings == []


def test_derived_floor_above_cap_clamped():
    # target 10 derives round(10 - band 2) = 8, above the scorer's ceiling; the
    # cap applies to derived conditions the same as authored ones.
    beat = _beat(tension_target=10)
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == [{"check": "tension_at_least", "value": 7}]
    assert any("practical ceiling" in w for w in warnings)
