"""Tests for tension pattern guidance in planner context."""
import pytest
from pathlib import Path
import tempfile

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Scene
from novel_agent.agent.context import ContextBuilder
from novel_agent.memory.vector_store import VectorStore
from novel_agent.tools.registry import ToolRegistry
from novel_agent.configs.config import Config


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "memory").mkdir()
        (project_dir / "memory" / "scenes").mkdir()
        yield project_dir


def test_steady_tension_guidance(temp_project):
    """Test that steady tension triggers appropriate guidance."""
    memory = MemoryManager(temp_project)
    
    # Create 4 scenes with steady tension (variance <= 1)
    scenes = [
        Scene(id="S001", tick=1, tension_level=5, tension_category="rising"),
        Scene(id="S002", tick=2, tension_level=6, tension_category="rising"),
        Scene(id="S003", tick=3, tension_level=5, tension_category="rising"),
        Scene(id="S004", tick=4, tension_level=6, tension_category="rising"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    # Build context
    config = Config()
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    tension_history = context_builder._get_tension_history()
    
    # Should include guidance about steady tension
    assert "Tension has been steady" in tension_history
    assert "calm moment" in tension_history
    assert "tension spike" in tension_history
    assert "Continued current pacing" in tension_history
    assert "informational only" in tension_history


def test_high_tension_guidance(temp_project):
    """Test that sustained high tension triggers respite suggestion."""
    memory = MemoryManager(temp_project)
    
    # Create scenes with sustained high tension
    scenes = [
        Scene(id="S001", tick=1, tension_level=7, tension_category="high"),
        Scene(id="S002", tick=2, tension_level=8, tension_category="high"),
        Scene(id="S003", tick=3, tension_level=9, tension_category="climactic"),
        Scene(id="S004", tick=4, tension_level=8, tension_category="high"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    config = Config()
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    tension_history = context_builder._get_tension_history()
    
    # Should suggest respite
    assert "Tension has been high" in tension_history
    assert "brief respite" in tension_history
    assert "reflection" in tension_history
    assert "anticipation" in tension_history


def test_low_tension_guidance(temp_project):
    """Test that sustained low tension triggers escalation suggestion."""
    memory = MemoryManager(temp_project)
    
    # Create scenes with sustained low tension
    scenes = [
        Scene(id="S001", tick=1, tension_level=2, tension_category="calm"),
        Scene(id="S002", tick=2, tension_level=3, tension_category="calm"),
        Scene(id="S003", tick=3, tension_level=2, tension_category="calm"),
        Scene(id="S004", tick=4, tension_level=3, tension_category="calm"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    config = Config()
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    tension_history = context_builder._get_tension_history()
    
    # Should suggest escalation
    assert "Tension has been low" in tension_history
    assert "Rising stakes" in tension_history or "rising stakes" in tension_history
    assert "conflict" in tension_history
    assert "obstacles" in tension_history


def test_varied_tension_no_guidance(temp_project):
    """Test that varied tension doesn't trigger guidance."""
    memory = MemoryManager(temp_project)
    
    # Create scenes with good variance
    scenes = [
        Scene(id="S001", tick=1, tension_level=3, tension_category="calm"),
        Scene(id="S002", tick=2, tension_level=6, tension_category="rising"),
        Scene(id="S003", tick=3, tension_level=8, tension_category="high"),
        Scene(id="S004", tick=4, tension_level=5, tension_category="rising"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    config = Config()
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    tension_history = context_builder._get_tension_history()
    
    # Should not include specific guidance (variance > 1)
    assert "Tension has been steady" not in tension_history
    assert "Tension has been high" not in tension_history
    assert "Tension has been low" not in tension_history
    # But should still have the informational note
    assert "informational only" in tension_history


def test_insufficient_data_no_guidance(temp_project):
    """Test that insufficient scenes don't trigger guidance."""
    memory = MemoryManager(temp_project)
    
    # Create only 2 scenes (need 3+ for analysis)
    scenes = [
        Scene(id="S001", tick=1, tension_level=5, tension_category="rising"),
        Scene(id="S002", tick=2, tension_level=5, tension_category="rising"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    config = Config()
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    tension_history = context_builder._get_tension_history()
    
    # Should show tension but no analysis
    assert "Recent tension:" in tension_history
    assert "5, 5" in tension_history
    # Should not have guidance (need 3+ scenes)
    assert "Note:" not in tension_history


def test_tension_disabled_returns_empty(temp_project):
    """Test that disabled tension tracking returns empty string."""
    memory = MemoryManager(temp_project)
    
    # Create scenes
    scenes = [
        Scene(id="S001", tick=1, tension_level=5, tension_category="rising"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    # Disable tension tracking
    config_dict = {
        'generation': {
            'enable_tension_tracking': False
        }
    }
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    context_builder = ContextBuilder(memory, vector, tools, config_dict)
    
    tension_history = context_builder._get_tension_history()
    
    # Should be empty
    assert tension_history == ""


def test_format_includes_progression(temp_project):
    """Test that tension history includes category progression."""
    memory = MemoryManager(temp_project)
    
    scenes = [
        Scene(id="S001", tick=1, tension_level=3, tension_category="calm"),
        Scene(id="S002", tick=2, tension_level=5, tension_category="rising"),
        Scene(id="S003", tick=3, tension_level=7, tension_category="high"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    config = Config()
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    tension_history = context_builder._get_tension_history()
    
    # Should show levels and progression
    assert "3, 5, 7" in tension_history
    assert "calm → rising → high" in tension_history


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
