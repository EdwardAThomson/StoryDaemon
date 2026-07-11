"""Entity updater for applying extracted facts to memory."""

import logging
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from novel_agent.memory.entities import OpenLoop, RelationshipGraph, HistoryEntry, RelationshipHistoryEntry

logger = logging.getLogger(__name__)


class EntityUpdater:
    """Applies extracted facts to memory entities with history tracking."""
    
    def __init__(self, memory_manager, config):
        """Initialize entity updater.
        
        Args:
            memory_manager: Memory manager for entity operations
            config: Configuration object
        """
        self.memory = memory_manager
        self.config = config
        self._pov_character_name = None  # Track POV character name for detection
    
    def apply_updates(self, facts: dict, tick: int, scene_id: str, scene_context: dict = None) -> dict:
        """Apply extracted facts to entities.
        
        Args:
            facts: Extracted facts from FactExtractor
            tick: Current tick number
            scene_id: Scene ID for history tracking
            scene_context: Optional scene context with pov_character_id and pov_character_name
        
        Returns:
            Statistics dictionary:
            {
                "characters_updated": int,
                "locations_updated": int,
                "loops_created": int,
                "loops_deduped": int,
                "loops_capped": int,
                "loops_resolved": int,
                "relationships_updated": int,
                "characters_created": int
            }
        """
        stats = {
            "characters_updated": 0,
            "locations_updated": 0,
            "loops_created": 0,
            "loops_deduped": 0,
            "loops_capped": 0,
            "loops_resolved": 0,
            "relationships_updated": 0,
            "characters_created": 0
        }
        
        try:
            # 1. Update characters (with POV switch detection)
            for char_update in facts.get("character_updates", []):
                result = self._update_character(char_update, tick, scene_id, scene_context)
                if result == "updated":
                    stats["characters_updated"] += 1
                elif result == "created":
                    stats["characters_created"] += 1
            
            # 2. Update locations
            for loc_update in facts.get("location_updates", []):
                if self._update_location(loc_update, tick, scene_id):
                    stats["locations_updated"] += 1
            
            # 3. Create open loops (Phase 3, Slice 0 of the interleaving design:
            # creation hygiene, gated by coherence.loop_dedup). The per-tick cap
            # runs first, then each survivor is fuzzy-deduped against existing
            # open loops inside _create_open_loop.
            new_loops, capped = self._cap_new_loops(facts.get("open_loops_created", []))
            stats["loops_capped"] = capped
            for loop_data in new_loops:
                result = self._create_open_loop(loop_data, tick, scene_id)
                if result == "created":
                    stats["loops_created"] += 1
                elif result == "duplicate":
                    stats["loops_deduped"] += 1
            
            # 4. Resolve open loops
            for loop_id in facts.get("open_loops_resolved", []):
                if self._resolve_open_loop(loop_id, tick, scene_id):
                    stats["loops_resolved"] += 1
            
            # 5. Update relationships
            for rel_change in facts.get("relationship_changes", []):
                if self._update_relationship(rel_change, tick, scene_id):
                    stats["relationships_updated"] += 1
            
            logger.info(f"Applied updates: {stats}")
            
        except Exception as e:
            logger.error(f"Error applying updates: {e}")
        
        return stats
    
    def _update_character(self, update: dict, tick: int, scene_id: str, scene_context: dict = None) -> str:
        """Update character with history tracking, detecting POV switches.
        
        Args:
            update: Character update dict with id and changes
            tick: Current tick
            scene_id: Current scene ID
            scene_context: Optional scene context with pov_character_id and pov_character_name
        
        Returns:
            "updated" if character was updated, "created" if new character was created, "" if nothing happened
        """
        try:
            char_id = update["id"]
            changes = update["changes"]
            
            # Load existing character
            character = self.memory.load_character(char_id)
            if not character:
                logger.warning(f"Character {char_id} not found, skipping update")
                return ""
            
            # POV Switch Detection: Check if this is actually a different character
            # This happens when the story switches POV but the LLM still uses C0
            if scene_context and char_id == scene_context.get('pov_character_id'):
                pov_name = scene_context.get('pov_character_name', '')
                if pov_name and pov_name != character.display_name and pov_name != character.full_name:
                    # POV character name doesn't match - this is a different character!
                    logger.info(f"POV switch detected: '{character.full_name}' -> '{pov_name}'")
                    logger.info(f"Creating new character entity for '{pov_name}'")
                    
                    # Create new character with the POV character's name
                    new_char_id = self._create_character_from_pov(pov_name, changes, tick, scene_id)
                    if new_char_id:
                        # Update the scene context to use the new character ID
                        # Note: This won't affect the current scene, but will help future scenes
                        logger.info(f"Created new character {new_char_id} for '{pov_name}'")
                        return "created"
                    else:
                        logger.error(f"Failed to create new character for '{pov_name}'")
                        return ""
            
            # Build history entry
            history_changes = {}
            
            # Apply changes to current_state
            for field, new_value in changes.items():
                if new_value is None:
                    continue
                
                # Get current value
                old_value = getattr(character.current_state, field, None)
                
                if field in ["inventory", "goals", "beliefs"]:
                    # List fields - append new items
                    current = getattr(character.current_state, field, [])
                    if isinstance(new_value, list):
                        added_items = []
                        for item in new_value:
                            if item not in current:
                                current.append(item)
                                added_items.append(item)
                        if added_items:
                            setattr(character.current_state, field, current)
                            history_changes[field] = f"added: {added_items}"
                else:
                    # Simple fields - replace
                    setattr(character.current_state, field, new_value)
                    history_changes[field] = {"old": old_value, "new": new_value}
            
            # Add to history if there were changes
            if history_changes:
                history_entry = HistoryEntry(
                    tick=tick,
                    scene_id=scene_id,
                    changes=history_changes,
                    summary=f"Updated in scene {scene_id}"
                )
                character.history.append(history_entry)
                
                # Save character
                self.memory.save_character(character)
                logger.debug(f"Updated character {char_id}: {list(history_changes.keys())}")
                return "updated"
            
            return ""
            
        except Exception as e:
            logger.error(f"Error updating character: {e}")
            return ""
    
    def _create_character_from_pov(self, pov_name: str, changes: dict, tick: int, scene_id: str) -> str:
        """Create a new character entity from POV character information.
        
        Args:
            pov_name: Name of the POV character
            changes: Character changes from fact extraction
            tick: Current tick
            scene_id: Current scene ID
        
        Returns:
            New character ID if successful, None otherwise
        """
        try:
            from novel_agent.memory.entities import Character, CurrentState, Personality
            
            # Parse name
            parts = pov_name.strip().split()
            first_name = parts[0] if parts else pov_name
            family_name = ' '.join(parts[1:]) if len(parts) > 1 else ""
            
            # Generate new character ID
            new_char_id = self.memory.generate_id("character")
            
            # Create character with initial state from changes
            current_state = CurrentState()
            if changes:
                for field, value in changes.items():
                    if value is not None and hasattr(current_state, field):
                        setattr(current_state, field, value)
            
            character = Character(
                id=new_char_id,
                first_name=first_name,
                family_name=family_name,
                role="protagonist",  # Assume POV character is protagonist
                current_state=current_state,
                personality=Personality()
            )
            
            # Save character
            self.memory.save_character(character)
            logger.info(f"Created new character {new_char_id}: {character.full_name}")
            
            # Set as active character (this will be the new POV)
            self.memory.set_active_character(new_char_id)
            
            return new_char_id
            
        except Exception as e:
            logger.error(f"Error creating character from POV: {e}")
            return None
    
    def _update_location(self, update: dict, tick: int, scene_id: str) -> bool:
        """Update location with history tracking.
        
        Args:
            update: Location update dict with id and changes
            tick: Current tick
            scene_id: Current scene ID
        
        Returns:
            True if updated successfully
        """
        try:
            loc_id = update["id"]
            changes = update["changes"]
            
            # Load existing location
            location = self.memory.load_location(loc_id)
            if not location:
                logger.warning(f"Location {loc_id} not found, skipping update")
                return False
            
            # Build history entry
            history_changes = {}
            
            # Apply changes
            for field, new_value in changes.items():
                if new_value is None:
                    continue
                
                old_value = getattr(location, field, None)
                
                if field == "features":
                    # List field - append new features
                    current = getattr(location, field, [])
                    if isinstance(new_value, list):
                        added_items = []
                        for item in new_value:
                            if item not in current:
                                current.append(item)
                                added_items.append(item)
                        if added_items:
                            setattr(location, field, current)
                            history_changes[field] = f"added: {added_items}"
                else:
                    # Simple fields - replace
                    setattr(location, field, new_value)
                    history_changes[field] = {"old": old_value, "new": new_value}
            
            # Add to history if there were changes
            if history_changes:
                history_entry = HistoryEntry(
                    tick=tick,
                    scene_id=scene_id,
                    changes=history_changes,
                    summary=f"Updated in scene {scene_id}"
                )
                location.history.append(history_entry)
                
                # Save location
                self.memory.save_location(location)
                logger.debug(f"Updated location {loc_id}: {list(history_changes.keys())}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating location: {e}")
            return False
    
    def _create_open_loop(self, loop_data: dict, tick: int, scene_id: str) -> str:
        """Create new open loop, deduplicating against existing open loops.

        Phase 3 (Slice 0 of the interleaving design): before adding, the new
        description is fuzzy-matched against every existing OPEN loop (see
        _find_duplicate_loop); a match skips creation so near-identical
        questions stop piling up (live runs re-minted "will Aris stay silent"
        three times over). Gated by coherence.loop_dedup.

        Args:
            loop_data: Loop data dict
            tick: Current tick
            scene_id: Current scene ID

        Returns:
            "created" on success, "duplicate" when dedup skipped creation,
            "" on error
        """
        try:
            duplicate_of = self._find_duplicate_loop(loop_data.get("description", ""))
            if duplicate_of:
                # Warning level so dedup skips are visible in run artifacts (the
                # 2026-07-11 validation flagged info-level drops as unobservable).
                logger.warning(f"Skipping open loop (duplicate of {duplicate_of}): "
                               f"{loop_data.get('description', '')}")
                return "duplicate"

            loop_id = self.memory.generate_id("open_loop")
            
            open_loop = OpenLoop(
                id=loop_id,
                created_in_scene=scene_id,
                status="open",
                category=loop_data.get("category", ""),
                description=loop_data["description"],
                importance=loop_data.get("importance", "medium"),
                related_characters=loop_data.get("related_characters", []),
                related_locations=loop_data.get("related_locations", []),
                notes="",
                resolved_in_scene=None,
                resolution_summary=None
            )
            
            self.memory.add_open_loop(open_loop)
            logger.info(f"Created open loop {loop_id}: {loop_data['description']}")
            return "created"

        except Exception as e:
            logger.error(f"Error creating open loop: {e}")
            return ""

    def _find_duplicate_loop(self, description: str) -> Optional[str]:
        """The ID of an existing OPEN loop this description duplicates, or None.

        Phase 3 (Slice 0 of the interleaving design): purely deterministic, no
        LLM. difflib.SequenceMatcher ratio on case-insensitive descriptions,
        against open loops only (a resolved loop's question may legitimately
        reopen). Threshold from coherence.loop_dedup_threshold (default 0.8:
        light rewordings of the same question land well above it, distinct
        questions sharing sentence scaffolding land below it). Returns the
        best match at or above the threshold. Never raises; any problem means
        "no duplicate" so creation proceeds (graceful degradation).
        """
        try:
            if not self.config.get('coherence.loop_dedup', True):
                return None
            threshold = float(self.config.get('coherence.loop_dedup_threshold', 0.8))
            text = (description or "").strip().lower()
            if not text:
                return None

            best_id, best_ratio = None, 0.0
            for loop in self.memory.load_open_loops():
                if getattr(loop, "status", "open") != "open":
                    continue
                existing = (getattr(loop, "description", "") or "").strip().lower()
                if not existing:
                    continue
                ratio = SequenceMatcher(None, text, existing).ratio()
                if ratio >= threshold and ratio > best_ratio:
                    best_id, best_ratio = loop.id, ratio
            return best_id
        except Exception as e:
            logger.warning(f"Loop dedup check failed; creating without dedup: {e}")
            return None

    def _cap_new_loops(self, loop_datas: List[dict]) -> Tuple[List[dict], int]:
        """Cap the per-tick loop creations, dropping lowest-importance first.

        Phase 3 (Slice 0 of the interleaving design): one scene must not flood
        the ledger (denouement samples minted 3-5 hook loops each). Cap from
        coherence.loop_creation_cap (default 4; None or 0 disables). Kept
        entries preserve their original order; ties on importance keep the
        earlier entry. Returns (kept, dropped_count). Never raises; any
        problem keeps the full list (graceful degradation).
        """
        try:
            if not self.config.get('coherence.loop_dedup', True):
                return loop_datas, 0
            cap = int(self.config.get('coherence.loop_creation_cap', 4) or 0)
            if cap <= 0 or len(loop_datas) <= cap:
                return loop_datas, 0

            rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}

            def importance_rank(data) -> int:
                value = data.get("importance", "medium") if isinstance(data, dict) else ""
                return rank.get(str(value).lower(), 2)

            indexed = list(enumerate(loop_datas))
            keep = sorted(indexed, key=lambda p: (-importance_rank(p[1]), p[0]))[:cap]
            keep_indices = {i for i, _ in keep}
            kept = [data for i, data in indexed if i in keep_indices]
            for i, data in indexed:
                if i not in keep_indices:
                    desc = data.get("description", "") if isinstance(data, dict) else str(data)
                    # Warning level so cap drops are visible in run artifacts (the
                    # 2026-07-11 validation flagged info-level drops as unobservable).
                    logger.warning(f"Dropping over-cap open loop (cap {cap}, lowest "
                                   f"importance first): {desc}")
            return kept, len(loop_datas) - len(kept)
        except Exception as e:
            logger.warning(f"Loop creation cap skipped: {e}")
            return loop_datas, 0

    def _resolve_open_loop(self, loop_id: str, tick: int, scene_id: str) -> bool:
        """Mark open loop as resolved.
        
        Args:
            loop_id: Loop ID to resolve
            tick: Current tick
            scene_id: Current scene ID
        
        Returns:
            True if resolved successfully
        """
        try:
            # Use existing memory manager method
            self.memory.resolve_open_loop(
                loop_id=loop_id,
                scene_id=scene_id,
                summary=f"Resolved in scene {scene_id}"
            )
            logger.info(f"Resolved open loop {loop_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error resolving open loop: {e}")
            return False
    
    def _update_relationship(self, change: dict, tick: int, scene_id: str) -> bool:
        """Update relationship between characters.
        
        Args:
            change: Relationship change dict
            tick: Current tick
            scene_id: Current scene ID
        
        Returns:
            True if updated successfully
        """
        try:
            char_a = change["character_a"]
            char_b = change["character_b"]
            changes = change["changes"]
            
            # Validate both characters exist before creating/updating relationship
            char_a_exists = self.memory.load_character(char_a) is not None
            char_b_exists = self.memory.load_character(char_b) is not None
            
            if not char_a_exists:
                logger.warning(f"Character {char_a} not found, skipping relationship update with {char_b}")
                return False
            
            if not char_b_exists:
                logger.warning(f"Character {char_b} not found, skipping relationship update with {char_a}")
                return False
            
            # Get existing relationship
            relationship = self.memory.get_relationship_between(char_a, char_b)
            
            if not relationship:
                # Create new relationship
                rel_id = self.memory.generate_id("relationship")
                relationship = RelationshipGraph(
                    id=rel_id,
                    character_a=char_a,
                    character_b=char_b,
                    relationship_type="",
                    status="neutral",
                    perspective_a="",
                    perspective_b="",
                    intensity=5,
                    history=[]
                )
            
            # Track what changed
            history_changes = {}
            
            # Apply changes
            for field, new_value in changes.items():
                if new_value is None:
                    continue
                
                old_value = getattr(relationship, field, None)
                setattr(relationship, field, new_value)
                history_changes[field] = {"old": old_value, "new": new_value}
            
            # Add history entry if there were changes
            if history_changes:
                history_entry = RelationshipHistoryEntry(
                    tick=tick,
                    scene_id=scene_id,
                    event=f"Relationship updated in scene {scene_id}",
                    status_change=changes.get("status")
                )
                relationship.history.append(history_entry)
                relationship.updated_at = datetime.utcnow().isoformat() + "Z"
                
                # Save relationship
                # Check if it's new or existing
                existing = self.memory.get_relationship_between(char_a, char_b)
                if existing:
                    self.memory.update_relationship(relationship.id, history_changes)
                else:
                    self.memory.add_relationship(relationship)
                
                logger.debug(f"Updated relationship {char_a}-{char_b}: {list(history_changes.keys())}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating relationship: {e}")
            return False
