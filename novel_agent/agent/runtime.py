"""Plan execution runtime for running tool calls."""

from typing import Dict, Any
from ..tools.registry import ToolRegistry
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore


class PlanExecutor:
    """Executes plans by running tool calls.
    
    Takes a validated plan and executes each action in sequence,
    stopping on the first error.
    """
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_manager: MemoryManager,
        vector_store: VectorStore
    ):
        """Initialize plan executor.
        
        Args:
            tool_registry: Registry of available tools
            memory_manager: Memory manager instance
            vector_store: Vector store instance
        """
        self.tools = tool_registry
        self.memory = memory_manager
        self.vector = vector_store
    
    def execute_plan(self, plan: dict, tick: int) -> dict:
        """Execute a plan and return results.
        
        Args:
            plan: Validated plan dictionary
            tick: Current tick number
        
        Returns:
            Execution results dictionary with:
                - tick: Tick number
                - plan: Original plan
                - actions_executed: List of action results
                - errors: List of error messages
                - success: Boolean indicating overall success
        
        Raises:
            RuntimeError: If any tool execution fails (stops on first error)
        """
        results = {
            "tick": tick,
            "plan": plan,
            "actions_executed": [],
            "errors": [],
            "success": True
        }
        
        # Execute each action - STOP ON FIRST ERROR
        for i, action in enumerate(plan.get("actions", [])):
            try:
                result = self._execute_action(action, tick)
                results["actions_executed"].append({
                    "action_index": i,
                    "tool": action["tool"],
                    "args": action["args"],
                    "result": result,
                    "success": True
                })
            except Exception as e:
                error_msg = f"Error executing {action['tool']}: {str(e)}"
                results["errors"].append(error_msg)
                results["actions_executed"].append({
                    "action_index": i,
                    "tool": action["tool"],
                    "args": action["args"],
                    "error": error_msg,
                    "success": False
                })
                results["success"] = False
                
                # STOP EXECUTION - something is seriously wrong
                raise RuntimeError(
                    f"Tool execution failed at action {i}: {error_msg}\n"
                    f"Plan execution halted. Check error log for details."
                )
        
        return results
    
    def _execute_action(self, action: dict, tick: int) -> dict:
        """Execute a single tool action.
        
        Args:
            action: Action dictionary with tool and args
            tick: Current tick number
        
        Returns:
            Tool execution result
        
        Raises:
            ValueError: If tool is not found
            Exception: If tool execution fails
        """
        tool_name = action["tool"]
        args = action.get("args", {})
        
        # Get tool from registry
        tool = self.tools.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        # Validate arguments
        tool.validate_args(args)
        
        # Add tick to args if tool supports it (for relationship.update)
        if tool_name == "relationship.update":
            args["tick"] = tick
        
        # Execute tool
        result = tool.execute(**args)
        
        return result
