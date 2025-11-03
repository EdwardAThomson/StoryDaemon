"""Main CLI entry point for StoryDaemon."""
import typer
from typing import Optional
from .project import (
    create_novel_project,
    find_project_dir,
    load_project_state,
    save_project_state,
    get_project_config
)
from ..tools.llm_interface import initialize_llm, send_prompt


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
    
    Generates a single scene passage (500-900 words) using the
    planner → tools → writer → evaluator loop.
    
    Example:
        novel tick
        novel tick --project ~/novels/my-story
    """
    try:
        # Find project directory
        project_dir = find_project_dir(project)
        typer.echo(f"📖 Running tick for project: {project_dir}")
        
        # Load project state and config
        state = load_project_state(project_dir)
        config = get_project_config(project_dir)
        
        typer.echo(f"   Current tick: {state['current_tick']}")
        
        # Initialize LLM
        codex_bin = config.get('llm.codex_bin_path', 'codex')
        try:
            initialize_llm(codex_bin)
            typer.echo(f"✅ Codex CLI initialized")
        except RuntimeError as e:
            typer.echo(f"❌ {e}", err=True)
            raise typer.Exit(1)
        
        # TODO: Implement actual tick logic (Phase 3-4)
        # For now, just test Codex CLI connection
        typer.echo(f"\n🧪 Testing Codex CLI connection...")
        try:
            response = send_prompt(
                "Write a single creative sentence about a mysterious character.",
                max_tokens=50
            )
            typer.echo(f"✅ Test generation successful:")
            typer.echo(f"   {response}\n")
        except RuntimeError as e:
            typer.echo(f"❌ Generation failed: {e}", err=True)
            raise typer.Exit(1)
        
        # Update state
        state['current_tick'] += 1
        save_project_state(project_dir, state)
        
        typer.echo(f"✅ Tick complete. Next tick: {state['current_tick']}")
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
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
