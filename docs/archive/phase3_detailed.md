# Phase 3 — Planner and Execution Loop (Detailed Design)

**Goal:** Build the agent runtime that decides and acts using tool calls to generate story content.

---

## 1. Overview

Phase 3 establishes the core agent loop that:
- Analyzes current story state
- Decides which tools to use (character generation, memory search, etc.)
- Executes tool calls deterministically
- Prepares context for the writer
- Stores plans for transparency and debugging

**Key Principle:** The planner is an autonomous decision-maker that uses structured tool calls to shape the narrative.

---

## 2. Architecture

### 2.1 Story Tick Flow

```
┌─────────────────────────────────────────────────────────┐
│                     STORY TICK N                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. GATHER CONTEXT                                      │
│     ├─ Load project state (current tick, active char)  │
│     ├─ Load recent scenes (last 3)                     │
│     ├─ Load open loops                                 │
│     └─ Load active character details                   │
│                                                         │
│  2. PLANNER LLM                                         │
│     ├─ Input: Context + Available Tools                │
│     ├─ Output: Structured Plan (JSON)                  │
│     └─ Validate: Schema check                          │
│                                                         │
│  3. EXECUTE PLAN                                        │
│     ├─ For each action in plan:                        │
│     │   ├─ Look up tool in registry                    │
│     │   ├─ Execute with arguments                      │
│     │   └─ Collect result                              │
│     └─ Aggregate results                               │
│                                                         │
│  4. STORE PLAN                                          │
│     ├─ Save plan JSON to /plans/plan_NNN.json          │
│     └─ Include execution results                       │
│                                                         │
│  5. PREPARE WRITER CONTEXT (Phase 4)                   │
│     └─ [Not implemented in Phase 3]                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Plan Schema

### 3.1 Plan JSON Structure

```json
{
  "tick": 5,
  "timestamp": "2024-11-04T20:00:00Z",
  "rationale": "Elena needs to confront her mentor about the map fragment. This scene will reveal crucial backstory and strain their relationship.",
  "scene_intention": "Tense confrontation in the Archive where Elena demands answers",
  "pov_character": "C0",
  "target_location": "L0",
  "actions": [
    {
      "tool": "memory.search",
      "args": {
        "query": "mentor relationship history",
        "entity_types": ["character"],
        "limit": 3
      },
      "reason": "Need context on their past relationship"
    },
    {
      "tool": "relationship.query",
      "args": {
        "character_id": "C0",
        "status_filter": "strained"
      },
      "reason": "Check current relationship dynamics"
    }
  ],
  "expected_outcomes": [
    "Reveal mentor's connection to father's disappearance",
    "Escalate tension between Elena and Marcus",
    "Introduce new mystery element"
  ]
}
```

### 3.2 Plan Schema Definition

**File:** `novel_agent/agent/schemas.py`

```python
PLAN_SCHEMA = {
    "type": "object",
    "required": ["rationale", "actions", "scene_intention"],
    "properties": {
        "rationale": {
            "type": "string",
            "description": "Why this plan makes sense for the story"
        },
        "scene_intention": {
            "type": "string",
            "description": "What should happen in this scene"
        },
        "pov_character": {
            "type": "string",
            "description": "Character ID for POV (optional, can be inferred)"
        },
        "target_location": {
            "type": "string",
            "description": "Location ID where scene takes place (optional)"
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tool", "args"],
                "properties": {
                    "tool": {
                        "type": "string",
                        "description": "Tool name (e.g., memory.search)"
                    },
                    "args": {
                        "type": "object",
                        "description": "Tool arguments"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this tool is needed (optional)"
                    }
                }
            }
        },
        "expected_outcomes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What should result from this scene"
        }
    }
}
```

---

## 4. Planner LLM Prompt

### 4.1 Prompt Template

**File:** `novel_agent/agent/prompts.py`

```python
PLANNER_PROMPT_TEMPLATE = """You are a creative story planner for an emergent narrative system.

Your task is to analyze the current story state and create a plan for the next scene.

## Current Story State

**Novel:** {novel_name}
**Current Tick:** {current_tick}
**Active Character:** {active_character_name} ({active_character_id})

### Overall Story Summary
{overall_summary}

### Recent Scenes (Detailed)
{recent_scenes_summary}

### Open Story Loops
{open_loops_list}

### Active Character Details
{active_character_details}

### Available Relationships
{character_relationships}

## Available Tools

You can use the following tools to gather information or create entities:

{available_tools_description}

## Your Task

Create a plan for the next scene. Consider:
1. Which open loops should be addressed or developed?
2. What information do you need to write this scene effectively?
3. Should new characters or locations be introduced?
4. How should relationships evolve?

## Output Format

Respond with a JSON object following this structure:

```json
{
  "rationale": "Brief explanation of your planning decisions",
  "scene_intention": "What should happen in this scene (1-2 sentences)",
  "pov_character": "Character ID for POV (use {active_character_id} or specify another)",
  "target_location": "Location ID where scene takes place (or null for new location)",
  "actions": [
    {
      "tool": "tool.name",
      "args": {
        "arg1": "value1"
      },
      "reason": "Why this tool is needed"
    }
  ],
  "expected_outcomes": [
    "Outcome 1",
    "Outcome 2"
  ]
}
```

## Guidelines

- Keep actions focused (2-4 tools maximum per plan)
- Use memory.search to recall relevant context
- Use character.generate only when introducing new characters
- Use relationship.create when characters first interact significantly
- Use relationship.update to track relationship changes
- Scene intention should be specific and actionable
- Expected outcomes should be concrete story developments

Generate your plan now:"""
```

### 4.2 Context Building

**File:** `novel_agent/agent/context.py`

```python
class ContextBuilder:
    """Builds context for planner prompts."""
    
    def __init__(self, memory_manager, vector_store, config):
        self.memory = memory_manager
        self.vector = vector_store
        self.config = config
        
        # Get configurable context settings
        self.recent_scenes_count = config.get('generation.recent_scenes_count', 3)
        self.include_overall_summary = config.get('generation.include_overall_summary', True)
    
    def build_planner_context(self, project_state: dict) -> dict:
        """Build context dictionary for planner prompt.
        
        Args:
            project_state: Current project state from state.json
        
        Returns:
            Dictionary with all context variables
        """
        context = {
            "novel_name": project_state.get("novel_name", "Untitled"),
            "current_tick": project_state.get("current_tick", 0),
            "active_character_id": project_state.get("active_character"),
        }
        
        # Load active character
        if context["active_character_id"]:
            char = self.memory.load_character(context["active_character_id"])
            if char:
                context["active_character_name"] = char.name
                context["active_character_details"] = self._format_character(char)
        
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
        
        # Get character relationships
        if context["active_character_id"]:
            context["character_relationships"] = self._format_relationships(
                context["active_character_id"]
            )
        
        # Get available tools description
        context["available_tools_description"] = self._format_available_tools()
        
        return context
    
    def _format_character(self, character) -> str:
        """Format character details for prompt."""
        parts = [
            f"Name: {character.name}",
            f"Role: {character.role}",
            f"Description: {character.description}",
        ]
        
        if character.current_state.goals:
            parts.append(f"Current Goals: {', '.join(character.current_state.goals)}")
        
        if character.current_state.emotional_state:
            parts.append(f"Emotional State: {character.current_state.emotional_state}")
        
        return "\n".join(parts)
    
    def _get_overall_summary(self) -> str:
        """Get high-level summary of all scenes so far."""
        scene_ids = self.memory.list_scenes()
        
        if not scene_ids:
            return "Story has not yet begun."
        
        # Get all scene summaries
        all_summaries = []
        for scene_id in scene_ids:
            scene = self.memory.load_scene(scene_id)
            if scene and scene.summary:
                # Take first bullet point from each scene as high-level summary
                all_summaries.append(f"Tick {scene.tick}: {scene.summary[0]}")
        
        if not all_summaries:
            return f"{len(scene_ids)} scenes generated so far."
        
        summary_text = "\n".join(all_summaries)
        return f"**Story So Far** ({len(scene_ids)} scenes):\n{summary_text}"
    
    def _get_recent_scenes_summary(self, count: int) -> str:
        """Get detailed summaries of recent scenes."""
        scene_ids = self.memory.list_scenes()
        recent_ids = scene_ids[-count:] if len(scene_ids) >= count else scene_ids
        
        summaries = []
        for scene_id in recent_ids:
            scene = self.memory.load_scene(scene_id)
            if scene and scene.summary:
                summary_text = "\n  - ".join(scene.summary)
                summaries.append(f"**{scene.title}** (Tick {scene.tick}):\n  - {summary_text}")
        
        return "\n\n".join(summaries) if summaries else "No previous scenes yet."
    
    def _format_open_loops(self) -> str:
        """Format open loops for prompt."""
        loops = self.memory.get_open_loops(status="open")
        
        if not loops:
            return "No open loops yet."
        
        formatted = []
        for loop in loops:
            formatted.append(
                f"- [{loop.importance.upper()}] {loop.description} "
                f"(Category: {loop.category}, Created: Scene {loop.created_in_scene})"
            )
        
        return "\n".join(formatted)
    
    def _format_relationships(self, character_id: str) -> str:
        """Format character relationships for prompt."""
        rels = self.memory.get_character_relationships(character_id)
        
        if not rels:
            return "No established relationships yet."
        
        formatted = []
        for rel in rels:
            other_id = rel.get_other_character(character_id)
            other_char = self.memory.load_character(other_id)
            other_name = other_char.name if other_char else other_id
            
            perspective = rel.get_perspective(character_id)
            formatted.append(
                f"- {other_name} ({rel.relationship_type}): {rel.status} "
                f"[Intensity: {rel.intensity}/10]\n  Your view: \"{perspective}\""
            )
        
        return "\n".join(formatted)
    
    def _format_available_tools(self) -> str:
        """Format available tools description."""
        # This will be populated from the tool registry
        tools_desc = [
            "**memory.search** - Search for relevant characters, locations, or scenes",
            "  Args: query (str), entity_types (list), limit (int)",
            "",
            "**character.generate** - Create a new character",
            "  Args: name (str), role (str), description (str), traits (list), goals (list)",
            "",
            "**location.generate** - Create a new location",
            "  Args: name (str), description (str), atmosphere (str), features (list)",
            "",
            "**relationship.create** - Establish a relationship between two characters",
            "  Args: character_a (str), character_b (str), relationship_type (str), perspective_a (str), perspective_b (str)",
            "",
            "**relationship.update** - Update an existing relationship",
            "  Args: character_a (str), character_b (str), status (str), event (str), scene_id (str)",
            "",
            "**relationship.query** - Query relationships for a character",
            "  Args: character_id (str), status_filter (str)",
        ]
        
        return "\n".join(tools_desc)
```

---

## 5. Plan Execution Runtime

### 5.1 Runtime Class

**File:** `novel_agent/agent/runtime.py`

```python
class PlanExecutor:
    """Executes plans by running tool calls."""
    
    def __init__(self, tool_registry, memory_manager, vector_store):
        self.tools = tool_registry
        self.memory = memory_manager
        self.vector = vector_store
    
    def execute_plan(self, plan: dict, tick: int) -> dict:
        """Execute a plan and return results.
        
        Args:
            plan: Validated plan dictionary
            tick: Current tick number
        
        Returns:
            Execution results dictionary
        
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
        """
        tool_name = action["tool"]
        args = action.get("args", {})
        
        # Get tool from registry
        tool = self.tools.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        # Add tick to args if tool supports it (for relationship.update)
        if tool_name == "relationship.update":
            args["tick"] = tick
        
        # Execute tool
        result = tool.execute(**args)
        
        return result
```

---

## 6. Plan Storage

### 6.1 Plan File Format

**Location:** `~/novels/<novel-name>/plans/plan_NNN.json`

```json
{
  "tick": 5,
  "timestamp": "2024-11-04T20:00:00Z",
  "plan": {
    "rationale": "...",
    "scene_intention": "...",
    "actions": [...]
  },
  "execution": {
    "success": true,
    "actions_executed": [
      {
        "action_index": 0,
        "tool": "memory.search",
        "args": {...},
        "result": {...},
        "success": true
      }
    ],
    "errors": []
  },
  "context_used": {
    "active_character": "C0",
    "recent_scenes": ["S003", "S004"],
    "open_loops_count": 3
  }
}
```

### 6.2 Plan Manager

**File:** `novel_agent/agent/plan_manager.py`

```python
class PlanManager:
    """Manages plan storage and retrieval."""
    
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.plans_path = self.project_path / "plans"
        self.errors_path = self.project_path / "errors"
        self.plans_path.mkdir(exist_ok=True)
        self.errors_path.mkdir(exist_ok=True)
    
    def save_plan(self, tick: int, plan: dict, execution_results: dict, 
                  context: dict):
        """Save a plan with execution results.
        
        Args:
            tick: Tick number
            plan: Plan dictionary
            execution_results: Results from execution
            context: Context used for planning
        """
        plan_data = {
            "tick": tick,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "plan": plan,
            "execution": execution_results,
            "context_used": {
                "active_character": context.get("active_character_id"),
                "recent_scenes": context.get("recent_scene_ids", []),
                "open_loops_count": context.get("open_loops_count", 0)
            }
        }
        
        filename = f"plan_{tick:03d}.json"
        filepath = self.plans_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(plan_data, f, indent=2, ensure_ascii=False)
    
    def save_error(self, tick: int, error: Exception, plan: dict, 
                   execution_results: dict, context: dict):
        """Save error details for human review.
        
        Args:
            tick: Tick number where error occurred
            error: Exception that was raised
            plan: Plan that was being executed
            execution_results: Partial execution results
            context: Context used for planning
        """
        error_data = {
            "tick": tick,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc()
            },
            "plan": plan,
            "execution": execution_results,
            "context_used": {
                "active_character": context.get("active_character_id"),
                "recent_scenes": context.get("recent_scene_ids", []),
                "open_loops_count": context.get("open_loops_count", 0)
            },
            "instructions": (
                "This tick failed during execution. Review the error and plan, "
                "then either:\n"
                "1. Fix the underlying issue (e.g., missing entity, invalid args)\n"
                "2. Manually edit the plan and retry\n"
                "3. Skip this tick and continue with next tick\n"
                "\nTo retry: novel tick --retry {tick}\n"
                "To skip: Update state.json current_tick to {tick} and run novel tick"
            ).format(tick=tick)
        }
        
        filename = f"error_{tick:03d}.json"
        filepath = self.errors_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, indent=2, ensure_ascii=False)
        
        # Also write human-readable error log
        log_filename = f"error_{tick:03d}.log"
        log_filepath = self.errors_path / log_filename
        
        with open(log_filepath, 'w', encoding='utf-8') as f:
            f.write(f"=== TICK {tick} EXECUTION ERROR ===\n\n")
            f.write(f"Error Type: {type(error).__name__}\n")
            f.write(f"Error Message: {str(error)}\n\n")
            f.write(f"Traceback:\n{traceback.format_exc()}\n\n")
            f.write(f"Plan:\n{json.dumps(plan, indent=2)}\n\n")
            f.write(f"Partial Execution Results:\n{json.dumps(execution_results, indent=2)}\n")
    
    def load_plan(self, tick: int) -> Optional[dict]:
        """Load a plan by tick number."""
        filename = f"plan_{tick:03d}.json"
        filepath = self.plans_path / filename
        
        if not filepath.exists():
            return None
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_plans(self) -> List[int]:
        """List all plan tick numbers."""
        ticks = []
        for filepath in self.plans_path.glob("plan_*.json"):
            # Extract tick number from filename
            tick_str = filepath.stem.replace("plan_", "")
            try:
                ticks.append(int(tick_str))
            except ValueError:
                continue
        return sorted(ticks)
    
    def list_errors(self) -> List[int]:
        """List all error tick numbers."""
        ticks = []
        for filepath in self.errors_path.glob("error_*.json"):
            tick_str = filepath.stem.replace("error_", "")
            try:
                ticks.append(int(tick_str))
            except ValueError:
                continue
        return sorted(ticks)
```

---

## 7. Agent Orchestrator

### 7.1 Main Agent Class

**File:** `novel_agent/agent/agent.py`

```python
class StoryAgent:
    """Main agent orchestrator for story generation."""
    
    def __init__(self, project_path: Path, llm_interface, tool_registry):
        self.project_path = Path(project_path)
        self.llm = llm_interface
        self.tools = tool_registry
        
        # Initialize components
        self.memory = MemoryManager(project_path)
        self.vector = VectorStore(project_path)
        self.context_builder = ContextBuilder(self.memory, self.vector)
        self.executor = PlanExecutor(tool_registry, self.memory, self.vector)
        self.plan_manager = PlanManager(project_path)
        
        # Load project state
        self.state = self._load_state()
    
    def tick(self) -> dict:
        """Execute one story tick.
        
        Returns:
            Tick results dictionary
        
        Raises:
            RuntimeError: If execution fails (error saved to /errors/)
        """
        current_tick = self.state.get("current_tick", 0) + 1
        
        print(f"🎬 Starting Tick {current_tick}...")
        
        context = None
        plan = None
        execution_results = None
        
        try:
            # 1. Build context
            print("📚 Gathering context...")
            context = self.context_builder.build_planner_context(self.state)
            
            # 2. Generate plan
            print("🤔 Planning scene...")
            plan = self._generate_plan(context)
            
            # 3. Validate plan
            print("✓ Validating plan...")
            self._validate_plan(plan)
            
            # 4. Execute plan (will raise RuntimeError on failure)
            print("⚙️  Executing tools...")
            execution_results = self.executor.execute_plan(plan, current_tick)
            
            # 5. Store plan
            print("💾 Saving plan...")
            self.plan_manager.save_plan(current_tick, plan, execution_results, context)
            
            # 6. Update state
            self.state["current_tick"] = current_tick
            self._save_state()
            
            print(f"✅ Tick {current_tick} complete!")
            
            return {
                "tick": current_tick,
                "plan": plan,
                "execution": execution_results,
                "success": True
            }
        
        except Exception as e:
            # Save error for human review
            print(f"❌ Tick {current_tick} failed: {str(e)}")
            print(f"💾 Saving error details to /errors/error_{current_tick:03d}.json")
            
            if execution_results is None:
                execution_results = {
                    "tick": current_tick,
                    "plan": plan,
                    "actions_executed": [],
                    "errors": [str(e)],
                    "success": False
                }
            
            self.plan_manager.save_error(
                current_tick, e, plan or {}, execution_results, context or {}
            )
            
            # Re-raise so CLI can handle it
            raise
    
    def _generate_plan(self, context: dict) -> dict:
        """Generate plan using planner LLM."""
        from .prompts import PLANNER_PROMPT_TEMPLATE
        
        # Build prompt
        prompt = PLANNER_PROMPT_TEMPLATE.format(**context)
        
        # Call LLM
        response = self.llm.send_prompt(prompt)
        
        # Parse JSON response
        plan = self._parse_plan_response(response)
        
        return plan
    
    def _parse_plan_response(self, response: str) -> dict:
        """Parse LLM response into plan dictionary."""
        import json
        import re
        
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
    
    def _validate_plan(self, plan: dict):
        """Validate plan against schema."""
        from jsonschema import validate, ValidationError
        from .schemas import PLAN_SCHEMA
        
        try:
            validate(instance=plan, schema=PLAN_SCHEMA)
        except ValidationError as e:
            raise ValueError(f"Plan validation failed: {e.message}")
    
    def _load_state(self) -> dict:
        """Load project state."""
        state_file = self.project_path / "state.json"
        with open(state_file, 'r') as f:
            return json.load(f)
    
    def _save_state(self):
        """Save project state."""
        state_file = self.project_path / "state.json"
        self.state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        with open(state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
```

---

## 8. CLI Integration

### 8.1 Update Tick Command

**File:** `novel_agent/cli/main.py`

```python
@app.command()
def tick(
    project: Optional[str] = typer.Option(None, help="Project directory path"),
    dry_run: bool = typer.Option(False, help="Show plan without executing")
):
    """Generate the next scene (one story tick)."""
    try:
        # Find project directory
        project_dir = project if project else find_project_dir()
        
        # Initialize components
        config = get_project_config(project_dir)
        llm = CodexInterface(config)
        tool_registry = ToolRegistry()
        
        # Register tools
        memory_manager = MemoryManager(Path(project_dir))
        vector_store = VectorStore(Path(project_dir))
        
        tool_registry.register(MemorySearchTool(memory_manager, vector_store))
        tool_registry.register(CharacterGenerateTool(memory_manager, vector_store))
        tool_registry.register(LocationGenerateTool(memory_manager, vector_store))
        tool_registry.register(RelationshipCreateTool(memory_manager))
        tool_registry.register(RelationshipUpdateTool(memory_manager))
        tool_registry.register(RelationshipQueryTool(memory_manager))
        
        # Create agent
        agent = StoryAgent(Path(project_dir), llm, tool_registry)
        
        # Execute tick
        result = agent.tick()
        
        typer.echo(f"✅ Tick {result['tick']} completed successfully")
    
    except RuntimeError as e:
        # Tool execution error - details saved to /errors/
        typer.echo(f"\n❌ Tick execution failed", err=True)
        typer.echo(f"Error: {str(e)}", err=True)
        typer.echo(f"\n📋 Error details saved to {project_dir}/errors/", err=True)
        typer.echo(f"Review the error and either:", err=True)
        typer.echo(f"  1. Fix the issue and retry", err=True)
        typer.echo(f"  2. Manually edit the plan", err=True)
        typer.echo(f"  3. Skip this tick", err=True)
        raise typer.Exit(1)
    
    except Exception as e:
        # Other errors (validation, LLM, etc.)
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)
```

---

## 9. Implementation Order

1. **Schemas** (`novel_agent/agent/schemas.py`)
   - Define PLAN_SCHEMA
   - Add validation helpers

2. **Prompts** (`novel_agent/agent/prompts.py`)
   - Create PLANNER_PROMPT_TEMPLATE
   - Add prompt formatting utilities

3. **Context Builder** (`novel_agent/agent/context.py`)
   - Implement ContextBuilder class
   - Add formatting methods

4. **Plan Executor** (`novel_agent/agent/runtime.py`)
   - Implement PlanExecutor class
   - Add error handling

5. **Plan Manager** (`novel_agent/agent/plan_manager.py`)
   - Implement plan storage
   - Add retrieval methods

6. **Agent Orchestrator** (`novel_agent/agent/agent.py`)
   - Implement StoryAgent class
   - Wire all components together

7. **CLI Integration** (`novel_agent/cli/main.py`)
   - Update tick command
   - Add tool registration

8. **Testing**
   - Unit tests for each component
   - Integration test for full tick cycle

---

## 10. Testing Strategy

### Unit Tests

- **Schema validation:** Test valid and invalid plans
- **Context building:** Test with various story states
- **Plan execution:** Test tool calls with mocked tools
- **Plan storage:** Test save/load operations
- **JSON parsing:** Test LLM response parsing

### Integration Tests

- **Full tick cycle:** Create test project, run tick, verify outputs
- **Tool execution:** Verify tools are called correctly
- **Error handling:** Test with failing tools
- **State updates:** Verify state.json updates correctly

### Test Files

```
tests/
  test_schemas.py
  test_context_builder.py
  test_plan_executor.py
  test_plan_manager.py
  test_agent.py
  integration/
    test_full_tick.py
```

---

## 11. Success Criteria

Phase 3 is complete when:

- ✅ Plan schema defined and validated
- ✅ Planner prompt template creates valid plans
- ✅ Context builder gathers all necessary information
- ✅ Plan executor runs tools correctly
- ✅ Plans are stored in `/plans/` directory
- ✅ Agent orchestrator coordinates all components
- ✅ `novel tick` command executes full planning cycle
- ✅ Integration tests pass for full tick workflow
- ✅ Error handling works for invalid plans and failed tools

---

## 12. Design Decisions Made

1. **Error Handling:** ✅ STOP on first tool error
   - Save full error details to `/errors/error_NNN.json` and `.log`
   - Include instructions for human review
   - Provide options: fix, edit plan, or skip tick
   - **Rationale:** Something is seriously wrong; human intervention needed

2. **Context Configuration:** ✅ Overall summary + configurable recent scenes
   - Overall summary: High-level view of all scenes (first bullet from each)
   - Recent scenes: Detailed summaries (default: 3, configurable)
   - Config options:
     - `generation.recent_scenes_count` (default: 3)
     - `generation.include_overall_summary` (default: true)
   - **Rationale:** Need both big picture and recent details; adjust based on testing

3. **POV Character Selection:** Fixed active character for Phase 3
   - Add switching in Phase 5
   - **Rationale:** Simplify initial implementation

4. **Tool Limits:** Soft limit of 4 tools per plan
   - Warn if exceeded but don't block
   - **Rationale:** Encourage focused plans without hard constraints

---

## 13. Next Steps (Phase 4 Preview)

Once Phase 3 is complete, Phase 4 will:
- Implement Writer LLM prompt template
- Generate actual scene prose
- Implement Evaluator for continuity/POV checks
- Commit scenes to `/scenes/` directory
- Update memory with scene results

---

**Phase 3 Status: READY TO IMPLEMENT**

All design decisions made. Ready to begin coding.
