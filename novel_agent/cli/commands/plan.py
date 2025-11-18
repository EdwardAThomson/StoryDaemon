"""Plan preview command - preview next plan without executing."""
import json
from pathlib import Path
from typing import Optional


def preview_plan(project_dir: Path, save: Optional[Path] = None, verbose: bool = False) -> bool:
    """Preview the next plan without executing it.
    
    Args:
        project_dir: Path to project directory
        save: Optional path to save plan JSON
        verbose: Show full context and prompts
        
    Returns:
        True if successful, False otherwise
    """
    from ...cli.project import load_project_state, get_project_config
    from ...tools.llm_interface import initialize_llm
    from ...tools.registry import ToolRegistry
    from ...tools.memory_tools import (
        MemorySearchTool,
        CharacterGenerateTool,
        LocationGenerateTool,
        RelationshipCreateTool,
        RelationshipUpdateTool,
        RelationshipQueryTool
    )
    from ...memory.manager import MemoryManager
    from ...memory.vector_store import VectorStore
    from ...agent.context import ContextBuilder
    from ...agent.prompts import format_planner_prompt
    
    try:
        # Load state and config
        state = load_project_state(str(project_dir))
        config = get_project_config(str(project_dir))
        
        current_tick = state['current_tick']
        
        print(f"📋 Generating plan preview for tick {current_tick}...\n")
        
        # Initialize LLM backend
        backend = config.get('llm.backend', 'codex')
        codex_bin = config.get('llm.codex_bin_path', 'codex')
        model = (
            config.get('llm.model')
            or config.get('llm.openai_model', 'gpt-5.1')
        )
        try:
            llm = initialize_llm(
                backend=backend,
                codex_bin=codex_bin,
                model=model,
            )
        except RuntimeError as e:
            print(f"❌ {e}")
            return False
        
        # Initialize components
        memory_manager = MemoryManager(project_dir)
        vector_store = VectorStore(project_dir)
        
        # Initialize tool registry
        tool_registry = ToolRegistry()
        tool_registry.register(MemorySearchTool(memory_manager, vector_store))
        tool_registry.register(CharacterGenerateTool(memory_manager, vector_store))
        tool_registry.register(LocationGenerateTool(memory_manager, vector_store))
        tool_registry.register(RelationshipCreateTool(memory_manager))
        tool_registry.register(RelationshipUpdateTool(memory_manager))
        tool_registry.register(RelationshipQueryTool(memory_manager))
        
        # Build context
        context_builder = ContextBuilder(
            memory_manager,
            vector_store,
            tool_registry,
            config
        )
        context = context_builder.build_planner_context(state)
        
        if verbose:
            print("=" * 60)
            print("PLANNER CONTEXT")
            print("=" * 60)
            print(f"\nCurrent Tick: {context.get('current_tick')}")
            print(f"Active Character: {context.get('active_character')}")
            print(f"\nAvailable Tools: {len(context.get('available_tools', []))}")
            for tool in context.get('available_tools', []):
                print(f"  - {tool.get('name')}: {tool.get('description', '')[:60]}...")
            print(f"\nOpen Loops: {len(context.get('open_loops', []))}")
            print(f"Recent Scenes: {len(context.get('recent_scenes', []))}")
            print("\n" + "=" * 60)
            print("PLANNER PROMPT")
            print("=" * 60)
            prompt = format_planner_prompt(context)
            print(prompt)
            print("=" * 60)
            print()
        
        # Generate plan
        prompt = format_planner_prompt(context)
        max_tokens = config.get('llm.planner_max_tokens', 2000)
        
        print("Calling LLM...")
        response = llm.generate(prompt, max_tokens=max_tokens)
        
        # Parse plan
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                print("❌ Could not extract JSON from LLM response")
                if verbose:
                    print("\nRaw response:")
                    print(response)
                return False
        
        try:
            plan = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in plan: {e}")
            if verbose:
                print("\nExtracted JSON:")
                print(json_str)
            return False
        
        # Display plan
        display_plan_preview(plan, current_tick, state.get('active_character'))
        
        # Save if requested
        if save:
            try:
                with open(save, 'w', encoding='utf-8') as f:
                    json.dump(plan, f, indent=2)
                print(f"\n💾 Plan saved to: {save}")
            except Exception as e:
                print(f"\n⚠️  Could not save plan: {e}")
        
        print("\n⚠️  This plan has NOT been executed. Use 'novel tick' to execute.\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating plan preview: {e}")
        if verbose:
            import traceback
            print("\nTraceback:")
            print(traceback.format_exc())
        return False


def display_plan_preview(plan: dict, tick: int, active_character: Optional[str] = None):
    """Display plan in human-readable format.
    
    Args:
        plan: Plan dictionary
        tick: Current tick number
        active_character: Active character ID
    """
    print(f"📋 Plan Preview (Tick {tick})\n")
    
    # Rationale
    rationale = plan.get('rationale', 'No rationale provided')
    print("Rationale:")
    print(f"  {rationale}\n")
    
    # Actions
    actions = plan.get('actions', [])
    if actions:
        print(f"Actions ({len(actions)}):")
        for i, action in enumerate(actions, 1):
            tool = action.get('tool', 'unknown')
            args = action.get('args', {})
            print(f"  {i}. {tool}")
            if args:
                # Format args nicely
                for key, value in args.items():
                    if isinstance(value, str) and len(value) > 60:
                        value = value[:60] + "..."
                    print(f"      {key}: {value}")
        print()
    
    # Scene intention
    scene_intention = plan.get('scene_intention', 'No scene intention provided')
    print("Scene Intention:")
    print(f"  {scene_intention}\n")
    
    # Metadata
    print(f"POV Character: {active_character or 'None'}")
    
    # Estimate tokens (rough)
    import json
    plan_str = json.dumps(plan)
    estimated_tokens = len(plan_str.split()) * 1.3  # Rough estimate
    print(f"Estimated Tokens: ~{int(estimated_tokens):,}")
