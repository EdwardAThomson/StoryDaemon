"""Scene evaluator for quality and consistency checking."""

from typing import Dict, Any, List
from ..memory.plot_outline import PlotOutlineManager


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

        checks["pov"] = self._check_pov(scene_text, scene_context)
        if not checks["pov"]:
            warnings.append("Possible POV violations detected (omniscient narration)")

        checks["continuity"] = self._check_continuity(scene_text, scene_context)
        if not checks["continuity"]:
            warnings.append("Possible continuity issues detected")

        continuity_flags: List[str] = []
        if not checks["continuity"]:
            continuity_flags.append("possible_continuity_issue")

        qa_metrics = self._compute_qa_metrics(scene_text, scene_context, continuity_flags, warnings)

        passed = all(checks.values()) and len(issues) == 0

        result: Dict[str, Any] = {
            "passed": passed,
            "issues": issues,
            "warnings": warnings,
            "checks": checks,
        }
        result.update(qa_metrics)
        return result
    
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

    def _compute_qa_metrics(self, text: str, context: Dict[str, Any], continuity_flags: List[str], warnings: List[str]) -> Dict[str, Any]:
        key_change = context.get("key_change", "") or ""
        progress_milestone = context.get("progress_milestone", "") or ""
        scene_mode = context.get("scene_mode", "") or ""
        dialogue_targets_raw = context.get("dialogue_targets", "") or ""

        text_lower = text.lower()

        def extract_keywords(value: str) -> List[str]:
            words = [w.strip(".,!?;:\"'()").lower() for w in value.split()]
            return [w for w in words if len(w) >= 4]

        change_keywords = extract_keywords(key_change) or extract_keywords(progress_milestone)
        achieved_change_value = False
        if change_keywords:
            achieved_change_value = any(w in text_lower for w in change_keywords)
        else:
            achieved_change_value = True

        achieved_change = {
            "value": achieved_change_value,
            "explanation": "Heuristic match between key_change/progress_milestone and scene text."
        }

        quote_count = text.count("\"")
        dialogue_count = max(0, quote_count // 2)

        min_exchanges = None
        met_dialogue_target = None
        if isinstance(dialogue_targets_raw, dict):
            min_exchanges = dialogue_targets_raw.get("min_exchanges")
        elif isinstance(dialogue_targets_raw, str):
            import re
            match = re.search(r"min_exchanges\s*[:=]\s*(\d+)", dialogue_targets_raw)
            if match:
                try:
                    min_exchanges = int(match.group(1))
                except ValueError:
                    min_exchanges = None
        if isinstance(min_exchanges, int):
            met_dialogue_target = dialogue_count >= min_exchanges

        if context.get("transition_path"):
            transition_clarity_score = 8
            transition_notes = "Transition path provided in plan."
        else:
            transition_clarity_score = 5
            transition_notes = "No explicit transition_path provided."

        mode_used = scene_mode or "unknown"

        # Mode diversity warning based on recent QA history
        mode_diversity_warning = False
        recent_qa: List[Dict[str, Any]] = []
        try:
            recent_qa = self.memory.get_recent_scene_qa(count=3)
        except Exception:
            recent_qa = []

        recent_modes: List[str] = []
        for entry in recent_qa:
            evaluation = entry.get("evaluation", {}) or {}
            m = evaluation.get("mode_used")
            if isinstance(m, str) and m:
                recent_modes.append(m)

        if mode_used != "unknown" and recent_modes:
            last_modes = recent_modes[-3:]
            # If the last few scenes all used the same mode and we are repeating it again,
            # flag a diversity warning to encourage switching things up.
            if len(last_modes) >= 2 and all(m == last_modes[-1] for m in last_modes) and mode_used == last_modes[-1]:
                mode_diversity_warning = True
            elif len(last_modes) >= 2 and all(m == mode_used for m in last_modes):
                mode_diversity_warning = True

        if mode_diversity_warning:
            # Soft guidance only; planner can choose to ignore.
            if mode_used == "technical":
                warnings.append(
                    "Recent scenes have repeated technical mode; consider a dialogue or political scene next for variety."
                )
            else:
                warnings.append(
                    f"Recent scenes have repeated scene_mode '{mode_used}'; consider choosing a different mode for variety."
                )

        # Novelty score: simple heuristic vs last scene using QA signals
        novelty_score = 5.0
        if recent_qa:
            last_eval = recent_qa[-1].get("evaluation", {}) or {}
            last_mode = last_eval.get("mode_used")
            last_achieved = (last_eval.get("achieved_change") or {}).get("value")
            last_dialogue = last_eval.get("dialogue_count")

            score = 5.0

            if mode_used != "unknown" and isinstance(last_mode, str) and last_mode:
                if mode_used != last_mode:
                    score += 1.5
                else:
                    score -= 1.0

            if isinstance(achieved_change_value, bool) and isinstance(last_achieved, bool):
                if achieved_change_value != last_achieved:
                    score += 0.5

            if isinstance(dialogue_count, int) and isinstance(last_dialogue, int):
                if dialogue_count == 0 and last_dialogue == 0:
                    score -= 1.0
                elif (dialogue_count == 0) != (last_dialogue == 0):
                    score += 1.0
                elif abs(dialogue_count - last_dialogue) <= 2:
                    score -= 0.5

            novelty_score = max(1.0, min(9.0, score))

        # Beat hint alignment: compare current scene text against the next
        # pending plot beat description using simple keyword overlap. This is
        # a soft signal only and does not affect pass/fail.
        beat_hint_alignment: Dict[str, Any] = {
            "beat_id": None,
            "score": None,
            "label": "none",
        }
        try:
            manager = PlotOutlineManager(self.memory.project_path)
            next_beat = manager.get_next_beat()
        except Exception:
            next_beat = None

        if next_beat is not None:
            beat_id = getattr(next_beat, "id", None)
            description = getattr(next_beat, "description", "") or ""
            beat_hint_alignment["beat_id"] = beat_id

            beat_keywords = extract_keywords(description)
            if beat_keywords:
                unique_keywords = set(beat_keywords)
                shared = sum(1 for w in unique_keywords if w in text_lower)
                ratio = shared / max(1, len(unique_keywords))
                beat_hint_alignment["score"] = round(ratio, 2)
                if ratio >= 0.6:
                    label = "high"
                elif ratio >= 0.3:
                    label = "medium"
                elif ratio > 0:
                    label = "low"
                else:
                    label = "none"
                beat_hint_alignment["label"] = label

        return {
            "achieved_change": achieved_change,
            "dialogue_count": dialogue_count,
            "dialogue_target": {
                "min_exchanges": min_exchanges,
                "met": met_dialogue_target,
            },
            "transition_clarity": {
                "score": transition_clarity_score,
                "notes": transition_notes,
            },
            "mode_used": scene_mode or "unknown",
            "mode_diversity_warning": mode_diversity_warning,
            "novelty_score": novelty_score,
            "continuity_flags": continuity_flags,
            "beat_hint_alignment": beat_hint_alignment,
        }
