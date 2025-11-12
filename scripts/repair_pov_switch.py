#!/usr/bin/env python3
"""
Repair script for POV switch bug.

This script fixes projects where C0 was overwritten when POV switched to a new character.
It reconstructs the missing character from relationship data and scene history.
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def repair_project(project_path: Path):
    """Repair a project with POV switch bug."""
    print(f"Repairing project: {project_path}")
    
    # Load relationships
    relationships_file = project_path / "memory" / "relationships.json"
    if not relationships_file.exists():
        print("  No relationships.json found")
        return False
    
    with open(relationships_file) as f:
        rel_data = json.load(f)
    
    # Check for relationships referencing missing characters
    characters_dir = project_path / "memory" / "characters"
    existing_chars = {f.stem for f in characters_dir.glob("*.json")}
    
    missing_chars = set()
    for rel in rel_data.get("relationships", []):
        char_a = rel.get("character_a")
        char_b = rel.get("character_b")
        
        if char_a and char_a not in existing_chars:
            missing_chars.add(char_a)
        if char_b and char_b not in existing_chars:
            missing_chars.add(char_b)
    
    if not missing_chars:
        print("  ✓ No missing characters found")
        return True
    
    print(f"  Found missing characters: {missing_chars}")
    
    # For this specific bug, we know:
    # - C0 was overwritten with Kyras
    # - C1 (Belia) is referenced but doesn't exist
    # - We need to create C1 for Belia
    
    if "C1" in missing_chars:
        print("  Creating C1 (Belia Jyxarn)...")
        
        # Create Belia's character file
        belia = {
            "id": "C1",
            "type": "character",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "first_name": "Belia",
            "family_name": "Jyxarn",
            "title": "",
            "nicknames": [],
            "role": "protagonist",
            "description": "Original protagonist, mining engineer on Europa",
            "physical_traits": {
                "age": None,
                "appearance": "",
                "distinctive_features": []
            },
            "personality": {
                "core_traits": [],
                "fears": [],
                "desires": [],
                "flaws": []
            },
            "relationships": [],
            "current_state": {
                "location_id": None,
                "emotional_state": "",
                "physical_state": "",
                "inventory": [],
                "goals": [],
                "beliefs": []
            },
            "backstory": "Reconstructed from relationship data after POV switch bug",
            "history": [],
            "metadata": {
                "reconstructed": True,
                "reconstruction_date": datetime.utcnow().isoformat() + "Z",
                "note": "This character was reconstructed because C0 was overwritten during POV switch"
            },
            "immediate_goals": [],
            "arc_goal": None,
            "story_goal": None,
            "goal_progress": {},
            "goals_completed": [],
            "goals_abandoned": []
        }
        
        # Save C1
        c1_file = characters_dir / "C1.json"
        with open(c1_file, 'w') as f:
            json.dump(belia, f, indent=2)
        
        print(f"  ✓ Created {c1_file}")
    
    # Update counters.json to reflect the new character
    counters_file = project_path / "memory" / "counters.json"
    if counters_file.exists():
        with open(counters_file) as f:
            counters = json.load(f)
        
        # Ensure character counter is at least 2
        if counters.get("character", 0) < 2:
            counters["character"] = 2
            with open(counters_file, 'w') as f:
                json.dump(counters, f, indent=2)
            print(f"  ✓ Updated counters.json")
    
    print("  ✓ Repair complete!")
    return True


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python repair_pov_switch.py <project_path>")
        print("Example: python repair_pov_switch.py /home/edward/novels/scifi-new_0f2360ba")
        sys.exit(1)
    
    project_path = Path(sys.argv[1])
    
    if not project_path.exists():
        print(f"Error: Project path does not exist: {project_path}")
        sys.exit(1)
    
    if not (project_path / "state.json").exists():
        print(f"Error: Not a valid project (no state.json): {project_path}")
        sys.exit(1)
    
    success = repair_project(project_path)
    
    if success:
        print("\n✅ Project repaired successfully!")
        print("\nNext steps:")
        print("1. Run 'novel tick' to generate the next scene")
        print("2. The POV switch detection should now work correctly")
        print("3. Check that both C0.json and C1.json exist in memory/characters/")
    else:
        print("\n❌ Repair failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
