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
    
    Executes the planner → tools → execution loop to generate a plan
    for the next scene. (Phase 3: Planning only, Phase 4 will add writing)
    
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
        typer.echo(f"   1. Gathering context...")
        typer.echo(f"   2. Generating plan with LLM...")
        typer.echo(f"   3. Validating plan...")
        typer.echo(f"   4. Executing tool calls...")
        typer.echo(f"   5. Storing results...")
        
        result = agent.tick()
        
        typer.echo(f"\n✅ Tick {current_tick} completed successfully!")
        typer.echo(f"   Plan saved: {result['plan_file']}")
        typer.echo(f"   Actions executed: {result['actions_executed']}")
        typer.echo(f"   Next tick: {current_tick + 1}")
        
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
    )
):
    """Run multiple story generation ticks.
    
    Runs N consecutive ticks, generating multiple scenes.
    
    Example:
        novel run --n 10
        novel run --n 5 --project ~/novels/my-story
    """
    try:
        project_dir = find_project_dir(project)
        typer.echo(f"📖 Running {n} ticks for project: {project_dir}\n")
        
        for i in range(n):
            typer.echo(f"--- Tick {i+1}/{n} ---")
            # Call tick command (reuse logic)
            # TODO: Refactor tick logic into separate function
            typer.echo(f"TODO: Implement multi-tick execution\n")
        
        typer.echo(f"✅ Completed {n} ticks")
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
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
    )
):
    """Show current project status.
    
    Displays project information, current tick, and statistics.
    
    Example:
        novel status
    """
    try:
        project_dir = find_project_dir(project)
        state = load_project_state(project_dir)
        
        typer.echo(f"\n📖 Project: {state['novel_name']}")
        typer.echo(f"📍 Location: {project_dir}")
        typer.echo(f"🎬 Current tick: {state['current_tick']}")
        typer.echo(f"👤 Active character: {state.get('active_character', 'None')}")
        typer.echo(f"📅 Created: {state.get('created_at', 'Unknown')}")
        typer.echo(f"🔄 Last updated: {state.get('last_updated', 'Unknown')}\n")
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
