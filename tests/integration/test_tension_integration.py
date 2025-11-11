"""Integration tests for tension tracking in story generation."""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from novel_agent.agent.agent import StoryAgent
from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Scene
from novel_agent.configs.config import Config


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with minimal state."""
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()
    
    # Create required directories
    (project_dir / "scenes").mkdir()
    (project_dir / "memory").mkdir()
    (project_dir / "memory" / "characters").mkdir()
    (project_dir / "memory" / "locations").mkdir()
    (project_dir / "memory" / "scenes").mkdir()
    (project_dir / "plans").mkdir()
    (project_dir / "vector_db").mkdir()
    
    # Create minimal state.json
    state = {
        "novel_name": "Test Novel",
        "project_id": "test_001",
        "current_tick": 0,
        "active_character": "CHAR_001",
        "created_at": "2024-01-01T00:00:00Z",
        "last_updated": "2024-01-01T00:00:00Z",
        "story_foundation": {
            "genre": "thriller",
            "premise": "A detective investigates a mysterious case",
            "protagonist_archetype": "detective",
            "setting": "modern city",
            "tone": "dark",
            "themes": ["justice", "truth"]
        },
        "story_goals": {
            "primary": None,
            "secondary": [],
            "promotion_candidates": [],
            "promotion_tick": None
        }
    }
    
    with open(project_dir / "state.json", 'w') as f:
        json.dump(state, f, indent=2)
    
    # Create a test character
    char_data = {
        "id": "CHAR_001",
        "type": "character",
        "name": "Detective Sarah Chen",
        "role": "protagonist",
        "description": "A determined detective",
        "archetype": "detective",
        "traits": ["intelligent", "persistent"],
        "immediate_goals": ["solve the case"],
        "arc_goal": None,
        "story_goal": None
    }
    
    with open(project_dir / "memory" / "characters" / "CHAR_001.json", 'w') as f:
        json.dump(char_data, f, indent=2)
    
    return project_dir


@pytest.fixture
def mock_llm():
    """Create a mock LLM interface."""
    llm = Mock()
    
    # Mock planner response
    llm.generate.side_effect = [
        # Planner response
        json.dumps({
            "rationale": "Start with a tense investigation scene",
            "scene_intention": "Sarah discovers a crucial clue at the crime scene",
            "pov_character": "CHAR_001",
            "location": "crime_scene",
            "actions": []
        }),
        # Writer response (high tension scene)
        """Sarah's heart pounded as she stepped into the abandoned warehouse. Blood. 
        Everywhere. Fresh. The killer had been here minutes ago.
        
        "No!" she gasped, spotting the body. Too late. Always too late.
        
        Her radio crackled. "Detective, we've got movement on the east side!"
        
        She drew her weapon. Danger. The killer was still here.""",
        # Fact extractor response
        json.dumps({
            "facts": [
                {
                    "type": "character_update",
                    "character_id": "CHAR_001",
                    "field": "emotional_state",
                    "value": "tense and alert"
                }
            ]
        })
    ]
    
    return llm


def test_tension_tracking_enabled_by_default(temp_project, mock_llm):
    """Test that tension tracking works in normal story generation."""
    # Create config with tension tracking enabled (default)
    config = Config()
    
    # Create agent
    from novel_agent.tools.registry import ToolRegistry
    tools = ToolRegistry()
    
    with patch('novel_agent.agent.agent.MemoryManager') as MockMemory, \
         patch('novel_agent.agent.agent.VectorStore') as MockVector:
        
        # Setup mocks
        mock_memory = MockMemory.return_value
        mock_memory.load_state.return_value = json.load(open(temp_project / "state.json"))
        mock_memory.load_character.return_value = Mock(
            id="CHAR_001",
            name="Detective Sarah Chen",
            role="protagonist",
            description="A determined detective"
        )
        mock_memory.list_scenes.return_value = []
        mock_memory.get_character_relationships.return_value = []
        
        # Create agent
        agent = StoryAgent(temp_project, mock_llm, tools, config.to_dict())
        
        # Verify tension evaluator is enabled
        assert agent.tension_evaluator.enabled is True


def test_tension_evaluation_in_tick_cycle(temp_project):
    """Test that tension is evaluated and saved during tick cycle."""
    # Create a scene with high tension content
    high_tension_text = """
    The explosion rocked the building. Sarah screamed as debris rained down.
    Blood streamed from her wound. The danger was immediate and terrifying.
    She had to escape before the next attack came. Run! Now! No time!
    """
    
    # Create memory manager
    memory = MemoryManager(temp_project)
    
    # Create and save a scene
    scene = Scene(
        id="S001",
        tick=1,
        title="The Attack",
        pov_character_id="CHAR_001",
        word_count=len(high_tension_text.split())
    )
    memory.save_scene(scene)
    
    # Evaluate tension
    from novel_agent.agent.tension_evaluator import TensionEvaluator
    config = Config()
    evaluator = TensionEvaluator(config.to_dict())
    
    result = evaluator.evaluate_tension(high_tension_text)
    
    # Verify tension was evaluated
    assert result['enabled'] is True
    assert result['tension_level'] is not None
    assert result['tension_level'] >= 7  # Should be high tension
    assert result['tension_category'] in ['high', 'climactic']
    
    # Update scene with tension data
    scene.tension_level = result['tension_level']
    scene.tension_category = result['tension_category']
    memory.save_scene(scene)
    
    # Verify scene was saved with tension data
    loaded_scene = memory.load_scene("S001")
    assert loaded_scene.tension_level == result['tension_level']
    assert loaded_scene.tension_category == result['tension_category']


def test_tension_tracking_can_be_disabled(temp_project):
    """Test that tension tracking can be disabled via config."""
    # Create config with tension tracking disabled
    config = Config()
    config.set('generation.enable_tension_tracking', False)
    
    from novel_agent.agent.tension_evaluator import TensionEvaluator
    evaluator = TensionEvaluator(config.to_dict())
    
    # Verify it's disabled
    assert evaluator.enabled is False
    
    # Evaluate tension
    result = evaluator.evaluate_tension("Some scene text")
    
    # Should return None values
    assert result['enabled'] is False
    assert result['tension_level'] is None
    assert result['tension_category'] is None


def test_tension_history_in_context(temp_project):
    """Test that tension history appears in planner context."""
    # Create memory manager
    memory = MemoryManager(temp_project)
    
    # Create multiple scenes with tension data
    scenes = [
        Scene(id="S001", tick=1, tension_level=3, tension_category="calm"),
        Scene(id="S002", tick=2, tension_level=5, tension_category="rising"),
        Scene(id="S003", tick=3, tension_level=7, tension_category="high"),
        Scene(id="S004", tick=4, tension_level=6, tension_category="rising"),
        Scene(id="S005", tick=5, tension_level=4, tension_category="rising"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    # Create context builder
    from novel_agent.agent.context import ContextBuilder
    from novel_agent.memory.vector_store import VectorStore
    from novel_agent.tools.registry import ToolRegistry
    
    config = Config()
    vector = VectorStore(temp_project)
    tools = ToolRegistry()
    
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    # Get tension history
    tension_history = context_builder._get_tension_history()
    
    # Verify format
    assert tension_history != ""
    assert "3, 5, 7, 6, 4" in tension_history
    assert "calm → rising → high → rising → rising" in tension_history


def test_tension_visualization_in_status(temp_project):
    """Test that tension appears in status command output."""
    from novel_agent.cli.commands.status import get_status_info
    
    # Create memory manager and scenes
    memory = MemoryManager(temp_project)
    
    scenes = [
        Scene(id="S001", tick=1, tension_level=3, tension_category="calm"),
        Scene(id="S002", tick=2, tension_level=7, tension_category="high"),
    ]
    
    for scene in scenes:
        memory.save_scene(scene)
    
    # Load state
    with open(temp_project / "state.json") as f:
        state = json.load(f)
    
    # Get status info
    info = get_status_info(temp_project, state)
    
    # Verify tension history is included
    assert 'tension_history' in info
    assert len(info['tension_history']) == 2
    assert info['tension_history'][0]['level'] == 3
    assert info['tension_history'][0]['category'] == 'calm'
    assert info['tension_history'][1]['level'] == 7
    assert info['tension_history'][1]['category'] == 'high'


def test_tension_in_scene_list(temp_project):
    """Test that tension appears in scene list output."""
    from novel_agent.cli.commands.list import list_scenes
    
    # Create memory manager and scenes
    memory = MemoryManager(temp_project)
    
    # Create scene files
    scene_file = temp_project / "scenes" / "scene_001.md"
    scene_file.write_text("# Scene 1\n\nSome content here.")
    
    # Create scene metadata
    scene = Scene(
        id="S001",
        tick=1,
        pov_character_id="CHAR_001",
        tension_level=7,
        tension_category="high"
    )
    memory.save_scene(scene)
    
    # List scenes
    scenes = list_scenes(temp_project, verbose=False)
    
    # Verify tension data is included
    assert len(scenes) == 1
    assert scenes[0]['tension_level'] == 7
    assert scenes[0]['tension_category'] == 'high'


def test_different_tension_levels(temp_project):
    """Test tension evaluation across different scene types."""
    from novel_agent.agent.tension_evaluator import TensionEvaluator
    config = Config()
    evaluator = TensionEvaluator(config.to_dict())
    
    # Calm scene
    calm_scene = """
    Sarah sat in the quiet café, sipping her coffee. The warm afternoon sun
    filtered through the windows. She felt peaceful and content, enjoying
    this rare moment of rest. Everything was calm and ordinary.
    """
    
    calm_result = evaluator.evaluate_tension(calm_scene)
    assert calm_result['tension_level'] <= 4
    assert calm_result['tension_category'] in ['calm', 'rising']
    
    # Rising tension scene
    rising_scene = """
    Sarah noticed something odd about the file. The dates didn't match.
    She frowned, feeling uneasy. Something was wrong here. What was she missing?
    The pieces didn't fit together. She needed to investigate further.
    """
    
    rising_result = evaluator.evaluate_tension(rising_scene)
    assert 4 <= rising_result['tension_level'] <= 7
    assert rising_result['tension_category'] in ['rising', 'high']
    
    # High tension scene
    high_scene = """
    "Get down!" Sarah shouted. Gunfire erupted. Glass shattered everywhere.
    She dove behind the desk. Her heart raced. Blood on her hands. The killer
    was here. Now. She grabbed her weapon. No time to think. Just survive.
    """
    
    high_result = evaluator.evaluate_tension(high_scene)
    assert high_result['tension_level'] >= 7
    assert high_result['tension_category'] in ['high', 'climactic']
    
    # Verify progression
    assert calm_result['tension_level'] < rising_result['tension_level']
    assert rising_result['tension_level'] < high_result['tension_level']


def test_tension_with_goal_promotion(temp_project):
    """Test that tension tracking works alongside goal promotion."""
    # This verifies Phase 7A.2 and 7A.3 work together
    memory = MemoryManager(temp_project)
    
    # Create scenes that would trigger goal promotion
    for i in range(1, 16):
        scene = Scene(
            id=f"S{i:03d}",
            tick=i,
            tension_level=3 + (i % 5),  # Varying tension
            tension_category="rising"
        )
        memory.save_scene(scene)
    
    # Verify all scenes have tension data
    all_scenes = memory.list_scenes()
    assert len(all_scenes) == 15
    
    for scene in all_scenes:
        assert scene.tension_level is not None
        assert scene.tension_category is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
