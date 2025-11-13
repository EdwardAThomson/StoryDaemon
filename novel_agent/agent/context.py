"""Context builder for planner prompts."""

from pathlib import Path
from typing import Dict, Any, Optional
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..tools.registry import ToolRegistry


class ContextBuilder:
    """Builds context for planner prompts.
    
    Gathers all necessary information from the story state and formats it
    for inclusion in the planner LLM prompt.
    """
    
    def __init__(
        self,
        memory_manager: MemoryManager,
        vector_store: VectorStore,
        tool_registry: ToolRegistry,
        config: dict
    ):
        """Initialize context builder.
        
        Args:
            memory_manager: Memory manager instance
            vector_store: Vector store instance
            tool_registry: Tool registry instance
            config: Project configuration
        """
        self.memory = memory_manager
        self.vector = vector_store
        self.tools = tool_registry
        self.config = config
        
        # Get configurable context settings
        self.recent_scenes_count = config.get('generation.recent_scenes_count', 3)
        self.include_overall_summary = config.get('generation.include_overall_summary', True)
    
    def build_planner_context(self, project_state: dict) -> dict:
        """Build context dictionary for planner prompt.
        
        Args:
            project_state: Current project state from state.json
        
        Returns:
            Dictionary with all context variables for prompt formatting
        """
        context = {
            "novel_name": project_state.get("novel_name", "Untitled"),
            "current_tick": project_state.get("current_tick", 0),
            "active_character_id": project_state.get("active_character", ""),
            "active_character_name": "Unknown",
            "active_character_details": "No active character set.",
            "character_relationships": "No relationships yet.",
        }
        
        # Load active character
        if context["active_character_id"]:
            char = self.memory.load_character(context["active_character_id"])
            if char:
                context["active_character_name"] = char.name
                context["active_character_details"] = self._format_character(char)
                context["character_relationships"] = self._format_relationships(
                    context["active_character_id"]
                )
        
        # Get overall summary (if enabled) and recent scenes
        if self.include_overall_summary:
            context["overall_summary"] = self._get_overall_summary()
        else:
            context["overall_summary"] = ""
        
        context["recent_scenes_summary"] = self._get_recent_scenes_summary(
            self.recent_scenes_count
        )
        
        # Get open loops
        context["open_loops_list"] = self._format_open_loops()
        
        # Get tension history (Phase 7A.3)
        context["tension_history"] = self._get_tension_history()
        
        # Get factions summary (organizations relevant to the story)
        context["factions_summary"] = self._format_factions()
        
        # Get available tools description
        context["available_tools_description"] = self.tools.get_tools_description()
        
        return context
    
    def _format_character(self, character) -> str:
        """Format character details for prompt.
        
        Args:
            character: Character entity
        
        Returns:
            Formatted character description
        """
        parts = [
            f"Name: {character.name}",
            f"Role: {character.role}",
            f"Description: {character.description}",
        ]
        
        if character.current_state.goals:
            parts.append(f"Current Goals: {', '.join(character.current_state.goals)}")
        
        if character.current_state.emotional_state:
            parts.append(f"Emotional State: {character.current_state.emotional_state}")
        
        if character.current_state.location_id:
            parts.append(f"Current Location: {character.current_state.location_id}")
        
        return "\n".join(parts)
    
    def _get_overall_summary(self) -> str:
        """Get high-level summary of all scenes so far.
        
        Returns:
            Formatted overall story summary
        """
        scene_ids = self.memory.list_scenes()
        
        if not scene_ids:
            return "Story has not yet begun."
        
        # Get all scene summaries
        all_summaries = []
        for scene_id in scene_ids:
            scene = self.memory.load_scene(scene_id)
            if scene and scene.summary:
                # Take first bullet point from each scene as high-level summary
                first_bullet = scene.summary[0] if scene.summary else "Scene generated"
                all_summaries.append(f"Tick {scene.tick}: {first_bullet}")
        
        if not all_summaries:
            return f"{len(scene_ids)} scenes generated so far."
        
        summary_text = "\n".join(all_summaries)
        return f"**Story So Far** ({len(scene_ids)} scenes):\n{summary_text}"
    
    def _get_recent_scenes_summary(self, count: int) -> str:
        """Get detailed summaries of recent scenes.
        
        Args:
            count: Number of recent scenes to include
        
        Returns:
            Formatted recent scenes summary
        """
        scene_ids = self.memory.list_scenes()
        
        if not scene_ids:
            return "No scenes yet."
        
        recent_ids = scene_ids[-count:] if len(scene_ids) >= count else scene_ids
        
        summaries = []
        for scene_id in recent_ids:
            scene = self.memory.load_scene(scene_id)
            if scene and scene.summary:
                summary_text = "\n  - ".join(scene.summary)
                title = scene.title if hasattr(scene, 'title') and scene.title else f"Scene {scene_id}"
                summaries.append(f"**{title}** (Tick {scene.tick}):\n  - {summary_text}")
        
        if not summaries:
            return f"Last {len(recent_ids)} scenes have no summaries."
        
        return "\n\n".join(summaries)
    
    def _format_open_loops(self) -> str:
        """Format open story loops for prompt.
        
        Returns:
            Formatted open loops list
        """
        open_loops = self.memory.get_open_loops()
        
        if not open_loops:
            return "No open loops."
        
        # Sort by importance (descending)
        sorted_loops = sorted(
            open_loops,
            key=lambda x: x.importance,
            reverse=True
        )
        
        loop_lines = []
        for loop in sorted_loops:
            status_marker = "🔴" if loop.status == "urgent" else "🟡" if loop.status == "active" else "⚪"
            loop_lines.append(
                f"{status_marker} **{loop.id}** (Importance: {loop.importance}): {loop.description}"
            )
        
        return "\n".join(loop_lines)
    
    def _format_relationships(self, character_id: str) -> str:
        """Format character relationships for prompt.
        
        Args:
            character_id: Character ID to get relationships for
        
        Returns:
            Formatted relationships description
        """
        relationships = self.memory.get_character_relationships(character_id)
        
        if not relationships:
            return f"Character {character_id} has no established relationships yet."
        
        rel_lines = []
        for rel in relationships:
            other_id = rel.get_other_character(character_id)
            other_char = self.memory.load_character(other_id)
            other_name = other_char.name if other_char else other_id
            
            perspective = rel.get_perspective(character_id)
            rel_type = rel.relationship_type
            status = rel.status
            
            rel_lines.append(
                f"- **{other_name}** ({other_id}): {rel_type} - {status}\n"
                f"  Perspective: \"{perspective}\""
            )
        
        return "\n".join(rel_lines)
    
    def _get_tension_history(self) -> str:
        """Get recent tension history for context (Phase 7A.3).
        
        Returns:
            Formatted tension history string with pacing suggestions
        """
        # Handle both Config object and plain dict
        if isinstance(self.config, dict) and 'generation' in self.config:
            enabled = self.config.get('generation', {}).get('enable_tension_tracking', True)
        else:
            enabled = self.config.get('generation.enable_tension_tracking', True)
        
        if not enabled:
            return ""
        
        # Get recent scene IDs
        scene_ids = self.memory.list_scenes()
        if not scene_ids:
            return ""
        
        # Get last 5 scene IDs
        recent_ids = scene_ids[-5:]
        
        # Load scenes and filter for tension data
        tension_scenes = []
        for scene_id in recent_ids:
            scene = self.memory.load_scene(scene_id)
            if scene and hasattr(scene, 'tension_level') and scene.tension_level is not None:
                tension_scenes.append(scene)
        
        if not tension_scenes:
            return ""
        
        # Format tension progression
        levels = [s.tension_level for s in tension_scenes]
        categories = [s.tension_category for s in tension_scenes]
        
        progression = ' → '.join(categories)
        levels_str = ', '.join(str(l) for l in levels)
        
        # Analyze pattern for gentle guidance
        result = f"Recent tension: [{levels_str}] ({progression})\n"
        
        # Add contextual pacing notes (informational, not prescriptive)
        if len(levels) >= 3:
            avg_tension = sum(levels) / len(levels)
            variance = max(levels) - min(levels)
            
            # Check for sustained high tension (priority check)
            if avg_tension >= 7 and all(l >= 6 for l in levels[-3:]):
                result += "\nNote: Tension has been high. Consider whether a brief respite would:\n"
                result += "  - Allow character reflection and emotional processing\n"
                result += "  - Build anticipation for the next major event\n"
                result += "  - Provide contrast to make future tension more impactful\n"
            
            # Check for sustained low tension (priority check)
            elif avg_tension <= 3 and all(l <= 4 for l in levels[-3:]):
                result += "\nNote: Tension has been low. Consider whether the story needs:\n"
                result += "  - Rising stakes or complications\n"
                result += "  - Introduction of conflict or obstacles\n"
                result += "  - Continued calm (if building toward something)\n"
            
            # Check for flatness (low variance) - only if not already caught above
            elif variance <= 1 and len(levels) >= 4:
                result += "\nNote: Tension has been steady. Consider whether the story would benefit from:\n"
                result += "  - A calm moment (reflection, planning, character interaction)\n"
                result += "  - A tension spike (revelation, confrontation, danger)\n"
                result += "  - Continued current pacing (if appropriate for the narrative)\n"
        
        result += "\nThis is informational only - follow the natural story flow."
        
        return result

    def _format_factions(self) -> str:
        """Format factions (organizations) for prompt context.
        
        Returns:
            Formatted list of factions by importance
        """
        # Access MemoryManager directly
        try:
            faction_ids = self.memory.list_factions()
        except Exception:
            return "No factions."
        if not faction_ids:
            return "No factions."
        factions = []
        for fid in faction_ids:
            fac = self.memory.load_faction(fid)
            if fac:
                factions.append(fac)
        # Sort by importance
        importance_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        factions.sort(key=lambda f: importance_order.get(getattr(f, 'importance', 'medium'), 1), reverse=True)
        lines = []
        for f in factions[:8]:
            imp = getattr(f, 'importance', 'medium')
            org_type = getattr(f, 'org_type', 'other')
            name = getattr(f, 'name', f.id)
            summary = getattr(f, 'summary', '')
            lines.append(f"- {name} ({f.id}) — type: {org_type}, importance: {imp}. {summary}")
        return "\n".join(lines)
