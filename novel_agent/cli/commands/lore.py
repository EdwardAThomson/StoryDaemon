"""Lore command - display world rules and lore (Phase 7A.4)."""
import json
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict


def get_lore_info(project_dir: Path) -> Dict[str, Any]:
    """Gather lore information.
    
    Args:
        project_dir: Path to project directory
        
    Returns:
        Dictionary with lore information
    """
    from ...memory.manager import MemoryManager
    
    memory = MemoryManager(project_dir)
    
    # Get all lore
    all_lore = memory.load_all_lore()
    
    # Group by category
    by_category = defaultdict(list)
    for lore in all_lore:
        by_category[lore.category].append({
            'id': lore.id,
            'type': lore.lore_type,
            'content': lore.content,
            'importance': lore.importance,
            'source_scene': lore.source_scene_id,
            'tick': lore.tick,
            'tags': lore.tags,
            'contradictions': lore.potential_contradictions
        })
    
    # Group by type
    by_type = defaultdict(list)
    for lore in all_lore:
        by_type[lore.lore_type].append({
            'id': lore.id,
            'category': lore.category,
            'content': lore.content,
            'importance': lore.importance,
            'source_scene': lore.source_scene_id,
            'tick': lore.tick
        })
    
    # Count by importance
    importance_counts = defaultdict(int)
    for lore in all_lore:
        importance_counts[lore.importance] += 1
    
    return {
        'total_count': len(all_lore),
        'by_category': dict(by_category),
        'by_type': dict(by_type),
        'importance_counts': dict(importance_counts),
        'all_lore': [
            {
                'id': lore.id,
                'type': lore.lore_type,
                'category': lore.category,
                'content': lore.content,
                'importance': lore.importance,
                'source_scene': lore.source_scene_id,
                'tick': lore.tick,
                'tags': lore.tags,
                'contradictions': lore.potential_contradictions
            }
            for lore in all_lore
        ]
    }


def display_lore(
    info: Dict[str, Any],
    use_color: bool = True,
    group_by: str = 'category',
    filter_category: str = None,
    filter_type: str = None,
    filter_importance: str = None
):
    """Display lore in formatted output.
    
    Args:
        info: Lore information dictionary
        use_color: Whether to use colored output
        group_by: How to group lore ('category', 'type', or 'none')
        filter_category: Optional category filter
        filter_type: Optional type filter
        filter_importance: Optional importance filter
    """
    def bold(text):
        return f"\033[1m{text}\033[0m" if use_color else text
    
    def dim(text):
        return f"\033[2m{text}\033[0m" if use_color else text
    
    def importance_color(importance):
        if not use_color:
            return importance
        colors = {
            'critical': '\033[91m',  # Red
            'important': '\033[93m',  # Yellow
            'normal': '\033[92m',     # Green
            'minor': '\033[94m'       # Blue
        }
        reset = '\033[0m'
        return f"{colors.get(importance, '')}{importance}{reset}"
    
    print()
    print(f"🌍 {bold('World Lore')}")
    print("━" * 80)
    
    total = info.get('total_count', 0)
    if total == 0:
        print("\nNo lore established yet. Lore will be extracted as scenes are generated.")
        print()
        return
    
    # Apply filters
    lore_items = info.get('all_lore', [])
    if filter_category:
        lore_items = [l for l in lore_items if l['category'].lower() == filter_category.lower()]
    if filter_type:
        lore_items = [l for l in lore_items if l['type'].lower() == filter_type.lower()]
    if filter_importance:
        lore_items = [l for l in lore_items if l['importance'].lower() == filter_importance.lower()]
    
    if not lore_items:
        print(f"\nNo lore found matching filters.")
        print()
        return
    
    print(f"\n{bold('Summary:')}")
    print(f"  Total lore items: {total}")
    
    importance_counts = info.get('importance_counts', {})
    if importance_counts:
        print(f"  By importance:")
        for imp in ['critical', 'important', 'normal', 'minor']:
            count = importance_counts.get(imp, 0)
            if count > 0:
                print(f"    • {importance_color(imp)}: {count}")
    
    # Display grouped
    if group_by == 'category':
        print(f"\n{bold('By Category:')}")
        by_category = defaultdict(list)
        for item in lore_items:
            by_category[item['category']].append(item)
        
        for category in sorted(by_category.keys()):
            items = by_category[category]
            print(f"\n  {bold(category.title())} ({len(items)} items)")
            for item in items:
                _display_lore_item(item, use_color, indent=4)
    
    elif group_by == 'type':
        print(f"\n{bold('By Type:')}")
        by_type = defaultdict(list)
        for item in lore_items:
            by_type[item['type']].append(item)
        
        for lore_type in sorted(by_type.keys()):
            items = by_type[lore_type]
            print(f"\n  {bold(lore_type.title())} ({len(items)} items)")
            for item in items:
                _display_lore_item(item, use_color, indent=4)
    
    else:  # group_by == 'none'
        print(f"\n{bold('All Lore:')}")
        for item in sorted(lore_items, key=lambda x: x['tick']):
            _display_lore_item(item, use_color, indent=2)
    
    print()


def _display_lore_item(item: Dict[str, Any], use_color: bool, indent: int = 2):
    """Display a single lore item.
    
    Args:
        item: Lore item dictionary
        use_color: Whether to use colored output
        indent: Number of spaces to indent
    """
    def dim(text):
        return f"\033[2m{text}\033[0m" if use_color else text
    
    def importance_color(importance):
        if not use_color:
            return importance
        colors = {
            'critical': '\033[91m',  # Red
            'important': '\033[93m',  # Yellow
            'normal': '\033[92m',     # Green
            'minor': '\033[94m'       # Blue
        }
        reset = '\033[0m'
        return f"{colors.get(importance, '')}{importance}{reset}"
    
    prefix = " " * indent
    
    # Main content
    print(f"{prefix}• {item['content']}")
    
    # Metadata
    meta_parts = [
        f"[{item['id']}]",
        f"{item['type']}",
        f"{item['category']}",
        importance_color(item['importance']),
        f"Scene {item['source_scene']}"
    ]
    print(f"{prefix}  {dim(' | '.join(meta_parts))}")
    
    # Tags
    if item.get('tags'):
        tags_str = ', '.join(item['tags'])
        print(f"{prefix}  {dim('Tags: ' + tags_str)}")
    
    # Contradictions
    if item.get('contradictions'):
        contradiction_count = len(item['contradictions'])
        print(f"{prefix}  {dim('⚠️  Potential contradictions: ' + str(contradiction_count))}")


def display_lore_json(info: Dict[str, Any]):
    """Display lore information as JSON.
    
    Args:
        info: Lore information dictionary
    """
    print(json.dumps(info, indent=2))


def display_lore_stats(info: Dict[str, Any], use_color: bool = True):
    """Display lore statistics.
    
    Args:
        info: Lore information dictionary
        use_color: Whether to use colored output
    """
    def bold(text):
        return f"\033[1m{text}\033[0m" if use_color else text
    
    print()
    print(f"📊 {bold('Lore Statistics')}")
    print("━" * 60)
    
    total = info.get('total_count', 0)
    print(f"\n{bold('Total Lore Items:')} {total}")
    
    if total == 0:
        print()
        return
    
    # By category
    by_category = info.get('by_category', {})
    if by_category:
        print(f"\n{bold('By Category:')}")
        for category in sorted(by_category.keys()):
            count = len(by_category[category])
            print(f"  • {category.title()}: {count}")
    
    # By type
    by_type = info.get('by_type', {})
    if by_type:
        print(f"\n{bold('By Type:')}")
        for lore_type in sorted(by_type.keys()):
            count = len(by_type[lore_type])
            print(f"  • {lore_type.title()}: {count}")
    
    # By importance
    importance_counts = info.get('importance_counts', {})
    if importance_counts:
        print(f"\n{bold('By Importance:')}")
        for imp in ['critical', 'important', 'normal', 'minor']:
            count = importance_counts.get(imp, 0)
            if count > 0:
                print(f"  • {imp.title()}: {count}")
    
    # Contradictions
    all_lore = info.get('all_lore', [])
    with_contradictions = [l for l in all_lore if l.get('contradictions')]
    if with_contradictions:
        print(f"\n{bold('Contradictions:')}")
        print(f"  ⚠️  {len(with_contradictions)} items have potential contradictions")
    
    print()
