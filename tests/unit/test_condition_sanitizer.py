"""Contracts Slice 1: sanitize-not-trust for LLM-authored beat conditions.

The shared helper (novel_agent/contracts/authoring.py) drops unknown checks and
phantom refs with a warning (never failing beat generation), caps conditions per
beat, and keeps tension conditions consistent with the beat's own tension_target.
"""

import pytest

from novel_agent.configs.config import Config
from novel_agent.contracts.authoring import (
    MAX_CONDITIONS_PER_BEAT,
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


def test_phantom_entity_and_loop_refs_dropped():
    beat = _beat(postconditions=[
        {"check": "char_in_prose", "char": "C999"},
        {"check": "entity_exists", "id": "L999"},
        {"check": "entity_exists", "id": "X001"},
        {"check": "char_at_location", "char": "C000", "location": "L999"},
        {"check": "loop_resolved", "loop": "OL999"},
        {"check": "loop_resolved", "loop": "OL001"},
    ])
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions[0] == {"check": "loop_resolved", "loop": "OL001"}
    assert len(warnings) == 5
    assert any("C999" in w for w in warnings)
    assert any("L999" in w for w in warnings)
    assert any("OL999" in w for w in warnings)


def test_resolvable_refs_kept():
    conditions = [
        {"check": "entity_exists", "id": "C000"},
        {"check": "char_at_location", "char": "C000", "location": "L000"},
        {"check": "prose_contains", "any": ["Skyvault"]},
    ]
    beat = _beat(postconditions=list(conditions))
    warnings = sanitize_beat_conditions([beat], FakeMemory(), _config())
    assert beat.postconditions == conditions
    assert warnings == []


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
