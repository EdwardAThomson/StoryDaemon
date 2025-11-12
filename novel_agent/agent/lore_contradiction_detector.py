"""Lore contradiction detection (Phase 7A.4)."""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class LoreContradictionDetector:
    """Detects potential contradictions in world lore using semantic similarity."""
    
    def __init__(self, memory_manager, vector_store, config):
        """Initialize contradiction detector.
        
        Args:
            memory_manager: Memory manager for accessing lore
            vector_store: Vector store for semantic search
            config: Configuration object
        """
        self.memory = memory_manager
        self.vector = vector_store
        self.config = config
        
        # Similarity threshold for flagging potential contradictions
        # Lower distance = more similar (0.0 = identical, 2.0 = very different)
        self.similarity_threshold = config.get('lore.contradiction_threshold', 0.5)
    
    def check_for_contradictions(self, lore_id: str) -> List[str]:
        """Check if a lore item contradicts existing lore.
        
        Args:
            lore_id: ID of lore to check
        
        Returns:
            List of lore IDs that potentially contradict this lore
        """
        # Check if contradiction detection is enabled
        if not self.config.get('generation.enable_lore_tracking', True):
            return []
        
        # Load the lore item
        lore = self.memory.load_lore(lore_id)
        if not lore:
            logger.warning(f"Lore {lore_id} not found")
            return []
        
        # Find similar lore in the same category
        similar_lore = self.vector.find_similar_lore(lore, n_results=10)
        
        # Filter for potential contradictions
        contradictions = []
        for similar in similar_lore:
            # Skip self
            if similar['id'] == lore_id:
                continue
            
            # Check if similarity is high enough to warrant investigation
            distance = similar.get('distance', 1.0)
            if distance < self.similarity_threshold:
                # Load the similar lore to check for actual contradiction
                similar_lore_obj = self.memory.load_lore(similar['id'])
                if similar_lore_obj:
                    # Basic heuristic: if they're very similar but have different types,
                    # or if they're in the same category with high similarity,
                    # flag as potential contradiction
                    if self._might_contradict(lore, similar_lore_obj):
                        contradictions.append(similar['id'])
                        logger.info(f"Potential contradiction: {lore_id} <-> {similar['id']} (distance: {distance:.3f})")
        
        return contradictions
    
    def _might_contradict(self, lore1, lore2) -> bool:
        """Heuristic to determine if two lore items might contradict.
        
        Args:
            lore1: First lore object
            lore2: Second lore object
        
        Returns:
            True if they might contradict, False otherwise
        """
        # Same category is a prerequisite
        if lore1.category != lore2.category:
            return False
        
        # If both are rules or constraints in the same category, they might contradict
        if lore1.lore_type in ['rule', 'constraint'] and lore2.lore_type in ['rule', 'constraint']:
            return True
        
        # If both are capabilities/limitations, they might contradict
        if lore1.lore_type in ['capability', 'limitation'] and lore2.lore_type in ['capability', 'limitation']:
            return True
        
        # Facts are less likely to contradict unless they're very similar
        return False
    
    def update_contradictions(self, lore_id: str):
        """Update contradiction links for a lore item.
        
        Args:
            lore_id: ID of lore to update
        """
        # Find contradictions
        contradictions = self.check_for_contradictions(lore_id)
        
        if contradictions:
            # Load and update the lore
            lore = self.memory.load_lore(lore_id)
            if lore:
                lore.potential_contradictions = contradictions
                self.memory.save_lore(lore)
                
                # Also update the reverse links
                for contradiction_id in contradictions:
                    other_lore = self.memory.load_lore(contradiction_id)
                    if other_lore:
                        if lore_id not in other_lore.potential_contradictions:
                            other_lore.potential_contradictions.append(lore_id)
                            self.memory.save_lore(other_lore)
    
    def get_contradiction_report(self) -> Dict[str, Any]:
        """Generate a report of all lore contradictions.
        
        Returns:
            Dictionary with contradiction information
        """
        all_lore = self.memory.load_all_lore()
        
        # Find all lore with contradictions
        contradicted_lore = [l for l in all_lore if l.potential_contradictions]
        
        # Build contradiction pairs (avoid duplicates)
        pairs = []
        seen = set()
        
        for lore in contradicted_lore:
            for contradiction_id in lore.potential_contradictions:
                # Create a sorted tuple to avoid duplicates
                pair_key = tuple(sorted([lore.id, contradiction_id]))
                if pair_key not in seen:
                    seen.add(pair_key)
                    
                    other_lore = self.memory.load_lore(contradiction_id)
                    if other_lore:
                        pairs.append({
                            'lore_a': {
                                'id': lore.id,
                                'content': lore.content,
                                'type': lore.lore_type,
                                'category': lore.category,
                                'scene': lore.source_scene_id
                            },
                            'lore_b': {
                                'id': other_lore.id,
                                'content': other_lore.content,
                                'type': other_lore.lore_type,
                                'category': other_lore.category,
                                'scene': other_lore.source_scene_id
                            }
                        })
        
        return {
            'total_lore': len(all_lore),
            'contradicted_count': len(contradicted_lore),
            'contradiction_pairs': len(pairs),
            'pairs': pairs
        }
