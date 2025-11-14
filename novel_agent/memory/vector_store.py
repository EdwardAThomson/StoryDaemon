"""Vector store for semantic search using ChromaDB."""

from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings

from .entities import Character, Location, Scene, Lore, Faction


class VectorStore:
    """Manages semantic search using ChromaDB."""
    
    def __init__(self, project_path: Path):
        """Initialize vector store.
        
        Args:
            project_path: Path to the novel project directory
        """
        self.project_path = Path(project_path)
        self.index_path = self.project_path / "memory" / "index"
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.index_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize collections
        self.characters_collection = self.client.get_or_create_collection(
            name="characters",
            metadata={"description": "Character entities"}
        )
        self.locations_collection = self.client.get_or_create_collection(
            name="locations",
            metadata={"description": "Location entities"}
        )
        self.scenes_collection = self.client.get_or_create_collection(
            name="scenes",
            metadata={"description": "Scene summaries"}
        )
        self.lore_collection = self.client.get_or_create_collection(
            name="lore",
            metadata={"description": "World rules and lore (Phase 7A.4)"}
        )
        self.factions_collection = self.client.get_or_create_collection(
            name="factions",
            metadata={"description": "Faction/organization entities"}
        )
    
    # ========================================================================
    # Indexing Methods
    # ========================================================================
    
    def index_character(self, character: Character):
        """Add or update character in vector index.
        
        Args:
            character: Character entity to index
        """
        # Build searchable text from character attributes
        text_parts = [
            f"Name: {character.full_name}",
            f"First name: {character.first_name}",
            f"Family name: {character.family_name}" if character.family_name else "",
            f"Title: {character.title}" if character.title else "",
            f"Nicknames: {', '.join(character.nicknames)}" if character.nicknames else "",
            f"Role: {character.role}",
            f"Description: {character.description}",
            f"Traits: {', '.join(character.personality.core_traits)}" if character.personality.core_traits else "",
            f"Fears: {', '.join(character.personality.fears)}" if character.personality.fears else "",
            f"Desires: {', '.join(character.personality.desires)}" if character.personality.desires else "",
            f"Backstory: {character.backstory}",
            f"Goals: {', '.join(character.current_state.goals)}" if character.current_state.goals else "",
        ]
        
        text = " ".join([part for part in text_parts if part])
        
        # Metadata for filtering
        metadata = {
            "entity_type": "character",
            "name": character.full_name,
            "first_name": character.first_name,
            "role": character.role,
            "updated_at": character.updated_at
        }
        
        # Upsert to collection
        self.characters_collection.upsert(
            ids=[character.id],
            documents=[text],
            metadatas=[metadata]
        )
    
    def index_location(self, location: Location):
        """Add or update location in vector index.
        
        Args:
            location: Location entity to index
        """
        # Build searchable text
        text_parts = [
            f"Name: {location.name}",
            f"Aliases: {', '.join(location.aliases)}" if location.aliases else "",
            f"Description: {location.description}",
            f"Atmosphere: {location.atmosphere}",
            f"Visual: {location.sensory_details.visual}" if location.sensory_details.visual else "",
            f"Auditory: {location.sensory_details.auditory}" if location.sensory_details.auditory else "",
            f"Olfactory: {location.sensory_details.olfactory}" if location.sensory_details.olfactory else "",
            f"Features: {', '.join(location.features)}" if location.features else "",
            f"Significance: {location.significance}",
        ]
        
        text = " ".join([part for part in text_parts if part])
        
        metadata = {
            "entity_type": "location",
            "name": location.name,
            "updated_at": location.updated_at
        }
        
        self.locations_collection.upsert(
            ids=[location.id],
            documents=[text],
            metadatas=[metadata]
        )
    
    def index_scene(self, scene: Scene):
        """Add or update scene in vector index.
        
        Args:
            scene: Scene entity to index
        """
        # Build searchable text from scene summary and events
        text_parts = [
            f"Title: {scene.title}",
            f"Summary: {' '.join(scene.summary)}" if scene.summary else "",
            f"Key Events: {', '.join(scene.key_events)}" if scene.key_events else "",
            f"Emotional Beats: {', '.join(scene.emotional_beats)}" if scene.emotional_beats else "",
        ]
        
        text = " ".join([part for part in text_parts if part])
        
        metadata = {
            "entity_type": "scene",
            "tick": scene.tick,
            "pov_character_id": scene.pov_character_id,
            "location_id": scene.location_id,
            "created_at": scene.created_at
        }
        
        self.scenes_collection.upsert(
            ids=[scene.id],
            documents=[text],
            metadatas=[metadata]
        )

    def index_faction(self, faction: Faction):
        """Add or update faction in vector index.
        
        Args:
            faction: Faction entity to index
        """
        text_parts = [
            f"Name: {faction.name}",
            f"Type: {faction.org_type}",
            f"Summary: {faction.summary}",
            f"Mandate: {', '.join(faction.mandate_objectives)}" if faction.mandate_objectives else "",
            f"Influence: {', '.join(faction.influence_domains)}" if faction.influence_domains else "",
            f"Assets: {', '.join(faction.assets_resources)}" if faction.assets_resources else "",
            f"Methods: {', '.join(faction.methods_tactics)}" if faction.methods_tactics else "",
            f"Tags: {', '.join(faction.tags)}" if faction.tags else "",
            f"Importance: {faction.importance}",
        ]
        text = " ".join([p for p in text_parts if p])
        metadata = {
            "entity_type": "faction",
            "name": faction.name,
            "org_type": faction.org_type,
            "importance": faction.importance,
            "tags": faction.tags,
            "updated_at": faction.updated_at,
        }
        self.factions_collection.upsert(
            ids=[faction.id],
            documents=[text],
            metadatas=[metadata]
        )
    
    # ========================================================================
    # Search Methods
    # ========================================================================
    
    def search_characters(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant characters.
        
        Args:
            query: Natural language search query
            limit: Maximum number of results
        
        Returns:
            List of search results with id, distance, metadata, and document
        """
        results = self.characters_collection.query(
            query_texts=[query],
            n_results=limit
        )
        
        return self._format_results(results)
    
    def search_locations(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant locations.
        
        Args:
            query: Natural language search query
            limit: Maximum number of results
        
        Returns:
            List of search results
        """
        results = self.locations_collection.query(
            query_texts=[query],
            n_results=limit
        )
        
        return self._format_results(results)
    
    def search_scenes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant scenes.
        
        Args:
            query: Natural language search query
            limit: Maximum number of results
        
        Returns:
            List of search results
        """
        results = self.scenes_collection.query(
            query_texts=[query],
            n_results=limit
        )
        
        return self._format_results(results)
    
    def search(self, query: str, entity_types: Optional[List[str]] = None, 
               limit: int = 5) -> List[Dict[str, Any]]:
        """Search across multiple entity types.
        
        Args:
            query: Natural language search query
            entity_types: List of entity types to search (character, location, scene)
                         If None, searches all types
            limit: Maximum number of results per type
        
        Returns:
            List of search results sorted by relevance
        """
        if entity_types is None:
            entity_types = ["character", "location", "scene", "faction"]
        
        all_results = []
        
        if "character" in entity_types:
            char_results = self.search_characters(query, limit)
            all_results.extend(char_results)
        
        if "location" in entity_types:
            loc_results = self.search_locations(query, limit)
            all_results.extend(loc_results)
        
        if "scene" in entity_types:
            scene_results = self.search_scenes(query, limit)
            all_results.extend(scene_results)
        if "faction" in entity_types:
            fac_results = self.search_factions(query, limit)
            all_results.extend(fac_results)
        
        # Sort by distance (lower is better)
        all_results.sort(key=lambda x: x["distance"])
        
        return all_results[:limit]

    def search_factions(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant factions.
        
        Args:
            query: Natural language search query
            limit: Maximum number of results
        
        Returns:
            List of search results
        """
        results = self.factions_collection.query(
            query_texts=[query],
            n_results=limit
        )
        return self._format_results(results)
    
    def _format_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format ChromaDB results into a consistent structure.
        
        Args:
            results: Raw results from ChromaDB query
        
        Returns:
            List of formatted result dictionaries
        """
        formatted = []
        
        # ChromaDB returns results in nested lists
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]
        
        for i in range(len(ids)):
            formatted.append({
                "entity_id": ids[i],
                "distance": distances[i],
                "relevance_score": 1.0 - min(distances[i], 1.0),  # Convert distance to 0-1 score
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "snippet": documents[i] if i < len(documents) else ""
            })
        
        return formatted
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def delete_entity(self, entity_id: str):
        """Delete an entity from all collections.
        
        Args:
            entity_id: Entity ID to delete
        """
        # Try to delete from all collections (will silently fail if not present)
        try:
            self.characters_collection.delete(ids=[entity_id])
        except:
            pass
        
        try:
            self.locations_collection.delete(ids=[entity_id])
        except:
            pass
        
        try:
            self.scenes_collection.delete(ids=[entity_id])
        except:
            pass
    
    def get_collection_counts(self) -> Dict[str, int]:
        """Get count of entities in each collection.
        
        Returns:
            Dictionary with counts for each entity type
        """
        return {
            "characters": self.characters_collection.count(),
            "locations": self.locations_collection.count(),
            "scenes": self.scenes_collection.count(),
            "lore": self.lore_collection.count(),
            "factions": self.factions_collection.count(),
        }
    
    # ========================================================================
    # Lore Methods (Phase 7A.4)
    # ========================================================================
    
    def index_lore(self, lore: Lore):
        """Add or update lore in vector index (Phase 7A.4).
        
        Args:
            lore: Lore entity to index
        """
        # Build searchable text from lore attributes
        text_parts = [
            f"Type: {lore.lore_type}",
            f"Category: {lore.category}",
            f"Content: {lore.content}",
            f"Tags: {', '.join(lore.tags)}" if lore.tags else "",
            f"Importance: {lore.importance}"
        ]
        
        searchable_text = "\n".join([p for p in text_parts if p])
        
        # Prepare metadata
        metadata = {
            "type": "lore",
            "lore_type": lore.lore_type,
            "category": lore.category,
            "importance": lore.importance,
            "source_scene": lore.source_scene_id,
            "tick": lore.tick
        }
        
        # Upsert to collection
        self.lore_collection.upsert(
            ids=[lore.id],
            documents=[searchable_text],
            metadatas=[metadata]
        )
    
    def search_lore(
        self,
        query: str,
        n_results: int = 5,
        category: Optional[str] = None,
        lore_type: Optional[str] = None,
        importance: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for relevant lore (Phase 7A.4).
        
        Args:
            query: Search query
            n_results: Number of results to return
            category: Optional category filter
            lore_type: Optional type filter
            importance: Optional importance filter
        
        Returns:
            List of lore search results with metadata
        """
        # Build where filter
        where = {}
        if category:
            where["category"] = category
        if lore_type:
            where["lore_type"] = lore_type
        if importance:
            where["importance"] = importance
        
        # Search
        results = self.lore_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where if where else None
        )
        
        # Format results
        formatted_results = []
        if results and results['ids'] and results['ids'][0]:
            for i, lore_id in enumerate(results['ids'][0]):
                formatted_results.append({
                    "id": lore_id,
                    "distance": results['distances'][0][i] if 'distances' in results else None,
                    "metadata": results['metadatas'][0][i] if 'metadatas' in results else {},
                    "document": results['documents'][0][i] if 'documents' in results else ""
                })
        
        return formatted_results
    
    def find_similar_lore(self, lore: Lore, n_results: int = 5) -> List[Dict[str, Any]]:
        """Find lore similar to the given lore (for contradiction detection).
        
        Args:
            lore: Lore entity to find similar items for
            n_results: Number of results to return
        
        Returns:
            List of similar lore items
        """
        # Use the lore content as query
        return self.search_lore(
            query=lore.content,
            n_results=n_results + 1,  # +1 because it might return itself
            category=lore.category  # Search within same category
        )
