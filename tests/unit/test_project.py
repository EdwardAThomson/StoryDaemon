"""Tests for project management."""
import os
import tempfile
import pytest
from novel_agent.cli.project import (
    create_novel_project,
    find_project_dir,
    load_project_state,
    save_project_state
)


def test_create_novel_project():
    """Test creating a new novel project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = create_novel_project("test-novel", tmpdir)
        
        # Check directory exists
        assert os.path.exists(project_dir)
        assert os.path.basename(project_dir) == "test-novel"
        
        # Check subdirectories
        assert os.path.exists(os.path.join(project_dir, "memory", "characters"))
        assert os.path.exists(os.path.join(project_dir, "memory", "locations"))
        assert os.path.exists(os.path.join(project_dir, "memory", "scenes"))
        assert os.path.exists(os.path.join(project_dir, "memory", "index"))
        assert os.path.exists(os.path.join(project_dir, "scenes"))
        assert os.path.exists(os.path.join(project_dir, "plans"))
        
        # Check files
        assert os.path.exists(os.path.join(project_dir, "state.json"))
        assert os.path.exists(os.path.join(project_dir, "config.yaml"))
        assert os.path.exists(os.path.join(project_dir, "README.md"))
        assert os.path.exists(os.path.join(project_dir, "memory", "open_loops.json"))


def test_create_duplicate_project():
    """Test that creating a duplicate project raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create first project
        create_novel_project("test-novel", tmpdir)
        
        # Try to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            create_novel_project("test-novel", tmpdir)


def test_load_and_save_project_state():
    """Test loading and saving project state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = create_novel_project("test-novel", tmpdir)
        
        # Load initial state
        state = load_project_state(project_dir)
        assert state['novel_name'] == "test-novel"
        assert state['current_tick'] == 0
        assert state['active_character'] is None
        
        # Modify and save state
        state['current_tick'] = 5
        state['active_character'] = "C0"
        save_project_state(project_dir, state)
        
        # Load again and verify
        loaded_state = load_project_state(project_dir)
        assert loaded_state['current_tick'] == 5
        assert loaded_state['active_character'] == "C0"


def test_find_project_dir():
    """Test finding project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = create_novel_project("test-novel", tmpdir)
        
        # Find from project directory
        found_dir = find_project_dir(project_dir)
        assert found_dir == project_dir
        
        # Find from subdirectory
        subdir = os.path.join(project_dir, "scenes")
        found_dir = find_project_dir(subdir)
        assert found_dir == project_dir


def test_find_project_dir_not_found():
    """Test that find_project_dir raises error when not found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="No novel project found"):
            find_project_dir(tmpdir)
