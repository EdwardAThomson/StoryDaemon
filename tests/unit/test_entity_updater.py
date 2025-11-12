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
    assert result is True
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
