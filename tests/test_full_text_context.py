"""Test full text context in writer context builder."""

import pytest
from pathlib import Path
import tempfile
import shutil
from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.vector_store import VectorStore
from novel_agent.agent.writer_context import WriterContextBuilder
from novel_agent.configs.config import Config


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    temp_dir = Path(tempfile.mkdtemp())
    
    # Create necessary directories
    (temp_dir / "memory" / "characters").mkdir(parents=True)
    (temp_dir / "memory" / "locations").mkdir(parents=True)
    (temp_dir / "memory" / "scenes").mkdir(parents=True)
    (temp_dir / "memory" / "index").mkdir(parents=True)
    (temp_dir / "scenes").mkdir(parents=True)
    
    # Create state.json
    import json
    state = {
        "novel_name": "Test Novel",
        "current_tick": 3,
        "active_character": "C0"
    }
    (temp_dir / "state.json").write_text(json.dumps(state))
    
    # Create config.yaml
    (temp_dir / "config.yaml").write_text("llm:\n  codex_bin_path: codex\n")
    
    yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir)


def test_full_text_context_format(temp_project):
    """Test that full text context includes actual scene text."""
    # Create some test scenes
    memory = MemoryManager(temp_project)
    
    # Create scene files with actual content
    scene_0_content = """# First scene title

*Scene ID: S000*
*Tick: 0*

---

This is the full text of scene zero. It has some prose with sensory details and character voice.
"""
    
    scene_1_content = """# Second scene title

*Scene ID: S001*
*Tick: 1*

---

This is the full text of scene one. More prose continues the story with consistent style.
"""
    
    scene_2_content = """# Third scene title

*Scene ID: S002*
*Tick: 2*

---

This is the full text of scene two. The style should be maintained across scenes.
"""
    
    (temp_project / "scenes" / "scene_000.md").write_text(scene_0_content)
    (temp_project / "scenes" / "scene_001.md").write_text(scene_1_content)
    (temp_project / "scenes" / "scene_002.md").write_text(scene_2_content)
    
    # Create scene metadata
    from novel_agent.memory.entities import Scene
    
    for i in range(3):
        scene = Scene(
            id=f"S{str(i).zfill(3)}",
            tick=i,
            title=f"Scene {i} title",
            summary=[f"Summary point {i}"]
        )
        memory.save_scene(scene)
    
    # Create writer context builder
    config = Config()
    vector_store = VectorStore(temp_project)
    builder = WriterContextBuilder(memory, vector_store, config)
    
    # Test with default settings (2 full text, 3 summaries)
    context = builder._format_recent_context(full_text_count=2, summary_count=1)
    
    # Verify structure
    assert "## Earlier Scenes (Summaries)" in context
    assert "## Recent Scenes (Full Text)" in context
    
    # Verify full text is included for recent scenes
    assert "This is the full text of scene one" in context
    assert "This is the full text of scene two" in context
    
    # Verify older scene is summarized
    assert "Summary point 0" in context
    
    # Verify full text of oldest scene is NOT included
    assert "This is the full text of scene zero" not in context
    
    print("✅ Full text context test passed!")


def test_config_controls_scene_counts(temp_project):
    """Test that config values control full text and summary counts."""
    memory = MemoryManager(temp_project)
    
    # Create 5 test scenes
    for i in range(5):
        scene_content = f"""# Scene {i}

*Scene ID: S{str(i).zfill(3)}*
*Tick: {i}*

---

Full text content for scene {i}.
"""
        (temp_project / "scenes" / f"scene_{str(i).zfill(3)}.md").write_text(scene_content)
        
        from novel_agent.memory.entities import Scene
        scene = Scene(
            id=f"S{str(i).zfill(3)}",
            tick=i,
            title=f"Scene {i}",
            summary=[f"Summary {i}"]
        )
        memory.save_scene(scene)
    
    # Test with custom config
    config = Config()
    config.set('generation.full_text_scenes_count', 3)
    config.set('generation.summary_scenes_count', 2)
    
    vector_store = VectorStore(temp_project)
    builder = WriterContextBuilder(memory, vector_store, config)
    
    # Get context using config values
    full_text_count = config.get('generation.full_text_scenes_count', 2)
    summary_count = config.get('generation.summary_scenes_count', 3)
    context = builder._format_recent_context(
        full_text_count=full_text_count,
        summary_count=summary_count
    )
    
    # Verify 3 full text scenes (2, 3, 4)
    assert "Full text content for scene 2" in context
    assert "Full text content for scene 3" in context
    assert "Full text content for scene 4" in context
    
    # Verify 2 summary scenes (0, 1)
    assert "Summary 0" in context
    assert "Summary 1" in context
    
    # Verify scene 2 is NOT in summaries (should be in full text)
    summary_section = context.split("## Recent Scenes (Full Text)")[0]
    assert "Summary 2" not in summary_section
    
    print("✅ Config controls test passed!")


def test_first_scene_handling(temp_project):
    """Test that first scene works when no previous context exists."""
    memory = MemoryManager(temp_project)
    config = Config()
    vector_store = VectorStore(temp_project)
    builder = WriterContextBuilder(memory, vector_store, config)
    
    # Test with no scenes
    context = builder._format_recent_context(full_text_count=2, summary_count=3)
    
    assert context == "This is the first scene of the novel."
    
    print("✅ First scene handling test passed!")


if __name__ == "__main__":
    # Run tests manually
    import sys
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # Setup temp project
        (temp_dir / "memory" / "characters").mkdir(parents=True)
        (temp_dir / "memory" / "locations").mkdir(parents=True)
        (temp_dir / "memory" / "scenes").mkdir(parents=True)
        (temp_dir / "memory" / "index").mkdir(parents=True)
        (temp_dir / "scenes").mkdir(parents=True)
        
        import json
        state = {"novel_name": "Test", "current_tick": 3, "active_character": "C0"}
        (temp_dir / "state.json").write_text(json.dumps(state))
        (temp_dir / "config.yaml").write_text("llm:\n  codex_bin_path: codex\n")
        
        # Run tests
        test_full_text_context_format(temp_dir)
        test_config_controls_scene_counts(temp_dir)
        test_first_scene_handling(temp_dir)
        
        print("\n✅ All tests passed!")
        
    finally:
        shutil.rmtree(temp_dir)
