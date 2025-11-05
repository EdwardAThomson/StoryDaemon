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
        
        # 1. Word count check
        word_count = len(scene_text.split())
        min_words = self.config.get('generation.target_word_count_min', 500)
        max_words = self.config.get('generation.target_word_count_max', 900)
        
        checks["word_count"] = min_words <= word_count <= max_words
        if not checks["word_count"]:
            issues.append(
                f"Word count {word_count} outside target range {min_words}-{max_words}"
            )
        
        # 2. POV check (heuristic)
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
        """Basic continuity check.
        
        For Phase 4, this is a placeholder that always returns True.
        Phase 5 will add more sophisticated continuity checking.
        
        Args:
            text: Scene text
            context: Scene context
        
        Returns:
            True (always passes for now)
        """
        # Placeholder for Phase 5
        # Future: Check for contradictions with established facts
        # Future: Verify character consistency
        # Future: Check location consistency
        return True
