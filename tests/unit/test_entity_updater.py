"""Unit tests for EntityUpdater."""

import pytest
from unittest.mock import Mock, MagicMock
from novel_agent.agent.entity_updater import EntityUpdater
from novel_agent.memory.entities import Character, Location, CurrentState, OpenLoop


@pytest.fixture
def mock_memory():
    """Mock memory manager."""
    memory = Mock()
    return memory


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return Mock()


@pytest.fixture
def entity_updater(mock_memory, mock_config):
    """Create EntityUpdater instance."""
    return EntityUpdater(mock_memory, mock_config)


def test_update_character_emotional_state(entity_updater, mock_memory):
    """Test updating character emotional state."""
    # Create test character
    character = Character(
        id="C001",
        first_name="Bob",
        family_name="Smith",
        role="protagonist",
        description="A clever thief",
        current_state=CurrentState(emotional_state="calm")
    )
    mock_memory.load_character.return_value = character
    
    # Update
    update = {
        "id": "C001",
        "changes": {
            "emotional_state": "anxious"
        }
    }
    
    result = entity_updater._update_character(update, tick=1, scene_id="S001")
    
    # Verify
    assert result == "updated"
    assert character.current_state.emotional_state == "anxious"
    assert len(character.history) == 1
    assert character.history[0].tick == 1
    mock_memory.save_character.assert_called_once_with(character)


def test_update_character_inventory(entity_updater, mock_memory):
    """Test updating character inventory (list field)."""
    # Create test character
    character = Character(
        id="C001",
        first_name="Alice",
        family_name="Johnson",
        role="protagonist",
        description="A brave adventurer",
        current_state=CurrentState(inventory=["sword"])
    )
    mock_memory.load_character.return_value = character
    
    # Update - add new items
    update = {
        "id": "C001",
        "changes": {
            "inventory": ["key", "map"]
        }
    }
    
    result = entity_updater._update_character(update, tick=1, scene_id="S001")
    
    # Verify - should append, not replace
    assert result == "updated"
    assert "sword" in character.current_state.inventory
    assert "key" in character.current_state.inventory
    assert "map" in character.current_state.inventory
    assert len(character.current_state.inventory) == 3


def test_update_character_not_found(entity_updater, mock_memory):
    """Test updating non-existent character."""
    mock_memory.load_character.return_value = None
    
    update = {
        "id": "C999",
        "changes": {
            "emotional_state": "happy"
        }
    }
    
    result = entity_updater._update_character(update, tick=1, scene_id="S001")
    
    # Should return empty string and not save
    assert result == ""
    mock_memory.save_character.assert_not_called()


def test_update_location(entity_updater, mock_memory):
    """Test updating location."""
    # Create test location
    location = Location(
        id="L0",
        name="Tavern",
        atmosphere="lively"
    )
    mock_memory.load_location.return_value = location
    
    # Update
    update = {
        "id": "L0",
        "changes": {
            "atmosphere": "tense"
        }
    }
    
    result = entity_updater._update_location(update, tick=1, scene_id="S001")
    
    # Verify
    assert result is True
    assert location.atmosphere == "tense"
    assert len(location.history) == 1
    mock_memory.save_location.assert_called_once_with(location)


def test_create_open_loop(entity_updater, mock_memory):
    """Test creating open loop."""
    mock_memory.generate_id.return_value = "OL1"
    
    loop_data = {
        "description": "Find the artifact",
        "importance": "high",
        "category": "goal",
        "related_characters": ["C0"],
        "related_locations": ["L0"]
    }
    
    result = entity_updater._create_open_loop(loop_data, tick=1, scene_id="S001")

    # Verify
    assert result == "created"
    mock_memory.add_open_loop.assert_called_once()
    
    # Check the loop that was created
    created_loop = mock_memory.add_open_loop.call_args[0][0]
    assert created_loop.id == "OL1"
    assert created_loop.description == "Find the artifact"
    assert created_loop.importance == "high"


def test_resolve_open_loop(entity_updater, mock_memory):
    """Test resolving open loop."""
    result = entity_updater._resolve_open_loop("OL1", tick=5, scene_id="S005")
    
    # Verify
    assert result is True
    mock_memory.resolve_open_loop.assert_called_once_with(
        loop_id="OL1",
        scene_id="S005",
        summary="Resolved in scene S005"
    )


def test_apply_updates_all_types(entity_updater, mock_memory):
    """Test applying all types of updates."""
    # Setup mocks
    character = Character(id="C0", first_name="Sarah", current_state=CurrentState())
    mock_memory.load_character.return_value = character
    mock_memory.generate_id.return_value = "OL1"
    
    # Facts with all update types
    facts = {
        "character_updates": [
            {"id": "C0", "changes": {"emotional_state": "anxious"}}
        ],
        "location_updates": [],
        "open_loops_created": [
            {"description": "Test loop", "importance": "medium", "category": "goal"}
        ],
        "open_loops_resolved": ["OL0"],
        "relationship_changes": []
    }
    
    stats = entity_updater.apply_updates(facts, tick=1, scene_id="S001")
    
    # Verify stats
    assert stats["characters_updated"] == 1
    assert stats["loops_created"] == 1
    assert stats["loops_resolved"] == 1


def test_pov_switch_detection_creates_new_character(entity_updater, mock_memory):
    """Test that POV switch to different character creates new character entity."""
    # Setup: Existing character C0 is "Alice"
    existing_character = Character(
        id="C0",
        first_name="Alice",
        family_name="Smith",
        role="protagonist",
        current_state=CurrentState()
    )
    mock_memory.load_character.return_value = existing_character
    mock_memory.generate_id.return_value = "C1"
    
    # Scene context indicates POV is now "Bob Johnson" (different character)
    scene_context = {
        "pov_character_id": "C0",  # LLM still thinks it's C0
        "pov_character_name": "Bob Johnson"  # But the name is different!
    }
    
    # Character update for "C0" (which is actually Bob)
    update = {
        "id": "C0",
        "changes": {
            "emotional_state": "confident"
        }
    }
    
    result = entity_updater._update_character(update, tick=5, scene_id="S005", scene_context=scene_context)
    
    # Verify: Should create new character, not update existing
    assert result == "created"
    mock_memory.save_character.assert_called_once()
    mock_memory.set_active_character.assert_called_once_with("C1")
    
    # Verify the created character has correct name
    created_char = mock_memory.save_character.call_args[0][0]
    assert created_char.first_name == "Bob"
    assert created_char.family_name == "Johnson"
    assert created_char.id == "C1"


def test_pov_switch_detection_same_character_updates_normally(entity_updater, mock_memory):
    """Test that same POV character updates normally without creating new entity."""
    # Setup: Existing character C0 is "Alice Smith"
    existing_character = Character(
        id="C0",
        first_name="Alice",
        family_name="Smith",
        role="protagonist",
        current_state=CurrentState()
    )
    mock_memory.load_character.return_value = existing_character
    
    # Scene context indicates POV is still "Alice Smith"
    scene_context = {
        "pov_character_id": "C0",
        "pov_character_name": "Alice Smith"  # Same character
    }
    
    # Character update for C0
    update = {
        "id": "C0",
        "changes": {
            "emotional_state": "happy"
        }
    }
    
    result = entity_updater._update_character(update, tick=2, scene_id="S002", scene_context=scene_context)
    
    # Verify: Should update existing character
    assert result == "updated"
    assert existing_character.current_state.emotional_state == "happy"
    mock_memory.save_character.assert_called_once_with(existing_character)
    mock_memory.set_active_character.assert_not_called()


# ---------------------------------------------------------------------------
# Loop creation hygiene (Phase 3, Slice 0 of the interleaving design):
# deterministic dedup against existing open loops, plus the per-tick cap.
# ---------------------------------------------------------------------------

from difflib import SequenceMatcher

from novel_agent.configs.config import Config


def _hygiene_updater(mock_memory, **overrides):
    """EntityUpdater over a real Config so the dedup gates actually read."""
    config = Config()
    for key, value in overrides.items():
        config.set(key, value)
    return EntityUpdater(mock_memory, config)


_EXISTING_DESC = "Will Aris stay silent about the data heist after the merger closes?"


def _open_loop(loop_id="OL001", description=_EXISTING_DESC, status="open"):
    return OpenLoop(id=loop_id, description=description, status=status)


def test_near_duplicate_loop_skipped_with_count(mock_memory):
    """A light rewording of an existing open loop is skipped, not created."""
    updater = _hygiene_updater(mock_memory)
    mock_memory.load_open_loops.return_value = [_open_loop()]

    result = updater._create_open_loop(
        {"description": "Will Aris stay silent about the data heist after the merger closes"},
        tick=3, scene_id="S003")

    assert result == "duplicate"
    mock_memory.add_open_loop.assert_not_called()


def test_dedup_is_case_insensitive(mock_memory):
    updater = _hygiene_updater(mock_memory)
    mock_memory.load_open_loops.return_value = [_open_loop()]

    result = updater._create_open_loop(
        {"description": _EXISTING_DESC.upper()}, tick=3, scene_id="S003")

    assert result == "duplicate"


def test_distinct_loop_kept(mock_memory):
    updater = _hygiene_updater(mock_memory)
    mock_memory.load_open_loops.return_value = [_open_loop()]
    mock_memory.generate_id.return_value = "OL002"

    result = updater._create_open_loop(
        {"description": "Who is funding the Meridian Initiative shell companies?"},
        tick=3, scene_id="S003")

    assert result == "created"
    mock_memory.add_open_loop.assert_called_once()


def test_resolved_loops_do_not_block_creation(mock_memory):
    """Only OPEN loops participate: a resolved question may legitimately reopen."""
    updater = _hygiene_updater(mock_memory)
    mock_memory.load_open_loops.return_value = [_open_loop(status="resolved")]
    mock_memory.generate_id.return_value = "OL002"

    result = updater._create_open_loop(
        {"description": _EXISTING_DESC}, tick=3, scene_id="S003")

    assert result == "created"


def test_dedup_default_threshold_is_075():
    """Default lowered 0.8 -> 0.75 (docs/progress_report_20260712.md section 8.3):
    two documented near-misses at 0.784/0.788 sat just under the old threshold."""
    assert Config().get('coherence.loop_dedup_threshold') == 0.75


def test_documented_near_miss_pair_now_dedups_at_defaults(mock_memory):
    """The triple run's OL23/OL27 (verbatim, ratio 0.788): semantically the same
    legal-firm question, double-created under 0.8 and then double-closed by one
    event. At the 0.75 default it dedups. Semantic dedup remains the roadmap
    fix for the paraphrase species character matching can never see."""
    ol23 = ("Will the legal firm accept Darol's case and provide representation "
            "before Brixoth moves against her?")
    ol27 = ("Will the legal firm accept Darol's whistleblower case and provide "
            "representation before Brixoth discovers her decision to escalate?")
    ratio = SequenceMatcher(None, ol27.strip().lower(), ol23.strip().lower()).ratio()
    assert 0.75 <= ratio < 0.8  # the blind-spot band the change closes

    updater = _hygiene_updater(mock_memory)
    mock_memory.load_open_loops.return_value = [_open_loop(description=ol23)]

    result = updater._create_open_loop({"description": ol27}, tick=7, scene_id="S007")

    assert result == "duplicate"
    mock_memory.add_open_loop.assert_not_called()


def test_dedup_threshold_boundary(mock_memory):
    """The threshold is inclusive: ratio == threshold dedups, just above it keeps."""
    new_desc = "Will Aris stay quiet about the data heist after the merger closes?"
    ratio = SequenceMatcher(
        None, new_desc.strip().lower(), _EXISTING_DESC.strip().lower()).ratio()

    mock_memory.load_open_loops.return_value = [_open_loop()]

    at_threshold = _hygiene_updater(
        mock_memory, **{"coherence.loop_dedup_threshold": ratio})
    assert at_threshold._create_open_loop(
        {"description": new_desc}, tick=3, scene_id="S003") == "duplicate"

    mock_memory.generate_id.return_value = "OL002"
    above_threshold = _hygiene_updater(
        mock_memory, **{"coherence.loop_dedup_threshold": ratio + 0.0001})
    assert above_threshold._create_open_loop(
        {"description": new_desc}, tick=3, scene_id="S003") == "created"


def test_dedup_gate_off_restores_old_behavior(mock_memory):
    updater = _hygiene_updater(mock_memory, **{"coherence.loop_dedup": False})
    mock_memory.load_open_loops.return_value = [_open_loop()]
    mock_memory.generate_id.return_value = "OL002"

    result = updater._create_open_loop(
        {"description": _EXISTING_DESC}, tick=3, scene_id="S003")

    assert result == "created"
    mock_memory.add_open_loop.assert_called_once()


def test_dedup_never_raises_on_ledger_failure(mock_memory):
    """An unreadable ledger means no dedup, never a failed creation."""
    updater = _hygiene_updater(mock_memory)
    mock_memory.load_open_loops.side_effect = RuntimeError("ledger unreadable")
    mock_memory.generate_id.return_value = "OL002"

    result = updater._create_open_loop(
        {"description": _EXISTING_DESC}, tick=3, scene_id="S003")

    assert result == "created"


def test_creation_cap_drops_lowest_importance_first(mock_memory):
    updater = _hygiene_updater(mock_memory)
    loops = [
        {"description": "a", "importance": "low"},
        {"description": "b", "importance": "high"},
        {"description": "c", "importance": "medium"},
        {"description": "d", "importance": "low"},
        {"description": "e", "importance": "critical"},
        {"description": "f", "importance": "medium"},
    ]

    kept, dropped = updater._cap_new_loops(loops)

    assert dropped == 2
    # The two lows go; the survivors keep their original order.
    assert [d["description"] for d in kept] == ["b", "c", "e", "f"]


def test_creation_cap_ties_keep_earlier_entries(mock_memory):
    updater = _hygiene_updater(mock_memory, **{"coherence.loop_creation_cap": 2})
    loops = [{"description": str(i), "importance": "medium"} for i in range(4)]

    kept, dropped = updater._cap_new_loops(loops)

    assert dropped == 2
    assert [d["description"] for d in kept] == ["0", "1"]


def test_creation_cap_noop_under_cap(mock_memory):
    updater = _hygiene_updater(mock_memory)
    loops = [{"description": "a"}, {"description": "b"}]
    assert updater._cap_new_loops(loops) == (loops, 0)


def test_creation_cap_gate_off_keeps_everything(mock_memory):
    updater = _hygiene_updater(mock_memory, **{"coherence.loop_dedup": False})
    loops = [{"description": str(i)} for i in range(9)]
    assert updater._cap_new_loops(loops) == (loops, 0)


def test_creation_cap_disabled_by_none(mock_memory):
    updater = _hygiene_updater(mock_memory, **{"coherence.loop_creation_cap": None})
    loops = [{"description": str(i)} for i in range(9)]
    assert updater._cap_new_loops(loops) == (loops, 0)


def test_apply_updates_counts_dedup_and_cap(mock_memory):
    """The stats surface both hygiene counters for the rubric."""
    updater = _hygiene_updater(mock_memory, **{"coherence.loop_creation_cap": 2})
    mock_memory.load_open_loops.return_value = [_open_loop()]
    mock_memory.generate_id.return_value = "OL002"

    facts = {
        "open_loops_created": [
            {"description": _EXISTING_DESC, "importance": "high"},     # duplicate
            {"description": "Who tipped off the regulator?", "importance": "high"},
            {"description": "dropped by the cap", "importance": "low"},
        ],
    }
    stats = updater.apply_updates(facts, tick=3, scene_id="S003")

    assert stats["loops_capped"] == 1
    assert stats["loops_deduped"] == 1
    assert stats["loops_created"] == 1


def test_relationship_validation_both_characters_exist(entity_updater, mock_memory):
    """Test that relationships are created when both characters exist."""
    from novel_agent.memory.entities import RelationshipGraph
    
    # Setup: Both characters exist
    char_a = Character(id="C0", first_name="Alice", current_state=CurrentState())
    char_b = Character(id="C1", first_name="Bob", current_state=CurrentState())
    
    def load_character_side_effect(char_id):
        if char_id == "C0":
            return char_a
        elif char_id == "C1":
            return char_b
        return None
    
    mock_memory.load_character.side_effect = load_character_side_effect
    mock_memory.get_relationship_between.return_value = None
    mock_memory.generate_id.return_value = "R1"
    
    # Relationship change
    change = {
        "character_a": "C0",
        "character_b": "C1",
        "changes": {
            "status": "allies",
            "intensity": 7
        }
    }
    
    result = entity_updater._update_relationship(change, tick=3, scene_id="S003")
    
    # Verify: Should create relationship
    assert result is True
    mock_memory.add_relationship.assert_called_once()


def test_relationship_validation_character_missing(entity_updater, mock_memory):
    """Test that relationships are NOT created when a character is missing."""
    # Setup: Only C0 exists, C1 does not
    char_a = Character(id="C0", first_name="Alice", current_state=CurrentState())
    
    def load_character_side_effect(char_id):
        if char_id == "C0":
            return char_a
        return None  # C1 doesn't exist
    
    mock_memory.load_character.side_effect = load_character_side_effect
    
    # Relationship change with missing character
    change = {
        "character_a": "C0",
        "character_b": "C1",  # This character doesn't exist
        "changes": {
            "status": "allies"
        }
    }
    
    result = entity_updater._update_relationship(change, tick=3, scene_id="S003")
    
    # Verify: Should NOT create relationship
    assert result is False
    mock_memory.add_relationship.assert_not_called()
    mock_memory.update_relationship.assert_not_called()
