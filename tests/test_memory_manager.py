"""Tests for memory manager."""

import pytest
import tempfile
import shutil
from pathlib import Path

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Character, Location, RelationshipGraph


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def memory_manager(temp_project):
    """Create a memory manager instance."""
    return MemoryManager(temp_project)


def test_memory_manager_initialization(memory_manager, temp_project):
    """Test memory manager initializes directories correctly."""
    assert (temp_project / "memory").exists()
    assert (temp_project / "memory" / "characters").exists()
    assert (temp_project / "memory" / "locations").exists()
    assert (temp_project / "memory" / "scenes").exists()
    assert (temp_project / "memory" / "open_loops.json").exists()
    assert (temp_project / "memory" / "relationships.json").exists()
    assert (temp_project / "memory" / "counters.json").exists()


def test_generate_character_id(memory_manager):
    """Test character ID generation."""
    id1 = memory_manager.generate_id("character")
    id2 = memory_manager.generate_id("character")
    
    assert id1 == "C0"
    assert id2 == "C1"


def test_generate_location_id(memory_manager):
    """Test location ID generation."""
    id1 = memory_manager.generate_id("location")
    id2 = memory_manager.generate_id("location")
    
    assert id1 == "L0"
    assert id2 == "L1"


def test_generate_scene_id(memory_manager):
    """Test scene ID generation with zero-padding."""
    id1 = memory_manager.generate_id("scene")
    id2 = memory_manager.generate_id("scene")
    
    assert id1 == "S000"
    assert id2 == "S001"


def test_generate_relationship_id(memory_manager):
    """Test relationship ID generation."""
    id1 = memory_manager.generate_id("relationship")
    id2 = memory_manager.generate_id("relationship")
    
    assert id1 == "R0"
    assert id2 == "R1"


def test_save_and_load_character(memory_manager):
    """Test saving and loading a character."""
    char = Character(
        id="C0",
        name="Elena Thorne",
        role="protagonist",
        description="A skilled mapmaker"
    )
    
    memory_manager.save_character(char)
    loaded = memory_manager.load_character("C0")
    
    assert loaded is not None
    assert loaded.id == "C0"
    assert loaded.name == "Elena Thorne"
    assert loaded.role == "protagonist"


def test_update_character(memory_manager):
    """Test updating character fields."""
    char = Character(
        id="C0",
        name="Elena Thorne",
        role="protagonist"
    )
    
    memory_manager.save_character(char)
    memory_manager.update_character("C0", {"role": "antagonist", "description": "Changed"})
    
    loaded = memory_manager.load_character("C0")
    assert loaded.role == "antagonist"
    assert loaded.description == "Changed"


def test_list_characters(memory_manager):
    """Test listing all characters."""
    char1 = Character(id="C0", name="Elena")
    char2 = Character(id="C1", name="Marcus")
    
    memory_manager.save_character(char1)
    memory_manager.save_character(char2)
    
    char_ids = memory_manager.list_characters()
    assert "C0" in char_ids
    assert "C1" in char_ids


def test_save_and_load_location(memory_manager):
    """Test saving and loading a location."""
    loc = Location(
        id="L0",
        name="The Archive",
        description="A vast library"
    )
    
    memory_manager.save_location(loc)
    loaded = memory_manager.load_location("L0")
    
    assert loaded is not None
    assert loaded.id == "L0"
    assert loaded.name == "The Archive"


def test_add_and_load_relationship(memory_manager):
    """Test adding and loading relationships."""
    rel = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="mentor-student",
        perspective_a="My teacher",
        perspective_b="My student"
    )
    
    memory_manager.add_relationship(rel)
    relationships = memory_manager.load_relationships()
    
    assert len(relationships) == 1
    assert relationships[0].id == "R0"
    assert relationships[0].character_a == "C0"


def test_get_character_relationships(memory_manager):
    """Test getting relationships for a character."""
    rel1 = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="friends"
    )
    rel2 = RelationshipGraph(
        id="R1",
        character_a="C0",
        character_b="C2",
        relationship_type="rivals"
    )
    rel3 = RelationshipGraph(
        id="R2",
        character_a="C1",
        character_b="C2",
        relationship_type="siblings"
    )
    
    memory_manager.add_relationship(rel1)
    memory_manager.add_relationship(rel2)
    memory_manager.add_relationship(rel3)
    
    c0_rels = memory_manager.get_character_relationships("C0")
    assert len(c0_rels) == 2
    
    c1_rels = memory_manager.get_character_relationships("C1")
    assert len(c1_rels) == 2


def test_get_relationship_between(memory_manager):
    """Test getting relationship between two characters."""
    rel = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="friends"
    )
    
    memory_manager.add_relationship(rel)
    
    # Should work in both orders
    found1 = memory_manager.get_relationship_between("C0", "C1")
    found2 = memory_manager.get_relationship_between("C1", "C0")
    
    assert found1 is not None
    assert found2 is not None
    assert found1.id == "R0"
    assert found2.id == "R0"
    
    # Should return None for non-existent relationship
    not_found = memory_manager.get_relationship_between("C0", "C2")
    assert not_found is None


def test_update_relationship(memory_manager):
    """Test updating a relationship."""
    rel = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="friends",
        status="close"
    )
    
    memory_manager.add_relationship(rel)
    memory_manager.update_relationship("R0", {"status": "strained", "intensity": 8})
    
    relationships = memory_manager.load_relationships()
    assert relationships[0].status == "strained"
    assert relationships[0].intensity == 8
