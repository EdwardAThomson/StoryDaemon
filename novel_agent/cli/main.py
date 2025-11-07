"""Main CLI entry point for StoryDaemon."""
import typer
from pathlib import Path
from typing import Optional
from .project import (
    create_novel_project,
    find_project_dir,
    load_project_state,
    save_project_state,
    get_project_config
)
from ..tools.llm_interface import initialize_llm, send_prompt
from ..tools.codex_interface import CodexInterface
from ..tools.registry import ToolRegistry
from ..tools.memory_tools import (
    MemorySearchTool,
    CharacterGenerateTool,
    LocationGenerateTool,
    RelationshipCreateTool,
    RelationshipUpdateTool,
    RelationshipQueryTool
)
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..agent.agent import StoryAgent


app = typer.Typer(
    name="novel",
    help="StoryDaemon - Agentic novel generation system",
    add_completion=False
)


@app.command()
def new(
    name: str = typer.Argument(..., help="Name of the novel"),
    dir: Optional[str] = typer.Option(
        None,
        "--dir",
        "-d",
        help="Base directory for novel (default: ~/novels)"
    )
):
    """Create a new novel project.
    
    Creates a complete project structure with memory directories,
    configuration files, and initial state.
    
    Example:
        novel new my-story
        novel new my-story --dir ~/Documents/novels
    """
    try:
        project_dir = create_novel_project(name, dir)
        typer.echo(f"✅ Created novel project: {project_dir}")
        typer.echo(f"\n📝 Next steps:")
        typer.echo(f"  cd {project_dir}")
        typer.echo(f"  novel tick")
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)
    except IOError as e:
        typer.echo(f"❌ Error creating project: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def tick(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project (default: current directory)"
    )
):
    """Run one story generation tick.
    
    Executes the full story generation pipeline:
    - Planning with LLM
    - Tool execution
    - Scene prose generation
    - Quality evaluation
    - Scene commit to disk and memory
    
    Example:
        novel tick
        novel tick --project ~/novels/my-story
    """
    try:
        # Find project directory
        project_dir = Path(find_project_dir(project))
        typer.echo(f"📖 Running tick for project: {project_dir}")
        
        # Load project state and config
        state = load_project_state(project_dir)
        config = get_project_config(project_dir)
        
        current_tick = state['current_tick']
        typer.echo(f"   Current tick: {current_tick}")
        
        # Initialize LLM
        codex_bin = config.get('llm.codex_bin_path', 'codex')
        try:
            initialize_llm(codex_bin)
            llm = CodexInterface(codex_bin)
            typer.echo(f"✅ Codex CLI initialized")
        except RuntimeError as e:
            typer.echo(f"❌ {e}", err=True)
            raise typer.Exit(1)
        
        # Initialize tool registry
        typer.echo(f"🔧 Registering tools...")
        tool_registry = ToolRegistry()
        
        # Initialize memory components
        memory_manager = MemoryManager(project_dir)
        vector_store = VectorStore(project_dir)
        
        # Register all tools
        tool_registry.register(MemorySearchTool(memory_manager, vector_store))
        tool_registry.register(CharacterGenerateTool(memory_manager, vector_store))
        tool_registry.register(LocationGenerateTool(memory_manager, vector_store))
        tool_registry.register(RelationshipCreateTool(memory_manager))
        tool_registry.register(RelationshipUpdateTool(memory_manager))
        tool_registry.register(RelationshipQueryTool(memory_manager))
        
        typer.echo(f"   Registered {len(tool_registry)} tools")
        
        # Create agent
        typer.echo(f"🤖 Initializing story agent...")
        agent = StoryAgent(project_dir, llm, tool_registry, config)
        
        # Execute tick
        typer.echo(f"\n⚙️  Executing tick {current_tick}...")
        
        result = agent.tick()
        
        typer.echo(f"\n✅ Tick {current_tick} completed successfully!")
        typer.echo(f"   📋 Plan: {result['plan_file']}")
        typer.echo(f"   📝 Scene: {result['scene_file']}")
        typer.echo(f"   📊 Word count: {result['word_count']}")
        typer.echo(f"   🔧 Actions: {result['actions_executed']}")
        
        # Show entity updates if any
        entities = result.get('entities_updated', {})
        if entities and any(entities.values()):
            typer.echo(f"\n   📊 Entity Updates:")
            if entities.get('characters_updated'):
                typer.echo(f"      👤 Characters: {entities['characters_updated']}")
            if entities.get('locations_updated'):
                typer.echo(f"      📍 Locations: {entities['locations_updated']}")
            if entities.get('loops_created'):
                typer.echo(f"      🔄 Loops created: {entities['loops_created']}")
            if entities.get('loops_resolved'):
                typer.echo(f"      ✓ Loops resolved: {entities['loops_resolved']}")
            if entities.get('relationships_updated'):
                typer.echo(f"      🤝 Relationships: {entities['relationships_updated']}")
        
        # Show warnings if any
        if result.get('eval_warnings'):
            typer.echo(f"\n   ⚠️  Warnings: {len(result['eval_warnings'])}")
            for warning in result['eval_warnings']:
                typer.echo(f"      - {warning}")
        
        typer.echo(f"\n   ⏭️  Next tick: {current_tick + 1}")
        
    except RuntimeError as e:
        # Tool execution error - details saved to /errors/
        typer.echo(f"\n❌ Tick execution failed", err=True)
        typer.echo(f"   Error: {str(e)}", err=True)
        typer.echo(f"\n📋 Error details saved to {project_dir}/errors/", err=True)
        typer.echo(f"\n🔧 Recovery options:", err=True)
        typer.echo(f"   1. Fix the issue and run 'novel tick' again", err=True)
        typer.echo(f"   2. Manually edit the plan file", err=True)
        typer.echo(f"   3. Skip this tick (edit state.json)", err=True)
        raise typer.Exit(1)
    
    except ValueError as e:
        typer.echo(f"❌ Validation error: {e}", err=True)
        raise typer.Exit(1)
    
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        import traceback
        typer.echo(traceback.format_exc(), err=True)
        raise typer.Exit(1)


@app.command()
def run(
    n: int = typer.Option(
        5,
        "--n",
        "-n",
        help="Number of ticks to run"
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    checkpoint_interval: int = typer.Option(
        10,
        "--checkpoint-interval",
        help="Create checkpoint every N ticks (0 to disable)"
    )
):
    """Run multiple story generation ticks.
    
    Runs N consecutive ticks, generating multiple scenes.
    Automatically creates checkpoints at specified intervals.
    
    Example:
        novel run --n 10
        novel run --n 5 --project ~/novels/my-story
        novel run --n 20 --checkpoint-interval 5
    """
    from ..memory.checkpoint import create_checkpoint, should_create_checkpoint
    
    try:
        project_dir = Path(find_project_dir(project))
        typer.echo(f"📖 Running {n} ticks for project: {project_dir}")
        
        if checkpoint_interval > 0:
            typer.echo(f"💾 Checkpoints enabled (every {checkpoint_interval} ticks)\n")
        else:
            typer.echo(f"💾 Checkpoints disabled\n")
        
        # Track last checkpoint
        state = load_project_state(project_dir)
        last_checkpoint_tick = None
        
        # Find last checkpoint if any
        from ..memory.checkpoint import list_checkpoints
        checkpoints = list_checkpoints(project_dir)
        if checkpoints:
            last_checkpoint_tick = max(c.tick for c in checkpoints)
        
        successful_ticks = 0
        
        for i in range(n):
            typer.echo(f"--- Tick {i+1}/{n} ---")
            
            # Execute single tick by calling tick() logic
            # We need to import and reuse the tick logic here
            try:
                # Load fresh state
                state = load_project_state(project_dir)
                config = get_project_config(project_dir)
                current_tick = state['current_tick']
                
                # Initialize LLM
                codex_bin = config.get('llm.codex_bin_path', 'codex')
                initialize_llm(codex_bin)
                llm = CodexInterface(codex_bin)
                
                # Initialize tool registry
                tool_registry = ToolRegistry()
                memory_manager = MemoryManager(project_dir)
                vector_store = VectorStore(project_dir)
                
                tool_registry.register(MemorySearchTool(memory_manager, vector_store))
                tool_registry.register(CharacterGenerateTool(memory_manager, vector_store))
                tool_registry.register(LocationGenerateTool(memory_manager, vector_store))
                tool_registry.register(RelationshipCreateTool(memory_manager))
                tool_registry.register(RelationshipUpdateTool(memory_manager))
                tool_registry.register(RelationshipQueryTool(memory_manager))
                
                # Create agent
                agent = StoryAgent(project_dir, llm, tool_registry, config)
                
                # Execute tick
                result = agent.tick()
                
                typer.echo(f"   ✅ Tick {current_tick} completed")
                typer.echo(f"   📝 Scene: {result['scene_file']}")
                typer.echo(f"   📊 Words: {result['word_count']}\n")
                
                successful_ticks += 1
                
                # Check if we should create checkpoint
                if checkpoint_interval > 0:
                    new_tick = current_tick + 1  # Tick was incremented
                    if should_create_checkpoint(new_tick, checkpoint_interval, last_checkpoint_tick):
                        typer.echo(f"   💾 Creating checkpoint...")
                        try:
                            checkpoint_path = create_checkpoint(
                                project_dir, 
                                new_tick, 
                                f"auto (novel run --n {n})"
                            )
                            typer.echo(f"   ✅ Checkpoint created: {checkpoint_path.name}\n")
                            last_checkpoint_tick = new_tick
                        except Exception as e:
                            typer.echo(f"   ⚠️  Checkpoint failed: {e}\n")
                
            except Exception as e:
                typer.echo(f"   ❌ Tick failed: {e}\n")
                typer.echo(f"   Stopping after {successful_ticks} successful ticks")
                break
        
        typer.echo(f"\n✅ Completed {successful_ticks}/{n} ticks")
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def summarize(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    )
):
    """Compile summaries of all scenes.
    
    Generates a summary document from all scene files.
    
    Example:
        novel summarize
        novel summarize --project ~/novels/my-story
    """
    try:
        project_dir = find_project_dir(project)
        typer.echo(f"📖 Summarizing project: {project_dir}")
        
        # TODO: Implement summarization (Phase 2-3)
        typer.echo(f"TODO: Implement scene summarization")
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def status(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON"
    )
):
    """Show current project status.
    
    Displays project information, current tick, and statistics.
    
    Example:
        novel status
        novel status --json
    """
    from .commands.status import get_status_info, display_status, display_status_json
    
    try:
        project_dir = Path(find_project_dir(project))
        state = load_project_state(project_dir)
        
        info = get_status_info(project_dir, state)
        
        if json_output:
            display_status_json(info)
        else:
            display_status(info)
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command(name="list")
def list_entities(
    entity_type: str = typer.Argument(
        ...,
        help="Entity type to list: characters, locations, loops, scenes"
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Show detailed information"
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON"
    )
):
    """List entities in the project.
    
    Examples:
        novel list characters
        novel list locations --verbose
        novel list loops --json
        novel list scenes
    """
    from .commands.list import (
        list_characters, list_locations, list_open_loops, list_scenes,
        display_characters, display_locations, display_loops, display_scenes,
        display_json
    )
    
    try:
        project_dir = Path(find_project_dir(project))
        
        if entity_type == "characters":
            items = list_characters(project_dir, verbose)
            if json_output:
                display_json(items)
            else:
                display_characters(items, verbose)
        
        elif entity_type == "locations":
            items = list_locations(project_dir, verbose)
            if json_output:
                display_json(items)
            else:
                display_locations(items, verbose)
        
        elif entity_type == "loops":
            items = list_open_loops(project_dir, verbose)
            if json_output:
                display_json(items)
            else:
                display_loops(items, verbose)
        
        elif entity_type == "scenes":
            items = list_scenes(project_dir, verbose)
            if json_output:
                display_json(items)
            else:
                display_scenes(items, verbose)
        
        else:
            typer.echo(f"❌ Unknown entity type: {entity_type}", err=True)
            typer.echo("Valid types: characters, locations, loops, scenes", err=True)
            raise typer.Exit(1)
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def inspect(
    id: Optional[str] = typer.Option(
        None,
        "--id",
        help="Entity ID (C0, L0, S001, etc.)"
    ),
    file: Optional[str] = typer.Option(
        None,
        "--file",
        help="Direct file path"
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Output raw JSON"
    ),
    history_limit: int = typer.Option(
        5,
        "--history-limit",
        help="Number of history entries to show"
    )
):
    """Inspect detailed information about an entity.
    
    Examples:
        novel inspect --id C0
        novel inspect --id L3 --verbose
        novel inspect --file memory/characters/C0.json --raw
    """
    from .commands.inspect import inspect_entity
    
    try:
        project_dir = Path(find_project_dir(project))
        
        file_path = Path(file) if file else None
        success = inspect_entity(project_dir, id, file_path, raw, history_limit)
        
        if not success:
            raise typer.Exit(1)
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def compile(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    output: str = typer.Option(
        "manuscript.md",
        "--output",
        "-o",
        help="Output file path"
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        help="Output format: markdown, html"
    ),
    include_metadata: bool = typer.Option(
        True,
        "--include-metadata/--no-metadata",
        help="Include metadata appendix"
    ),
    scenes: Optional[str] = typer.Option(
        None,
        "--scenes",
        help="Scene range: 1-10 or 5,7,9"
    )
):
    """Compile all scenes into a single manuscript.
    
    Examples:
        novel compile
        novel compile --output draft.md --scenes 1-10
        novel compile --format html --output manuscript.html
    """
    from .commands.compile import compile_manuscript
    
    try:
        project_dir = Path(find_project_dir(project))
        output_path = Path(output)
        
        success = compile_manuscript(
            project_dir,
            output_path,
            format,
            include_metadata,
            scenes
        )
        
        if not success:
            raise typer.Exit(1)
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def plan(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    save: Optional[str] = typer.Option(
        None,
        "--save",
        help="Save plan to file"
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Show full context and prompts"
    )
):
    """Preview the next plan without executing it.
    
    Examples:
        novel plan
        novel plan --save preview.json
        novel plan --verbose
    """
    from .commands.plan import preview_plan
    
    try:
        project_dir = Path(find_project_dir(project))
        save_path = Path(save) if save else None
        
        success = preview_plan(project_dir, save_path, verbose)
        
        if not success:
            raise typer.Exit(1)
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def checkpoint(
    action: str = typer.Argument(
        ...,
        help="Action: create, list, restore, delete"
    ),
    checkpoint_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="Checkpoint ID (for restore/delete)"
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    message: Optional[str] = typer.Option(
        None,
        "--message",
        "-m",
        help="Description for checkpoint creation"
    )
):
    """Manage project checkpoints.
    
    Examples:
        novel checkpoint create --message "Before major plot twist"
        novel checkpoint list
        novel checkpoint restore --id checkpoint_tick_010
        novel checkpoint delete --id checkpoint_tick_005
    """
    from .commands.checkpoint import (
        create_checkpoint_cmd,
        list_checkpoints_cmd,
        restore_checkpoint_cmd,
        delete_checkpoint_cmd
    )
    
    try:
        project_dir = Path(find_project_dir(project))
        
        if action == "create":
            create_checkpoint_cmd(project_dir, message)
        elif action == "list":
            list_checkpoints_cmd(project_dir)
        elif action == "restore":
            if not checkpoint_id:
                typer.echo("❌ --id required for restore", err=True)
                raise typer.Exit(1)
            restore_checkpoint_cmd(project_dir, checkpoint_id)
        elif action == "delete":
            if not checkpoint_id:
                typer.echo("❌ --id required for delete", err=True)
                raise typer.Exit(1)
            delete_checkpoint_cmd(project_dir, checkpoint_id)
        else:
            typer.echo(f"❌ Unknown action: {action}", err=True)
            typer.echo("Valid actions: create, list, restore, delete", err=True)
            raise typer.Exit(1)
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)
    except IOError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
