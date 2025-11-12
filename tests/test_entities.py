"""Tests for entity dataclasses."""

import pytest
from novel_agent.memory.entities import (
    Character, Location, Scene, OpenLoop, RelationshipGraph,
    PhysicalTraits, Personality, CurrentState
)


def test_character_creation():
    """Test creating a character entity."""
    char = Character(
        id="C0",
        first_name="Elena",
        family_name="Thorne",
        role="protagonist",
        description="A skilled mapmaker"
    )
    
    assert char.id == "C0"
    assert char.first_name == "Elena"
    assert char.family_name == "Thorne"
    assert char.full_name == "Elena Thorne"
    assert char.display_name == "Elena"
    assert char.role == "protagonist"
    assert char.type == "character"
    assert char.created_at != ""
    assert char.updated_at != ""


def test_character_serialization():
    """Test character to_dict and from_dict."""
    char = Character(
        id="C0",
        first_name="Elena",
        family_name="Thorne",
        role="protagonist",
        description="A skilled mapmaker",
        personality=Personality(
            core_traits=["meticulous", "curious"],
            fears=["failure"],
            desires=["discover truth"]
        )
    )
    
    # Serialize
    data = char.to_dict()
    assert data["id"] == "C0"
    assert data["first_name"] == "Elena"
    assert data["family_name"] == "Thorne"
    assert "personality" in data
    assert data["personality"]["core_traits"] == ["meticulous", "curious"]
    
    # Deserialize
    char2 = Character.from_dict(data)
    assert char2.id == char.id
    assert char2.name == char.name
    assert char2.personality.core_traits == char.personality.core_traits


def test_location_creation():
    """Test creating a location entity."""
    loc = Location(
        id="L0",
        name="The Archive",
        description="A vast underground library",
        atmosphere="musty, dimly lit"
    )
    
    assert loc.id == "L0"
    assert loc.name == "The Archive"
    assert loc.type == "location"


def test_location_serialization():
    """Test location to_dict and from_dict."""
    loc = Location(
        id="L0",
        name="The Archive",
        description="A vast underground library",
        features=["locked vault", "spiral staircase"]
    )
    
    data = loc.to_dict()
    assert data["id"] == "L0"
    assert data["features"] == ["locked vault", "spiral staircase"]
    
    loc2 = Location.from_dict(data)
    assert loc2.id == loc.id
    assert loc2.features == loc.features


def test_scene_creation():
    """Test creating a scene entity."""
    scene = Scene(
        id="S001",
        tick=1,
        title="The Hidden Fragment",
        pov_character_id="C0",
        location_id="L0"
    )
    
    assert scene.id == "S001"
    assert scene.tick == 1
    assert scene.type == "scene"


def test_open_loop_creation():
    """Test creating an open loop."""
    loop = OpenLoop(
        id="OL0",
        created_in_scene="S001",
        category="mystery",
        description="What does the map fragment lead to?",
        importance="high"
    )
    
    assert loop.id == "OL0"
    assert loop.status == "open"
    assert loop.category == "mystery"


def test_relationship_creation():
    """Test creating a relationship."""
    rel = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="mentor-student",
        perspective_a="My former teacher",
        perspective_b="My most promising student",
        status="strained"
    )
    
    assert rel.id == "R0"
    assert rel.character_a == "C0"
    assert rel.character_b == "C1"
    assert rel.status == "strained"


def test_relationship_involves_character():
    """Test relationship character involvement check."""
    rel = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="friends"
    )
    
    assert rel.involves_character("C0") is True
    assert rel.involves_character("C1") is True
    assert rel.involves_character("C2") is False


def test_relationship_get_other_character():
    """Test getting the other character in a relationship."""
    rel = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="friends"
    )
    
    assert rel.get_other_character("C0") == "C1"
    assert rel.get_other_character("C1") == "C0"
    assert rel.get_other_character("C2") is None


def test_relationship_get_perspective():
    """Test getting perspective from a character's viewpoint."""
    rel = RelationshipGraph(
        id="R0",
        character_a="C0",
        character_b="C1",
        relationship_type="mentor-student",
        perspective_a="My former teacher",
        perspective_b="My best student"
    )
    
    assert rel.get_perspective("C0") == "My former teacher"
    assert rel.get_perspective("C1") == "My best student"
    assert rel.get_perspective("C2") is None
