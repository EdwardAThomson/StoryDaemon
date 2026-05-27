"""Phase 1: planner POV/location refs resolve to canonical IDs (no prefix guessing)."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Character, Location
from novel_agent.agent.agent import StoryAgent


class _Shim:
    """Minimal stand-in exposing only what the resolution methods touch."""

    def __init__(self, mm):
        self.memory = mm

    def resolve(self, plan):
        StoryAgent._resolve_plan_entities(self, plan)

    def update_with_ids(self, plan, entity_results):
        StoryAgent._update_plan_with_entity_ids(self, plan, entity_results)

    # _update_plan_with_entity_ids calls self._resolve_plan_entities
    def _resolve_plan_entities(self, plan):
        StoryAgent._resolve_plan_entities(self, plan)


@pytest.fixture
def shim():
    d = Path(tempfile.mkdtemp())
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Joran", family_name="Vell",
                               role="protagonist", description="lead", nicknames=["Jo"]))
    mm.save_location(Location(id="L000", name="The Citadel", description="a fortress"))
    yield _Shim(mm)
    shutil.rmtree(d, ignore_errors=True)


def test_name_and_nickname_resolve_to_id(shim):
    plan = {"pov_character": "Joran"}
    shim.resolve(plan)
    assert plan["pov_character"] == "C000"

    plan = {"pov_character": "Jo"}  # nickname
    shim.resolve(plan)
    assert plan["pov_character"] == "C000"


def test_real_id_round_trips(shim):
    plan = {"pov_character": "C000", "target_location": "L000"}
    shim.resolve(plan)
    assert plan["pov_character"] == "C000"
    assert plan["target_location"] == "L000"


def test_location_name_resolves(shim):
    plan = {"target_location": "The Citadel"}
    shim.resolve(plan)
    assert plan["target_location"] == "L000"


def test_phantom_ref_left_for_fallback(shim):
    # "Caleb" starts with C but is not an ID and matches no character -> untouched.
    plan = {"pov_character": "Caleb"}
    shim.resolve(plan)
    assert plan["pov_character"] == "Caleb"


def test_update_falls_back_to_generated_id(shim):
    # Planner used a placeholder that resolves to nothing; a char was generated.
    plan = {"pov_character": "PROTAGONIST", "target_location": "SOMEWHERE"}
    entity_results = {"actions_executed": [
        {"tool": "character.generate", "success": True, "result": {"character_id": "C001"}},
        {"tool": "location.generate", "success": True, "result": {"location_id": "L001"}},
    ]}
    shim.update_with_ids(plan, entity_results)
    assert plan["pov_character"] == "C001"
    assert plan["target_location"] == "L001"


def test_update_does_not_clobber_resolved_ref(shim):
    # POV names an existing character -> keep it, ignore the freshly generated one.
    plan = {"pov_character": "Joran"}
    entity_results = {"actions_executed": [
        {"tool": "character.generate", "success": True, "result": {"character_id": "C001"}},
    ]}
    shim.update_with_ids(plan, entity_results)
    assert plan["pov_character"] == "C000"
