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
from ..tools.registry import ToolRegistry
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore


class StoryAgent:
    """Main agent orchestrator for story generation.
    
    Coordinates the full tick cycle:
    1. Gather context
    2. Generate plan with LLM
    3. Execute plan
    4. Store results
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
        
        # Load state
        self.state = self._load_state()
    
    def tick(self) -> Dict[str, Any]:
        """Execute one story generation tick.
        
        Returns:
            Result dictionary with tick info and success status
        
        Raises:
            RuntimeError: If tool execution fails
            ValueError: If plan validation fails
        """
        tick = self.state["current_tick"]
        
        try:
            # Step 1: Gather context
            context = self.context_builder.build_planner_context(self.state)
            
            # Step 2: Generate plan with LLM
            plan = self._generate_plan(context)
            
            # Step 3: Validate plan
            validate_plan(plan)
            
            # Step 4: Execute plan
            execution_results = self.executor.execute_plan(plan, tick)
            
            # Step 5: Store plan and results
            plan_file = self.plan_manager.save_plan(
                tick,
                plan,
                execution_results,
                context
            )
            
            # Step 6: Update state
            self.state["current_tick"] += 1
            self._save_state()
            
            return {
                "success": True,
                "tick": tick,
                "plan_file": str(plan_file),
                "actions_executed": len(execution_results.get("actions_executed", []))
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
        response = self.llm.send_prompt(prompt, max_tokens=max_tokens)
        
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
