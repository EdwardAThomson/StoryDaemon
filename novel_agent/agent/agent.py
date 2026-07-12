"""Main StoryAgent orchestrator for coordinating the planning and execution loop."""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

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
from .tension_evaluator import TensionEvaluator
from .lore_extractor import LoreExtractor
from .lore_contradiction_detector import LoreContradictionDetector
from .coherence_metrics import CoherenceMetrics
from .multi_stage_planner import MultiStagePlanner
from .character_detector import CharacterDetector
from ..tools.registry import ToolRegistry
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..memory.summarizer import SceneSummarizer
from ..plot.manager import PlotOutlineManager
from ..contracts.conditions import CheckContext, Condition, evaluate_conditions


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
        config: dict,
        save_prompts: bool = False
    ):
        """Initialize story agent.
        
        Args:
            project_path: Path to novel project
            llm_interface: LLM interface (CodexInterface or similar)
            tool_registry: Registry of available tools
            config: Project configuration
            save_prompts: Whether to save prompts to files (Phase 7A.5)
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
        self.character_detector = CharacterDetector(self.memory, config)
        
        # Phase 7A.3 components
        self.tension_evaluator = TensionEvaluator(config, llm_interface)
        
        # Phase 7A.4 components
        self.lore_extractor = LoreExtractor(llm_interface, self.memory, config)
        self.lore_detector = LoreContradictionDetector(self.memory, self.vector, config, llm_interface)

        # Phase 3 (Emergent Coherence) — per-tick coherence instrumentation
        self.coherence_metrics = CoherenceMetrics(self.project_path, self.memory, self.vector, config, self.llm)
        
        # Phase 7A.5 components (optional)
        self.use_multi_stage = config.get('generation.use_multi_stage_planner', True)
        if self.use_multi_stage:
            prompts_dir = self.project_path / "prompts" if save_prompts else None
            self.multi_stage_planner = MultiStagePlanner(
                llm_interface,
                self.memory,
                self.vector,
                self.tools,
                config,
                save_prompts=save_prompts,
                prompts_dir=prompts_dir
            )
        
        # Plot-first components (config feeds the arc-pressure beat schedule, Phase 3)
        self.plot_manager = PlotOutlineManager(self.project_path, llm_interface, config)

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
            # Check if plot-first mode is enabled
            # Skip plot-first for tick 1 to allow character/world establishment
            use_plot_first = self.config.get('generation.use_plot_first', False)
            plot_first_start_tick = self.config.get('generation.plot_first_start_tick', 2)
            current_beat = None
            finale_info = None

            if use_plot_first and tick >= plot_first_start_tick:
                # Phase 3 sacred finale: on the finale tick Python owns the ask. The
                # three-step chain (pending-beat screen, authored finale beat,
                # deterministic template) replaces normal beat selection; a total
                # failure falls through to the normal path below, so the worst case
                # is exactly today's behavior.
                if self._sacred_finale_applies(tick):
                    current_beat, ask_source = self._sacred_finale_beat(tick)
                    if current_beat is not None:
                        finale_info = {
                            "ask_source": ask_source,
                            "retries_used": 0,
                            "loops_suppressed": 0,
                        }
                        print(f"   🎬 Sacred finale ({ask_source}): {current_beat.description}")

                if current_beat is None:
                    # Check if we need to regenerate beats
                    if self._needs_beat_regeneration():
                        print("   📖 Generating plot beats...")
                        beats_ahead = self.config.get('generation.plot_beats_ahead', 5)
                        try:
                            new_beats = self.plot_manager.generate_next_beats(count=beats_ahead)
                            self.plot_manager.add_beats(new_beats)
                            print(f"        Generated {len(new_beats)} new plot beats")
                        except Exception as e:
                            print(f"        ⚠️  Beat generation failed: {e}")
                            # Fallback to reactive mode if configured
                            if not self.config.get('generation.fallback_to_reactive', True):
                                raise

                    # Get next beat to execute
                    current_beat = self.plot_manager.get_next_beat()
                    if current_beat:
                        print(f"   🎯 Executing beat: {current_beat.description}")
                    elif not self.config.get('generation.fallback_to_reactive', True):
                        raise RuntimeError("No plot beats available and fallback disabled")
            
            # Step 1: Gather context
            print("   1. Gathering context...")
            context = self.context_builder.build_planner_context(self.state, current_beat=current_beat)
            
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
                            # Point POV at the real ID unless it already names a real character
                            if plan.get("pov_character") and plan["pov_character"] not in self.memory.list_characters():
                                plan["pov_character"] = char_id
                            break

            # Resolve planner POV/location refs (name/nickname/ID) to canonical IDs
            self._resolve_plan_entities(plan)

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
            
            # Inject beat constraints into plan before building writer context
            if use_plot_first and current_beat:
                plan["plot_beat"] = {
                    "description": current_beat.description,
                    "characters_involved": current_beat.characters_involved,
                    "location": current_beat.location,
                    "tension_target": current_beat.tension_target,
                    "plot_threads": current_beat.plot_threads
                }
                # Phase 3 contracts Slice 1: show the writer what will be checked
                # (rendered as plain language in the plot beat section).
                if (self.config.get('generation.use_contracts', False)
                        and getattr(current_beat, "postconditions", None)):
                    plan["plot_beat"]["postconditions"] = current_beat.postconditions

            # Phase 3 sacred finale: ending-mode writer instruction (settled by
            # default; ONE deliberate hook when coherence.ending_hook is set).
            if finale_info is not None:
                plan["finale_mode"] = (
                    "hook" if self.config.get('coherence.ending_hook', False) else "settled"
                )

            writer_context = self.writer_context_builder.build_writer_context(
                plan,
                execution_results,
                self.state
            )
            
            scene_data = self.writer.write_scene(writer_context)
            
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
            
            # Step 7.5: Evaluate tension (Phase 7A.3)
            print("   7.5. Evaluating tension...")
            tension_result = self.tension_evaluator.evaluate_tension(
                scene_data["text"],
                writer_context
            )

            # Step 7.6: Phase 3 #2, one bounded revision pass toward the arc-pressure
            # target. On the sacred finale tick the bounded re-roll supersedes it
            # (staging, not wording, sets the tension floor; one LLM budget, not two).
            scene_data, tension_result = self._control_scene_tension(
                scene_data, tension_result, tick, writer_context, finale_info
            )

            print("   8. Committing scene...")
            scene_id = self.committer.commit_scene(scene_data, tick, plan)

            if eval_result:
                try:
                    self.memory.save_scene_qa(scene_id, tick, eval_result)
                except Exception:
                    pass
                try:
                    self._update_beats_from_evaluation(scene_id, plan, eval_result)
                except Exception:
                    pass
            
            # Step 8.5: Update scene with tension data (Phase 7A.3)
            if tension_result.get('enabled'):
                scene = self.memory.load_scene(scene_id)
                if scene:
                    scene.tension_level = tension_result['tension_level']
                    scene.tension_category = tension_result['tension_category']
                    self.memory.save_scene(scene)
                    print(f"        Tension: {tension_result['tension_level']}/10 ({tension_result['tension_category']})")


            # Step 8.6: Detect new characters (Phase 6)
            if self.config.get('generation.auto_detect_characters', True):
                print("   8.6. Detecting new characters...")
                new_characters = self.character_detector.find_new_characters(scene_data["text"])
                if new_characters:
                    print(f"        Found {len(new_characters)} new character(s): {', '.join(new_characters)}")
                    
                    # Check if we should prompt or auto-create
                    prompt_for_creation = self.config.get('generation.prompt_for_character_creation', True)
                    auto_create = self.config.get('generation.auto_create_minor_characters', False)
                    
                    if auto_create:
                        # Auto-create stubs for all new characters
                        for name in new_characters:
                            char_id = self.character_detector.create_character_stub(name)
                            print(f"        ✓ Created stub for '{name}' ({char_id})")
                    elif prompt_for_creation:
                        # Prompt user for each character
                        print(f"        💡 Tip: Run 'novel list characters' to see tracked characters")
                        print(f"        💡 Consider creating entities for: {', '.join(new_characters)}")
                        print(f"        💡 Use character.generate tool in next tick or enable auto_create_minor_characters")
            
            # Step 9: Extract facts (Phase 5)
            print("   9. Extracting facts...")
            facts = self._extract_facts_with_retry(
                scene_data["text"],
                writer_context
            )

            # Step 9.5: Sacred finale loop discipline (Phase 3): a settled ending
            # quarantines the finale's freshly minted loops before they are applied.
            if facts and finale_info is not None:
                facts = self._quarantine_finale_loops(facts, finale_info)

            # Step 9.6: Judged extractor resolutions (Phase 3, Slice 0 follow-ups):
            # the extractor's open_loops_resolved claims face the same one-loop,
            # one-scene judge as beat claims before anything closes (the 2026-07-11
            # run's finale sweep closed 47 loops unaudited). Gated by
            # coherence.loop_closure; when off, the facts pass through untouched and
            # EntityUpdater keeps the old unjudged behavior exactly.
            extractor_closure_result = None
            if facts:
                facts, extractor_closure_result = self._judge_extractor_resolutions(
                    facts, scene_id, scene_data["text"]
                )

            # Step 10: Update entities (Phase 5)
            print("   10. Updating entities...")
            update_stats = {}
            if facts:  # Only update if extraction succeeded
                update_stats = self.entity_updater.apply_updates(facts, tick, scene_id, writer_context)
                
                # Step 11: Re-index updated entities (Phase 5)
                print("   11. Syncing vector database...")
                self._reindex_updated_entities(facts)

            # Step 11.5: Verify beat execution and mark complete (Phase 5;
            # contract-aware since Phase 3 contracts Slice 1). Runs after fact
            # extraction and entity updates (steps 9-11) so state-reading
            # contract checks evaluate the post-scene world, not a stale one
            # (2026-07-10 run, docs/progress_report_20260710.md section 5).
            contract_result = None
            if use_plot_first and current_beat:
                print("   11.5. Verifying beat execution...")
                contract_result = self._verify_and_complete_beat(
                    current_beat,
                    plan,
                    scene_data["text"],
                    scene_id,
                    tension_result.get("tension_level"),
                    tick,
                )

            # Step 11.6: Judged loop closure (Phase 3, Slice 0 of the interleaving
            # design): a beat that just completed verification and claims
            # resolves_loops gets each claim confirmed by a focused one-loop,
            # one-scene judge before any loop is closed. Gated by
            # coherence.loop_closure; a failure here never breaks the tick.
            loop_closure_result = None
            if use_plot_first and current_beat:
                loop_closure_result = self._close_claimed_loops(
                    current_beat, scene_id, scene_data["text"]
                )

            # Step 11.7: Finale loop expiry (Phase 3, Slice 0 follow-ups): on the
            # finale tick, AFTER the scene's own judged closures (steps 9.6 and
            # 11.6), every still-open loop is marked expired ("left open at story
            # end") so end-of-run accounting stays honest instead of mass-swept.
            expiry_result = None
            if self._sacred_finale_applies(tick):
                expiry_result = self._expire_finale_loops(scene_id)

            # Step 11.8: Thread attribution (Phase 3, interleaving Slice T1):
            # the committed scene joins its beat's primary thread's trace
            # (implicit "main" when there is no beat or no labels, so the
            # trace stays total). Pure instrumentation, never breaks a tick.
            thread_result = self._update_thread_registry(
                tick, scene_id, tension_result, current_beat
            )

            # Step 12: Extract lore (Phase 7A.4)
            print("   12. Extracting lore...")
            lore_items = self._extract_lore_with_retry(
                scene_data["text"],
                writer_context,
                tick
            )
            if lore_items:
                print(f"        Found {len(lore_items)} lore items")
                self._save_lore_items(lore_items, scene_id, tick)
            
            # Step 13: Check for goal promotion (Phase 7A.2)
            print("   13. Checking goal promotion...")
            promotion_result = self._check_goal_promotion(tick)
            
            # Step 14: Update state
            self.state["current_tick"] += 1
            self._save_state()

            # Phase 3: record per-tick coherence metrics (instrumentation only)
            coherence_record = self._record_coherence_metrics(
                tick, scene_id, scene_data, tension_result, contract_result, finale_info,
                loop_closure_result=loop_closure_result,
                loops_deduped=self._loops_deduped_metric(facts, update_stats),
                loops_capped=self._loops_capped_metric(facts, update_stats),
                expiry_result=expiry_result,
                thread_result=thread_result,
            )

            result = {
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

            scene_generation = self._scene_generation_meta(scene_data)
            if scene_generation:
                result["scene_generation"] = scene_generation

            if coherence_record:
                result["coherence"] = coherence_record
            
            if promotion_result:
                result["goal_promoted"] = promotion_result

            if contract_result:
                result["contract"] = contract_result

            if loop_closure_result:
                result["loop_closure"] = loop_closure_result

            if thread_result:
                result["thread"] = thread_result

            if extractor_closure_result:
                result["extractor_closure"] = extractor_closure_result

            if expiry_result:
                result["loop_expiry"] = expiry_result

            if finale_info:
                result["finale"] = finale_info

            if tension_result.get('enabled'):
                result["tension"] = {
                    "level": tension_result['tension_level'],
                    "category": tension_result['tension_category']
                }
            
            # Include multi-stage planner stats if available (Phase 7A.5)
            if self.use_multi_stage and hasattr(self.multi_stage_planner, 'stage_stats'):
                result["stage_stats"] = self.multi_stage_planner.stage_stats
            
            return result
        
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
            
            print("   10. Committing scene...")
            scene_id = self.committer.commit_scene(scene_data, tick, plan)

            if eval_result:
                try:
                    self.memory.save_scene_qa(scene_id, tick, eval_result)
                except Exception:
                    pass
                try:
                    self._update_beats_from_evaluation(scene_id, plan, eval_result)
                except Exception:
                    pass
            
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
                update_stats = self.entity_updater.apply_updates(facts, tick, scene_id, writer_context)
            
            # Step 14: Extract lore (Phase 7A.4)
            print("   13. Extracting lore...")
            lore_items = self._extract_lore_with_retry(
                scene_data["text"],
                writer_context,
                tick
            )
            if lore_items:
                print(f"        Found {len(lore_items)} lore items")
                self._save_lore_items(lore_items, scene_id, tick)
            
            # Step 15: Sync vector database
            print("   14. Syncing vector database...")
            self.vector.index_scene(self.memory.load_scene(scene_id))
            
            # Increment tick
            self.state["current_tick"] += 1
            self._save_state()

            # Thread attribution (Phase 3, interleaving Slice T1): tick 0 has no
            # beat, so the scene lands on the implicit "main" thread (no tension
            # signal yet), keeping the trace total from the first scene.
            thread_result = self._update_thread_registry(tick, scene_id, None, None)

            # Phase 3: record per-tick coherence metrics (tick 0 has no tension evaluation)
            coherence_record = self._record_coherence_metrics(
                tick, scene_id, scene_data, None, thread_result=thread_result
            )

            result = {
                "success": True,
                "tick": tick,
                "scene_id": scene_id,
                "scene_file": f"scenes/scene_{tick:03d}.md",
                "word_count": scene_data["word_count"],
                "plan_file": str(plan_file),
                "update_stats": update_stats,
                "actions_executed": len(execution_results.get("actions_executed", []))
            }

            scene_generation = self._scene_generation_meta(scene_data)
            if scene_generation:
                result["scene_generation"] = scene_generation

            if coherence_record:
                result["coherence"] = coherence_record

            return result
        
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
    
    def _resolve_plan_entities(self, plan: Dict) -> None:
        """Map planner-supplied pov_character / target_location refs to canonical IDs.

        The planner may emit a canonical ID (``C000``), a name, or a nickname; it
        may also emit a name that happens to start with ``C``/``L``. Resolve against
        current memory rather than guessing from the prefix, so a real reference
        lands on its ID and a name like "Caleb" is not mistaken for an ID. Refs
        that resolve to nothing are left untouched for the caller's fallback.
        """
        from ..memory.entity_resolver import EntityResolver
        resolver = EntityResolver(self.memory)
        pov = plan.get("pov_character")
        if pov:
            cid = resolver.resolve_character(pov)
            if cid:
                plan["pov_character"] = cid
        loc = plan.get("target_location")
        if loc:
            lid = resolver.resolve_location(loc)
            if lid:
                plan["target_location"] = lid

    def _update_plan_with_entity_ids(self, plan: Dict, entity_results: Dict):
        """Update plan with real entity IDs after generation.

        Args:
            plan: The plan to update (modified in place)
            entity_results: Results from entity generation
        """
        # Resolve any planner refs that point at entities now in memory.
        self._resolve_plan_entities(plan)
        existing_chars = set(self.memory.list_characters())
        existing_locs = set(self.memory.list_locations())
        for action in entity_results.get("actions_executed", []):
            if action.get("tool") == "character.generate" and action.get("success"):
                char_id = action.get("result", {}).get("character_id")
                # Fallback: still-unresolved POV placeholder -> freshly generated char.
                if char_id and plan.get("pov_character") and plan["pov_character"] not in existing_chars:
                    plan["pov_character"] = char_id

            elif action.get("tool") == "location.generate" and action.get("success"):
                loc_id = action.get("result", {}).get("location_id")
                if loc_id and plan.get("target_location") and plan["target_location"] not in existing_locs:
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
    
    def _update_beats_from_evaluation(self, scene_id: str, plan: Dict[str, Any], eval_result: Dict[str, Any]) -> None:
        if isinstance(self.config, dict):
            mode = self.config.get("plot", {}).get("beat_mode", "soft_hint")
        else:
            mode = self.config.get("plot.beat_mode", "soft_hint")
        if mode != "guided":
            return
        beat_target = plan.get("beat_target") or {}
        if not isinstance(beat_target, dict):
            return
        beat_id = beat_target.get("beat_id")
        if not beat_id:
            return
        alignment = eval_result.get("beat_hint_alignment") or {}
        if not isinstance(alignment, dict):
            return
        if alignment.get("beat_id") != beat_id:
            return
        label = alignment.get("label")
        if label not in ("medium", "high"):
            return
        score = alignment.get("score")
        try:
            manager = PlotOutlineManager(self.project_path)
            outline = manager.load_outline()
        except Exception:
            return
        updated = False
        for beat in outline.beats:
            if getattr(beat, "id", None) == beat_id:
                # Mark beat as completed for consistency with CLI summary,
                # while keeping executed_in_scene/execution_notes as metadata.
                setattr(beat, "status", "completed")
                setattr(beat, "executed_in_scene", scene_id)
                notes = getattr(beat, "execution_notes", "") or ""
                extra = f"Executed in {scene_id} with alignment {label}"
                if isinstance(score, (int, float)):
                    extra += f" (score={score})"
                if notes:
                    notes = notes.rstrip()
                    extra = notes + " " + extra
                setattr(beat, "execution_notes", extra)
                updated = True
                break
        if updated:
            try:
                manager.save_outline(outline)
            except Exception:
                return
    
    def _generate_plan(self, context: dict) -> dict:
        """Generate a plan using the planner LLM.
        
        Args:
            context: Context dictionary for prompt
        
        Returns:
            Parsed plan dictionary
        
        Raises:
            ValueError: If LLM response cannot be parsed
        """
        # Use multi-stage planner if enabled (Phase 7A.5)
        if self.use_multi_stage:
            # Check if we have a current beat to execute (from plot-first mode)
            # Get beat from context if it was passed in
            beat_to_execute = context.get('_current_beat')  # Internal key
            
            if beat_to_execute is not None:
                # Use beat-first planning
                try:
                    return self.multi_stage_planner.plan_for_beat(self.state, beat_to_execute)
                except Exception as e:
                    print(f"        ⚠️  Beat-first planning failed: {e}")
                    # Fall back to normal planning
                    pass
            
            # Legacy beat_mode check for backwards compatibility
            try:
                if isinstance(self.config, dict):
                    beat_mode = self.config.get("plot", {}).get("beat_mode", "soft_hint")
                else:
                    beat_mode = self.config.get("plot.beat_mode", "soft_hint")
            except Exception:
                beat_mode = "soft_hint"

            if beat_mode == "guided":
                try:
                    manager = PlotOutlineManager(self.project_path)
                    next_beat = manager.get_next_beat()
                except Exception:
                    next_beat = None

                if next_beat is not None:
                    try:
                        return self.multi_stage_planner.plan_for_beat(self.state, next_beat)
                    except Exception:
                        # Fall back to normal planning if beat-first path fails
                        pass

            return self.multi_stage_planner.plan(self.state)
        
        # Otherwise use legacy single-stage planning
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

    def _maybe_rewrite_for_tension(self, scene_data, tension_result, tick, writer_context):
        """Phase 3 #2: one bounded revision pass to pull tension toward the arc target.

        When the scored scene is more than `coherence.tension_rewrite_threshold` off the
        target, revise once and re-score; keep the revision only if it lands closer.
        Never raises — a failure leaves the original scene untouched.
        """
        try:
            from .arc_pressure import (compute_target_tension, needs_tension_rewrite,
                                       rewrite_futile, rewrite_improved, last_scene_tension)

            if not self.config.get('coherence.tension_rewrite', True):
                return scene_data, tension_result
            if not (tension_result and tension_result.get('enabled')):
                return scene_data, tension_result
            target = compute_target_tension(tick, self.config)
            current = tension_result.get('tension_level')
            threshold = self.config.get('coherence.tension_rewrite_threshold', 2)
            if not needs_tension_rewrite(current, target, threshold):
                return scene_data, tension_result

            # Phase 3 arc-phase mandate: a drop of a full transition step or more cannot
            # be rewritten away (the EVENTS set the floor, and only the planner changes
            # those), so skip the revision pass instead of wasting two LLM calls.
            step = self.config.get('coherence.tension_step_for_transition', 3)
            if (self.config.get('coherence.arc_phase_mandate', True)
                    and rewrite_futile(current, target, step)):
                print(f"   7.6. Tension {current}/10 vs target {target:g}: drop too big for a "
                      f"prose rewrite; skipping (events set the floor)")
                return scene_data, tension_result

            print(f"   7.6. Tension {current}/10 off target {target:g} — revising once...")
            prev_tension = last_scene_tension(self.memory)
            # Phase 3 segment plumbing: prefer the meta variant (carries the
            # completion guarantee's trimmed flag); plain revise_for_tension is
            # the fallback so hand-rolled writers keep working.
            revise_meta = {}
            reviser = getattr(self.writer, "revise_for_tension_with_meta", None)
            if reviser is not None:
                revised_text, revise_meta = reviser(
                    scene_data["text"], target, current, writer_context, prev_tension
                )
            else:
                revised_text = self.writer.revise_for_tension(
                    scene_data["text"], target, current, writer_context, prev_tension
                )
            if not revised_text:
                return scene_data, tension_result

            new_result = self.tension_evaluator.evaluate_tension(revised_text, writer_context)
            new_level = new_result.get('tension_level') if new_result.get('enabled') else None
            if rewrite_improved(new_level, current, target):
                print(f"        revised tension {current} -> {new_level} (target {target:g})")
                new_result['rewritten'] = True
                new_result['tension_pre_rewrite'] = current
                scene_data = {**scene_data, "text": revised_text,
                              "word_count": len(revised_text.split())}
                if revise_meta.get("trimmed"):
                    # The adopted revision was trim-flagged; the committed scene
                    # must carry that truth (scene_truncated in metrics).
                    scene_data["trimmed"] = True
                return scene_data, new_result

            print(f"        revision not closer ({new_level}); keeping original")
            tension_result['rewritten'] = False
            return scene_data, tension_result
        except Exception as e:
            logging.getLogger(__name__).warning(f"Tension rewrite failed (tick {tick}): {e}")
            return scene_data, tension_result

    def _sacred_finale_applies(self, tick) -> bool:
        """Phase 3 sacred finale gate. Never raises; False means today's behavior."""
        try:
            from .finale import is_finale_tick
            return is_finale_tick(tick, self.config)
        except Exception:
            return False

    def _sacred_finale_beat(self, tick):
        """Phase 3 sacred finale: the guaranteed finale ask, run in place of normal
        beat selection at the top of the finale tick.

        Three-step fallback chain (addendum 5 design consequences):
        (a) the next pending beat, when its tension_target sits at or under the
            finale cap AND a one-call LLM screen judges it a genuine denouement;
        (b) otherwise a dedicated finale beat authored with the strict prompt
            (retried once on a malformed response);
        (c) otherwise a deterministic template beat built from canon, so the
            guarantee is unconditional.
        A bypassed pending beat is not deleted: it stays pending with an
        execution note. Authored/template beats are persisted to the outline via
        add_beats (with sanitization) so step 11.5 beat verification and contract
        bookkeeping work on a real beat. Returns (beat, ask_source), or
        (None, None) on total failure (the tick proceeds exactly as today).
        """
        try:
            from .finale import (author_finale_beat, beat_satisfies_finale_tension,
                                 screen_beat_for_finale, template_finale_beat)

            pending = self.plot_manager.get_next_beat()
            if pending is not None and beat_satisfies_finale_tension(pending, self.config):
                screen = screen_beat_for_finale(self.llm, pending, self.config)
                if screen and screen.get("denouement"):
                    reason = screen.get("reason", "")
                    print(f"        ✓ Pending beat {pending.id} passes the finale screen"
                          + (f": {reason}" if reason else ""))
                    return pending, "pending_beat"
            if pending is not None:
                self._note_finale_bypass(pending, tick)

            beat = author_finale_beat(
                self.llm, self.plot_manager, self.memory, self.state, self.config
            )
            source = "authored"
            if beat is None:
                print("        Finale beat authoring failed; using the deterministic template")
                beat = template_finale_beat(self.memory, self.state, self.config)
                source = "template"
            persisted = self.plot_manager.add_beats([beat])
            return (persisted[0] if persisted else beat), source
        except Exception as e:
            logging.getLogger(__name__).warning(f"Sacred finale ask failed (tick {tick}): {e}")
            return None, None

    def _note_finale_bypass(self, beat, tick) -> None:
        """Record on a bypassed pending beat that the sacred finale superseded it.

        The beat is NOT deleted or abandoned: it stays pending (overtime ticks can
        still consume it), it just carries the note. Never raises.
        """
        try:
            outline = self.plot_manager.load_outline()
            for b in outline.beats:
                if b.id == beat.id:
                    note = f"Superseded by the sacred finale at tick {tick}; left pending"
                    notes = (b.execution_notes or "").rstrip()
                    b.execution_notes = f"{notes} {note}".strip()
                    break
            self.plot_manager.save_outline(outline)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to note finale bypass on beat {getattr(beat, 'id', '?')}: {e}"
            )

    def _control_scene_tension(self, scene_data, tension_result, tick, writer_context,
                               finale_info=None):
        """Step 7.6 dispatch: normal ticks get the bounded prose rewrite; the sacred
        finale tick gets the bounded full re-roll instead (never both)."""
        if finale_info is not None:
            return self._finale_reroll_for_tension(
                scene_data, tension_result, writer_context, finale_info
            )
        return self._maybe_rewrite_for_tension(scene_data, tension_result, tick, writer_context)

    def _finale_reroll_for_tension(self, scene_data, tension_result, writer_context,
                                   finale_info):
        """Phase 3 sacred finale: bounded fresh re-rolls toward the finale tension cap.

        Addendum 5 (sunshine test): the hot finale flips are STAGING choices (the
        same beat text renders as quiet reflection or as a staged event), which a
        prose rewrite cannot unstage; only a fresh render re-flips the coin, and
        the cap referees the flips reliably. Up to coherence.finale_retries full
        writer re-rolls: the first render at or under the cap wins; if none pass,
        the lowest-scoring render is kept. Never raises; with the scorer
        unavailable the first render stands.
        """
        try:
            from .finale import finale_tension_cap

            cap = finale_tension_cap(self.config)
            retries = int(self.config.get('coherence.finale_retries', 2))
            enabled = bool(tension_result and tension_result.get('enabled'))
            level = tension_result.get('tension_level') if enabled else None
            if level is None or level <= cap or retries <= 0:
                return scene_data, tension_result

            print(f"   7.6. Finale tension {level}/10 above cap {cap:g}: re-rolling the "
                  f"scene (up to {retries} fresh render(s))...")
            candidates = [(scene_data, tension_result, level)]
            for attempt in range(1, retries + 1):
                finale_info["retries_used"] = attempt
                new_scene = self.writer.write_scene(writer_context)
                new_result = self.tension_evaluator.evaluate_tension(
                    new_scene["text"], writer_context
                )
                new_level = (new_result.get('tension_level')
                             if new_result.get('enabled') else None)
                if new_level is None:
                    print("        scorer unavailable mid-retry; keeping the best render so far")
                    break
                print(f"        re-roll {attempt}: tension {new_level}/10 (cap {cap:g})")
                candidates.append((new_scene, new_result, new_level))
                if new_level <= cap:
                    return new_scene, new_result

            best_scene, best_result, best_level = min(candidates, key=lambda c: c[2])
            if best_level > cap:
                print(f"        no render passed the cap; keeping the lowest ({best_level}/10)")
            return best_scene, best_result
        except Exception as e:
            logging.getLogger(__name__).warning(f"Finale re-roll failed: {e}")
            return scene_data, tension_result

    def _quarantine_finale_loops(self, facts, finale_info):
        """Phase 3 sacred finale: settled-ending loop discipline (step 9.5).

        The sunshine test minted 3-5 new loops per denouement despite "nothing is
        at stake" (4 of 5 scenes pivoted to a hook), so telling does not work: on
        a settled finale the extracted open_loops_created are quarantined here,
        at the agent level, before entity_updater.apply_updates sees them, so
        extraction itself stays honest. Hook mode (coherence.ending_hook) lets
        them through untouched. Never raises.
        """
        try:
            if self.config.get('coherence.ending_hook', False):
                return facts
            from .finale import suppress_finale_loops
            facts, suppressed = suppress_finale_loops(facts)
            finale_info["loops_suppressed"] = len(suppressed)
            if suppressed:
                print(f"        suppressed {len(suppressed)} finale loop(s): "
                      + "; ".join(suppressed))
            return facts
        except Exception as e:
            logging.getLogger(__name__).warning(f"Finale loop quarantine failed: {e}")
            return facts

    def _close_claimed_loops(self, current_beat, scene_id, scene_text):
        """Phase 3 (Slice 0 of the interleaving design): judged loop closure (step 11.6).

        Runs only when the beat actually completed verification against THIS
        scene (step 11.5 marked it completed): completion nominates the beat's
        resolves_loops claims, and loop_closure.close_claimed_loops has a
        focused judge confirm each before memory.resolve_open_loop runs.
        Returns the closure payload for the tick result and the rubric, or
        None when the coherence.loop_closure gate is off (default True since
        the 2026-07-11 validation run), the beat did not complete, or the
        beat claims nothing. Refusal reasons are printed at the tick console
        level (they also persist in the result dict). Never raises.
        """
        try:
            from .loop_closure import close_claimed_loops

            if not self.config.get('coherence.loop_closure', True):
                return None
            if not (getattr(current_beat, "resolves_loops", None) or []):
                return None
            if not self._beat_completed_in_scene(current_beat, scene_id):
                return None
            result = close_claimed_loops(
                self.llm, self.memory, current_beat, scene_id, scene_text, self.config
            )
            if result:
                closed = result.get("closed") or []
                if closed:
                    print(f"        ✓ Closed {len(closed)} loop(s) via beat "
                          f"{current_beat.id}: {', '.join(closed)}")
                elif result.get("judged"):
                    print(f"        Loop claims not confirmed by the judge "
                          f"({result['judged']} checked); leaving open")
                for entry in result.get("refused") or []:
                    print(f"        ✗ Loop {entry['loop']} claim refused: "
                          f"{entry['reason']}")
            return result
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Judged loop closure failed (beat {getattr(current_beat, 'id', '?')}): {e}"
            )
            return None

    def _beat_completed_in_scene(self, beat, scene_id) -> bool:
        """True when the beat completed verification against this scene.

        Reads the persisted outline (step 11.5 writes status and
        executed_in_scene there via _mark_beat_complete), so a beat kept
        pending by a semantic miss or a contract failure never nominates its
        loop claims. Never raises; unreadable outline means False.
        """
        try:
            outline = self.plot_manager.load_outline()
            for b in outline.beats:
                if b.id == beat.id:
                    return b.status == "completed" and b.executed_in_scene == scene_id
        except Exception:
            pass
        return False

    def _judge_extractor_resolutions(self, facts, scene_id, scene_text):
        """Phase 3 (Slice 0 follow-ups): judge extractor loop-resolution claims (step 9.6).

        With coherence.loop_closure on, the extractor's open_loops_resolved
        claims are removed from the facts (so EntityUpdater's unjudged path
        never sees them) and each is confirmed by the same focused judge as
        beat claims before memory.resolve_open_loop runs, bounded per tick by
        coherence.extractor_resolutions_judged_cap. With the gate off the
        facts pass through untouched: the old unjudged behavior, kept exactly
        so A/B stays possible. Returns (facts, result-or-None). Never raises.
        """
        try:
            if not self.config.get('coherence.loop_closure', True):
                return facts, None
            claims = (facts or {}).get("open_loops_resolved") or []
            if not claims:
                return facts, None
            # Strip the claims first: even if judging fails below, the unjudged
            # mass-sweep must not silently come back (the honest-accounting rule).
            facts = dict(facts)
            facts["open_loops_resolved"] = []

            from .loop_closure import judge_extractor_resolutions
            result = judge_extractor_resolutions(
                self.llm, self.memory, claims, scene_id, scene_text, self.config
            )
            if result:
                closed = result.get("closed") or []
                if closed:
                    print(f"        ✓ Closed {len(closed)} loop(s) via judged extractor "
                          f"claims: {', '.join(closed)}")
                for entry in result.get("refused") or []:
                    print(f"        ✗ Extractor claim on {entry['loop']} refused: "
                          f"{entry['reason']}")
                capped = result.get("capped") or []
                if capped:
                    print(f"        ⚠️  Extractor resolution claims over the judged cap "
                          f"ignored: {', '.join(capped)}")
            return facts, result
        except Exception as e:
            logging.getLogger(__name__).warning(f"Judged extractor resolutions failed: {e}")
            return facts, None

    def _expire_finale_loops(self, scene_id):
        """Phase 3 (Slice 0 follow-ups): expire still-open loops at the finale (step 11.7).

        Gated by the same coherence.loop_closure flag as the judged closures,
        so an A/B run with the gate off keeps the old end-of-story behavior
        exactly. Returns the expiry payload for the tick result and the
        rubric, or None (gate off, nothing to expire is still a payload).
        Never raises.
        """
        try:
            from .loop_closure import expire_open_loops_at_finale

            if not self.config.get('coherence.loop_closure', True):
                return None
            result = expire_open_loops_at_finale(self.memory, scene_id)
            if result and result.get("expired"):
                print(f"        Expired {len(result['expired'])} still-open loop(s) at "
                      f"story end ({result['dangling_threads']} dangling high/critical "
                      f"thread(s))")
            return result
        except Exception as e:
            logging.getLogger(__name__).warning(f"Finale loop expiry failed: {e}")
            return None

    def _loops_deduped_metric(self, facts, update_stats):
        """The rubric's loops_deduped value (Phase 3, Slice 0 creation hygiene).

        None (not 0) when the coherence.loop_dedup gate is off or no loop
        creations were attempted this tick, so "checked nothing" and "checked
        and deduped none" stay distinguishable (the contract-counter
        convention). Never raises.
        """
        try:
            if not self.config.get('coherence.loop_dedup', True):
                return None
            if not facts or not (facts.get("open_loops_created") or []):
                return None
            return int((update_stats or {}).get("loops_deduped", 0) or 0)
        except Exception:
            return None

    def _loops_capped_metric(self, facts, update_stats):
        """The rubric's loops_capped value (Phase 3, Slice 0 follow-ups).

        Same conventions as _loops_deduped_metric: None (not 0) when the
        coherence.loop_dedup gate is off or no loop creations were attempted
        this tick (the 2026-07-11 validation flagged log-only cap counts as an
        observability gap). Never raises.
        """
        try:
            if not self.config.get('coherence.loop_dedup', True):
                return None
            if not facts or not (facts.get("open_loops_created") or []):
                return None
            return int((update_stats or {}).get("loops_capped", 0) or 0)
        except Exception:
            return None

    def _update_thread_registry(self, tick, scene_id, tension_result, current_beat=None):
        """Phase 3 (interleaving Slice T1): thread attribution (step 11.8).

        Pure instrumentation: the committed scene is attributed to its beat's
        primary thread (the FIRST plot_threads label; implicit "main" when
        there is no beat or no labels), updating the thread's tension trace,
        membership, and consecutive-run count in memory/threads.json. Nothing
        reads the registry for decisions in this slice. Returns the
        attribution summary for the tick result and the rubric, or None on
        failure (the rubric's thread fields stay null, the
        None-when-unavailable convention). Never raises.
        """
        try:
            from .thread_registry import ThreadRegistry

            tension_level = (tension_result or {}).get("tension_level")
            result = ThreadRegistry(self.memory, self.config).attribute_scene(
                tick=tick,
                scene_id=scene_id,
                beat=current_beat,
                tension_level=tension_level,
            )
            if result:
                print(f"        Thread: {result['thread_name']} "
                      f"(run {result['run_length']}, {result['thread_count']} tracked)")
            return result
        except Exception as e:
            logging.getLogger(__name__).warning(f"Thread attribution failed (tick {tick}): {e}")
            return None

    @staticmethod
    def _scene_generation_meta(scene_data):
        """Write-until-concluded metadata for the tick result (Phase 3 segment plumbing).

        Returns {segments_used, concluded_naturally, trimmed} when the writer
        reported it, else None (hand-rolled writers, older scene dicts).
        """
        if not isinstance(scene_data, dict) or scene_data.get("segments_used") is None:
            return None
        return {
            "segments_used": scene_data.get("segments_used"),
            "concluded_naturally": scene_data.get("concluded_naturally"),
            "trimmed": scene_data.get("trimmed"),
        }

    def _record_coherence_metrics(self, tick, scene_id, scene_data, tension_result,
                                  contract_result=None, finale_result=None,
                                  loop_closure_result=None, loops_deduped=None,
                                  loops_capped=None, expiry_result=None,
                                  thread_result=None):
        """Phase 3 coherence instrumentation. Never raises (graceful degradation).

        Returns the per-tick metric record, or None if disabled/failed. A failure here
        must never break a tick or the multi-tick run loop, so everything is swallowed.
        """
        try:
            if not self.config.get('coherence.enabled', True):
                return None
            scene_data = scene_data if isinstance(scene_data, dict) else {}
            primary = (self.state.get("story_goals") or {}).get("primary") or {}
            return self.coherence_metrics.record_tick(
                tick=tick,
                scene_id=scene_id,
                scene_text=scene_data.get("text"),
                word_count=scene_data.get("word_count", 0),
                # Write-until-concluded loop (Phase 3, segment plumbing): how many
                # segments produced the scene, and whether the trim fallback fired.
                # None when the writer did not report (hand-rolled writers).
                scene_segments=scene_data.get("segments_used"),
                scene_truncated=scene_data.get("trimmed"),
                tension_result=tension_result,
                goal_description=primary.get("description"),
                contract_result=contract_result,
                finale_result=finale_result,
                loops_closed_by_beat=(
                    len(loop_closure_result.get("closed") or [])
                    if loop_closure_result else None
                ),
                loops_deduped=loops_deduped,
                loops_capped=loops_capped,
                # Finale expiry (Phase 3, Slice 0 follow-ups): counts only on the
                # finale tick with the loop_closure gate on; None otherwise.
                loops_expired=(
                    len(expiry_result.get("expired") or [])
                    if expiry_result else None
                ),
                dangling_threads=(
                    expiry_result.get("dangling_threads")
                    if expiry_result else None
                ),
                thread_result=thread_result,
            )
        except Exception as e:
            logging.getLogger(__name__).warning(f"Coherence metrics failed (tick {tick}): {e}")
            return None
    
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
    
    def _check_goal_promotion(self, tick: int) -> dict:
        """Check if a story goal should be auto-promoted (Phase 7A.2).
        
        After 10-15 scenes, promote the most active protagonist-related loop
        to become the primary story goal. Skips if user specified a goal.
        
        Args:
            tick: Current tick number
            
        Returns:
            Dictionary with promotion info if promotion occurred, None otherwise
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Only check during the promotion window
        if tick < 10 or tick > 15:
            return None
        
        # Check if already promoted or user-specified
        story_goals = self.state.get('story_goals', {})
        primary = story_goals.get('primary')
        if primary:
            # Don't auto-promote if user specified a goal or already promoted
            if primary.get('source') == 'user_specified':
                logger.debug("Primary goal was user-specified, skipping auto-promotion")
            return None
        
        # Get protagonist ID
        protagonist_id = self.state.get('active_character')
        if not protagonist_id:
            logger.debug("No protagonist set, skipping goal promotion")
            return None
        
        # Get all open loops
        open_loops = self.memory.get_open_loops()
        if not open_loops:
            logger.debug("No open loops, skipping goal promotion")
            return None
        
        # Find protagonist-related loops
        protagonist_loops = [
            loop for loop in open_loops
            if protagonist_id in loop.related_characters
        ]
        
        if not protagonist_loops:
            logger.debug("No protagonist-related loops, skipping goal promotion")
            return None
        
        # Find most mentioned loop (must have been mentioned at least 5 times)
        top_loop = max(
            protagonist_loops,
            key=lambda l: l.scenes_mentioned,
            default=None
        )
        
        if not top_loop or top_loop.scenes_mentioned < 5:
            logger.debug(f"Top loop only mentioned {top_loop.scenes_mentioned if top_loop else 0} times, need 5+")
            return None
        
        # Promote to story goal!
        top_loop.is_story_goal = True
        self.memory.save_open_loop(top_loop)
        
        # Update state
        story_goals['primary'] = {
            'loop_id': top_loop.id,
            'description': top_loop.description,
            'source': 'auto_promoted',
            'promoted_at_tick': tick
        }
        story_goals['promotion_tick'] = tick
        self.state['story_goals'] = story_goals
        
        logger.info(f"🎯 Story Goal Emerged: {top_loop.description}")
        print(f"\n🎯 Story Goal Emerged: {top_loop.description}\n")
        
        return {
            'loop_id': top_loop.id,
            'description': top_loop.description,
            'tick': tick,
            'mentions': top_loop.scenes_mentioned
        }
    
    def _extract_lore_with_retry(self, scene_text: str, scene_context: dict, tick: int) -> list:
        """Extract lore with retry logic for graceful degradation (Phase 7A.4).
        
        Args:
            scene_text: Scene prose text
            scene_context: Scene context dictionary
            tick: Current tick number
        
        Returns:
            List of lore items or empty list on failure
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # First attempt
            lore_items = self.lore_extractor.extract_lore(scene_text, scene_context, tick)
            return lore_items
            
        except Exception as e:
            logger.warning(f"Lore extraction failed: {e}")
            
            try:
                # Retry once
                logger.info("Retrying lore extraction...")
                lore_items = self.lore_extractor.extract_lore(scene_text, scene_context, tick)
                return lore_items
                
            except Exception as e2:
                logger.error(f"Lore extraction failed after retry: {e2}")
                # Return empty list on failure (graceful degradation)
                return []
    
    def _save_lore_items(self, lore_items: list, scene_id: str, tick: int):
        """Save extracted lore items to memory (Phase 7A.4).
        
        Args:
            lore_items: List of lore item dictionaries
            scene_id: Scene ID where lore was established
            tick: Current tick number
        """
        from ..memory.entities import Lore
        import logging
        logger = logging.getLogger(__name__)
        
        for item in lore_items:
            try:
                # Generate lore ID
                lore_id = self.memory.generate_lore_id()
                
                # Create Lore object
                lore = Lore(
                    id=lore_id,
                    lore_type=item.get('type', 'fact'),
                    content=item.get('content', ''),
                    category=item.get('category', 'other'),
                    source_scene_id=scene_id,
                    tick=tick,
                    importance=item.get('importance', 'normal'),
                    tags=item.get('tags', [])
                )
                
                # Save to memory
                self.memory.save_lore(lore)
                
                # Index in vector store for semantic search
                self.vector.index_lore(lore)
                
                # Check for contradictions
                self.lore_detector.update_contradictions(lore_id)
                
                logger.info(f"Saved lore {lore_id}: {lore.content[:50]}...")
                
            except Exception as e:
                logger.error(f"Failed to save lore item: {e}")
                continue
    
    def _needs_beat_regeneration(self) -> bool:
        """Check if we need to generate more plot beats (Phase 5).
        
        Returns:
            True if pending beats are below threshold
        """
        threshold = self.config.get('generation.plot_regeneration_threshold', 2)
        outline = self.plot_manager.load_outline()
        pending_count = sum(1 for beat in outline.beats if beat.status == "pending")
        return pending_count < threshold

    def _revise_horizon(self, reason: str, tick: int) -> Optional[Dict[str, Any]]:
        """Rolling horizon (Phase 2): regenerate the pending beats from current canon.

        Graceful degradation per repo convention: a revision failure must never
        kill the tick (which would stop a multi-tick ``run``).
        """
        try:
            beats_ahead = self.config.get('generation.plot_beats_ahead', 5)
            result = self.plot_manager.revise_horizon(
                reason=reason, count=beats_ahead, current_tick=tick
            )
            if result.get("abandoned") or result.get("generated"):
                print(f"        ↻ Rolling horizon: abandoned {len(result['abandoned'])}, "
                      f"generated {len(result['generated'])} beat(s)")
            return result
        except Exception as e:
            print(f"        ⚠️  Horizon revision failed: {e}")
            return None
    
    def _verify_beat_execution(self, scene_text: str, beat) -> bool:
        """Verify that the scene accomplished the plot beat (Phase 5).
        
        Args:
            scene_text: The scene prose text
            beat: The PlotBeat that was supposed to be executed
        
        Returns:
            True if beat was accomplished, False otherwise
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            prompt = f"""Evaluate if this scene accomplishes the following plot beat.

Plot Beat: {beat.description}

Scene Text:
{scene_text[:3000]}

IMPORTANT: Focus on SEMANTIC MEANING, not exact wording. The scene may use:
- Different character names/titles than the beat description
- Synonyms or alternative phrasings (e.g., "hunter" = "cleaner" = "assassin")
- Implicit rather than explicit depiction of events
- Different terminology for the same concepts

The beat is ACCOMPLISHED if the scene depicts the CORE EVENT happening, even if:
- Character names differ from the beat description
- The vocabulary/terminology differs
- It's shown through flashback, memory, or implication
- It's interwoven with other events
- The scene continues after the beat event

Answer YES if the essential meaning of the beat occurs in the scene.
Answer NO only if the core event genuinely does not happen at all.

Brief explanation (1 sentence), then your answer:
Answer:"""
            
            response = self.llm.generate(prompt, max_tokens=200)
            result = response.strip().upper().startswith("YES")
            
            if result:
                logger.info(f"Beat {beat.id} verified as accomplished")
            else:
                logger.warning(f"Beat {beat.id} may not be fully accomplished: {response[:100]}")
            
            return result
            
        except Exception as e:
            logger.error(f"Beat verification failed: {e}")
            # Default to True on error (graceful degradation)
            return True
    
    def _verify_and_complete_beat(
        self,
        current_beat,
        plan: dict,
        scene_text: str,
        scene_id: str,
        tension_level,
        tick: int,
    ) -> Optional[dict]:
        """Step 11.5: decide beat completion and route failures (Phase 5 + Phase 3 Slice 1).

        Verification signals, in order: trust the planner when it explicitly
        targeted this beat; otherwise gate on semantic similarity
        (generation.beat_verification_threshold); with verification off, auto-
        complete. When contracts are on and the beat carries postconditions,
        they are evaluated here (deterministic, tension already scored at step
        7.5) and recorded on the beat either way:

        - all conditions passing on a verified beat upgrades confidence
          (verification_method="contract");
        - any condition failing downgrades an otherwise-verified beat to the
          existing failure routing (rolling-horizon revision, or keep-pending).
          Never a raise: a hard contract gate would stall the multi-tick run
          loop on the first stubborn beat.

        Returns the contract payload for the tick result and metrics, or None
        when contracts did not run.
        """
        beat_target = plan.get("beat_target", {}) or {}
        planner_targeted = beat_target.get("beat_id") == current_beat.id

        # Compute semantic similarity score (always, for visibility)
        semantic_score = self.vector.compute_semantic_similarity(
            current_beat.description,
            scene_text[:3000]  # Use first 3000 chars
        )

        # Phase 3 contracts Slice 1: postconditions ride the beat; evaluate them
        # against the written scene and persist the verdict on the beat (audit
        # trail whether or not it changes the completion decision).
        contract_result = self._evaluate_beat_contract(current_beat, scene_text, tension_level)
        if contract_result is not None:
            self._record_contract_results(current_beat.id, contract_result)
        contract_failed = contract_result is not None and not contract_result["is_valid"]

        score_threshold = self.config.get('generation.beat_verification_threshold', 0.5)
        verified = False
        method = ""
        if planner_targeted:
            verified, method = True, "trusted_planner"
        elif not self.config.get('generation.verify_beat_execution', True):
            # Auto-mark complete without verification
            verified, method = True, "auto"
        elif semantic_score >= score_threshold:
            verified, method = True, "semantic"

        if verified and not contract_failed:
            if contract_result is not None:
                # Deterministic postconditions all passed: upgrade confidence.
                method = "contract"
            print(f"        ✓ Beat {current_beat.id} accomplished ({method}, score={semantic_score:.2f})")
            self._mark_beat_complete(
                current_beat.id,
                scene_id,
                verification_score=semantic_score,
                verification_method=method
            )
            if planner_targeted and semantic_score < 0.4:
                print(f"        ⚠️  Low confidence score - consider manual review")
            return contract_result

        # Failure routing, shared by semantic misses and contract failures: the
        # beat is not marked complete; the rolling horizon re-derives the pending
        # lookahead from what was actually written, or the beat stays pending.
        if verified and contract_failed:
            print(f"        ⚠️  Beat {current_beat.id} verified ({method}) but contract failed; not marking complete")
            reason = (f"beat {current_beat.id} failed contract "
                      f"({contract_result['failed']}/{contract_result['checked']} postconditions)")
        else:
            print(f"        ⚠️  Beat may not have been fully executed (score={semantic_score:.2f} < {score_threshold})")
            reason = f"beat {current_beat.id} diverged (score={semantic_score:.2f} < {score_threshold})"

        if self.config.get('generation.rolling_horizon', False):
            # The story diverged from the planned beat: re-derive the
            # pending horizon from what was actually written.
            self._revise_horizon(reason=reason, tick=tick)
        elif not self.config.get('generation.allow_beat_skip', False):
            print(f"        Keeping beat {current_beat.id} as pending")
        return contract_result

    def _evaluate_beat_contract(self, beat, scene_text: str, tension_level) -> Optional[dict]:
        """Evaluate a beat's embedded postconditions against the written scene.

        Phase 3 contracts Slice 1: conditions live on the beat itself (inside
        plot_outline.json), authored at beat-generation time, so they survive
        exactly as long as their beat does. Opt-in via ``generation.use_contracts``.
        Returns a result payload, or None when contracts are disabled, the beat
        carries no postconditions, or evaluation crashed; never raises.
        """
        if beat is None or not self.config.get('generation.use_contracts', False):
            return None
        raw_conditions = getattr(beat, "postconditions", None) or []
        if not raw_conditions:
            return None

        import logging
        logger = logging.getLogger(__name__)

        try:
            conditions = [Condition.from_dict(c) for c in raw_conditions]
            ctx = CheckContext(
                memory=self.memory,
                state=self.state,
                prose=scene_text,
                scene_tension=tension_level,
            )
            result = evaluate_conditions(conditions, ctx)
        except Exception as e:
            logger.error(f"Contract evaluation crashed for beat {beat.id}: {e}")
            return None

        if result.is_valid:
            print(f"        ✓ Contract satisfied for beat {beat.id} "
                  f"({len(result.passed)} postconditions)")
        else:
            print(f"        ⚠️  Contract violations for beat {beat.id}:")
            for failure in result.failures:
                print(f"           - {failure}")

        payload = result.to_dict()
        payload["beat_id"] = beat.id
        payload["checked"] = len(conditions)
        payload["failed"] = len(result.failures)
        payload["checked_at_tick"] = self.state.get("current_tick")
        return payload

    def _record_contract_results(self, beat_id: str, contract_result: dict) -> None:
        """Persist a contract evaluation onto its beat in the outline. Never raises."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            outline = self.plot_manager.load_outline()
            for beat in outline.beats:
                if beat.id == beat_id:
                    beat.contract_results = dict(contract_result)
                    break
            self.plot_manager.save_outline(outline)
        except Exception as e:
            logger.warning(f"Failed to record contract results for beat {beat_id}: {e}")

    def _mark_beat_complete(
        self,
        beat_id: str,
        scene_id: str,
        verification_score: float = None,
        verification_method: str = None
    ):
        """Mark a plot beat as completed (Phase 5).
        
        Args:
            beat_id: ID of the beat to mark complete
            scene_id: ID of the scene where beat was executed
            verification_score: Optional confidence score (0.0-1.0)
            verification_method: How verification was done (trusted_planner, semantic, llm, manual)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            outline = self.plot_manager.load_outline()
            for beat in outline.beats:
                if beat.id == beat_id:
                    beat.status = "completed"
                    beat.executed_in_scene = scene_id
                    beat.execution_notes = f"Executed in {scene_id}"
                    if verification_score is not None:
                        beat.verification_score = verification_score
                    if verification_method:
                        beat.verification_method = verification_method
                    break
            self.plot_manager.save_outline(outline)
            logger.info(f"Marked beat {beat_id} as completed (score={verification_score}, method={verification_method})")
            
        except Exception as e:
            logger.error(f"Failed to mark beat complete: {e}")
