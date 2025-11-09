"""Tests for goal promotion logic."""
import pytest
from novel_agent.memory.entities import Character, OpenLoop


def test_character_goal_fields():
    """Test that Character has new goal fields."""
    char = Character(
        id="C0",
        name="Test Character",
        immediate_goals=["Fix antenna", "Avoid detection"],
        arc_goal="Learn to trust others",
        story_goal="Make contact with aliens"
    )
    
    assert char.immediate_goals == ["Fix antenna", "Avoid detection"]
    assert char.arc_goal == "Learn to trust others"
    assert char.story_goal == "Make contact with aliens"
    assert char.goal_progress == {}
    assert char.goals_completed == []
    assert char.goals_abandoned == []


def test_character_goal_tracking():
    """Test character goal tracking fields."""
    char = Character(
        id="C0",
        name="Test Character",
        goal_progress={"Fix antenna": 0.75, "Learn to trust": 0.3},
        goals_completed=["Repair suit", "Find shelter"],
        goals_abandoned=["Return to Earth"]
    )
    
    assert char.goal_progress["Fix antenna"] == 0.75
    assert char.goal_progress["Learn to trust"] == 0.3
    assert "Repair suit" in char.goals_completed
    assert "Return to Earth" in char.goals_abandoned


def test_character_to_dict_with_goals():
    """Test Character serialization with goals."""
    char = Character(
        id="C0",
        name="Sarah",
        immediate_goals=["Goal 1", "Goal 2"],
        arc_goal="Arc goal",
        goal_progress={"Goal 1": 0.5}
    )
    
    data = char.to_dict()
    
    assert data["immediate_goals"] == ["Goal 1", "Goal 2"]
    assert data["arc_goal"] == "Arc goal"
    assert data["goal_progress"] == {"Goal 1": 0.5}


def test_character_from_dict_with_goals():
    """Test Character deserialization with goals."""
    data = {
        "id": "C0",
        "name": "Sarah",
        "immediate_goals": ["Goal 1"],
        "arc_goal": "Arc goal",
        "story_goal": "Story goal",
        "goal_progress": {"Goal 1": 0.8},
        "goals_completed": ["Old goal"],
        "goals_abandoned": []
    }
    
    char = Character.from_dict(data)
    
    assert char.immediate_goals == ["Goal 1"]
    assert char.arc_goal == "Arc goal"
    assert char.story_goal == "Story goal"
    assert char.goal_progress == {"Goal 1": 0.8}
    assert char.goals_completed == ["Old goal"]


def test_openloop_tracking_fields():
    """Test that OpenLoop has new tracking fields."""
    loop = OpenLoop(
        id="OL0",
        description="Mysterious signal",
        scenes_mentioned=7,
        last_mentioned_tick=12,
        is_story_goal=True
    )
    
    assert loop.scenes_mentioned == 7
    assert loop.last_mentioned_tick == 12
    assert loop.is_story_goal is True


def test_openloop_default_tracking_values():
    """Test OpenLoop tracking fields have correct defaults."""
    loop = OpenLoop(
        id="OL0",
        description="Test loop"
    )
    
    assert loop.scenes_mentioned == 0
    assert loop.last_mentioned_tick is None
    assert loop.is_story_goal is False


def test_openloop_to_dict_with_tracking():
    """Test OpenLoop serialization with tracking fields."""
    loop = OpenLoop(
        id="OL0",
        description="Signal mystery",
        scenes_mentioned=5,
        last_mentioned_tick=10,
        is_story_goal=True
    )
    
    data = loop.to_dict()
    
    assert data["scenes_mentioned"] == 5
    assert data["last_mentioned_tick"] == 10
    assert data["is_story_goal"] is True


def test_openloop_from_dict_with_tracking():
    """Test OpenLoop deserialization with tracking fields."""
    data = {
        "id": "OL0",
        "description": "Test loop",
        "scenes_mentioned": 8,
        "last_mentioned_tick": 15,
        "is_story_goal": False
    }
    
    loop = OpenLoop.from_dict(data)
    
    assert loop.scenes_mentioned == 8
    assert loop.last_mentioned_tick == 15
    assert loop.is_story_goal is False


def test_goal_promotion_candidate_selection():
    """Test logic for selecting goal promotion candidate."""
    # Simulate protagonist-related loops
    loops = [
        OpenLoop(
            id="OL0",
            description="Minor mystery",
            related_characters=["C0"],
            scenes_mentioned=3
        ),
        OpenLoop(
            id="OL1",
            description="Major quest",
            related_characters=["C0"],
            scenes_mentioned=8
        ),
        OpenLoop(
            id="OL2",
            description="Unrelated event",
            related_characters=["C1"],
            scenes_mentioned=10
        ),
        OpenLoop(
            id="OL3",
            description="Secondary goal",
            related_characters=["C0"],
            scenes_mentioned=6
        )
    ]
    
    protagonist_id = "C0"
    
    # Filter protagonist-related loops
    protagonist_loops = [
        loop for loop in loops
        if protagonist_id in loop.related_characters
    ]
    
    # Find most mentioned
    top_loop = max(protagonist_loops, key=lambda l: l.scenes_mentioned)
    
    assert top_loop.id == "OL1"
    assert top_loop.description == "Major quest"
    assert top_loop.scenes_mentioned == 8


def test_goal_promotion_minimum_mentions():
    """Test that loops need minimum mentions to be promoted."""
    loops = [
        OpenLoop(
            id="OL0",
            description="Barely mentioned",
            related_characters=["C0"],
            scenes_mentioned=3  # Less than 5
        ),
        OpenLoop(
            id="OL1",
            description="Well established",
            related_characters=["C0"],
            scenes_mentioned=6  # More than 5
        )
    ]
    
    protagonist_id = "C0"
    protagonist_loops = [
        loop for loop in loops
        if protagonist_id in loop.related_characters
    ]
    
    top_loop = max(protagonist_loops, key=lambda l: l.scenes_mentioned)
    
    # Should select OL1, and it meets the 5+ requirement
    assert top_loop.id == "OL1"
    assert top_loop.scenes_mentioned >= 5


def test_state_story_goals_structure():
    """Test the story_goals structure in state.json."""
    story_goals = {
        'primary': None,
        'secondary': [],
        'promotion_candidates': [],
        'promotion_tick': None
    }
    
    assert story_goals['primary'] is None
    assert isinstance(story_goals['secondary'], list)
    assert isinstance(story_goals['promotion_candidates'], list)
    assert story_goals['promotion_tick'] is None


def test_state_story_goals_after_promotion():
    """Test story_goals structure after promotion."""
    story_goals = {
        'primary': {
            'loop_id': 'OL1',
            'description': 'Decode the alien signal',
            'promoted_at_tick': 12
        },
        'secondary': [],
        'promotion_candidates': [],
        'promotion_tick': 12
    }
    
    assert story_goals['primary'] is not None
    assert story_goals['primary']['loop_id'] == 'OL1'
    assert story_goals['primary']['description'] == 'Decode the alien signal'
    assert story_goals['primary']['promoted_at_tick'] == 12
    assert story_goals['promotion_tick'] == 12
