"""List command - list entities in the project."""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_entity_file(filepath: Path) -> Optional[Dict[str, Any]]:
    """Load entity JSON file."""
    if not filepath.exists():
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def list_characters(project_dir: Path, verbose: bool = False) -> List[Dict[str, Any]]:
    """List all characters in the project.
    
    Args:
        project_dir: Path to project directory
        verbose: Include detailed information
        
    Returns:
        List of character info dictionaries
    """
    chars_dir = project_dir / "memory" / "characters"
    if not chars_dir.exists():
        return []
    
    characters = []
    for char_file in sorted(chars_dir.glob("*.json")):
        data = load_entity_file(char_file)
        if data:
            char_info = {
                'id': data.get('id', char_file.stem),
                'name': data.get('name', 'Unknown'),
                'role': data.get('role', ''),
                'type': data.get('type', ''),
            }
            if verbose:
                char_info['description'] = data.get('description', '')
                char_info['current_state'] = data.get('current_state', {})
            characters.append(char_info)
    
    return characters


def list_locations(project_dir: Path, verbose: bool = False) -> List[Dict[str, Any]]:
    """List all locations in the project.
    
    Args:
        project_dir: Path to project directory
        verbose: Include detailed information
        
    Returns:
        List of location info dictionaries
    """
    locs_dir = project_dir / "memory" / "locations"
    if not locs_dir.exists():
        return []
    
    locations = []
    for loc_file in sorted(locs_dir.glob("*.json")):
        data = load_entity_file(loc_file)
        if data:
            loc_info = {
                'id': data.get('id', loc_file.stem),
                'name': data.get('name', 'Unknown'),
                'type': data.get('type', ''),
                'atmosphere': data.get('atmosphere', ''),
            }
            if verbose:
                loc_info['description'] = data.get('description', '')
                loc_info['significance'] = data.get('significance', '')
            locations.append(loc_info)
    
    return locations


def list_open_loops(project_dir: Path, verbose: bool = False) -> List[Dict[str, Any]]:
    """List all open loops in the project.
    
    Args:
        project_dir: Path to project directory
        verbose: Include detailed information
        
    Returns:
        List of open loop info dictionaries
    """
    loops_file = project_dir / "memory" / "open_loops.json"
    if not loops_file.exists():
        return []
    
    try:
        with open(loops_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            loops = data.get('loops', [])
            
            loop_info = []
            for loop in loops:
                info = {
                    'id': loop.get('id', 'Unknown'),
                    'description': loop.get('description', ''),
                    'priority': loop.get('priority', 0),
                    'status': loop.get('status', 'open'),
                }
                if verbose:
                    info['created_in_scene'] = loop.get('created_in_scene', '')
                    info['resolved_in_scene'] = loop.get('resolved_in_scene', '')
                    info['tags'] = loop.get('tags', [])
                loop_info.append(info)
            
            return loop_info
    except Exception:
        return []


def list_scenes(project_dir: Path, verbose: bool = False) -> List[Dict[str, Any]]:
    """List all scenes in the project.
    
    Args:
        project_dir: Path to project directory
        verbose: Include detailed information
        
    Returns:
        List of scene info dictionaries
    """
    scenes_dir = project_dir / "scenes"
    memory_scenes_dir = project_dir / "memory" / "scenes"
    
    if not scenes_dir.exists():
        return []
    
    scenes = []
    for scene_file in sorted(scenes_dir.glob("scene_*.md")):
        # Extract scene number from filename
        scene_num = scene_file.stem.replace('scene_', '')
        
        # Try to load metadata from memory
        metadata_file = memory_scenes_dir / f"S{scene_num}.json"
        metadata = load_entity_file(metadata_file) if metadata_file.exists() else {}
        
        # Count words
        try:
            with open(scene_file, 'r', encoding='utf-8') as f:
                content = f.read()
                word_count = len(content.split())
        except Exception:
            word_count = 0
        
        scene_info = {
            'file': scene_file.name,
            'number': scene_num,
            'word_count': word_count,
            'pov_character': metadata.get('pov_character', 'Unknown'),
            'tension_level': metadata.get('tension_level'),
            'tension_category': metadata.get('tension_category'),
        }
        
        if verbose:
            scene_info['summary'] = metadata.get('summary', '')
            scene_info['location'] = metadata.get('location', '')
            scene_info['tick'] = metadata.get('tick', '')
        
        scenes.append(scene_info)
    
    return scenes


def display_table(items: List[Dict[str, Any]], headers: List[str], format_func=None):
    """Display items in a simple table format.
    
    Args:
        items: List of dictionaries to display
        headers: List of header names
        format_func: Optional function to format each row
    """
    if not items:
        print("  (none)")
        return
    
    # Calculate column widths
    col_widths = {h: len(h) for h in headers}
    for item in items:
        for header in headers:
            value = str(item.get(header, ''))
            col_widths[header] = max(col_widths[header], len(value))
    
    # Print header
    header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
    print(f"  {header_line}")
    print(f"  {'-' * len(header_line)}")
    
    # Print rows
    for item in items:
        if format_func:
            row = format_func(item, headers, col_widths)
        else:
            row = "  ".join(str(item.get(h, '')).ljust(col_widths[h]) for h in headers)
        print(f"  {row}")


def display_characters(characters: List[Dict[str, Any]], verbose: bool = False):
    """Display characters in formatted output."""
    print(f"\n👥 Characters ({len(characters)} total)\n")
    
    if not characters:
        print("  (none)")
        return
    
    if verbose:
        for char in characters:
            print(f"  {char['id']}  {char['name']}")
            print(f"      Role: {char['role']}")
            print(f"      Type: {char['type']}")
            if char.get('description'):
                print(f"      Description: {char['description'][:80]}...")
            print()
    else:
        headers = ['id', 'name', 'role', 'type']
        display_table(characters, headers)
    
    print()


def display_locations(locations: List[Dict[str, Any]], verbose: bool = False):
    """Display locations in formatted output."""
    print(f"\n🗺️  Locations ({len(locations)} total)\n")
    
    if not locations:
        print("  (none)")
        return
    
    if verbose:
        for loc in locations:
            print(f"  {loc['id']}  {loc['name']}")
            print(f"      Type: {loc['type']}")
            print(f"      Atmosphere: {loc['atmosphere']}")
            if loc.get('description'):
                print(f"      Description: {loc['description'][:80]}...")
            print()
    else:
        headers = ['id', 'name', 'type', 'atmosphere']
        display_table(locations, headers)
    
    print()


def display_loops(loops: List[Dict[str, Any]], verbose: bool = False):
    """Display open loops in formatted output."""
    print(f"\n🔗 Open Loops ({len(loops)} total)\n")
    
    if not loops:
        print("  (none)")
        return
    
    if verbose:
        for loop in loops:
            status_icon = "✓" if loop['status'] == 'resolved' else "○"
            print(f"  {status_icon} {loop['id']}  Priority: {loop['priority']}")
            print(f"      {loop['description']}")
            if loop.get('created_in_scene'):
                print(f"      Created: {loop['created_in_scene']}")
            if loop.get('resolved_in_scene'):
                print(f"      Resolved: {loop['resolved_in_scene']}")
            print()
    else:
        headers = ['id', 'description', 'priority', 'status']
        display_table(loops, headers)
    
    print()


def display_scenes(scenes: List[Dict[str, Any]], verbose: bool = False):
    """Display scenes in formatted output."""
    print(f"\n📝 Scenes ({len(scenes)} total)\n")
    
    if not scenes:
        print("  (none)")
        return
    
    if verbose:
        for scene in scenes:
            tension_str = ""
            if scene.get('tension_level') is not None:
                tension_str = f" | Tension: {scene['tension_level']}/10 ({scene.get('tension_category', 'unknown')})"
            
            print(f"  {scene['file']}  ({scene['word_count']:,} words{tension_str})")
            print(f"      POV: {scene['pov_character']}")
            if scene.get('location'):
                print(f"      Location: {scene['location']}")
            if scene.get('summary'):
                print(f"      Summary: {scene['summary'][:80]}...")
            print()
    else:
        # Add tension column if any scenes have tension data
        has_tension = any(s.get('tension_level') is not None for s in scenes)
        if has_tension:
            headers = ['file', 'word_count', 'pov_character', 'tension_level']
            
            # Format tension level with category
            def format_row(item, headers, col_widths):
                parts = []
                for h in headers:
                    if h == 'tension_level' and item.get('tension_level') is not None:
                        value = f"{item['tension_level']}/10 ({item.get('tension_category', 'N/A')})"
                    else:
                        value = str(item.get(h, ''))
                    parts.append(value.ljust(col_widths[h]))
                return "  ".join(parts)
            
            display_table(scenes, headers, format_func=format_row)
        else:
            headers = ['file', 'word_count', 'pov_character']
            display_table(scenes, headers)
    
    print()


def display_json(items: List[Dict[str, Any]]):
    """Display items as JSON."""
    print(json.dumps(items, indent=2))
