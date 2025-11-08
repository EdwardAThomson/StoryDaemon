"""Main StoryAgent orchestrator for coordinating the planning and execution loop."""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from .context import ContextBuilder
from .prompts import format_planner_prompt
from .schemas import validate_plan
from .runtime import PlanExecutor
from .plan_manager import PlanManager
from .writer_context import WriterContextBuilder
from .writer import SceneWriter
from .evaluator import SceneEvaluator
from .scene_committer import SceneCommitter
from .fact_extractor import FactExtractor
from .entity_updater import EntityUpdater
from ..tools.registry import ToolRegistry
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..memory.summarizer import SceneSummarizer


class StoryAgent:
    """Main agent orchestrator for story generation.
    
    Coordinates the full tick cycle:
    1. Gather context
    2. Generate plan with LLM
    3. Execute plan
    4. Store results
    5. Write scene prose (Phase 4)
    6. Evaluate scene (Phase 4)
    7. Commit scene (Phase 4)
    8. Extract facts (Phase 5)
    9. Update entities (Phase 5)
    10. Re-index entities (Phase 5)
    11. Update state
    """
    
    def __init__(
        self,
        project_path: Path,
        llm_interface,
        tool_registry: ToolRegistry,
        config: dict
    ):
        """Initialize story agent.
        
        Args:
            project_path: Path to novel project
            llm_interface: LLM interface (CodexInterface or similar)
            tool_registry: Registry of available tools
            config: Project configuration
        """
        self.project_path = Path(project_path)
        self.llm = llm_interface
        self.tools = tool_registry
        self.config = config
        
        # Initialize components
        self.memory = MemoryManager(self.project_path)
        self.vector = VectorStore(self.project_path)
        self.context_builder = ContextBuilder(
            self.memory,
            self.vector,
            self.tools,
            config
        )
        self.executor = PlanExecutor(self.tools, self.memory, self.vector)
        self.plan_manager = PlanManager(self.project_path)
        
        # Phase 4 components
        self.writer_context_builder = WriterContextBuilder(
            self.memory,
            self.vector,
            config
        )
        self.writer = SceneWriter(llm_interface, config)
        self.evaluator = SceneEvaluator(self.memory, config)
        self.summarizer = SceneSummarizer(llm_interface)
        self.committer = SceneCommitter(
            self.memory,
            self.vector,
            self.summarizer,
            project_path
        )
        
        # Phase 5 components
        self.fact_extractor = FactExtractor(llm_interface, self.memory, config)
        self.entity_updater = EntityUpdater(self.memory, config)
        
        # Load state
        self.state = self._load_state()
    
    def tick(self) -> Dict[str, Any]:
        """Execute one story generation tick.
        
        Uses two-phase execution for tick 0 (entity setup then scene writing)
        and normal execution for subsequent ticks.
        
        Returns:
            Result dictionary with tick info and success status
        
        Raises:
            RuntimeError: If tool execution fails
            ValueError: If plan validation fails
        """
        tick = self.state["current_tick"]
        
        # Use two-phase execution for first tick only
        if tick == 0:
            return self._first_tick()
        else:
            return self._normal_tick()
    
    def _normal_tick(self) -> Dict[str, Any]:
        """Execute normal tick (tick 1+).
        
        Returns:
            Result dictionary with tick info and success status
        """
        tick = self.state["current_tick"]
        
        try:
            # Step 1: Gather context
            print("   1. Gathering context...")
            context = self.context_builder.build_planner_context(self.state)
            
            # Step 2: Generate plan with LLM
            print("   2. Generating plan with LLM...")
            plan = self._generate_plan(context)
            
            # Step 3: Validate plan
            print("   3. Validating plan...")
            validate_plan(plan)
            
            # Step 4: Execute plan
            print("   4. Executing tool calls...")
            execution_results = self.executor.execute_plan(plan, tick)
            
            # Step 4.5: Set active character if none exists and a character was created
            if self.state.get("active_character") is None:
                # Check if a character was created in this tick
                for action in execution_results.get("actions_executed", []):
                    if action.get("tool") == "character.generate" and action.get("success"):
                        char_id = action.get("result", {}).get("character_id")
                        if char_id:
                            self.state["active_character"] = char_id
                            # Also update the plan's POV character to use the real ID
                            if plan.get("pov_character") and not plan["pov_character"].startswith("C"):
                                plan["pov_character"] = char_id
                            break
            
            # Step 5: Store plan and results
            print("   5. Storing plan...")
            plan_file = self.plan_manager.save_plan(
                tick,
                plan,
                execution_results,
                context
            )
            
            # Step 6: Write scene prose (Phase 4)
            print("   6. Writing scene prose...")
            writer_context = self.writer_context_builder.build_writer_context(
                plan,
                execution_results,
                self.state
            )
            scene_data = self.writer.write_scene(writer_context)
            
            # Step 7: Evaluate scene (Phase 4)
            print("   7. Evaluating scene...")
            eval_result = self.evaluator.evaluate_scene(
                scene_data["text"],
                writer_context
            )
            
            # Log evaluation warnings (non-blocking)
            if eval_result["warnings"]:
                # Warnings are logged but don't fail the tick
                pass
            
            # Fail if critical issues found
            if not eval_result["passed"]:
                raise ValueError(f"Scene evaluation failed: {eval_result['issues']}")
            
            # Step 8: Commit scene (Phase 4)
            print("   8. Committing scene...")
            scene_id = self.committer.commit_scene(scene_data, tick, plan)
            
            # Step 9: Extract facts (Phase 5)
            print("   9. Extracting facts...")
            facts = self._extract_facts_with_retry(
                scene_data["text"],
                writer_context
            )
            
            # Step 10: Update entities (Phase 5)
            print("   10. Updating entities...")
            update_stats = {}
            if facts:  # Only update if extraction succeeded
                update_stats = self.entity_updater.apply_updates(facts, tick, scene_id)
                
                # Step 11: Re-index updated entities (Phase 5)
                print("   11. Syncing vector database...")
                self._reindex_updated_entities(facts)
            
            # Step 12: Update state
            self.state["current_tick"] += 1
            self._save_state()
            
            return {
                "success": True,
                "tick": tick,
                "plan_file": str(plan_file),
                "scene_id": scene_id,
                "scene_file": f"scenes/scene_{tick:03d}.md",
                "word_count": scene_data["word_count"],
                "actions_executed": len(execution_results.get("actions_executed", [])),
                "eval_warnings": eval_result.get("warnings", []),
                "entities_updated": update_stats
            }
        
        except RuntimeError as e:
            # Tool execution error - save error details
            execution_results = getattr(e, 'execution_results', {
                "tick": tick,
                "actions_executed": [],
                "errors": [str(e)],
                "success": False
            })
            
            # Try to get the plan from the exception context
            plan = getattr(e, 'plan', {})
            
            self.plan_manager.save_error(tick, e, plan, execution_results)
            raise
        
        except Exception as e:
            # Other errors (validation, LLM, etc.)
            self.plan_manager.save_error(tick, e, {}, {})
            raise
    
    def _first_tick(self) -> Dict[str, Any]:
        """Execute first tick with two-phase entity generation.
        
        Phase 1: Generate entities (character, location)
        Phase 2: Write scene with established entities
        
        Returns:
            Result dictionary with tick info and success status
        """
        tick = 0
        
        print("   ⚙️  Executing tick 0 (two-phase initialization)...")
        
        try:
            # PHASE 1: Entity Generation
            print("   Phase 1: Generating entities...")
            
            # Step 1: Gather context
            print("   1. Gathering context...")
            context = self.context_builder.build_planner_context(self.state)
            
            # Step 2: Generate plan
            print("   2. Generating plan with LLM...")
            plan = self._generate_plan(context)
            
            # Step 3: Validate plan
            print("   3. Validating plan...")
            validate_plan(plan)
            
            # Step 4: Execute ONLY entity generation tools
            print("   4. Pre-generating entities...")
            entity_results = self._execute_entity_generation_only(plan, tick)
            
            # Step 5: Update plan with real entity IDs
            print("   5. Updating plan with entity IDs...")
            self._update_plan_with_entity_ids(plan, entity_results)
            
            # Step 6: Set active character
            if self.state.get("active_character") is None:
                for action in entity_results.get("actions_executed", []):
                    if action.get("tool") == "character.generate" and action.get("success"):
                        char_id = action.get("result", {}).get("character_id")
                        if char_id:
                            self.state["active_character"] = char_id
                            plan["pov_character"] = char_id
                            break
            
            # PHASE 2: Scene Writing
            print("   Phase 2: Writing scene...")
            
            # Step 7: Execute remaining tools (if any)
            print("   6. Executing remaining tools...")
            remaining_results = self._execute_remaining_tools(plan, tick, entity_results)
            
            # Merge results
            execution_results = self._merge_execution_results(entity_results, remaining_results)
            
            # Step 8: Store plan
            print("   7. Storing plan...")
            plan_file = self.plan_manager.save_plan(tick, plan, execution_results, context)
            
            # Step 9: Write scene (entities are now established)
            print("   8. Writing scene prose...")
            writer_context = self.writer_context_builder.build_writer_context(
                plan,
                execution_results,
                self.state
            )
            scene_data = self.writer.write_scene(writer_context)
            
            # Step 10: Evaluate scene
            print("   9. Evaluating scene...")
            eval_result = self.evaluator.evaluate_scene(
                scene_data["text"],
                writer_context
            )
            
            # Log evaluation warnings (non-blocking)
            if eval_result["warnings"]:
                pass
            
            # Fail if critical issues found
            if not eval_result["passed"]:
                raise ValueError(f"Scene evaluation failed: {eval_result['issues']}")
            
            # Step 11: Commit scene
            print("   10. Committing scene...")
            scene_id = self.committer.commit_scene(scene_data, tick, plan)
            
            # Step 12: Extract facts
            print("   11. Extracting facts...")
            facts = self._extract_facts_with_retry(
                scene_data["text"],
                writer_context
            )
            
            # Step 13: Update entities
            print("   12. Updating entities...")
            update_stats = {}
            if facts:
                update_stats = self.entity_updater.apply_updates(facts, tick, scene_id)
            
            # Step 14: Sync vector database
            print("   13. Syncing vector database...")
            self.vector.index_scene(self.memory.load_scene(scene_id))
            
            # Increment tick
            self.state["current_tick"] += 1
            self._save_state()
            
            return {
                "success": True,
                "tick": tick,
                "scene_id": scene_id,
                "scene_file": f"scenes/scene_{tick:03d}.md",
                "word_count": scene_data["word_count"],
                "plan_file": str(plan_file),
                "update_stats": update_stats,
                "actions_executed": len(execution_results.get("actions_executed", []))
            }
        
        except RuntimeError as e:
            # Tool execution error
            execution_results = getattr(e, 'execution_results', {
                "tick": tick,
                "actions_executed": [],
                "errors": [str(e)],
                "success": False
            })
            
            plan = getattr(e, 'plan', {})
            self.plan_manager.save_error(tick, e, plan, execution_results)
            raise
        
        except Exception as e:
            # Other errors
            self.plan_manager.save_error(tick, e, {}, {})
            raise
    
    def _execute_entity_generation_only(self, plan: Dict, tick: int) -> Dict:
        """Execute only entity generation tools from plan.
        
        Args:
            plan: The generated plan
            tick: Current tick number
        
        Returns:
            Execution results for entity generation tools only
        """
        entity_tools = ["name.generate", "character.generate", "location.generate"]
        
        filtered_actions = [
            action for action in plan.get("actions", [])
            if action.get("tool") in entity_tools
        ]
        
        if not filtered_actions:
            return {"actions_executed": [], "errors": [], "success": True}
        
        # Create temporary plan with only entity actions
        entity_plan = {**plan, "actions": filtered_actions}
        
        return self.executor.execute_plan(entity_plan, tick)
    
    def _execute_remaining_tools(self, plan: Dict, tick: int, entity_results: Dict) -> Dict:
        """Execute non-entity tools from plan.
        
        Args:
            plan: The generated plan (with updated entity IDs)
            tick: Current tick number
            entity_results: Results from entity generation
        
        Returns:
            Execution results for remaining tools
        """
        entity_tools = ["name.generate", "character.generate", "location.generate"]
        
        remaining_actions = [
            action for action in plan.get("actions", [])
            if action.get("tool") not in entity_tools
        ]
        
        if not remaining_actions:
            return {"actions_executed": [], "errors": [], "success": True}
        
        # Create temporary plan with only remaining actions
        remaining_plan = {**plan, "actions": remaining_actions}
        
        return self.executor.execute_plan(remaining_plan, tick)
    
    def _update_plan_with_entity_ids(self, plan: Dict, entity_results: Dict):
        """Update plan with real entity IDs after generation.
        
        Args:
            plan: The plan to update (modified in place)
            entity_results: Results from entity generation
        """
        for action in entity_results.get("actions_executed", []):
            if action.get("tool") == "character.generate" and action.get("success"):
                char_id = action.get("result", {}).get("character_id")
                if char_id and plan.get("pov_character"):
                    # Replace placeholder with real ID
                    if not plan["pov_character"].startswith("C"):
                        plan["pov_character"] = char_id
            
            elif action.get("tool") == "location.generate" and action.get("success"):
                loc_id = action.get("result", {}).get("location_id")
                if loc_id and plan.get("target_location"):
                    # Replace placeholder with real ID
                    if not plan["target_location"].startswith("L"):
                        plan["target_location"] = loc_id
    
    def _merge_execution_results(self, entity_results: Dict, remaining_results: Dict) -> Dict:
        """Merge entity and remaining execution results.
        
        Args:
            entity_results: Results from entity generation
            remaining_results: Results from remaining tools
        
        Returns:
            Combined execution results
        """
        return {
            "actions_executed": (
                entity_results.get("actions_executed", []) +
                remaining_results.get("actions_executed", [])
            ),
            "errors": (
                entity_results.get("errors", []) +
                remaining_results.get("errors", [])
            ),
            "success": entity_results.get("success", True) and remaining_results.get("success", True)
        }
    
    def _generate_plan(self, context: dict) -> dict:
        """Generate a plan using the planner LLM.
        
        Args:
            context: Context dictionary for prompt
        
        Returns:
            Parsed plan dictionary
        
        Raises:
            ValueError: If LLM response cannot be parsed
        """
        # Format prompt
        prompt = format_planner_prompt(context)
        
        # Get token limit from config
        max_tokens = self.config.get('llm.planner_max_tokens', 2000)
        
        # Call LLM
        response = self.llm.generate(prompt, max_tokens=max_tokens)
        
        # Parse response
        plan = self._parse_plan_response(response)
        
        return plan
    
    def _parse_plan_response(self, response: str) -> dict:
        """Parse LLM response into plan dictionary.
        
        Args:
            response: Raw LLM response text
        
        Returns:
            Parsed plan dictionary
        
        Raises:
            ValueError: If JSON cannot be extracted or parsed
        """
        # Try to extract JSON from response
        # LLM might wrap it in markdown code blocks
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError("Could not extract JSON from LLM response")
        
        try:
            plan = json.loads(json_str)
            return plan
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in plan: {e}")
    
    def _load_state(self) -> dict:
        """Load project state from state.json.
        
        Returns:
            State dictionary
        """
        state_file = self.project_path / "state.json"
        with open(state_file, 'r') as f:
            return json.load(f)
    
    def _save_state(self):
        """Save project state to state.json."""
        state_file = self.project_path / "state.json"
        self.state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        with open(state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _extract_facts_with_retry(self, scene_text: str, scene_context: dict) -> dict:
        """Extract facts with retry logic for graceful degradation.
        
        Args:
            scene_text: Scene prose
            scene_context: Scene context
        
        Returns:
            Extracted facts dict, or None if extraction failed
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Check if fact extraction is enabled
        if not self.config.get('generation.enable_fact_extraction', True):
            logger.info("Fact extraction disabled in config")
            return None
        
        try:
            # First attempt
            facts = self.fact_extractor.extract_facts(scene_text, scene_context)
            return facts
            
        except Exception as e:
            logger.warning(f"Fact extraction failed (attempt 1): {e}")
            
            try:
                # Retry once
                logger.info("Retrying fact extraction...")
                facts = self.fact_extractor.extract_facts(scene_text, scene_context)
                return facts
                
            except Exception as e2:
                # Second failure - log error and continue without updates
                logger.error(f"Fact extraction failed (attempt 2): {e2}")
                logger.error("Continuing without entity updates")
                return None
    
    def _reindex_updated_entities(self, facts: dict):
        """Re-index entities that were updated.
        
        Args:
            facts: Extracted facts dictionary
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Re-index characters
            for char_update in facts.get("character_updates", []):
                char_id = char_update["id"]
                character = self.memory.load_character(char_id)
                if character:
                    self.vector.index_character(character)
                    logger.debug(f"Re-indexed character {char_id}")
            
            # Re-index locations
            for loc_update in facts.get("location_updates", []):
                loc_id = loc_update["id"]
                location = self.memory.load_location(loc_id)
                if location:
                    self.vector.index_location(location)
                    logger.debug(f"Re-indexed location {loc_id}")
                    
        except Exception as e:
            logger.error(f"Error re-indexing entities: {e}")
