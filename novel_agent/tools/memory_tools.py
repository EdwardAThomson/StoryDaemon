"""Memory-related tools for the agent."""

from pathlib import Path
from typing import Dict, Any, List, Optional

from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..memory.entities import (
    Character, Location, RelationshipGraph,
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
                    "items": {"type": "string", "enum": ["character", "location", "scene"]},
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
    
    def __init__(self, memory_manager: MemoryManager, vector_store: VectorStore):
        super().__init__(
            name="character.generate",
            description="Create a new character with initial attributes",
            parameters={
                "name": {
                    "type": "string",
                    "description": "Character name"
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
    
    def execute(self, name: str, role: str, description: str,
                traits: Optional[List[str]] = None, 
                goals: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new character.
        
        Args:
            name: Character name
            role: Character role
            description: Character description
            traits: Optional personality traits
            goals: Optional initial goals
        
        Returns:
            Success status and character ID
        """
        # Generate ID
        character_id = self.memory_manager.generate_id("character")
        
        # Create character entity
        character = Character(
            id=character_id,
            name=name,
            role=role,
            description=description,
            personality=Personality(core_traits=traits or []),
            current_state=CurrentState(goals=goals or [])
        )
        
        # Save to disk
        self.memory_manager.save_character(character)
        
        # Index in vector store
        self.vector_store.index_character(character)
        
        return {
            "success": True,
            "character_id": character_id,
            "name": name
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
