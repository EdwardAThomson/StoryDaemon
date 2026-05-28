"""Unit tests for the contract validation layer."""

import pytest

from novel_agent.contracts.conditions import (
    Condition,
    CheckContext,
    ConditionError,
    evaluate_conditions,
    list_checkers,
)
from novel_agent.contracts.beat_contract import BeatContract
from novel_agent.memory.entities import Character, OpenLoop


class FakeMemory:
    """Minimal duck-typed stand-in for MemoryManager."""

    def __init__(self, characters=None, locations=None, loops=None):
        self._characters = characters or {}
        self._locations = locations or {}
        self._loops = loops or []

    def load_character(self, cid):
        return self._characters.get(cid)

    def load_location(self, lid):
        return self._locations.get(lid)

    def load_open_loops(self):
        return list(self._loops)


def make_character(cid="C0", first_name="Sylura", location_id=None):
    char = Character(id=cid, first_name=first_name, family_name="Vane")
    char.current_state.location_id = location_id
    return char


# ---------------------------------------------------------------------------
# Condition serialization
# ---------------------------------------------------------------------------

def test_condition_round_trips_flat_json():
    raw = {"check": "prose_contains", "any": ["blackout", "darkness"], "description": "lights out"}
    cond = Condition.from_dict(raw)
    assert cond.check == "prose_contains"
    assert cond.params == {"any": ["blackout", "darkness"]}
    assert cond.description == "lights out"
    assert cond.to_dict() == raw


def test_builtin_checkers_registered():
    names = list_checkers()
    for expected in ("prose_contains", "char_in_prose", "char_at_location",
                     "tension_at_least", "tension_at_most", "loop_resolved",
                     "entity_exists"):
        assert expected in names


# ---------------------------------------------------------------------------
# Individual checkers
# ---------------------------------------------------------------------------

def test_prose_contains_any():
    ctx = CheckContext(memory=FakeMemory(), prose="The lights died. Darkness everywhere.")
    assert Condition("prose_contains", {"any": ["blackout", "darkness"]}).evaluate(ctx)
    assert not Condition("prose_contains", {"any": ["sunrise"]}).evaluate(ctx)


def test_prose_contains_all():
    ctx = CheckContext(memory=FakeMemory(), prose="A power surge caused the blackout.")
    assert Condition("prose_contains", {"all": ["power", "surge", "blackout"]}).evaluate(ctx)
    assert not Condition("prose_contains", {"all": ["power", "rescue"]}).evaluate(ctx)


def test_prose_check_requires_prose():
    ctx = CheckContext(memory=FakeMemory(), prose=None)
    with pytest.raises(ConditionError):
        Condition("prose_contains", {"any": ["x"]}).evaluate(ctx)


def test_char_in_prose_matches_first_name():
    mem = FakeMemory(characters={"C0": make_character()})
    ctx = CheckContext(memory=mem, prose="Sylura crept along the gantry.")
    assert Condition("char_in_prose", {"char": "C0"}).evaluate(ctx)


def test_char_at_location():
    mem = FakeMemory(characters={"C0": make_character(location_id="L1")})
    ctx = CheckContext(memory=mem)
    assert Condition("char_at_location", {"char": "C0", "location": "L1"}).evaluate(ctx)
    assert not Condition("char_at_location", {"char": "C0", "location": "L2"}).evaluate(ctx)


def test_tension_bounds():
    ctx = CheckContext(memory=FakeMemory(), scene_tension=8)
    assert Condition("tension_at_least", {"value": 7}).evaluate(ctx)
    assert not Condition("tension_at_least", {"value": 9}).evaluate(ctx)
    assert Condition("tension_at_most", {"value": 8}).evaluate(ctx)


def test_loop_resolved():
    loop = OpenLoop(id="OL3", status="resolved", description="escape the pit")
    ctx = CheckContext(memory=FakeMemory(loops=[loop]))
    assert Condition("loop_resolved", {"loop": "OL3"}).evaluate(ctx)


# ---------------------------------------------------------------------------
# Aggregation & graceful degradation
# ---------------------------------------------------------------------------

def test_evaluate_collects_all_failures_without_raising():
    mem = FakeMemory(characters={"C0": make_character()})
    ctx = CheckContext(memory=mem, prose="Sylura ran.", scene_tension=3)
    conditions = [
        Condition("char_in_prose", {"char": "C0"}),         # pass
        Condition("tension_at_least", {"value": 7}),         # fail (3 < 7)
        Condition("bogus_check", {}),                        # unknown -> fail
        Condition("char_at_location", {"char": "C9", "location": "L1"}),  # error -> fail
    ]
    result = evaluate_conditions(conditions, ctx)
    assert not result.is_valid
    assert len(result.passed) == 1
    assert len(result.failures) == 3
    assert any("unknown check" in f for f in result.failures)


def test_beat_contract_round_trips_and_validates():
    contract = BeatContract(
        beat_id="PB001",
        description="Sylura triggers a blackout",
        postconditions=[
            Condition("prose_contains", {"any": ["blackout", "darkness"]}),
            Condition("tension_at_least", {"value": 7}),
        ],
        required_characters=["C0"],
        required_location="L1",
    )
    restored = BeatContract.from_dict(contract.to_dict())
    assert restored.to_dict() == contract.to_dict()

    ctx = CheckContext(memory=FakeMemory(), prose="Total blackout swept the pit.", scene_tension=8)
    result = restored.validate_postconditions(ctx)
    assert result.is_valid
