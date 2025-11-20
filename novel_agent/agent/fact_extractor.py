"""Fact extraction from scene prose for dynamic entity updates."""

import json
import logging
from typing import Dict, Any, List, Optional

from .prompts import format_fact_extraction_prompt

logger = logging.getLogger(__name__)


class FactExtractor:
    """Extracts structured facts from scene prose using LLM."""
    
    def __init__(self, llm_interface, memory_manager, config):
        """Initialize fact extractor.
        
        Args:
            llm_interface: LLM interface for text generation
            memory_manager: Memory manager for accessing entities
            config: Configuration object
        """
        self.llm = llm_interface
        self.memory = memory_manager
        self.config = config
    
    def extract_facts(self, scene_text: str, scene_context: dict) -> dict:
        """Extract structured facts from scene prose.
        
        Args:
            scene_text: The generated scene prose
            scene_context: Context used to write the scene (POV character, location, etc.)
        
        Returns:
            Dictionary with extracted facts:
            {
                "character_updates": [...],
                "location_updates": [...],
                "open_loops_created": [...],
                "open_loops_resolved": [...],
                "relationship_changes": [...]
            }
        """
        try:
            # Build extraction prompt
            prompt = self._build_extraction_prompt(scene_text, scene_context)
            
            # Get max tokens from config
            max_tokens = self.config.get('llm.extractor_max_tokens', 2000)
            
            # Call LLM
            logger.info("Extracting facts from scene prose...")
            response = self.llm.generate(prompt, max_tokens=max_tokens)
            
            # Parse response
            facts = self._parse_extraction_response(response)
            
            logger.info(f"Extracted facts: {len(facts.get('character_updates', []))} character updates, "
                       f"{len(facts.get('location_updates', []))} location updates, "
                       f"{len(facts.get('open_loops_created', []))} loops created, "
                       f"{len(facts.get('open_loops_resolved', []))} loops resolved")
            
            return facts
            
        except Exception as e:
            message = str(e)
            lower_msg = message.lower()
            if "timed out" in lower_msg:
                logger.error(
                    "Fact extraction timed out or was too slow; "
                    "continuing without dynamic entity updates. Details: %s",
                    message,
                )
            else:
                logger.error(
                    "Fact extraction failed; continuing without dynamic entity updates. "
                    "Details: %s",
                    message,
                )
            # Return empty facts on error
            return self._empty_facts()
    
    def _build_extraction_prompt(self, scene_text: str, scene_context: dict) -> str:
        """Build prompt for fact extraction.
        
        Args:
            scene_text: Scene prose
            scene_context: Scene context
        
        Returns:
            Formatted prompt string
        """
        # Get POV character and location IDs
        pov_character_id = scene_context.get('pov_character_id', 'Unknown')
        location_id = scene_context.get('location_id', 'Unknown')
        
        # Format existing open loops
        existing_open_loops = self._format_open_loops()
        
        # Build context dict for prompt
        prompt_context = {
            'scene_text': scene_text,
            'pov_character_id': pov_character_id,
            'location_id': location_id,
            'existing_open_loops': existing_open_loops
        }
        
        return format_fact_extraction_prompt(prompt_context)
    
    def _format_open_loops(self) -> str:
        """Format existing open loops for context.
        
        Returns:
            Formatted string of current open loops
        """
        try:
            loops = self.memory.get_open_loops(status="open")
            
            if not loops:
                return "No open loops currently."
            
            lines = []
            for loop in loops:
                lines.append(f"- **{loop.id}**: {loop.description} (importance: {loop.importance})")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"Error formatting open loops: {e}")
            return "Unable to load open loops."
    
    def _parse_extraction_response(self, response: str) -> dict:
        """Parse LLM response into structured fact data.
        
        Args:
            response: Raw LLM response
        
        Returns:
            Structured facts dictionary
        """
        try:
            # Clean response - remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]  # Remove ```json
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]  # Remove ```
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]  # Remove trailing ```
            cleaned = cleaned.strip()
            
            # Parse JSON
            facts = json.loads(cleaned)
            
            # Validate and normalize structure
            return {
                "character_updates": facts.get("character_updates", []),
                "location_updates": facts.get("location_updates", []),
                "open_loops_created": facts.get("open_loops_created", []),
                "open_loops_resolved": facts.get("open_loops_resolved", []),
                "relationship_changes": facts.get("relationship_changes", [])
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            logger.error(f"Response was: {response[:500]}...")
            raise
    
    def _empty_facts(self) -> dict:
        """Return empty facts structure.
        
        Returns:
            Empty facts dictionary
        """
        return {
            "character_updates": [],
            "location_updates": [],
            "open_loops_created": [],
            "open_loops_resolved": [],
            "relationship_changes": []
        }
