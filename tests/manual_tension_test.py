#!/usr/bin/env python3
"""Manual test script for tension tracking feature.

This script creates a test project and verifies that tension tracking
works correctly in the story generation pipeline.

Usage:
    python tests/manual_tension_test.py
"""
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Scene
from novel_agent.agent.tension_evaluator import TensionEvaluator
from novel_agent.agent.context import ContextBuilder
from novel_agent.memory.vector_store import VectorStore
from novel_agent.tools.registry import ToolRegistry
from novel_agent.configs.config import Config


def test_tension_evaluator():
    """Test the tension evaluator with sample scenes."""
    print("=" * 60)
    print("TEST 1: Tension Evaluator")
    print("=" * 60)
    
    config = Config()
    evaluator = TensionEvaluator(config.to_dict())
    
    test_scenes = [
        ("Calm scene", """
            Sarah sat in the peaceful garden, reading her book. The warm sun
            felt gentle on her face. She smiled, feeling safe and content.
            Everything was calm and normal, just another quiet afternoon.
        """),
        ("Rising tension", """
            Sarah noticed the door was ajar. Strange. She'd locked it this morning.
            Her pulse quickened. Something felt wrong. She approached cautiously,
            hand on her phone. Should she call someone? The silence was unsettling.
        """),
        ("High tension", """
            "Run!" Marcus shouted. The explosion rocked the building. Sarah screamed
            as debris rained down. Blood. Everywhere. Her heart pounded. Danger!
            She had to escape. Now! No time to think. Just survive. Get out!
        """),
        ("Climactic", """
            Sarah faced the killer. "It's over!" she shouted. He lunged. She fired.
            Blood sprayed. He collapsed. Dead. Her hands shook. The nightmare was
            finally over. She'd won. But at what cost? Everything had changed.
        """)
    ]
    
    print(f"\nTension tracking enabled: {evaluator.enabled}")
    print()
    
    for name, text in test_scenes:
        result = evaluator.evaluate_tension(text.strip())
        
        print(f"Scene: {name}")
        print(f"  Tension Level: {result['tension_level']}/10")
        print(f"  Category: {result['tension_category']}")
        print(f"  Analysis:")
        if result.get('analysis'):
            for key, value in result['analysis'].items():
                print(f"    {key}: {value:.2f}")
        print()
    
    print("✅ Tension evaluator test passed!\n")


def test_tension_with_scenes(tmp_path):
    """Test tension tracking with actual scene objects."""
    print("=" * 60)
    print("TEST 2: Scene Tension Storage")
    print("=" * 60)
    
    # Create temporary project
    project_dir = tmp_path / "test_tension_project"
    project_dir.mkdir()
    (project_dir / "memory").mkdir()
    (project_dir / "memory" / "scenes").mkdir()
    
    memory = MemoryManager(project_dir)
    config = Config()
    evaluator = TensionEvaluator(config.to_dict())
    
    # Create scenes with different tension levels
    scene_texts = [
        ("Calm morning", "Sarah woke up peacefully. The sun was shining. A beautiful day."),
        ("Growing concern", "Sarah noticed something odd. The file was missing. Where could it be?"),
        ("Confrontation", "Sarah confronted him. 'Tell me the truth!' she demanded. He refused."),
        ("Crisis", "Danger! The building shook. Sarah ran. Explosion! Get out! Now!"),
    ]
    
    print("\nCreating and evaluating scenes:\n")
    
    for i, (title, text) in enumerate(scene_texts, 1):
        # Create scene
        scene = Scene(
            id=f"S{i:03d}",
            tick=i,
            title=title,
            pov_character_id="CHAR_001",
            word_count=len(text.split())
        )
        
        # Evaluate tension
        result = evaluator.evaluate_tension(text)
        scene.tension_level = result['tension_level']
        scene.tension_category = result['tension_category']
        
        # Save scene
        memory.save_scene(scene)
        
        print(f"Scene {i}: {title}")
        print(f"  Tension: {scene.tension_level}/10 ({scene.tension_category})")
        print()
    
    # Verify scenes were saved correctly
    print("Verifying saved scenes:\n")
    
    scene_ids = memory.list_scenes()
    assert len(scene_ids) == 4, f"Expected 4 scenes, got {len(scene_ids)}"
    
    all_scenes = []
    for scene_id in scene_ids:
        scene = memory.load_scene(scene_id)
        assert scene is not None, f"Failed to load scene {scene_id}"
        assert scene.tension_level is not None, f"Scene {scene.id} missing tension_level"
        assert scene.tension_category is not None, f"Scene {scene.id} missing tension_category"
        print(f"✓ {scene.id}: {scene.tension_level}/10 ({scene.tension_category})")
        all_scenes.append(scene)
    
    print("\n✅ Scene tension storage test passed!\n")
    
    return project_dir, all_scenes


def test_tension_context(project_dir, scenes):
    """Test tension history in planner context."""
    print("=" * 60)
    print("TEST 3: Tension in Planner Context")
    print("=" * 60)
    
    config = Config()
    memory = MemoryManager(project_dir)
    vector = VectorStore(project_dir)
    tools = ToolRegistry()
    
    context_builder = ContextBuilder(memory, vector, tools, config.to_dict())
    
    # Get tension history
    tension_history = context_builder._get_tension_history()
    
    print(f"\nTension history for planner context:")
    print(f"  {tension_history}")
    print()
    
    # Verify it contains expected data
    assert tension_history != "", "Tension history should not be empty"
    assert "→" in tension_history, "Should show progression"
    
    # Extract levels
    levels = [s.tension_level for s in scenes]
    for level in levels:
        assert str(level) in tension_history, f"Level {level} should appear in history"
    
    print("✅ Tension context test passed!\n")


def test_tension_config():
    """Test tension tracking configuration."""
    print("=" * 60)
    print("TEST 4: Configuration Toggle")
    print("=" * 60)
    
    # Test with enabled (default)
    config_enabled = Config()
    evaluator_enabled = TensionEvaluator(config_enabled.to_dict())
    
    print(f"\nDefault config - Tension enabled: {evaluator_enabled.enabled}")
    assert evaluator_enabled.enabled is True
    
    result = evaluator_enabled.evaluate_tension("Some text")
    assert result['enabled'] is True
    assert result['tension_level'] is not None
    print(f"  Evaluation result: {result['tension_level']}/10")
    
    # Test with disabled
    config_dict_disabled = {
        'generation': {
            'enable_tension_tracking': False
        }
    }
    print(f"\nConfig dict: {config_dict_disabled}")
    evaluator_disabled = TensionEvaluator(config_dict_disabled)
    
    print(f"Disabled config - Tension enabled: {evaluator_disabled.enabled}")
    print(f"Expected: False, Got: {evaluator_disabled.enabled}")
    assert evaluator_disabled.enabled is False, f"Expected False, got {evaluator_disabled.enabled}"
    
    result = evaluator_disabled.evaluate_tension("Some text")
    assert result['enabled'] is False
    assert result['tension_level'] is None
    print(f"  Evaluation result: {result['tension_level']} (disabled)")
    
    print("\n✅ Configuration toggle test passed!\n")


def main():
    """Run all manual tests."""
    print("\n" + "=" * 60)
    print("MANUAL TENSION TRACKING TEST SUITE")
    print("=" * 60 + "\n")
    
    try:
        # Test 1: Basic tension evaluator
        test_tension_evaluator()
        
        # Test 2: Scene storage (needs temp directory)
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            project_dir, scenes = test_tension_with_scenes(tmp_path)
            
            # Test 3: Context integration
            test_tension_context(project_dir, scenes)
        
        # Test 4: Configuration
        test_tension_config()
        
        print("=" * 60)
        print("ALL TESTS PASSED! ✅")
        print("=" * 60)
        print("\nTension tracking is working correctly!")
        print("\nYou can now:")
        print("  1. Create a new novel with: novel new --interactive")
        print("  2. Generate scenes with: novel tick")
        print("  3. View tension with: novel status")
        print("  4. List scenes with: novel list scenes")
        print("\nTension will be automatically tracked for each scene.")
        print()
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
