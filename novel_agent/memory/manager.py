"""Memory manager for persistent storage and retrieval of entities."""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from .entities import (
    Character, Location, Scene, OpenLoop, RelationshipGraph, Lore, Faction,
    HistoryEntry, RelationshipHistoryEntry
)


class MemoryManager:
    """Manages persistent storage and retrieval of entities."""
    
    def __init__(self, project_path: Path):
        """Initialize memory manager.
        
        Args:
            project_path: Path to the novel project directory
        """
        self.project_path = Path(project_path)
        self.memory_path = self.project_path / "memory"
        self.characters_path = self.memory_path / "characters"
        self.locations_path = self.memory_path / "locations"
        self.scenes_path = self.memory_path / "scenes"
        self.factions_path = self.memory_path / "factions"
        self.qa_path = self.memory_path / "qa"
        self.open_loops_file = self.memory_path / "open_loops.json"
        self.relationships_file = self.memory_path / "relationships.json"
        self.lore_file = self.memory_path / "lore.json"
        self.counters_file = self.memory_path / "counters.json"
        
        self._ensure_directories()
        self._load_counters()
    
    def _ensure_directories(self):
        """Ensure all required directories exist."""
        self.memory_path.mkdir(parents=True, exist_ok=True)
        self.characters_path.mkdir(exist_ok=True)
        self.locations_path.mkdir(exist_ok=True)
        self.scenes_path.mkdir(exist_ok=True)
        self.factions_path.mkdir(exist_ok=True)
        self.qa_path.mkdir(exist_ok=True)
        
        # Initialize empty files if they don't exist
        if not self.open_loops_file.exists():
            self._write_json(self.open_loops_file, {"loops": []})
        
        if not self.relationships_file.exists():
            self._write_json(self.relationships_file, {"relationships": []})
        
        if not self.lore_file.exists():
            self._write_json(self.lore_file, {"lore": []})
        
        if not self.counters_file.exists():
            self._write_json(self.counters_file, {
                "character": 0,
                "location": 0,
                "scene": 0,
                "open_loop": 0,
                "relationship": 0,
                "lore": 0,
                "faction": 0
            })
    
    def _load_counters(self):
        """Load ID counters from disk."""
        self.counters = self._read_json(self.counters_file)

        # Backfill missing counters for backward compatibility
        for key in [
            "character",
            "location",
            "scene",
            "open_loop",
            "relationship",
            "lore",
            "faction",
        ]:
            if key not in self.counters:
                self.counters[key] = 0

        # Ensure the character counter is at least one past the highest
        # character ID present on disk, so existing projects with stale
        # counters.json do not reuse IDs.
        max_existing = -1
        for f in self.characters_path.glob("C*.json"):
            stem = f.stem
            try:
                idx = int(stem[1:])
            except (ValueError, IndexError):
                continue
            if idx > max_existing:
                max_existing = idx

        if max_existing >= 0 and self.counters.get("character", 0) <= max_existing:
            self.counters["character"] = max_existing + 1
            self._save_counters()
    
    def _save_counters(self):
        """Save ID counters to disk."""
        self._write_json(self.counters_file, self.counters)
    
    def _read_json(self, path: Path) -> Dict[str, Any]:
        """Read JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _write_json(self, path: Path, data: Dict[str, Any]):
        """Write JSON file with pretty formatting."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    # ========================================================================
    # ID Generation
    # ========================================================================
    
    def generate_id(self, entity_type: str) -> str:
        """Generate next ID for entity type.
        
        Args:
            entity_type: Type of entity (character, location, scene, open_loop, relationship)
        
        Returns:
            New ID string (e.g., C0, L0, S001, OL0, R0)
        """
        current = self.counters.get(entity_type, 0)

        # For characters, guard against stale or reset counters.json by
        # looking at existing character files on disk and ensuring we
        # never reuse an ID that already exists.
        if entity_type == "character":
            max_existing = -1
            for f in self.characters_path.glob("C*.json"):
                stem = f.stem
                # Expect IDs like C0, C1, C2, ...
                try:
                    idx = int(stem[1:])
                except (ValueError, IndexError):
                    continue
                if idx > max_existing:
                    max_existing = idx

            if max_existing >= 0 and current <= max_existing:
                current = max_existing + 1

        self.counters[entity_type] = current + 1
        self._save_counters()
        
        # Format based on type
        if entity_type == "character":
            return f"C{current}"
        elif entity_type == "location":
            return f"L{current}"
        elif entity_type == "scene":
            return f"S{current:03d}"  # Zero-padded to 3 digits
        elif entity_type == "open_loop":
            return f"OL{current}"
        elif entity_type == "relationship":
            return f"R{current}"
        elif entity_type == "faction":
            return f"F{current}"
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")
    
    # ========================================================================
    # CRUD Operations - Characters
    # ========================================================================
    
    def load_character(self, character_id: str) -> Optional[Character]:
        """Load a character by ID."""
        path = self.characters_path / f"{character_id}.json"
        if not path.exists():
            return None
        data = self._read_json(path)
        return Character.from_dict(data)
    
    def save_character(self, character: Character):
        """Save a character to disk."""
        character.updated_at = datetime.utcnow().isoformat() + "Z"
        path = self.characters_path / f"{character.id}.json"
        self._write_json(path, character.to_dict())
    
    def update_character(self, character_id: str, changes: Dict[str, Any]):
        """Update specific fields of a character.
        
        Args:
            character_id: Character ID
            changes: Dictionary of fields to update
        """
        character = self.load_character(character_id)
        if not character:
            raise ValueError(f"Character {character_id} not found")
        
        # Update fields
        for key, value in changes.items():
            if hasattr(character, key):
                setattr(character, key, value)
        
        self.save_character(character)
    
    def list_characters(self) -> List[str]:
        """List all character IDs."""
        return [f.stem for f in self.characters_path.glob("*.json")]
    
    # ========================================================================
    # CRUD Operations - Locations
    # ========================================================================
    
    def load_location(self, location_id: str) -> Optional[Location]:
        """Load a location by ID."""
        path = self.locations_path / f"{location_id}.json"
        if not path.exists():
            return None
        data = self._read_json(path)
        return Location.from_dict(data)
    
    def save_location(self, location: Location):
        """Save a location to disk."""
        location.updated_at = datetime.utcnow().isoformat() + "Z"
        path = self.locations_path / f"{location.id}.json"
        self._write_json(path, location.to_dict())
    
    def update_location(self, location_id: str, changes: Dict[str, Any]):
        """Update specific fields of a location."""
        location = self.load_location(location_id)
        if not location:
            raise ValueError(f"Location {location_id} not found")
        
        for key, value in changes.items():
            if hasattr(location, key):
                setattr(location, key, value)
        
        self.save_location(location)
    
    def list_locations(self) -> List[str]:
        """List all location IDs."""
        return [f.stem for f in self.locations_path.glob("*.json")]
    
    # ========================================================================
    # CRUD Operations - Scenes
    # ========================================================================
    
    def load_scene(self, scene_id: str) -> Optional[Scene]:
        """Load a scene by ID."""
        path = self.scenes_path / f"{scene_id}.json"
        if not path.exists():
            return None
        data = self._read_json(path)
        return Scene.from_dict(data)
    
    def save_scene(self, scene: Scene):
        """Save a scene to disk."""
        path = self.scenes_path / f"{scene.id}.json"
        self._write_json(path, scene.to_dict())
    
    def list_scenes(self) -> List[str]:
        """List all scene IDs."""
        return sorted([f.stem for f in self.scenes_path.glob("*.json")])

    def save_scene_qa(self, scene_id: str, tick: int, evaluation: Dict[str, Any]):
        """Save QA evaluation data for a scene."""
        data = {
            "scene_id": scene_id,
            "tick": tick,
            "evaluation": evaluation,
        }
        path = self.qa_path / f"{scene_id}.json"
        self._write_json(path, data)

    def load_scene_qa(self, scene_id: str) -> Optional[Dict[str, Any]]:
        """Load QA evaluation data for a scene."""
        path = self.qa_path / f"{scene_id}.json"
        if not path.exists():
            return None
        return self._read_json(path)

    def get_recent_scene_qa(self, count: int = 3) -> List[Dict[str, Any]]:
        """Get QA evaluations for the most recent scenes."""
        scene_ids = self.list_scenes()
        if not scene_ids:
            return []
        recent_ids = scene_ids[-count:]
        results: List[Dict[str, Any]] = []
        for scene_id in recent_ids:
            qa = self.load_scene_qa(scene_id)
            if qa:
                if "tick" not in qa:
                    scene = self.load_scene(scene_id)
                    if scene:
                        qa["tick"] = getattr(scene, "tick", None)
                results.append(qa)
        return results
    
    # ========================================================================
    # Generic Entity Operations
    # ========================================================================
    
    def load_entity(self, entity_id: str) -> Optional[Union[Character, Location, Scene, Faction]]:
        """Load an entity by ID (auto-detects type from prefix).
        
        Args:
            entity_id: Entity ID (C0, L0, S001, etc.)
        
        Returns:
            Entity object or None if not found
        """
        if entity_id.startswith("C"):
            return self.load_character(entity_id)
        elif entity_id.startswith("L"):
            return self.load_location(entity_id)
        elif entity_id.startswith("S"):
            return self.load_scene(entity_id)
        elif entity_id.startswith("F"):
            return self.load_faction(entity_id)
        else:
            raise ValueError(f"Unknown entity ID format: {entity_id}")
    
    def save_entity(self, entity: Union[Character, Location, Scene, Faction]):
        """Save an entity to disk (auto-detects type)."""
        if isinstance(entity, Character):
            self.save_character(entity)
        elif isinstance(entity, Location):
            self.save_location(entity)
        elif isinstance(entity, Scene):
            self.save_scene(entity)
        elif isinstance(entity, Faction):
            self.save_faction(entity)
        else:
            raise ValueError(f"Unknown entity type: {type(entity)}")
    
    def update_entity(self, entity_id: str, changes: Dict[str, Any]):
        """Update specific fields of an entity."""
        if entity_id.startswith("C"):
            self.update_character(entity_id, changes)
        elif entity_id.startswith("L"):
            self.update_location(entity_id, changes)
        else:
            raise ValueError(f"Cannot update entity type: {entity_id}")
    
    def list_entities(self, entity_type: str) -> List[str]:
        """List all entity IDs of a given type.
        
        Args:
            entity_type: Type of entity (character, location, scene)
        
        Returns:
            List of entity IDs
        """
        if entity_type == "character":
            return self.list_characters()
        elif entity_type == "location":
            return self.list_locations()
        elif entity_type == "scene":
            return self.list_scenes()
        elif entity_type == "faction":
            return self.list_factions()
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")

    # ========================================================================
    # CRUD Operations - Factions
    # ========================================================================

    def load_faction(self, faction_id: str) -> Optional[Faction]:
        """Load a faction by ID."""
        path = self.factions_path / f"{faction_id}.json"
        if not path.exists():
            return None
        data = self._read_json(path)
        return Faction.from_dict(data)

    def save_faction(self, faction: Faction):
        """Save a faction to disk."""
        faction.updated_at = datetime.utcnow().isoformat() + "Z"
        path = self.factions_path / f"{faction.id}.json"
        self._write_json(path, faction.to_dict())

    def update_faction(self, faction_id: str, changes: Dict[str, Any]):
        """Update specific fields of a faction."""
        faction = self.load_faction(faction_id)
        if not faction:
            raise ValueError(f"Faction {faction_id} not found")
        for key, value in changes.items():
            if hasattr(faction, key):
                setattr(faction, key, value)
        self.save_faction(faction)

    def list_factions(self) -> List[str]:
        """List all faction IDs."""
        return [f.stem for f in self.factions_path.glob("*.json")]
    
    # ========================================================================
    # Open Loops Management
    # ========================================================================
    
    def load_open_loops(self) -> List[OpenLoop]:
        """Load all open loops."""
        data = self._read_json(self.open_loops_file)
        return [OpenLoop.from_dict(loop) for loop in data.get("loops", [])]
    
    def save_open_loops(self, loops: List[OpenLoop]):
        """Save open loops to disk."""
        data = {"loops": [loop.to_dict() for loop in loops]}
        self._write_json(self.open_loops_file, data)
    
    def add_open_loop(self, loop: OpenLoop):
        """Add a new open loop."""
        loops = self.load_open_loops()
        loops.append(loop)
        self.save_open_loops(loops)
    
    def resolve_open_loop(self, loop_id: str, scene_id: str, summary: str):
        """Mark an open loop as resolved.
        
        Args:
            loop_id: ID of the loop to resolve
            scene_id: Scene where it was resolved
            summary: Summary of how it was resolved
        """
        loops = self.load_open_loops()
        for loop in loops:
            if loop.id == loop_id:
                loop.status = "resolved"
                loop.resolved_in_scene = scene_id
                loop.resolution_summary = summary
                break
        self.save_open_loops(loops)
    
    def get_open_loops(self, status: str = "open") -> List[OpenLoop]:
        """Get loops by status.
        
        Args:
            status: Status filter (open, resolved, abandoned)
        
        Returns:
            List of matching loops
        """
        loops = self.load_open_loops()
        return [loop for loop in loops if loop.status == status]
    
    # ========================================================================
    # Relationship Graph Management
    # ========================================================================
    
    def load_relationships(self) -> List[RelationshipGraph]:
        """Load all relationships."""
        data = self._read_json(self.relationships_file)
        return [RelationshipGraph.from_dict(rel) for rel in data.get("relationships", [])]
    
    def save_relationships(self, relationships: List[RelationshipGraph]):
        """Save relationships to disk."""
        data = {"relationships": [rel.to_dict() for rel in relationships]}
        self._write_json(self.relationships_file, data)
    
    def add_relationship(self, relationship: RelationshipGraph):
        """Add a new relationship."""
        relationships = self.load_relationships()
        relationships.append(relationship)
        self.save_relationships(relationships)
    
    def update_relationship(self, relationship_id: str, changes: Dict[str, Any]):
        """Update a relationship.
        
        Args:
            relationship_id: Relationship ID
            changes: Dictionary of fields to update
        """
        relationships = self.load_relationships()
        for rel in relationships:
            if rel.id == relationship_id:
                # Update fields
                for key, value in changes.items():
                    if hasattr(rel, key):
                        setattr(rel, key, value)
                rel.updated_at = datetime.utcnow().isoformat() + "Z"
                break
        self.save_relationships(relationships)
    
    def get_character_relationships(self, character_id: str) -> List[RelationshipGraph]:
        """Get all relationships involving a character.
        
        Args:
            character_id: Character ID
        
        Returns:
            List of relationships
        """
        relationships = self.load_relationships()
        return [rel for rel in relationships if rel.involves_character(character_id)]
    
    def get_relationship_between(self, char_a: str, char_b: str) -> Optional[RelationshipGraph]:
        """Get relationship between two characters (order-independent).
        
        Args:
            char_a: First character ID
            char_b: Second character ID
        
        Returns:
            Relationship or None if not found
        """
        relationships = self.load_relationships()
        for rel in relationships:
            if (rel.character_a == char_a and rel.character_b == char_b) or \
               (rel.character_a == char_b and rel.character_b == char_a):
                return rel
        return None
    
    def add_relationship_history(self, relationship_id: str, tick: int, scene_id: str, 
                                 event: str, status_change: Optional[str] = None):
        """Add a history entry to a relationship.
        
        Args:
            relationship_id: Relationship ID
            tick: Current tick number
            scene_id: Scene where event occurred
            event: Description of what happened
            status_change: Optional status change description
        """
        relationships = self.load_relationships()
        for rel in relationships:
            if rel.id == relationship_id:
                entry = RelationshipHistoryEntry(
                    tick=tick,
                    scene_id=scene_id,
                    event=event,
                    status_change=status_change
                )
                rel.history.append(entry)
                rel.updated_at = datetime.utcnow().isoformat() + "Z"
                break
        self.save_relationships(relationships)
    
    # ========================================================================
    # State Management
    # ========================================================================
    
    def set_active_character(self, character_id: str):
        """Set the active character in state.json.
        
        Args:
            character_id: Character ID to set as active
        """
        state_file = self.project_path / "state.json"
        
        # Load current state
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        # Update active character
        state["active_character"] = character_id
        state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        
        # Save state
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def get_active_character(self) -> Optional[str]:
        """Get the active character ID from state.json.
        
        Returns:
            Active character ID or None
        """
        state_file = self.project_path / "state.json"
        
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        return state.get("active_character")
    
    # ========================================================================
    # Lore Management (Phase 7A.4)
    # ========================================================================
    
    def generate_lore_id(self) -> str:
        """Generate a new lore ID.
        
        Returns:
            New lore ID (e.g., "L001")
        """
        # Handle missing lore counter (backward compatibility)
        current = self.counters.get("lore", 0)
        self.counters["lore"] = current + 1
        self._save_counters()
        return f"L{self.counters['lore']:03d}"
    
    def save_lore(self, lore: Lore):
        """Save a lore entry.
        
        Args:
            lore: Lore object to save
        """
        lore_list = self.load_all_lore()
        
        # Update existing or append new
        found = False
        for i, existing in enumerate(lore_list):
            if existing.id == lore.id:
                lore_list[i] = lore
                found = True
                break
        
        if not found:
            lore_list.append(lore)
        
        # Save to file
        data = {"lore": [l.to_dict() for l in lore_list]}
        self._write_json(self.lore_file, data)
    
    def load_lore(self, lore_id: str) -> Optional[Lore]:
        """Load a specific lore entry.
        
        Args:
            lore_id: Lore ID to load
            
        Returns:
            Lore object or None if not found
        """
        lore_list = self.load_all_lore()
        for lore in lore_list:
            if lore.id == lore_id:
                return lore
        return None
    
    def load_all_lore(self) -> List[Lore]:
        """Load all lore entries.
        
        Returns:
            List of Lore objects
        """
        data = self._read_json(self.lore_file)
        return [Lore.from_dict(l) for l in data.get("lore", [])]
    
    def list_lore_by_category(self, category: str) -> List[Lore]:
        """List lore entries by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of Lore objects in that category
        """
        all_lore = self.load_all_lore()
        return [l for l in all_lore if l.category.lower() == category.lower()]
    
    def list_lore_by_type(self, lore_type: str) -> List[Lore]:
        """List lore entries by type.
        
        Args:
            lore_type: Type to filter by (rule, fact, constraint, etc.)
            
        Returns:
            List of Lore objects of that type
        """
        all_lore = self.load_all_lore()
        return [l for l in all_lore if l.lore_type.lower() == lore_type.lower()]
    
    def delete_lore(self, lore_id: str):
        """Delete a lore entry.
        
        Args:
            lore_id: Lore ID to delete
        """
        lore_list = self.load_all_lore()
        lore_list = [l for l in lore_list if l.id != lore_id]
        data = {"lore": [l.to_dict() for l in lore_list]}
        self._write_json(self.lore_file, data)
