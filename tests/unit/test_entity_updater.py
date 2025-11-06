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
        id="C0",
        name="Sarah",
        current_state=CurrentState(emotional_state="calm")
    )
    mock_memory.load_character.return_value = character
    
    # Update
    update = {
        "id": "C0",
        "changes": {
            "emotional_state": "anxious"
        }
    }
    
    result = entity_updater._update_character(update, tick=1, scene_id="S001")
    
    # Verify
    assert result is True
    assert character.current_state.emotional_state == "anxious"
    assert len(character.history) == 1
    assert character.history[0].tick == 1
    mock_memory.save_character.assert_called_once_with(character)


def test_update_character_inventory(entity_updater, mock_memory):
    """Test updating character inventory (list field)."""
    # Create test character
    character = Character(
        id="C0",
        name="Sarah",
        current_state=CurrentState(inventory=["sword"])
    )
    mock_memory.load_character.return_value = character
    
    # Update - add new items
    update = {
        "id": "C0",
        "changes": {
            "inventory": ["key", "map"]
        }
    }
    
    result = entity_updater._update_character(update, tick=1, scene_id="S001")
    
    # Verify - should append, not replace
    assert result is True
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
    
    # Should return False and not save
    assert result is False
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
    character = Character(id="C0", name="Sarah", current_state=CurrentState())
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
