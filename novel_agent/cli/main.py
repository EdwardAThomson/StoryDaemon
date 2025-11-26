"""Main CLI entry point for StoryDaemon."""
import typer
from pathlib import Path
from typing import Optional, Dict, Any
from ..configs.config import Config
from .project import (
    create_novel_project,
    find_project_dir,
    load_project_state,
    save_project_state,
    get_project_config
)
from .foundation import (
    prompt_for_foundation,
    load_foundation_from_file,
    create_foundation_from_args
)
from ..tools.llm_interface import initialize_llm, send_prompt
from ..tools.registry import ToolRegistry
from ..tools.memory_tools import (
    MemorySearchTool,
    CharacterGenerateTool,
    LocationGenerateTool,
    RelationshipCreateTool,
    RelationshipUpdateTool,
    RelationshipQueryTool,
    FactionGenerateTool,
    FactionUpdateTool,
    FactionQueryTool
)
from ..tools.name_generator import NameGeneratorTool
from ..memory.manager import MemoryManager
from ..memory.vector_store import VectorStore
from ..agent.agent import StoryAgent
from .recent_projects import RecentProjects
from .commands.plot import (
    get_plot_status,
    display_plot_status,
    display_plot_status_detailed,
    get_next_beat,
    display_next_beat,
    generate_and_append_beats_cli,
    display_generated_beats,
)


def _show_stage_stats(stats: dict):
    """Display multi-stage planner statistics."""
    typer.echo(f"\n📊 Multi-Stage Planning Stats:")
    typer.echo(f"   Stage 1 (Strategic): {stats.get('stage1_tokens', 0)} tokens, {stats.get('stage1_time', 0):.2f}s")
    typer.echo(f"   Stage 2 (Semantic): {stats.get('stage2_items', 0)} items, {stats.get('stage2_time', 0):.2f}s")
    typer.echo(f"   Stage 3 (Tactical): {stats.get('stage3_tokens', 0)} tokens, {stats.get('stage3_time', 0):.2f}s")
    total_time = stats.get('stage1_time', 0) + stats.get('stage2_time', 0) + stats.get('stage3_time', 0)
    total_tokens = stats.get('stage1_tokens', 0) + stats.get('stage3_tokens', 0)
    typer.echo(f"   Total: {total_tokens} tokens, {total_time:.2f}s")


def _show_story_stats(project_dir: Path, state: dict):
    """Display story statistics summary."""
    from ..memory.manager import MemoryManager
    
    memory = MemoryManager(project_dir)
    
    # Count entities
    scene_ids = memory.list_scenes()
    all_chars = memory.list_characters()
    all_locs = memory.list_locations()
    all_factions = memory.list_factions()
    all_loops = memory.load_open_loops()
    all_lore = memory.load_all_lore()
    
    # Calculate total word count and tension from scene files
    total_words = 0
    tensions = []
    for scene_id in scene_ids:
        scene = memory.load_scene(scene_id)
        if scene and scene.word_count:
            total_words += scene.word_count
        if scene and scene.tension_level is not None:
            tensions.append(scene.tension_level)
    
    avg_tension = sum(tensions) / len(tensions) if tensions else 0
    
    typer.echo(f"\n📖 Story Stats:")
    typer.echo(f"   Scenes: {len(scene_ids)} ({total_words:,} words)")
    typer.echo(f"   Characters: {len(all_chars)}")
    typer.echo(f"   Locations: {len(all_locs)}")
    typer.echo(f"   Factions: {len(all_factions)}")
    typer.echo(f"   Open Loops: {len(all_loops)}")
    typer.echo(f"   Lore Items: {len(all_lore)}")
    if tensions:
        typer.echo(f"   Avg Tension: {avg_tension:.1f}/10")


def _prompt_for_llm_selection() -> tuple[str, str]:
    """Interactively select LLM backend and model for a new project.

    Returns a (backend, model) tuple which will be stored in the
    project's config.yaml. Defaults are derived from the global
    configuration and adjusted per backend so users can just press
    Enter to accept sensible values.
    """
    config = Config()

    default_backend = config.get("llm.backend", "codex")
    typer.echo("\n🧠 LLM Backend & Model")
    typer.echo("Select which LLM backend this project will use. This choice is "
               "stored in the project's config.yaml and used by `novel tick`/`run` "
               "unless you override it on the CLI.\n")

    options = [
        ("codex", "Codex CLI (default; uses local `codex` binary)"),
        ("api", "API backend (OpenAI GPT-5.x, Claude 4.5, Gemini 2.5 Pro)"),
        ("gemini-cli", "Gemini CLI (local `gemini` binary)"),
        ("claude-cli", "Claude Code CLI (local `claude` binary)"),
    ]

    # Determine which option index corresponds to the current default backend
    default_index = 1
    for idx, (value, _label) in enumerate(options, start=1):
        if value == default_backend:
            default_index = idx
            break

    typer.echo("Available backends:")
    for idx, (value, label) in enumerate(options, start=1):
        marker = " (default)" if value == default_backend else ""
        typer.echo(f"  {idx}. {label}{marker}")

    # Prompt for backend choice
    backend: Optional[str] = None
    while backend is None:
        choice = typer.prompt(
            "Choose LLM backend [1-4]",
            default=str(default_index),
        ).strip()
        try:
            idx = int(choice)
        except ValueError:
            typer.echo("Please enter a number between 1 and 4.")
            continue

        if 1 <= idx <= len(options):
            backend = options[idx - 1][0]
        else:
            typer.echo("Please enter a number between 1 and 4.")

    # Choose a sensible default model for the selected backend
    if backend == "gemini-cli":
        default_model = "gemini-2.5-pro"
    elif backend == "claude-cli":
        default_model = "claude-4.5"
    else:
        # codex or api: fall back to configured defaults
        default_model = (
            config.get("llm.model")
            or config.get("llm.openai_model", "gpt-5.1")
        )

    typer.echo(
        f"\nModel name for backend '{backend}' "
        f"(press Enter to use default: {default_model})"
    )
    model = typer.prompt("Model", default=default_model).strip()
    if not model:
        model = default_model

    return backend, model


app = typer.Typer(
    name="novel",
    help="StoryDaemon - Agentic novel generation system",
    add_completion=False
)

plot_app = typer.Typer(name="plot", help="Plot outline (PlotBeat Phase 3) commands")
app.add_typer(plot_app, name="plot")


@app.command()
def new(
    name: str = typer.Argument(..., help="Name of the novel"),
    dir: Optional[str] = typer.Option(
        None,
        "--dir",
        "-d",
        help="Base directory for novel (default: ~/novels)"
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Use interactive story foundation wizard (recommended for new users)"
    ),
    foundation_file: Optional[Path] = typer.Option(
        None,
        "--foundation",
        "-f",
        help="Load story foundation from YAML file"
    ),
    genre: Optional[str] = typer.Option(
        None,
        "--genre",
        help="Story genre (e.g., fantasy, sci-fi, thriller)"
    ),
    premise: Optional[str] = typer.Option(
        None,
        "--premise",
        help="Story premise (1-2 sentences)"
    ),
    protagonist: Optional[str] = typer.Option(
        None,
        "--protagonist",
        help="Protagonist archetype (personality/role)"
    ),
    setting: Optional[str] = typer.Option(
        None,
        "--setting",
        help="Story setting (time/place/world)"
    ),
    tone: Optional[str] = typer.Option(
        None,
        "--tone",
        help="Story tone (mood/atmosphere)"
    ),
    themes: Optional[str] = typer.Option(
        None,
        "--themes",
        help="Story themes (comma-separated)"
    )
):
    """Create a new novel project with optional story foundation.

    Creates a complete project structure with memory directories,
    configuration files, and initial state. By default, runs the
    interactive story foundation wizard so the LLM has clear
    constraints (genre, premise, setting, etc.). Advanced users
    can disable the wizard with ``--no-interactive`` or supply a
    foundation via file/CLI options.

    Examples:
        # Recommended: interactive foundation setup (default)
        novel new my-story

        # Explicitly disable interactive wizard (bare project)
        novel new my-story --no-interactive

        # Load foundation from file (non-interactive)
        novel new my-story --foundation foundation.yaml

        # Specify foundation via command-line (non-interactive)
        novel new my-story --genre "science fiction" --premise "..." --protagonist "..." --setting "..." --tone "..."
    """
    try:
        # Determine foundation source
        foundation = None

        # If the user has provided an explicit non-interactive source
        # (foundation file or CLI foundation fields), disable the
        # interactive wizard even though it is the default.
        has_foundation_args = any([genre, premise, protagonist, setting, tone, themes])
        interactive_effective = interactive
        if foundation_file or has_foundation_args:
            interactive_effective = False

        llm_backend_override: Optional[str] = None
        llm_model_override: Optional[str] = None
        plot_config: Optional[Dict[str, Any]] = None

        if interactive_effective:
            # Interactive prompting (recommended default)
            foundation, plot_config = prompt_for_foundation()
            llm_backend_override, llm_model_override = _prompt_for_llm_selection()
        elif foundation_file:
            # Load from file
            foundation = load_foundation_from_file(foundation_file)
            typer.echo(f"✅ Loaded foundation from: {foundation_file}")
        else:
            # Try to create from command-line args (may return None)
            foundation = create_foundation_from_args(
                genre=genre,
                premise=premise,
                protagonist=protagonist,
                setting=setting,
                tone=tone,
                themes=themes
            )
        
        # Create project with optional foundation, LLM overrides, and plot config
        project_dir = create_novel_project(
            name,
            dir,
            foundation=foundation,
            llm_backend=llm_backend_override,
            llm_model=llm_model_override,
            plot_config=plot_config,
        )
        typer.echo(f"✅ Created novel project: {project_dir}")
        
        if foundation:
            typer.echo(f"\n📚 Story foundation set:")
            typer.echo(f"   Genre: {foundation.genre}")
            typer.echo(f"   Setting: {foundation.setting}")
        
        if plot_config and plot_config.get("use_plot_first"):
            typer.echo(f"\n📋 Plot-first mode enabled:")
            if not plot_config.get("allow_beat_skip") and not plot_config.get("fallback_to_reactive"):
                typer.echo(f"   Mode: Strict (beats enforced)")
            else:
                typer.echo(f"   Mode: Lenient/Standard")
            typer.echo(f"   Beats will auto-generate starting from tick 2")
        
        typer.echo(f"\n📝 Next steps:")
        typer.echo(f"  cd {project_dir}")
        typer.echo(f"  novel tick  # Run a few ticks to establish characters/world")
        if plot_config and plot_config.get("use_plot_first"):
            typer.echo(f"  # Plot beats will auto-generate from tick 2 onwards")
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
    ),
    save_prompts: bool = typer.Option(
        False,
        "--save-prompts",
        help="Save prompts to prompts/ directory for inspection"
    ),
    llm_backend: Optional[str] = typer.Option(
        None,
        "--llm-backend",
        help="LLM backend: codex, api (multi-provider API), gemini-cli (Gemini CLI), or claude-cli (Claude Code CLI)"
    ),
    llm_model: Optional[str] = typer.Option(
        None,
        "--llm-model",
        help="Model name for API backend (e.g., gpt-5.1, gpt-5, gpt-5.1-mini, claude-4.5, gemini-2.5-pro)"
    ),
    codex_bin: Optional[str] = typer.Option(
        None,
        "--codex-bin",
        help="Path to Codex CLI binary"
    ),
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
    # When tick() is called programmatically (e.g., from resume()), Typer
    # may pass OptionInfo objects instead of plain strings for llm_* args.
    # Normalize these to None so our backend/model resolution logic behaves
    # the same as when invoked from the CLI.
    from typer.models import OptionInfo  # type: ignore
    if isinstance(llm_backend, OptionInfo):
        llm_backend = None
    if isinstance(llm_model, OptionInfo):
        llm_model = None
    if isinstance(codex_bin, OptionInfo):
        codex_bin = None

    try:
        # Find project directory
        project_dir = Path(find_project_dir(project))
        typer.echo(f"📖 Running tick for project: {project_dir}")
        
        # Track as recent project
        recent = RecentProjects()
        state = load_project_state(project_dir)
        recent.add_project(str(project_dir), state.get('novel_name'))
        
        # Load config
        config = get_project_config(project_dir)
        
        # Determine LLM backend configuration
        backend = llm_backend or config.get('llm.backend', 'codex')
        codex_bin_effective = codex_bin or config.get('llm.codex_bin_path', 'codex')
        # Prefer generic llm.model, fall back to legacy openai_model, then default
        model = (
            llm_model
            or config.get('llm.model')
            or config.get('llm.openai_model', 'gpt-5')
        )
        
        # Show prompt saving status
        if save_prompts:
            typer.echo(f"   💾 Saving prompts to: {project_dir}/prompts/")
        
        current_tick = state['current_tick']
        typer.echo(f"   Current tick: {current_tick}")
        
        # Initialize LLM backend
        try:
            llm = initialize_llm(
                backend=backend,
                codex_bin=codex_bin_effective,
                model=model,
            )
            typer.echo(f"✅ LLM backend initialized: {backend}")
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
        # Get data directory for name generator
        data_dir = Path(__file__).parent.parent / "data" / "names"
        name_gen_tool = NameGeneratorTool(data_dir)
        
        # Get beat_mode for strict name generation enforcement
        beat_mode = config.get('plot.beat_mode', 'soft_hint')
        
        tool_registry.register(name_gen_tool)
        tool_registry.register(MemorySearchTool(memory_manager, vector_store))
        tool_registry.register(CharacterGenerateTool(memory_manager, vector_store, name_gen_tool.generator, beat_mode=beat_mode))
        tool_registry.register(LocationGenerateTool(memory_manager, vector_store))
        tool_registry.register(RelationshipCreateTool(memory_manager))
        tool_registry.register(RelationshipUpdateTool(memory_manager))
        tool_registry.register(RelationshipQueryTool(memory_manager))
        # Faction tools
        tool_registry.register(FactionGenerateTool(memory_manager, vector_store, name_gen_tool.generator))
        tool_registry.register(FactionUpdateTool(memory_manager, vector_store))
        tool_registry.register(FactionQueryTool(memory_manager, vector_store))
        
        typer.echo(f"   Registered {len(tool_registry)} tools")
        
        # Create agent
        typer.echo(f"🤖 Initializing story agent...")
        agent = StoryAgent(project_dir, llm, tool_registry, config, save_prompts=save_prompts)
        
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
        
        # Show multi-stage planner stats if available (Phase 7A.5)
        if result.get('stage_stats'):
            _show_stage_stats(result['stage_stats'])
        
        # Show story stats summary
        _show_story_stats(project_dir, state)
        
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
    ),
    llm_backend: Optional[str] = typer.Option(
        None,
        "--llm-backend",
        help="LLM backend: codex, api (multi-provider API), gemini-cli (Gemini CLI), or claude-cli (Claude Code CLI)"
    ),
    llm_model: Optional[str] = typer.Option(
        None,
        "--llm-model",
        help="Model name for API backend (e.g., gpt-5.1, gpt-5, gpt-5.1-mini, claude-4.5, gemini-2.5-pro)"
    ),
    codex_bin: Optional[str] = typer.Option(
        None,
        "--codex-bin",
        help="Path to Codex CLI binary"
    ),
):
    """Run multiple story generation ticks.
    
    Runs N consecutive ticks, generating multiple scenes.
    Automatically creates checkpoints at specified intervals.
    
    Example:
        novel run --n 10
        novel run --n 5 --project ~/novels/my-story
        novel run --n 20 --checkpoint-interval 5
    """
    if not isinstance(llm_backend, (str, type(None))):
        llm_backend = None
    if not isinstance(llm_model, (str, type(None))):
        llm_model = None
    if not isinstance(codex_bin, (str, type(None))):
        codex_bin = None

    from ..memory.checkpoint import create_checkpoint, should_create_checkpoint
    
    try:
        project_dir = Path(find_project_dir(project))
        typer.echo(f"📖 Running {n} ticks for project: {project_dir}")
        
        # Track as recent project
        recent = RecentProjects()
        state = load_project_state(project_dir)
        recent.add_project(str(project_dir), state.get('novel_name'))
        
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
                
                # Initialize LLM backend
                backend = llm_backend or config.get('llm.backend', 'codex')
                codex_bin_effective = codex_bin or config.get('llm.codex_bin_path', 'codex')
                model = (
                    llm_model
                    or config.get('llm.model')
                    or config.get('llm.openai_model', 'gpt-5.1')
                )
                llm = initialize_llm(
                    backend=backend,
                    codex_bin=codex_bin_effective,
                    model=model,
                )
                
                # Initialize tool registry
                tool_registry = ToolRegistry()
                memory_manager = MemoryManager(project_dir)
                vector_store = VectorStore(project_dir)
                
                # Get data directory for name generator
                data_dir = Path(__file__).parent.parent / "data" / "names"
                name_gen_tool = NameGeneratorTool(data_dir)
                
                # Get beat_mode for strict name generation enforcement
                beat_mode = config.get('plot.beat_mode', 'soft_hint')
                
                tool_registry.register(name_gen_tool)
                tool_registry.register(MemorySearchTool(memory_manager, vector_store))
                tool_registry.register(CharacterGenerateTool(memory_manager, vector_store, name_gen_tool.generator, beat_mode=beat_mode))
                tool_registry.register(LocationGenerateTool(memory_manager, vector_store))
                tool_registry.register(RelationshipCreateTool(memory_manager))
                tool_registry.register(RelationshipUpdateTool(memory_manager))
                tool_registry.register(RelationshipQueryTool(memory_manager))
                # Faction tools
                tool_registry.register(FactionGenerateTool(memory_manager, vector_store, name_gen_tool.generator))
                
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
        help="Entity type to list: characters, locations, loops, scenes, factions"
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
        list_characters, list_locations, list_open_loops, list_scenes, list_factions,
        display_characters, display_locations, display_loops, display_scenes, display_factions,
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
        elif entity_type == "factions":
            items = list_factions(project_dir, verbose)
            if json_output:
                display_json(items)
            else:
                display_factions(items, verbose)
        
        else:
            typer.echo(f"❌ Unknown entity type: {entity_type}", err=True)
            typer.echo("Valid types: characters, locations, loops, scenes, factions", err=True)
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
def goals(
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
    """Show goal hierarchy and protagonist goals.
    
    Displays the story goal, protagonist goals (immediate, arc, story),
    and goal progress tracking.
    
    Example:
        novel goals
        novel goals --json
    """
    from .commands.goals import get_goals_info, display_goals, display_goals_json
    
    try:
        project_dir = Path(find_project_dir(project))
        state = load_project_state(project_dir)
        
        info = get_goals_info(project_dir, state)
        
        if json_output:
            display_goals_json(info)
        else:
            display_goals(info)
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def lore(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project"
    ),
    group_by: str = typer.Option(
        "category",
        "--group-by",
        "-g",
        help="Group by: category, type, or none"
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category",
        "-c",
        help="Filter by category"
    ),
    lore_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by type (rule, fact, constraint, capability, limitation)"
    ),
    importance: Optional[str] = typer.Option(
        None,
        "--importance",
        "-i",
        help="Filter by importance (critical, important, normal, minor)"
    ),
    stats: bool = typer.Option(
        False,
        "--stats",
        "-s",
        help="Show statistics only"
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON"
    )
):
    """Show world lore and rules (Phase 7A.4).
    
    Displays established world rules, constraints, and facts extracted
    from scenes. Helps maintain consistency and track world-building.
    
    Examples:
        novel lore                           # Show all lore grouped by category
        novel lore --group-by type           # Group by type instead
        novel lore --category magic          # Show only magic lore
        novel lore --importance critical     # Show only critical lore
        novel lore --stats                   # Show statistics
        novel lore --json                    # JSON output
    """
    from .commands.lore import (
        get_lore_info, display_lore, display_lore_json, display_lore_stats
    )
    
    try:
        project_dir = Path(find_project_dir(project))
        
        info = get_lore_info(project_dir)
        
        if json_output:
            display_lore_json(info)
        elif stats:
            display_lore_stats(info)
        else:
            display_lore(
                info,
                group_by=group_by,
                filter_category=category,
                filter_type=lore_type,
                filter_importance=importance
            )
        
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


@plot_app.command("status")
def plot_status(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project (default: current directory)",
    ),
    detailed: bool = typer.Option(
        False,
        "--detailed",
        "-d",
        help="Show detailed beat list with status and execution info",
    ),
):
    """Show plot outline status (beats and validation)."""
    try:
        project_dir = Path(find_project_dir(project))
        info = get_plot_status(project_dir)
        display_plot_status(info)
        if detailed:
            display_plot_status_detailed(project_dir)
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@plot_app.command("next")
def plot_next(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project (default: current directory)",
    ),
):
    """Show the next pending plot beat, if any."""
    try:
        project_dir = Path(find_project_dir(project))
        beat = get_next_beat(project_dir)
        display_next_beat(beat)
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@plot_app.command("generate")
def plot_generate(
    count: int = typer.Option(
        5,
        "--count",
        "-n",
        help="Number of beats to generate (stub; Phase 3 prompt to be implemented)",
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project (default: current directory)",
    ),
):
    """Generate plot beats using the PlotBeat Phase 3 prompt and append them.

    This is CLI-only and does not change the agent tick loop. Beats are stored
    in plot_outline.json and can be inspected with `novel plot status` and
    `novel plot next`.
    """
    try:
        project_dir = Path(find_project_dir(project))
        config = get_project_config(str(project_dir))

        # Determine LLM backend/model from project config (no CLI overrides for now)
        backend = config.get("llm.backend", "codex")
        codex_bin_effective = config.get("llm.codex_bin_path", "codex")
        model = (
            config.get("llm.model")
            or config.get("llm.openai_model", "gpt-5.1")
        )

        typer.echo(f"📍 Project: {project_dir}")
        typer.echo(f"🔧 Using LLM backend: {backend} (model={model})")

        # Initialize LLM and generate beats
        try:
            initialize_llm(backend=backend, codex_bin=codex_bin_effective, model=model)
        except RuntimeError as e:
            typer.echo(f"❌ Failed to initialize LLM backend: {e}", err=True)
            raise typer.Exit(1)

        result = generate_and_append_beats_cli(project_dir, count)
        display_generated_beats(result)

    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@plot_app.command("clear")
def plot_clear(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Path to novel project (default: current directory)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
):
    """Clear all plot beats from the project.
    
    This deletes the plot_outline.json file. Beats will auto-regenerate
    when plot-first mode is active and the agent reaches the configured
    start tick (default: tick 2).
    
    Examples:
        novel plot clear              # With confirmation
        novel plot clear --yes        # Skip confirmation
    """
    try:
        from .commands.plot import clear_plot_outline
        
        project_dir = Path(find_project_dir(project))
        clear_plot_outline(project_dir, confirm=not yes)
        
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


@app.command()
def recent(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Number of recent projects to show"
    )
):
    """Show recently accessed novel projects.
    
    Lists projects you've worked on recently, ordered by last access time.
    Use this to find project paths with UUIDs.
    
    Example:
        novel recent
        novel recent --limit 5
    """
    try:
        recent_tracker = RecentProjects()
        projects = recent_tracker.get_recent(limit=limit)
        
        if not projects:
            typer.echo("📚 No recent projects found")
            typer.echo("\n💡 Tip: Run 'novel tick' or 'novel run' on a project to track it")
            return
        
        typer.echo(f"📚 Recent Projects (last {len(projects)}):\n")
        
        for i, proj in enumerate(projects, 1):
            path = Path(proj['path'])
            name = proj.get('name', path.name)
            last_accessed = proj.get('last_accessed', 'unknown')
            
            # Load state to get tick count and UUID
            try:
                state = load_project_state(path)
                tick_count = state.get('current_tick', 0)
                tick_info = f"{tick_count} scenes"
                project_id = state.get('project_id', None)
            except:
                tick_info = "?"
                project_id = None
            
            typer.echo(f"  {i}. {name}")
            if project_id:
                typer.echo(f"     UUID: {project_id}")
            typer.echo(f"     Path: {path}")
            typer.echo(f"     Scenes: {tick_info}")
            typer.echo(f"     Last accessed: {last_accessed[:19]}")  # Trim milliseconds
            typer.echo()
        
        typer.echo("💡 Tip: Use 'novel resume' or 'novel resume --uuid <UUID>'")
        
    except Exception as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def resume(
    n: int = typer.Option(
        1,
        "--n",
        "-n",
        help="Number of ticks to run"
    ),
    uuid: Optional[str] = typer.Option(
        None,
        "--uuid",
        "-u",
        help="Resume project by UUID (e.g., 'f9f163a7')"
    )
):
    """Resume working on a recent project.
    
    Automatically finds and continues your most recently accessed project,
    or a specific project by UUID.
    
    Example:
        novel resume                    # Run 1 tick on most recent project
        novel resume --n 5              # Run 5 ticks on most recent project
        novel resume --uuid f9f163a7    # Resume specific project by UUID
    """
    try:
        recent_tracker = RecentProjects()
        
        # If UUID specified, find project by UUID
        if uuid:
            projects = recent_tracker.get_recent()
            matching_project = None
            
            for proj in projects:
                path = Path(proj['path'])
                # Check if path ends with UUID or state.json contains UUID
                if uuid in str(path):
                    matching_project = proj['path']
                    break
                # Also check state.json for project_id
                try:
                    state = load_project_state(path)
                    if state.get('project_id') == uuid:
                        matching_project = proj['path']
                        break
                except:
                    continue
            
            if not matching_project:
                typer.echo(f"❌ No recent project found with UUID: {uuid}")
                typer.echo("\n💡 Tip: Use 'novel recent' to see available projects")
                raise typer.Exit(1)
            
            recent_path = matching_project
        else:
            # Use most recent project
            recent_path = recent_tracker.get_most_recent()
            
            if not recent_path:
                typer.echo("❌ No recent projects found")
                typer.echo("\n💡 Tip: Create a project with 'novel new <name>'")
                raise typer.Exit(1)
        
        # Load project info
        state = load_project_state(Path(recent_path))
        project_name = state.get('novel_name', Path(recent_path).name)
        project_id = state.get('project_id', 'unknown')
        current_tick = state.get('current_tick', 0)
        
        typer.echo(f"📖 Resuming: {project_name}")
        typer.echo(f"   Path: {recent_path}")
        typer.echo(f"   Current progress: {current_tick} scenes")
        typer.echo()
        
        # Run the ticks using the run command logic
        if n == 1:
            # Use tick command for single tick
            from pathlib import Path as P
            tick(project=str(recent_path))
        else:
            # Use run command for multiple ticks
            run(n=n, project=str(recent_path))
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
