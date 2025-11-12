"""Multi-stage planner with semantic context selection (Phase 7A.5).

Breaks planning into focused stages:
1. Strategic Planning: Foundation + Goals → Scene intention
2. Semantic Context Gathering: Vector search for relevant context
3. Tactical Planning: Intention + Context → Detailed plan
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class MultiStagePlanner:
    """Multi-stage planner with semantic context selection."""
    
    def __init__(
        self,
        llm_interface,
        memory_manager: MemoryManager,
        vector_store: VectorStore,
        tool_registry: ToolRegistry,
        config: dict,
        save_prompts: bool = False,
        prompts_dir: Optional[Path] = None
    ):
        """Initialize multi-stage planner.
        
        Args:
            llm_interface: LLM interface for text generation
            memory_manager: Memory manager for accessing entities
            vector_store: Vector store for semantic search
            tool_registry: Registry of available tools
            config: Configuration object
            save_prompts: Whether to save prompts to files
            prompts_dir: Directory to save prompts (if save_prompts=True)
        """
        self.llm = llm_interface
        self.memory = memory_manager
        self.vector = vector_store
        self.tools = tool_registry
        self.config = config
        self.save_prompts = save_prompts
        self.prompts_dir = prompts_dir
        
        # Stage statistics for verbose output
        self.stage_stats = {
            'stage1_tokens': 0,
            'stage1_time': 0.0,
            'stage2_items': 0,
            'stage2_time': 0.0,
            'stage3_tokens': 0,
            'stage3_time': 0.0,
        }
        
        # Create prompts directory if needed
        if self.save_prompts and self.prompts_dir:
            self.prompts_dir.mkdir(parents=True, exist_ok=True)
    
    def plan(self, project_state: dict) -> dict:
        """Execute multi-stage planning.
        
        Args:
            project_state: Current project state
            
        Returns:
            Plan dictionary with rationale, scene_intention, actions, etc.
        """
        logger.info("Starting multi-stage planning...")
        
        # Stage 1: Strategic Planning (Small LLM call)
        logger.info("Stage 1: Strategic planning...")
        scene_intention = self._strategic_planning(project_state)
        logger.info(f"Scene intention: {scene_intention}")
        
        # Stage 2: Semantic Context Gathering (No LLM)
        logger.info("Stage 2: Gathering relevant context...")
        relevant_context = self._gather_relevant_context(
            scene_intention,
            project_state
        )
        logger.info(f"Found {self.stage_stats['stage2_items']} relevant items")
        
        # Stage 3: Tactical Planning (Medium LLM call)
        logger.info("Stage 3: Tactical planning...")
        plan = self._tactical_planning(
            scene_intention,
            relevant_context,
            project_state
        )
        logger.info("Multi-stage planning complete")
        
        # Add stage stats to plan for verbose output
        plan['_stage_stats'] = self.stage_stats
        
        return plan
    
    def _strategic_planning(self, state: dict) -> str:
        """Stage 1: High-level scene intention.
        
        Small focused prompt with foundation, goals, and dynamics.
        
        Args:
            state: Current project state
            
        Returns:
            Scene intention string
        """
        import time
        start_time = time.time()
        
        # Build strategic prompt
        prompt = self._build_strategic_prompt(state)
        
        # Track token count (approximate)
        self.stage_stats['stage1_tokens'] = len(prompt.split())
        
        # Save prompt if requested
        if self.save_prompts and self.prompts_dir:
            tick = state.get('current_tick', 0)
            prompt_file = self.prompts_dir / f"tick_{tick:03d}_stage1_strategic.txt"
            with open(prompt_file, 'w') as f:
                f.write(f"=== STAGE 1: STRATEGIC PLANNING ===\n")
                f.write(f"Tick: {tick}\n")
                f.write(f"Tokens (approx): {self.stage_stats['stage1_tokens']}\n")
                f.write(f"\n{prompt}\n")
        
        # Call LLM
        response = self.llm.generate(prompt, max_tokens=150)
        
        # Save response if requested
        if self.save_prompts and self.prompts_dir:
            tick = state.get('current_tick', 0)
            response_file = self.prompts_dir / f"tick_{tick:03d}_stage1_response.txt"
            with open(response_file, 'w') as f:
                f.write(response)
        
        self.stage_stats['stage1_time'] = time.time() - start_time
        
        return response.strip()
    
    def _gather_relevant_context(
        self,
        scene_intention: str,
        state: dict
    ) -> dict:
        """Stage 2: Semantic context selection (No LLM call).
        
        Uses vector search to find relevant entities.
        
        Args:
            scene_intention: Scene intention from Stage 1
            state: Current project state
            
        Returns:
            Dictionary of relevant context
        """
        import time
        start_time = time.time()
        
        context = {}
        items_count = 0
        
        # Get protagonist for context
        protagonist_id = state.get('active_character')
        protagonist = None
        if protagonist_id:
            protagonist = self.memory.load_character(protagonist_id)
        
        # Semantic search for relevant past scenes
        try:
            relevant_scenes = self.vector.search_scenes(
                query=scene_intention,
                limit=3
            )
            # search_scenes returns formatted results, not tuples
            context['relevant_scenes'] = relevant_scenes
            items_count += len(relevant_scenes)
        except Exception as e:
            logger.warning(f"Scene search failed: {e}")
            context['relevant_scenes'] = []
        
        # Get open loops (filter by relevance)
        all_loops = self.memory.load_open_loops()
        context['relevant_loops'] = self._filter_relevant_loops(
            scene_intention,
            all_loops,
            top_k=5
        )
        items_count += len(context['relevant_loops'])
        
        # Get protagonist's relationships (always relevant)
        if protagonist_id:
            relationships = self.memory.get_character_relationships(protagonist_id)
            context['relationships'] = relationships
            items_count += len(relationships)
        else:
            context['relationships'] = []
        
        # Semantic search for relevant lore
        try:
            all_lore = self.memory.load_all_lore()
            if all_lore:
                relevant_lore = self._filter_relevant_lore(
                    scene_intention,
                    all_lore,
                    top_k=5
                )
                context['relevant_lore'] = relevant_lore
                items_count += len(relevant_lore)
            else:
                context['relevant_lore'] = []
        except Exception as e:
            logger.warning(f"Lore filtering failed: {e}")
            context['relevant_lore'] = []
        
        self.stage_stats['stage2_items'] = items_count
        self.stage_stats['stage2_time'] = time.time() - start_time
        
        return context
    
    def _tactical_planning(
        self,
        scene_intention: str,
        context: dict,
        state: dict
    ) -> dict:
        """Stage 3: Detailed plan with tool calls.
        
        Medium prompt with intention and relevant context only.
        
        Args:
            scene_intention: Scene intention from Stage 1
            context: Relevant context from Stage 2
            state: Current project state
            
        Returns:
            Plan dictionary
        """
        import time
        start_time = time.time()
        
        # Build tactical prompt
        prompt = self._build_tactical_prompt(scene_intention, context, state)
        
        # Track token count (approximate)
        self.stage_stats['stage3_tokens'] = len(prompt.split())
        
        # Save prompt if requested
        if self.save_prompts and self.prompts_dir:
            tick = state.get('current_tick', 0)
            prompt_file = self.prompts_dir / f"tick_{tick:03d}_stage3_tactical.txt"
            with open(prompt_file, 'w') as f:
                f.write(f"=== STAGE 3: TACTICAL PLANNING ===\n")
                f.write(f"Tick: {tick}\n")
                f.write(f"Tokens (approx): {self.stage_stats['stage3_tokens']}\n")
                f.write(f"Scene Intention: {scene_intention}\n")
                f.write(f"\n{prompt}\n")
        
        # Call LLM
        response = self.llm.generate(prompt, max_tokens=2000)
        
        # Save response if requested
        if self.save_prompts and self.prompts_dir:
            tick = state.get('current_tick', 0)
            response_file = self.prompts_dir / f"tick_{tick:03d}_stage3_response.txt"
            with open(response_file, 'w') as f:
                f.write(response)
        
        self.stage_stats['stage3_time'] = time.time() - start_time
        
        # Parse response
        plan = self._parse_plan_response(response)
        
        return plan
    
    def _build_strategic_prompt(self, state: dict) -> str:
        """Build Stage 1 strategic planning prompt.
        
        Args:
            state: Current project state
            
        Returns:
            Formatted prompt string
        """
        # Get foundation
        foundation = state.get('story_foundation', {})
        
        # Get protagonist
        protagonist_id = state.get('active_character')
        protagonist = self.memory.load_character(protagonist_id) if protagonist_id else None
        
        # Get story goal if it exists
        story_goal = state.get('story_goal', {})
        
        # Get recent tension pattern
        tension_history = state.get('tension_history', [])
        recent_tension = tension_history[-5:] if tension_history else []
        
        prompt = f"""You are planning the next scene in a story.

## Story Foundation (IMMUTABLE)
Genre: {foundation.get('genre', 'Unknown')}
Premise: {foundation.get('premise', 'Unknown')}
Setting: {foundation.get('setting', 'Unknown')}
Tone: {foundation.get('tone', 'Unknown')}

## Current State
Tick: {state.get('current_tick', 0)}
Story Goal: {story_goal.get('description', 'Still emerging')}
Recent Tension: {recent_tension}

## Protagonist
"""
        
        if protagonist:
            prompt += f"""Name: {protagonist.display_name}
Role: {protagonist.role}
Current Goals: {', '.join(protagonist.current_state.goals[:3]) if protagonist.current_state.goals else 'None'}
Emotional State: {protagonist.current_state.emotional_state or 'Unknown'}
"""
        else:
            prompt += "No protagonist defined yet.\n"
        
        prompt += """
## Task
Based on the story foundation, current state, and pacing, what should happen in the next scene?

Consider:
- Story foundation constraints (genre, tone, setting)
- Protagonist's current goals and state
- Recent tension pattern (maintain variety)
- Story goal progress (if one exists)

Respond with a single sentence describing the scene intention.
Example: "Protagonist discovers a clue about the signal's origin, raising tension"

Scene intention:"""
        
        return prompt
    
    def _build_tactical_prompt(
        self,
        scene_intention: str,
        context: dict,
        state: dict
    ) -> str:
        """Build Stage 3 tactical planning prompt.
        
        Args:
            scene_intention: Scene intention from Stage 1
            context: Relevant context from Stage 2
            state: Current project state
            
        Returns:
            Formatted prompt string
        """
        # Get protagonist
        protagonist_id = state.get('active_character')
        protagonist = self.memory.load_character(protagonist_id) if protagonist_id else None
        
        prompt = f"""You are creating a detailed plan for the next scene.

## Scene Intention
{scene_intention}

## Relevant Context

### Relevant Past Scenes
"""
        
        # Add relevant scenes
        relevant_scenes = context.get('relevant_scenes', [])
        if relevant_scenes:
            for scene in relevant_scenes[:3]:
                # scene is a dict with entity_id, snippet, etc.
                prompt += f"- [{scene.get('entity_id', 'Unknown')}] {scene.get('snippet', '')}\n"
        else:
            prompt += "None\n"
        
        prompt += "\n### Relevant Open Loops\n"
        
        # Add relevant loops
        relevant_loops = context.get('relevant_loops', [])
        if relevant_loops:
            for loop in relevant_loops[:5]:
                prompt += f"- {loop.category}: {loop.description}\n"
        else:
            prompt += "None\n"
        
        prompt += "\n### Relevant Lore\n"
        
        # Add relevant lore
        relevant_lore = context.get('relevant_lore', [])
        if relevant_lore:
            for lore in relevant_lore[:5]:
                prompt += f"- [{lore.lore_type}] {lore.content}\n"
        else:
            prompt += "None\n"
        
        prompt += "\n### Character Relationships\n"
        
        # Add relationships
        relationships = context.get('relationships', [])
        if relationships:
            for rel in relationships[:5]:
                prompt += f"- {rel.character_a} ↔ {rel.character_b}: {rel.relationship_type}\n"
        else:
            prompt += "None\n"
        
        prompt += f"""
## Available Tools

You can use the following tools to gather information or create entities:

{self._format_tools_description()}

## Your Task

Create a detailed plan for executing the scene intention. Consider:
1. Which open loops should be addressed or developed?
2. What information do you need to write this scene effectively?
3. Should new characters or locations be introduced?
4. How should relationships evolve?

## Output Format

Respond with a JSON object following this structure:

```json
{{
  "rationale": "Brief explanation of your planning decisions",
  "scene_intention": "{scene_intention}",
  "pov_character": "{protagonist_id if protagonist else 'C0'}",
  "target_location": "Location ID where scene takes place (or null for new location)",
  "actions": [
    {{
      "tool": "tool.name",
      "args": {{
        "arg1": "value1"
      }},
      "reason": "Why this tool is needed"
    }}
  ],
  "expected_outcomes": [
    "Outcome 1",
    "Outcome 2"
  ]
}}
```

Generate your plan now:"""
        
        return prompt
    
    def _format_tools_description(self) -> str:
        """Format available tools for prompt.
        
        Returns:
            Formatted tools description
        """
        # Use the existing method from ToolRegistry
        return self.tools.get_tools_description()
    
    def _filter_relevant_loops(
        self,
        query: str,
        loops: List[Any],
        top_k: int = 5
    ) -> List[Any]:
        """Filter loops by semantic relevance to query.
        
        Args:
            query: Scene intention query
            loops: All open loops
            top_k: Number of loops to return
            
        Returns:
            Most relevant loops
        """
        if not loops:
            return []
        
        # Simple keyword-based relevance for now
        # TODO: Use proper embedding similarity
        scored_loops = []
        query_words = set(query.lower().split())
        
        for loop in loops:
            loop_text = f"{loop.category} {loop.description}".lower()
            loop_words = set(loop_text.split())
            overlap = len(query_words & loop_words)
            score = overlap / max(len(query_words), 1)
            scored_loops.append((score, loop))
        
        # Sort by score and return top K
        scored_loops.sort(reverse=True, key=lambda x: x[0])
        return [loop for score, loop in scored_loops[:top_k]]
    
    def _filter_relevant_lore(
        self,
        query: str,
        lore_items: List[Any],
        top_k: int = 5
    ) -> List[Any]:
        """Filter lore by semantic relevance to query.
        
        Args:
            query: Scene intention query
            lore_items: All lore items
            top_k: Number of items to return
            
        Returns:
            Most relevant lore items
        """
        if not lore_items:
            return []
        
        # Simple keyword-based relevance for now
        # TODO: Use proper embedding similarity via vector store
        scored_lore = []
        query_words = set(query.lower().split())
        
        for lore in lore_items:
            lore_text = f"{lore.category} {lore.content}".lower()
            lore_words = set(lore_text.split())
            overlap = len(query_words & lore_words)
            score = overlap / max(len(query_words), 1)
            scored_lore.append((score, lore))
        
        # Sort by score and return top K
        scored_lore.sort(reverse=True, key=lambda x: x[0])
        return [lore for score, lore in scored_lore[:top_k]]
    
    def _parse_plan_response(self, response: str) -> dict:
        """Parse LLM response into plan dictionary.
        
        Args:
            response: LLM response text
            
        Returns:
            Plan dictionary
        """
        try:
            # Try to find JSON in response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.error("No JSON found in plan response")
                return self._empty_plan()
            
            json_str = response[json_start:json_end]
            plan = json.loads(json_str)
            
            # Validate required fields
            if 'scene_intention' not in plan:
                logger.warning("Plan missing scene_intention")
                plan['scene_intention'] = "Continue the story"
            
            if 'actions' not in plan:
                plan['actions'] = []
            
            return plan
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan JSON: {e}")
            logger.debug(f"Response was: {response}")
            return self._empty_plan()
    
    def _empty_plan(self) -> dict:
        """Return empty plan as fallback.
        
        Returns:
            Minimal valid plan
        """
        return {
            'rationale': 'Planning failed, continuing with minimal plan',
            'scene_intention': 'Continue the story',
            'pov_character': self.memory.get_active_character(),
            'target_location': None,
            'actions': [],
            'expected_outcomes': []
        }
