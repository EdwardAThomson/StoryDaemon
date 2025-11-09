"""Status command - display project overview."""
import os
from pathlib import Path
from typing import Optional
from datetime import datetime


def count_files_in_dir(directory: Path, pattern: str = "*.json") -> int:
    """Count files matching pattern in directory."""
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def get_file_word_count(filepath: Path) -> int:
    """Count words in a text file."""
    if not filepath.exists():
        return 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            return len(content.split())
    except Exception:
        return 0


def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return iso_timestamp


def get_status_info(project_dir: Path, state: dict) -> dict:
    """Gather all status information for a project.
    
    Args:
        project_dir: Path to project directory
        state: Project state dictionary
        
    Returns:
        Dictionary with status information
    """
    scenes_dir = project_dir / "scenes"
    memory_dir = project_dir / "memory"
    
    # Count entities
    char_count = count_files_in_dir(memory_dir / "characters")
    loc_count = count_files_in_dir(memory_dir / "locations")
    scene_count = count_files_in_dir(scenes_dir, "*.md")
    
    # Load open loops
    loops_file = memory_dir / "open_loops.json"
    loop_count = 0
    if loops_file.exists():
        import json
        with open(loops_file, 'r') as f:
            data = json.load(f)
            loops = data.get('loops', [])
            loop_count = len([l for l in loops if l.get('status') == 'open'])
    
    # Get last scene info
    last_scene_file = None
    last_scene_words = 0
    last_scene_time = None
    
    if scene_count > 0:
        # Find highest numbered scene
        scene_files = sorted(scenes_dir.glob("scene_*.md"))
        if scene_files:
            last_scene_file = scene_files[-1].name
            last_scene_words = get_file_word_count(scene_files[-1])
            last_scene_time = datetime.fromtimestamp(
                scene_files[-1].stat().st_mtime
            ).strftime('%Y-%m-%d %H:%M:%S')
    
    return {
        'novel_name': state.get('novel_name', 'Unknown'),
        'project_dir': str(project_dir),
        'current_tick': state.get('current_tick', 0),
        'active_character': state.get('active_character', 'None'),
        'story_foundation': state.get('story_foundation'),
        'scenes_written': scene_count,
        'characters': char_count,
        'locations': loc_count,
        'open_loops': loop_count,
        'last_scene_file': last_scene_file,
        'last_scene_words': last_scene_words,
        'last_scene_time': last_scene_time,
        'created_at': format_timestamp(state.get('created_at', 'Unknown')),
        'last_updated': format_timestamp(state.get('last_updated', 'Unknown'))
    }


def display_status(info: dict, use_color: bool = True):
    """Display status information in formatted output.
    
    Args:
        info: Status information dictionary
        use_color: Whether to use colored output
    """
    # Simple colored output without rich dependency
    def bold(text):
        return f"\033[1m{text}\033[0m" if use_color else text
    
    print()
    print(f"📖 {bold('Novel:')} {info['novel_name']}")
    print(f"📍 {bold('Location:')} {info['project_dir']}")
    print(f"🎬 {bold('Current Tick:')} {info['current_tick']}")
    print(f"👤 {bold('Active POV:')} {info['active_character']}")
    
    # Display story foundation if present
    foundation = info.get('story_foundation')
    if foundation:
        print()
        print(f"📚 {bold('Story Foundation:')}")
        print(f"   Genre: {foundation.get('genre', 'N/A')}")
        print(f"   Setting: {foundation.get('setting', 'N/A')}")
        print(f"   Tone: {foundation.get('tone', 'N/A')}")
        if foundation.get('themes'):
            print(f"   Themes: {', '.join(foundation['themes'])}")
    
    print()
    print(f"📝 {bold('Scenes Written:')} {info['scenes_written']}")
    print(f"👥 {bold('Characters:')} {info['characters']}")
    print(f"🗺️  {bold('Locations:')} {info['locations']}")
    print(f"🔗 {bold('Open Loops:')} {info['open_loops']}")
    
    if info['last_scene_file']:
        print()
        print(f"{bold('Last Scene:')} {info['last_scene_file']} ({info['last_scene_words']:,} words)")
        print(f"{bold('Last Updated:')} {info['last_scene_time']}")
    
    print(f"\n{bold('Created:')} {info['created_at']}")
    print()


def display_status_json(info: dict):
    """Display status information as JSON.
    
    Args:
        info: Status information dictionary
    """
    import json
    print(json.dumps(info, indent=2))
