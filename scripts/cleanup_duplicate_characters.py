#!/usr/bin/env python3
"""Clean up duplicate characters by role."""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict

def cleanup_duplicate_characters(project_dir: str, dry_run: bool = True):
    """Remove duplicate characters, keeping the first of each unique role.
    
    Args:
        project_dir: Path to the novel project
        dry_run: If True, only show what would be deleted
    """
    char_dir = Path(project_dir) / "memory" / "characters"
    
    if not char_dir.exists():
        print(f"❌ Character directory not found: {char_dir}")
        return
    
    # Load all characters
    characters = []
    for char_file in sorted(char_dir.glob("C*.json")):
        try:
            with open(char_file) as f:
                char = json.load(f)
                char['_file'] = char_file
                characters.append(char)
        except Exception as e:
            print(f"⚠️  Error loading {char_file}: {e}")
    
    print(f"\n📊 Found {len(characters)} characters\n")
    
    # Group by role
    by_role = defaultdict(list)
    for char in characters:
        role = (char.get('role') or 'unknown').lower()
        by_role[role].append(char)
    
    # Find duplicates
    unique_roles = ['protagonist', 'antagonist']
    to_delete = []
    
    for role in unique_roles:
        chars_with_role = by_role.get(role, [])
        if len(chars_with_role) > 1:
            print(f"🔍 Found {len(chars_with_role)} {role}s:")
            for i, char in enumerate(chars_with_role):
                name = f"{char.get('first_name', '')} {char.get('family_name', '')}".strip()
                marker = "✅ KEEP" if i == 0 else "❌ DELETE"
                print(f"   {marker} - {char['id']}: {name}")
                if i > 0:
                    to_delete.append(char)
            print()
    
    # Also check for duplicate names
    by_name = defaultdict(list)
    for char in characters:
        first = (char.get('first_name') or '').lower()
        family = (char.get('family_name') or '').lower()
        if first:
            name_key = f"{first} {family}".strip()
            by_name[name_key].append(char)
    
    for name, chars_with_name in by_name.items():
        if len(chars_with_name) > 1:
            print(f"🔍 Found {len(chars_with_name)} characters named '{name}':")
            for i, char in enumerate(chars_with_name):
                role = char.get('role', 'unknown')
                marker = "✅ KEEP" if i == 0 else "❌ DELETE"
                print(f"   {marker} - {char['id']}: {role}")
                if i > 0 and char not in to_delete:
                    to_delete.append(char)
            print()
    
    if not to_delete:
        print("✅ No duplicates found!")
        return
    
    print(f"\n📋 Summary: {len(to_delete)} character(s) to delete\n")
    
    if dry_run:
        print("🔍 DRY RUN - No files will be deleted")
        print("   Run with --execute to actually delete files\n")
        return
    
    # Actually delete
    print("🗑️  Deleting duplicate characters...\n")
    for char in to_delete:
        char_file = char['_file']
        try:
            os.remove(char_file)
            name = f"{char.get('first_name', '')} {char.get('family_name', '')}".strip()
            print(f"   ✓ Deleted {char['id']}: {name}")
        except Exception as e:
            print(f"   ✗ Error deleting {char_file}: {e}")
    
    print(f"\n✅ Cleanup complete! Deleted {len(to_delete)} character(s)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cleanup_duplicate_characters.py <project_dir> [--execute]")
        print("\nExample:")
        print("  python cleanup_duplicate_characters.py ~/novels/my-novel")
        print("  python cleanup_duplicate_characters.py ~/novels/my-novel --execute")
        sys.exit(1)
    
    project_dir = sys.argv[1]
    execute = "--execute" in sys.argv
    
    cleanup_duplicate_characters(project_dir, dry_run=not execute)
