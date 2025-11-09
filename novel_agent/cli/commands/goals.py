"""Goals command - display goal hierarchy."""
import json
from pathlib import Path
from typing import Dict, Any, List


def get_goals_info(project_dir: Path, state: dict) -> Dict[str, Any]:
    """Gather goal hierarchy information.
    
    Args:
        project_dir: Path to project directory
        state: Project state dictionary
        
    Returns:
        Dictionary with goal information
    """
    from ...memory.manager import MemoryManager
    
    memory = MemoryManager(project_dir)
    
    # Get story goals
    story_goals = state.get('story_goals', {})
    primary_goal = story_goals.get('primary')
    secondary_goals = story_goals.get('secondary', [])
    
    # Get protagonist
    protagonist_id = state.get('active_character')
    protagonist = None
    protagonist_goals = None
    
    if protagonist_id:
        protagonist = memory.load_character(protagonist_id)
        if protagonist:
            protagonist_goals = {
                'immediate': protagonist.immediate_goals,
                'arc_goal': protagonist.arc_goal,
                'story_goal': protagonist.story_goal,
                'progress': protagonist.goal_progress,
                'completed': protagonist.goals_completed,
                'abandoned': protagonist.goals_abandoned
            }
    
    # Get open loops marked as story goals
    open_loops = memory.get_open_loops()
    story_goal_loops = [loop for loop in open_loops if loop.is_story_goal]
    
    return {
        'story_goal': primary_goal,
        'secondary_goals': secondary_goals,
        'protagonist_id': protagonist_id,
        'protagonist_name': protagonist.name if protagonist else None,
        'protagonist_goals': protagonist_goals,
        'story_goal_loops': [
            {
                'id': loop.id,
                'description': loop.description,
                'category': loop.category,
                'importance': loop.importance,
                'scenes_mentioned': loop.scenes_mentioned,
                'created_in_scene': loop.created_in_scene
            }
            for loop in story_goal_loops
        ],
        'current_tick': state.get('current_tick', 0)
    }


def display_goals(info: Dict[str, Any], use_color: bool = True):
    """Display goal hierarchy in formatted output.
    
    Args:
        info: Goals information dictionary
        use_color: Whether to use colored output
    """
    def bold(text):
        return f"\033[1m{text}\033[0m" if use_color else text
    
    print()
    print(f"🎯 {bold('Goal Hierarchy')}")
    print("━" * 60)
    
    # Story Goal
    story_goal = info.get('story_goal')
    if story_goal:
        print(f"\n{bold('Story Goal:')} {story_goal['description']}")
        print(f"  └─ Emerged at tick {story_goal['promoted_at_tick']}")
        print(f"  └─ Loop ID: {story_goal['loop_id']}")
    else:
        tick = info.get('current_tick', 0)
        if tick < 10:
            print(f"\n{bold('Story Goal:')} Not yet emerged (will emerge around tick 10-15)")
        else:
            print(f"\n{bold('Story Goal:')} None (no suitable loops found)")
    
    # Secondary Goals
    secondary = info.get('secondary_goals', [])
    if secondary:
        print(f"\n{bold('Secondary Goals:')}")
        for goal in secondary:
            print(f"  • {goal['description']}")
    
    # Protagonist Goals
    protagonist_name = info.get('protagonist_name')
    protagonist_goals = info.get('protagonist_goals')
    
    if protagonist_name and protagonist_goals:
        print(f"\n{bold(f'Protagonist Goals ({protagonist_name}):')}")
        
        # Immediate goals
        immediate = protagonist_goals.get('immediate', [])
        if immediate:
            print(f"\n  {bold('Immediate:')}")
            for goal in immediate:
                progress = protagonist_goals.get('progress', {}).get(goal, 0.0)
                progress_bar = _format_progress_bar(progress)
                print(f"    • {goal} {progress_bar}")
        else:
            print(f"\n  {bold('Immediate:')} None")
        
        # Arc goal
        arc_goal = protagonist_goals.get('arc_goal')
        if arc_goal:
            progress = protagonist_goals.get('progress', {}).get(arc_goal, 0.0)
            progress_bar = _format_progress_bar(progress)
            print(f"\n  {bold('Arc Goal:')} {arc_goal} {progress_bar}")
        
        # Story goal
        story_goal_char = protagonist_goals.get('story_goal')
        if story_goal_char:
            progress = protagonist_goals.get('progress', {}).get(story_goal_char, 0.0)
            progress_bar = _format_progress_bar(progress)
            print(f"\n  {bold('Story Goal:')} {story_goal_char} {progress_bar}")
        
        # Completed goals
        completed = protagonist_goals.get('completed', [])
        if completed:
            print(f"\n  {bold('Completed:')}")
            for goal in completed:
                print(f"    ✓ {goal}")
        
        # Abandoned goals
        abandoned = protagonist_goals.get('abandoned', [])
        if abandoned:
            print(f"\n  {bold('Abandoned:')}")
            for goal in abandoned:
                print(f"    ✗ {goal}")
    
    elif protagonist_name:
        print(f"\n{bold(f'Protagonist ({protagonist_name}):')} No goals tracked yet")
    else:
        print(f"\n{bold('Protagonist:')} Not yet established")
    
    # Story goal loops
    story_goal_loops = info.get('story_goal_loops', [])
    if story_goal_loops:
        print(f"\n{bold('Story Goal Loops:')}")
        for loop in story_goal_loops:
            print(f"  • [{loop['id']}] {loop['description']}")
            print(f"    Category: {loop['category']}, Importance: {loop['importance']}")
            print(f"    Mentioned in {loop['scenes_mentioned']} scenes")
    
    print()


def _format_progress_bar(progress: float, width: int = 10) -> str:
    """Format a simple progress bar.
    
    Args:
        progress: Progress value (0.0-1.0)
        width: Width of progress bar in characters
        
    Returns:
        Formatted progress bar string
    """
    filled = int(progress * width)
    empty = width - filled
    percentage = int(progress * 100)
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {percentage}%"


def display_goals_json(info: Dict[str, Any]):
    """Display goals information as JSON.
    
    Args:
        info: Goals information dictionary
    """
    print(json.dumps(info, indent=2))
