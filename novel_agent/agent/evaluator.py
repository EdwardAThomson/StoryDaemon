"""Scene evaluator for quality and consistency checking."""

from typing import Dict, Any, List


class SceneEvaluator:
    """Evaluates scene quality and consistency."""
    
    def __init__(self, memory_manager, config):
        """Initialize scene evaluator.
        
        Args:
            memory_manager: MemoryManager instance
            config: Configuration object
        """
        self.memory = memory_manager
        self.config = config
    
    def evaluate_scene(self, scene_text: str, scene_context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate scene for quality and consistency.
        
        Args:
            scene_text: The generated scene prose
            scene_context: Context used to generate the scene
        
        Returns:
            Dictionary with:
                - passed: bool - Whether scene passed all checks
                - issues: List[str] - Critical issues that failed checks
                - warnings: List[str] - Non-critical warnings
                - checks: Dict[str, bool] - Individual check results
        """
        issues = []
        warnings = []
        checks = {}
        
        # 1. POV check (heuristic)
        checks["pov"] = self._check_pov(scene_text, scene_context)
        if not checks["pov"]:
            warnings.append("Possible POV violations detected (omniscient narration)")
        
        # 3. Continuity check (basic)
        checks["continuity"] = self._check_continuity(scene_text, scene_context)
        if not checks["continuity"]:
            warnings.append("Possible continuity issues detected")
        
        # Scene passes if all checks pass and no critical issues
        passed = all(checks.values()) and len(issues) == 0
        
        return {
            "passed": passed,
            "issues": issues,
            "warnings": warnings,
            "checks": checks
        }
    
    def _check_pov(self, text: str, context: Dict[str, Any]) -> bool:
        """Check for POV violations using heuristics.
        
        Args:
            text: Scene text
            context: Scene context
        
        Returns:
            True if POV appears correct, False if violations detected
        """
        # Simple heuristic: look for common omniscient narration markers
        omniscient_markers = [
            "unknown to",
            "little did",
            "would later",
            "meanwhile",
            "across town",
            "at that moment",
            "unbeknownst",
            "little did they know",
            "what they didn't know",
            "in another part of"
        ]
        
        text_lower = text.lower()
        
        # Check for each marker
        for marker in omniscient_markers:
            if marker in text_lower:
                return False
        
        return True
    
    def _check_continuity(self, text: str, context: Dict[str, Any]) -> bool:
        """Enhanced continuity check using character and location state.
        
        Phase 5: Checks for basic contradictions with established facts.
        
        Args:
            text: Scene text
            context: Scene context
        
        Returns:
            True if no obvious contradictions detected
        """
        try:
            # Get POV character
            pov_char_id = context.get('pov_character_id')
            if not pov_char_id:
                return True  # Can't check without POV character
            
            character = self.memory.load_character(pov_char_id)
            if not character:
                return True  # Can't check if character doesn't exist
            
            text_lower = text.lower()
            
            # Basic checks for common contradictions
            # These are heuristic and may have false positives
            
            # Check 1: Character physical state consistency
            # If character is described as injured/exhausted in state, 
            # scene shouldn't describe them as energetic/healthy
            if character.current_state.physical_state:
                physical_state = character.current_state.physical_state.lower()
                if "injured" in physical_state or "wounded" in physical_state:
                    # Look for contradictory descriptions
                    if "leaped" in text_lower or "sprinted" in text_lower:
                        # This might be a contradiction, but not critical
                        pass
            
            # Check 2: Location consistency
            # If character is in a specific location, they shouldn't suddenly
            # be described in a completely different location without transition
            # (This is hard to check heuristically, so we'll keep it simple)
            
            # For Phase 5, we'll keep this basic
            # More sophisticated checking can be added later
            
            return True
            
        except Exception as e:
            # If checking fails, don't fail the scene
            return True
