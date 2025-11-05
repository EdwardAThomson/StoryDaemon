"""Plan storage and retrieval manager."""

import json
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class PlanManager:
    """Manages plan storage and error logging.
    
    Handles saving plans, execution results, and error details to disk
    for transparency and debugging.
    """
    
    def __init__(self, project_path: Path):
        """Initialize plan manager.
        
        Args:
            project_path: Path to novel project directory
        """
        self.project_path = Path(project_path)
        self.plans_dir = self.project_path / "plans"
        self.errors_dir = self.project_path / "errors"
        
        # Ensure directories exist
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.errors_dir.mkdir(parents=True, exist_ok=True)
    
    def save_plan(self, tick: int, plan: dict, execution_results: dict, context: dict) -> Path:
        """Save a plan and its execution results.
        
        Args:
            tick: Tick number
            plan: Plan dictionary
            execution_results: Results from PlanExecutor
            context: Context used for planning
        
        Returns:
            Path to saved plan file
        """
        plan_file = self.plans_dir / f"plan_{tick:03d}.json"
        
        plan_data = {
            "tick": tick,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "plan": plan,
            "execution": execution_results,
            "context_used": {
                "active_character": context.get("active_character_id"),
                "recent_scenes_count": len(context.get("recent_scenes_summary", "").split("\n\n")),
                "open_loops_count": len(context.get("open_loops_list", "").split("\n"))
            }
        }
        
        with open(plan_file, 'w') as f:
            json.dump(plan_data, f, indent=2)
        
        return plan_file
    
    def load_plan(self, tick: int) -> Optional[Dict[str, Any]]:
        """Load a plan by tick number.
        
        Args:
            tick: Tick number
        
        Returns:
            Plan data dictionary or None if not found
        """
        plan_file = self.plans_dir / f"plan_{tick:03d}.json"
        
        if not plan_file.exists():
            return None
        
        with open(plan_file, 'r') as f:
            return json.load(f)
    
    def list_plans(self) -> List[int]:
        """List all plan tick numbers.
        
        Returns:
            Sorted list of tick numbers with saved plans
        """
        plan_files = sorted(self.plans_dir.glob("plan_*.json"))
        tick_numbers = []
        
        for plan_file in plan_files:
            # Extract tick number from filename
            try:
                tick = int(plan_file.stem.split("_")[1])
                tick_numbers.append(tick)
            except (IndexError, ValueError):
                continue
        
        return sorted(tick_numbers)
    
    def save_error(
        self,
        tick: int,
        error: Exception,
        plan: dict,
        execution_results: dict
    ) -> Path:
        """Save error details for human review.
        
        Args:
            tick: Tick number where error occurred
            error: Exception that was raised
            plan: Plan that was being executed
            execution_results: Partial execution results
        
        Returns:
            Path to error JSON file
        """
        error_file = self.errors_dir / f"error_{tick:03d}.json"
        log_file = self.errors_dir / f"error_{tick:03d}.log"
        
        # Get traceback
        tb = traceback.format_exc()
        
        # Create structured error data
        error_data = {
            "tick": tick,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": tb
            },
            "plan": plan,
            "execution": execution_results,
            "instructions": (
                "Review error and either:\n"
                "1. Fix the underlying issue (e.g., create missing entity)\n"
                "2. Manually edit the plan and retry\n"
                "3. Skip this tick by incrementing current_tick in state.json"
            )
        }
        
        # Save JSON
        with open(error_file, 'w') as f:
            json.dump(error_data, f, indent=2)
        
        # Save human-readable log
        with open(log_file, 'w') as f:
            f.write(f"ERROR AT TICK {tick}\n")
            f.write(f"{'=' * 60}\n\n")
            f.write(f"Error Type: {type(error).__name__}\n")
            f.write(f"Error Message: {str(error)}\n\n")
            f.write(f"Traceback:\n{tb}\n")
            f.write(f"{'=' * 60}\n\n")
            f.write(f"Plan:\n{json.dumps(plan, indent=2)}\n\n")
            f.write(f"{'=' * 60}\n\n")
            f.write(f"Partial Execution Results:\n{json.dumps(execution_results, indent=2)}\n\n")
            f.write(f"{'=' * 60}\n\n")
            f.write("RECOVERY OPTIONS:\n")
            f.write("1. Fix the issue and run 'novel tick' again\n")
            f.write("2. Manually edit the plan file and retry\n")
            f.write("3. Skip this tick by editing state.json\n")
        
        return error_file
    
    def list_errors(self) -> List[int]:
        """List all error tick numbers.
        
        Returns:
            Sorted list of tick numbers with errors
        """
        error_files = sorted(self.errors_dir.glob("error_*.json"))
        tick_numbers = []
        
        for error_file in error_files:
            try:
                tick = int(error_file.stem.split("_")[1])
                tick_numbers.append(tick)
            except (IndexError, ValueError):
                continue
        
        return sorted(tick_numbers)
    
    def get_latest_plan(self) -> Optional[Dict[str, Any]]:
        """Get the most recent plan.
        
        Returns:
            Latest plan data or None if no plans exist
        """
        plans = self.list_plans()
        if not plans:
            return None
        
        return self.load_plan(plans[-1])
