"""Memory-related tools for the story agent."""

import random
from typing import Dict, List, Optional, Any
from pathlib import Path
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..memory.entities import (
    Character, Location, RelationshipGraph, Faction,
    PhysicalTraits, Personality, CurrentState
)
from .base import Tool


class MemorySearchTool(Tool):
    """Semantic search across stored entities."""
    
    def __init__(self, memory_manager: MemoryManager, vector_store: VectorStore):
        super().__init__(
            name="memory.search",
            description="Search for relevant characters, locations, or scenes using natural language",
            parameters={
                "query": {
                    "type": "string",
                    "description": "Natural language search query"
                },
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["character", "location", "scene", "faction"]},
                    "description": "Optional filter by entity types",
                    "optional": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5)",
                    "optional": True
                }
            }
        )
        self.memory_manager = memory_manager
        self.vector_store = vector_store
    
    def execute(self, query: str, entity_types: Optional[List[str]] = None, 
                limit: int = 5) -> Dict[str, Any]:
        """Execute semantic search.
        
        Args:
            query: Search query
            entity_types: Optional filter by entity types
            limit: Max results
        
        Returns:
            Search results with entity info
        """
        results = self.vector_store.search(query, entity_types, limit)
        
        # Format results for LLM
        formatted_results = []
        for result in results:
            entity_id = result["entity_id"]
            entity_type = result["metadata"].get("entity_type", "unknown")
            
            formatted_results.append({
                "entity_id": entity_id,
                "entity_type": entity_type,
                "name": result["metadata"].get("name", ""),
                "relevance_score": round(result["relevance_score"], 2),
                "snippet": result["snippet"][:200] + "..." if len(result["snippet"]) > 200 else result["snippet"]
            })
        
        return {
            "success": True,
            "results": formatted_results,
            "count": len(formatted_results)
        }


class CharacterGenerateTool(Tool):
    """Create a new character."""
    
    def __init__(self, memory_manager: MemoryManager, vector_store: VectorStore, name_generator=None):
        super().__init__(
            name="character.generate",
            description="Create a new character with initial attributes. Name will be auto-generated if not provided.",
            parameters={
                "name": {
                    "type": "string",
                    "description": "Character name (optional - will be auto-generated if omitted)",
                    "optional": True
                },
                "gender": {
                    "type": "string",
                    "enum": ["male", "female"],
                    "description": "Character gender for name generation (defaults to random 50/50 if not specified)",
                    "optional": True
                },
                "role": {
                    "type": "string",
                    "description": "Character role (protagonist, antagonist, supporting, minor)"
                },
                "description": {
                    "type": "string",
                    "description": "Brief character description"
                },
                "traits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Core personality traits",
                    "optional": True
                },
                "goals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Initial goals",
                    "optional": True
                }
            }
        )
        self.memory_manager = memory_manager
        self.vector_store = vector_store
        self.name_generator = name_generator
    
    def execute(self, role: str, description: str,
                name: Optional[str] = None,
                gender: Optional[str] = None,
                traits: Optional[List[str]] = None, 
                goals: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new character.
        
        Args:
            role: Character role
            description: Character description
            name: Character name (optional - will be auto-generated)
            gender: Character gender for name generation
            traits: Optional personality traits
            goals: Optional initial goals
        
        Returns:
            Success status and character ID
        """
        # Auto-generate name if not provided
        first_name = ""
        family_name = ""
        title = ""
        
        if not name and self.name_generator:
            # Random 50/50 if gender not specified (to avoid LLM bias)
            char_gender = gender or random.choice(["male", "female"])
            name_result = self.name_generator.generate_name(gender=char_gender, genre="scifi")
            first_name = name_result["first_name"]
            family_name = name_result["last_name"]
            title = name_result.get("title", "")
        elif name:
            # Split provided name
            parts = name.strip().split()
            if len(parts) >= 2:
                first_name = parts[0]
                family_name = ' '.join(parts[1:])
            elif len(parts) == 1:
                first_name = parts[0]
        else:
            # Fallback if no generator available
            first_name = f"Character_{self.memory_manager.generate_id('character')}"
        
        # Generate ID
        character_id = self.memory_manager.generate_id("character")
        
        # Create character entity
        character = Character(
            id=character_id,
            first_name=first_name,
            family_name=family_name,
            title=title,
            role=role,
            description=description,
            personality=Personality(core_traits=traits or []),
            current_state=CurrentState(goals=goals or [])
        )
        
        # Save to disk
        self.memory_manager.save_character(character)
        
        # Index in vector store
        self.vector_store.index_character(character)
        
        # Set as active character if no active character exists
        if self.memory_manager.get_active_character() is None:
            self.memory_manager.set_active_character(character_id)
        
        return {
            "success": True,
            "character_id": character_id,
            "name": character.full_name
        }


class LocationGenerateTool(Tool):
    """Create a new location."""
    
    def __init__(self, memory_manager: MemoryManager, vector_store: VectorStore):
        super().__init__(
            name="location.generate",
            description="Create a new location with initial attributes",
            parameters={
                "name": {
                    "type": "string",
                    "description": "Location name"
                },
                "description": {
                    "type": "string",
                    "description": "Brief location description"
                },
                "atmosphere": {
                    "type": "string",
                    "description": "Mood/feeling of the location",
                    "optional": True
                },
                "features": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notable features",
                    "optional": True
                }
            }
        )
        self.memory_manager = memory_manager
        self.vector_store = vector_store
    
    def execute(self, name: str, description: str,
                atmosphere: Optional[str] = None,
                features: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new location.
        
        Args:
            name: Location name
            description: Location description
            atmosphere: Optional atmosphere
            features: Optional features
        
        Returns:
            Success status and location ID
        """
        # Generate ID
        location_id = self.memory_manager.generate_id("location")
        
        # Create location entity
        location = Location(
            id=location_id,
            name=name,
            description=description,
            atmosphere=atmosphere or "",
            features=features or []
        )
        
        # Save to disk
        self.memory_manager.save_location(location)
        
        # Index in vector store
        self.vector_store.index_location(location)
        
        return {
            "success": True,
            "location_id": location_id,
            "name": name
        }


class RelationshipCreateTool(Tool):
    """Create a new relationship between two characters."""
    
    def __init__(self, memory_manager: MemoryManager):
        super().__init__(
            name="relationship.create",
            description="Create a new relationship between two characters",
            parameters={
                "character_a": {
                    "type": "string",
                    "description": "First character ID"
                },
                "character_b": {
                    "type": "string",
                    "description": "Second character ID"
                },
                "relationship_type": {
                    "type": "string",
                    "description": "Type of relationship (mentor-student, friends, rivals, enemies, family, romantic, etc.)"
                },
                "perspective_a": {
                    "type": "string",
                    "description": "How character_a views character_b"
                },
                "perspective_b": {
                    "type": "string",
                    "description": "How character_b views character_a"
                },
                "status": {
                    "type": "string",
                    "description": "Relationship status (neutral, close, strained, hostile, etc.)",
                    "optional": True
                },
                "intensity": {
                    "type": "integer",
                    "description": "Importance 0-10 (default: 5)",
                    "optional": True
                }
            }
        )
        self.memory_manager = memory_manager
    
    def execute(self, character_a: str, character_b: str, relationship_type: str,
                perspective_a: str, perspective_b: str,
                status: str = "neutral", intensity: int = 5) -> Dict[str, Any]:
        """Create a new relationship.
        
        Args:
            character_a: First character ID
            character_b: Second character ID
            relationship_type: Type of relationship
            perspective_a: How A views B
            perspective_b: How B views A
            status: Relationship status
            intensity: Importance 0-10
        
        Returns:
            Success status and relationship ID
        """
        # Check if relationship already exists
        existing = self.memory_manager.get_relationship_between(character_a, character_b)
        if existing:
            return {
                "success": False,
                "error": f"Relationship already exists: {existing.id}"
            }
        
        # Generate ID
        relationship_id = self.memory_manager.generate_id("relationship")
        
        # Create relationship
        relationship = RelationshipGraph(
            id=relationship_id,
            character_a=character_a,
            character_b=character_b,
            relationship_type=relationship_type,
            perspective_a=perspective_a,
            perspective_b=perspective_b,
            status=status,
            intensity=intensity
        )
        
        # Save to disk
        self.memory_manager.add_relationship(relationship)
        
        return {
            "success": True,
            "relationship_id": relationship_id
        }


class RelationshipUpdateTool(Tool):
    """Update an existing relationship."""
    
    def __init__(self, memory_manager: MemoryManager):
        super().__init__(
            name="relationship.update",
            description="Update an existing relationship between two characters",
            parameters={
                "character_a": {
                    "type": "string",
                    "description": "First character ID"
                },
                "character_b": {
                    "type": "string",
                    "description": "Second character ID"
                },
                "status": {
                    "type": "string",
                    "description": "New status",
                    "optional": True
                },
                "event": {
                    "type": "string",
                    "description": "Description of what happened",
                    "optional": True
                },
                "scene_id": {
                    "type": "string",
                    "description": "Scene where this occurred",
                    "optional": True
                },
                "intensity": {
                    "type": "integer",
                    "description": "New intensity level 0-10",
                    "optional": True
                }
            }
        )
        self.memory_manager = memory_manager
    
    def execute(self, character_a: str, character_b: str,
                status: Optional[str] = None, event: Optional[str] = None,
                scene_id: Optional[str] = None, intensity: Optional[int] = None,
                tick: Optional[int] = None) -> Dict[str, Any]:
        """Update a relationship.
        
        Args:
            character_a: First character ID
            character_b: Second character ID
            status: New status
            event: Event description
            scene_id: Scene ID
            intensity: New intensity
            tick: Current tick number
        
        Returns:
            Success status
        """
        # Find relationship
        relationship = self.memory_manager.get_relationship_between(character_a, character_b)
        if not relationship:
            return {
                "success": False,
                "error": f"No relationship found between {character_a} and {character_b}"
            }
        
        # Build changes dict
        changes = {}
        if status is not None:
            changes["status"] = status
        if intensity is not None:
            changes["intensity"] = intensity
        
        # Update relationship
        if changes:
            self.memory_manager.update_relationship(relationship.id, changes)
        
        # Add history entry if event provided
        if event and scene_id and tick is not None:
            status_change = f"{relationship.status} -> {status}" if status else None
            self.memory_manager.add_relationship_history(
                relationship.id, tick, scene_id, event, status_change
            )
        
        return {
            "success": True,
            "relationship_id": relationship.id,
            "updated": True
        }


class RelationshipQueryTool(Tool):
    """Query relationships for a character."""
    
    def __init__(self, memory_manager: MemoryManager):
        super().__init__(
            name="relationship.query",
            description="Query relationships for a character to understand social dynamics",
            parameters={
                "character_id": {
                    "type": "string",
                    "description": "Character to query relationships for"
                },
                "status_filter": {
                    "type": "string",
                    "description": "Optional filter by status (e.g., strained, hostile)",
                    "optional": True
                }
            }
        )
        self.memory_manager = memory_manager
    
    def execute(self, character_id: str, 
                status_filter: Optional[str] = None) -> Dict[str, Any]:
        """Query relationships for a character.
        
        Args:
            character_id: Character ID
            status_filter: Optional status filter
        
        Returns:
            List of relationships from character's perspective
        """
        relationships = self.memory_manager.get_character_relationships(character_id)
        
        # Filter by status if requested
        if status_filter:
            relationships = [r for r in relationships if r.status == status_filter]
        
        # Format results from character's perspective
        formatted = []
        for rel in relationships:
            other_char_id = rel.get_other_character(character_id)
            your_view = rel.get_perspective(character_id)
            
            # Load other character to get name
            other_char = self.memory_manager.load_character(other_char_id)
            other_char_name = other_char.name if other_char else other_char_id
            
            formatted.append({
                "character_id": other_char_id,
                "character_name": other_char_name,
                "relationship_type": rel.relationship_type,
                "status": rel.status,
                "your_view": your_view,
                "intensity": rel.intensity
            })
        
        return {
            "success": True,
            "relationships": formatted,
            "count": len(formatted)
        }


class FactionGenerateTool(Tool):
    """Create a new faction/organization entity."""
    
    def __init__(self, memory_manager: MemoryManager, vector_store: VectorStore):
        super().__init__(
            name="faction.generate",
            description="Create a new faction (organization) with core attributes",
            parameters={
                "name": {"type": "string", "description": "Faction name", "optional": True},
                "org_type": {"type": "string", "description": "Type (corporate, government, guild, etc.)"},
                "summary": {"type": "string", "description": "1-2 sentence summary"},
                "mandate_objectives": {"type": "array", "items": {"type": "string"}, "optional": True},
                "influence_domains": {"type": "array", "items": {"type": "string"}, "optional": True},
                "assets_resources": {"type": "array", "items": {"type": "string"}, "optional": True},
                "methods_tactics": {"type": "array", "items": {"type": "string"}, "optional": True},
                "stance_by_character": {"type": "object", "description": "Initial stances by character id", "optional": True},
                "importance": {"type": "string", "description": "low|medium|high|critical", "optional": True},
                "tags": {"type": "array", "items": {"type": "string"}, "optional": True}
            }
        )
        self.memory_manager = memory_manager
        self.vector_store = vector_store
    
    def execute(
        self,
        org_type: str,
        summary: str,
        name: Optional[str] = None,
        mandate_objectives: Optional[List[str]] = None,
        influence_domains: Optional[List[str]] = None,
        assets_resources: Optional[List[str]] = None,
        methods_tactics: Optional[List[str]] = None,
        stance_by_character: Optional[Dict[str, str]] = None,
        importance: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        faction_id = self.memory_manager.generate_id("faction")
        faction = Faction(
            id=faction_id,
            name=name or f"Faction_{faction_id}",
            org_type=org_type,
            summary=summary,
            mandate_objectives=mandate_objectives or [],
            influence_domains=influence_domains or [],
            assets_resources=assets_resources or [],
            methods_tactics=methods_tactics or [],
            stance_by_character=stance_by_character or {},
            importance=importance or "medium",
            tags=tags or []
        )
        self.memory_manager.save_faction(faction)
        self.vector_store.index_faction(faction)
        return {"success": True, "faction_id": faction_id, "name": faction.name}


class FactionUpdateTool(Tool):
    """Update an existing faction."""
    def __init__(self, memory_manager: MemoryManager, vector_store: VectorStore):
        super().__init__(
            name="faction.update",
            description="Update fields on a faction (e.g., stances, assets, methods)",
            parameters={
                "id": {"type": "string", "description": "Faction ID (e.g., F0)"},
                "changes": {"type": "object", "description": "Partial fields to update"}
            }
        )
        self.memory_manager = memory_manager
        self.vector_store = vector_store
    
    def execute(self, id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        self.memory_manager.update_faction(id, changes)
        faction = self.memory_manager.load_faction(id)
        if faction:
            self.vector_store.index_faction(faction)
        return {"success": True, "faction_id": id}


class FactionQueryTool(Tool):
    """Query factions using semantic search and simple filters."""
    def __init__(self, memory_manager: MemoryManager, vector_store: VectorStore):
        super().__init__(
            name="faction.query",
            description="Search for factions by natural language and optional filters",
            parameters={
                "query": {"type": "string", "description": "Search query", "optional": True},
                "org_type": {"type": "string", "description": "Filter by org type (corporate, government, etc.)", "optional": True},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Require these tags (all must match)", "optional": True},
                "importance": {"type": "string", "description": "Filter by importance (low|medium|high|critical)", "optional": True},
                "name_contains": {"type": "string", "description": "Substring to match in name (case-insensitive)", "optional": True},
                "limit": {"type": "integer", "description": "Max results (default: 5)", "optional": True}
            }
        )
        self.memory_manager = memory_manager
        self.vector_store = vector_store
    
    def execute(
        self,
        query: Optional[str] = None,
        org_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: Optional[str] = None,
        name_contains: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        q = query or "faction"
        # Fetch a few more to allow filtering, then trim
        raw_results = self.vector_store.search(q, entity_types=["faction"], limit=max(limit * 3, 10))
        filtered = []
        for r in raw_results:
            meta = r.get("metadata", {})
            # org_type filter
            if org_type and meta.get("org_type") != org_type:
                continue
            # importance filter
            if importance and meta.get("importance") != importance:
                continue
            # tags filter (all required tags must be present)
            if tags:
                entity_tags = set(meta.get("tags", []) or [])
                if not set(tags).issubset(entity_tags):
                    continue
            # name_contains filter
            if name_contains:
                name_val = (meta.get("name") or "").lower()
                if name_contains.lower() not in name_val:
                    continue
            filtered.append(r)
        # Sort by relevance score desc (vector_store provides distance asc)
        filtered.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)
        trimmed = filtered[:limit]
        formatted = []
        for r in trimmed:
            meta = r.get("metadata", {})
            formatted.append({
                "faction_id": r.get("entity_id"),
                "name": meta.get("name", ""),
                "org_type": meta.get("org_type", ""),
                "importance": meta.get("importance", ""),
                "tags": meta.get("tags", []),
                "relevance_score": round(r.get("relevance_score", 0.0), 2)
            })
        return {"success": True, "results": formatted, "count": len(formatted)}
