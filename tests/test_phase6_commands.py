"""Tests for Phase 6 CLI commands."""
import pytest
import json
from pathlib import Path
from novel_agent.cli.commands.status import get_status_info
from novel_agent.cli.commands.list import (
    list_characters,
    list_locations,
    list_open_loops,
    list_scenes
)
from novel_agent.cli.commands.inspect import find_entity_file
from novel_agent.cli.commands.compile import (
    parse_scene_range,
    get_scene_files,
    compile_to_markdown
)
from novel_agent.memory.checkpoint import (
    get_checkpoint_id,
    should_create_checkpoint
)


def test_parse_scene_range():
    """Test scene range parsing."""
    # Single range
    assert parse_scene_range("1-5") == [1, 2, 3, 4, 5]
    
    # Multiple ranges
    assert parse_scene_range("1-3,5,7-9") == [1, 2, 3, 5, 7, 8, 9]
    
    # Single numbers
    assert parse_scene_range("1,3,5") == [1, 3, 5]


def test_checkpoint_id_generation():
    """Test checkpoint ID generation."""
    assert get_checkpoint_id(0) == "checkpoint_tick_000"
    assert get_checkpoint_id(10) == "checkpoint_tick_010"
    assert get_checkpoint_id(123) == "checkpoint_tick_123"


def test_should_create_checkpoint():
    """Test checkpoint creation logic."""
    # First checkpoint at interval
    assert should_create_checkpoint(10, 10, None) == True
    assert should_create_checkpoint(5, 10, None) == False
    
    # Subsequent checkpoints
    assert should_create_checkpoint(20, 10, 10) == True
    assert should_create_checkpoint(15, 10, 10) == False
    
    # Disabled checkpoints
    assert should_create_checkpoint(10, 0, None) == False
    assert should_create_checkpoint(10, -1, None) == False


def test_get_status_info_empty_project(tmp_path):
    """Test status info with empty project."""
    # Create minimal project structure
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()
    (project_dir / "memory").mkdir()
    (project_dir / "memory" / "characters").mkdir()
    (project_dir / "memory" / "locations").mkdir()
    (project_dir / "scenes").mkdir()
    
    # Create state file
    state = {
        "novel_name": "Test Novel",
        "current_tick": 0,
        "active_character": None,
        "created_at": "2025-01-01T00:00:00Z",
        "last_updated": "2025-01-01T00:00:00Z"
    }
    
    state_file = project_dir / "state.json"
    with open(state_file, 'w') as f:
        json.dump(state, f)
    
    # Create empty open_loops.json
    loops_file = project_dir / "memory" / "open_loops.json"
    with open(loops_file, 'w') as f:
        json.dump({"loops": []}, f)
    
    # Get status info
    info = get_status_info(project_dir, state)
    
    assert info['novel_name'] == "Test Novel"
    assert info['current_tick'] == 0
    assert info['scenes_written'] == 0
    assert info['characters'] == 0
    assert info['locations'] == 0
    assert info['open_loops'] == 0


def test_list_characters_empty(tmp_path):
    """Test listing characters in empty project."""
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()
    (project_dir / "memory" / "characters").mkdir(parents=True)
    
    characters = list_characters(project_dir, verbose=False)
    assert characters == []


def test_list_locations_empty(tmp_path):
    """Test listing locations in empty project."""
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()
    (project_dir / "memory" / "locations").mkdir(parents=True)
    
    locations = list_locations(project_dir, verbose=False)
    assert locations == []


def test_list_open_loops_empty(tmp_path):
    """Test listing open loops in empty project."""
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()
    (project_dir / "memory").mkdir()
    
    loops_file = project_dir / "memory" / "open_loops.json"
    with open(loops_file, 'w') as f:
        json.dump({"loops": []}, f)
    
    loops = list_open_loops(project_dir, verbose=False)
    assert loops == []


def test_list_scenes_empty(tmp_path):
    """Test listing scenes in empty project."""
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()
    (project_dir / "scenes").mkdir()
    (project_dir / "memory" / "scenes").mkdir(parents=True)
    
    scenes = list_scenes(project_dir, verbose=False)
    assert scenes == []


def test_find_entity_file(tmp_path):
    """Test finding entity files by ID."""
    project_dir = tmp_path / "test_novel"
    (project_dir / "memory" / "characters").mkdir(parents=True)
    (project_dir / "memory" / "locations").mkdir(parents=True)
    
    # Create test files
    char_file = project_dir / "memory" / "characters" / "C0.json"
    char_file.write_text('{"id": "C0", "name": "Test"}')
    
    loc_file = project_dir / "memory" / "locations" / "L0.json"
    loc_file.write_text('{"id": "L0", "name": "Test Location"}')
    
    # Test finding
    assert find_entity_file(project_dir, "C0") == char_file
    assert find_entity_file(project_dir, "L0") == loc_file
    assert find_entity_file(project_dir, "C999") is None


def test_compile_to_markdown_empty(tmp_path):
    """Test compiling empty project."""
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()
    (project_dir / "scenes").mkdir()
    (project_dir / "memory" / "characters").mkdir(parents=True)
    (project_dir / "memory" / "locations").mkdir(parents=True)
    
    # Create state file
    state = {
        "novel_name": "Test Novel",
        "current_tick": 0,
        "created_at": "2025-01-01T00:00:00Z"
    }
    state_file = project_dir / "state.json"
    with open(state_file, 'w') as f:
        json.dump(state, f)
    
    # Compile with no scenes
    result = compile_to_markdown(project_dir, [], include_metadata=True)
    
    assert "Test Novel" in result
    assert "Generated by StoryDaemon" in result
    assert "**Scenes:** 0" in result  # Fixed: markdown bold format


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
