"""Tests for lore tracking system (Phase 7A.4)."""
import pytest
import tempfile
from pathlib import Path

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Lore
from novel_agent.memory.vector_store import VectorStore


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "memory").mkdir()
        yield project_dir


def test_lore_creation():
    """Test creating a Lore entity."""
    lore = Lore(
        id="L001",
        lore_type="rule",
        content="Magic requires verbal incantations",
        category="magic",
        source_scene_id="S001",
        tick=1,
        importance="critical",
        tags=["magic", "casting"]
    )
    
    assert lore.id == "L001"
    assert lore.lore_type == "rule"
    assert lore.content == "Magic requires verbal incantations"
    assert lore.category == "magic"
    assert lore.importance == "critical"
    assert "magic" in lore.tags


def test_lore_to_dict():
    """Test converting Lore to dictionary."""
    lore = Lore(
        id="L001",
        lore_type="constraint",
        content="FTL travel takes 3 days minimum",
        category="technology",
        source_scene_id="S002",
        tick=2
    )
    
    lore_dict = lore.to_dict()
    
    assert lore_dict['id'] == "L001"
    assert lore_dict['lore_type'] == "constraint"
    assert lore_dict['content'] == "FTL travel takes 3 days minimum"
    assert lore_dict['category'] == "technology"


def test_lore_from_dict():
    """Test creating Lore from dictionary."""
    lore_dict = {
        'id': "L001",
        'type': "lore",
        'lore_type': "fact",
        'content': "The city has 500 residents",
        'category': "society",
        'source_scene_id': "S003",
        'tick': 3,
        'importance': "normal",
        'tags': ["population", "city"],
        'related_lore': [],
        'potential_contradictions': [],
        'created_at': "2025-01-01T00:00:00Z"
    }
    
    lore = Lore.from_dict(lore_dict)
    
    assert lore.id == "L001"
    assert lore.lore_type == "fact"
    assert lore.content == "The city has 500 residents"
    assert lore.category == "society"


def test_memory_manager_lore_operations(temp_project):
    """Test MemoryManager lore operations."""
    memory = MemoryManager(temp_project)
    
    # Generate ID
    lore_id = memory.generate_lore_id()
    assert lore_id == "L001"
    
    # Create and save lore
    lore = Lore(
        id=lore_id,
        lore_type="rule",
        content="Magic requires verbal incantations",
        category="magic",
        source_scene_id="S001",
        tick=1
    )
    memory.save_lore(lore)
    
    # Load lore
    loaded = memory.load_lore(lore_id)
    assert loaded is not None
    assert loaded.id == lore_id
    assert loaded.content == "Magic requires verbal incantations"
    
    # Load all lore
    all_lore = memory.load_all_lore()
    assert len(all_lore) == 1
    assert all_lore[0].id == lore_id


def test_memory_manager_lore_by_category(temp_project):
    """Test filtering lore by category."""
    memory = MemoryManager(temp_project)
    
    # Create lore in different categories
    lore1 = Lore(
        id=memory.generate_lore_id(),
        lore_type="rule",
        content="Magic requires incantations",
        category="magic",
        source_scene_id="S001",
        tick=1
    )
    lore2 = Lore(
        id=memory.generate_lore_id(),
        lore_type="constraint",
        content="FTL takes 3 days",
        category="technology",
        source_scene_id="S002",
        tick=2
    )
    lore3 = Lore(
        id=memory.generate_lore_id(),
        lore_type="fact",
        content="Spells have cooldowns",
        category="magic",
        source_scene_id="S003",
        tick=3
    )
    
    memory.save_lore(lore1)
    memory.save_lore(lore2)
    memory.save_lore(lore3)
    
    # Filter by category
    magic_lore = memory.list_lore_by_category("magic")
    assert len(magic_lore) == 2
    assert all(l.category == "magic" for l in magic_lore)
    
    tech_lore = memory.list_lore_by_category("technology")
    assert len(tech_lore) == 1
    assert tech_lore[0].category == "technology"


def test_memory_manager_lore_by_type(temp_project):
    """Test filtering lore by type."""
    memory = MemoryManager(temp_project)
    
    # Create lore of different types
    lore1 = Lore(
        id=memory.generate_lore_id(),
        lore_type="rule",
        content="Magic requires incantations",
        category="magic",
        source_scene_id="S001",
        tick=1
    )
    lore2 = Lore(
        id=memory.generate_lore_id(),
        lore_type="constraint",
        content="FTL takes 3 days",
        category="technology",
        source_scene_id="S002",
        tick=2
    )
    lore3 = Lore(
        id=memory.generate_lore_id(),
        lore_type="rule",
        content="No magic on Sundays",
        category="magic",
        source_scene_id="S003",
        tick=3
    )
    
    memory.save_lore(lore1)
    memory.save_lore(lore2)
    memory.save_lore(lore3)
    
    # Filter by type
    rules = memory.list_lore_by_type("rule")
    assert len(rules) == 2
    assert all(l.lore_type == "rule" for l in rules)
    
    constraints = memory.list_lore_by_type("constraint")
    assert len(constraints) == 1
    assert constraints[0].lore_type == "constraint"


def test_memory_manager_delete_lore(temp_project):
    """Test deleting lore."""
    memory = MemoryManager(temp_project)
    
    # Create and save lore
    lore_id = memory.generate_lore_id()
    lore = Lore(
        id=lore_id,
        lore_type="fact",
        content="Test lore",
        category="test",
        source_scene_id="S001",
        tick=1
    )
    memory.save_lore(lore)
    
    # Verify it exists
    assert memory.load_lore(lore_id) is not None
    
    # Delete it
    memory.delete_lore(lore_id)
    
    # Verify it's gone
    assert memory.load_lore(lore_id) is None
    assert len(memory.load_all_lore()) == 0


def test_vector_store_lore_indexing(temp_project):
    """Test indexing lore in vector store."""
    vector = VectorStore(temp_project)
    
    lore = Lore(
        id="L001",
        lore_type="rule",
        content="Magic requires verbal incantations to function properly",
        category="magic",
        source_scene_id="S001",
        tick=1,
        importance="critical",
        tags=["magic", "casting", "requirements"]
    )
    
    # Index the lore
    vector.index_lore(lore)
    
    # Verify it was indexed
    counts = vector.get_collection_counts()
    assert counts['lore'] == 1


def test_vector_store_lore_search(temp_project):
    """Test searching for lore."""
    vector = VectorStore(temp_project)
    
    # Index multiple lore items
    lore1 = Lore(
        id="L001",
        lore_type="rule",
        content="Magic requires verbal incantations",
        category="magic",
        source_scene_id="S001",
        tick=1
    )
    lore2 = Lore(
        id="L002",
        lore_type="constraint",
        content="FTL travel takes minimum 3 days between systems",
        category="technology",
        source_scene_id="S002",
        tick=2
    )
    lore3 = Lore(
        id="L003",
        lore_type="capability",
        content="Wizards can cast spells silently with training",
        category="magic",
        source_scene_id="S003",
        tick=3
    )
    
    vector.index_lore(lore1)
    vector.index_lore(lore2)
    vector.index_lore(lore3)
    
    # Search for magic-related lore
    results = vector.search_lore("magic spells", n_results=3)
    
    assert len(results) > 0
    # Should find magic-related lore
    magic_results = [r for r in results if r['metadata']['category'] == 'magic']
    assert len(magic_results) >= 2


def test_vector_store_lore_search_with_filters(temp_project):
    """Test searching lore with category filter."""
    vector = VectorStore(temp_project)
    
    # Index lore
    lore1 = Lore(
        id="L001",
        lore_type="rule",
        content="Magic requires verbal incantations",
        category="magic",
        source_scene_id="S001",
        tick=1
    )
    lore2 = Lore(
        id="L002",
        lore_type="rule",
        content="FTL requires antimatter fuel",
        category="technology",
        source_scene_id="S002",
        tick=2
    )
    
    vector.index_lore(lore1)
    vector.index_lore(lore2)
    
    # Search with category filter
    results = vector.search_lore("requires", n_results=5, category="magic")
    
    # Should only return magic lore
    assert len(results) >= 1
    for result in results:
        assert result['metadata']['category'] == 'magic'


def test_lore_update(temp_project):
    """Test updating existing lore."""
    memory = MemoryManager(temp_project)
    
    # Create and save lore
    lore_id = memory.generate_lore_id()
    lore = Lore(
        id=lore_id,
        lore_type="rule",
        content="Original content",
        category="magic",
        source_scene_id="S001",
        tick=1
    )
    memory.save_lore(lore)
    
    # Update the lore
    lore.content = "Updated content"
    lore.importance = "critical"
    memory.save_lore(lore)
    
    # Load and verify
    loaded = memory.load_lore(lore_id)
    assert loaded.content == "Updated content"
    assert loaded.importance == "critical"
    
    # Should still only have one lore item
    assert len(memory.load_all_lore()) == 1


def test_lore_contradictions_field():
    """Test lore contradiction tracking fields."""
    lore = Lore(
        id="L001",
        lore_type="rule",
        content="Magic requires incantations",
        category="magic",
        source_scene_id="S001",
        tick=1
    )
    
    # Should start with empty contradictions
    assert lore.potential_contradictions == []
    
    # Add contradictions
    lore.potential_contradictions.append("L002")
    lore.potential_contradictions.append("L003")
    
    assert len(lore.potential_contradictions) == 2
    assert "L002" in lore.potential_contradictions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
