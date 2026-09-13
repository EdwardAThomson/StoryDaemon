"""Story foundation prompting and loading for project creation."""

import typer
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List


class StoryFoundation:
    """Represents the immutable story foundation."""
    
    def __init__(
        self,
        genre: str,
        premise: str,
        protagonist_archetype: str,
        setting: str,
        tone: str,
        themes: Optional[List[str]] = None,
        primary_goal: Optional[str] = None,
        protagonist_name: Optional[str] = None
    ):
        self.genre = genre
        self.premise = premise
        self.protagonist_archetype = protagonist_archetype
        self.setting = setting
        self.tone = tone
        self.themes = themes or []
        self.primary_goal = primary_goal  # Optional user-specified story goal
        # The protagonist's NAME, separate from the archetype describing their
        # role. They were one field, and a name written into the archetype was
        # recovered later by splitting on a comma and checking capitalisation,
        # which turned "Doctor Miriam Vale, a field surgeon" into a character
        # whose first name was "Doctor". Structure belongs in fields, not in
        # prose a regex has to mine.
        self.protagonist_name = (protagonist_name or "").strip() or None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for state.json."""
        return {
            "genre": self.genre,
            "premise": self.premise,
            "protagonist_archetype": self.protagonist_archetype,
            "setting": self.setting,
            "tone": self.tone,
            "themes": self.themes,
            "primary_goal": self.primary_goal,
            "protagonist_name": self.protagonist_name
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryFoundation":
        """Create from dictionary."""
        return cls(
            genre=data["genre"],
            premise=data["premise"],
            protagonist_archetype=data["protagonist_archetype"],
            setting=data["setting"],
            tone=data["tone"],
            themes=data.get("themes", []),
            primary_goal=data.get("primary_goal"),
            # Absent on foundations created before the field existed.
            protagonist_name=data.get("protagonist_name")
        )


def prompt_for_foundation() -> tuple[StoryFoundation, Dict[str, Any]]:
    """Interactively prompt user for story foundation and plot-first configuration.
    
    Returns:
        Tuple of (StoryFoundation object, plot_config dict)
    """
    typer.echo("\n📚 Story Foundation Setup")
    typer.echo("━" * 60)
    typer.echo("\nDefine the immutable constraints for your story.\n")
    
    # Genre
    genre = typer.prompt(
        "Genre (e.g., fantasy, sci-fi, thriller, literary)",
        type=str
    ).strip()
    
    # Premise
    typer.echo("\nPremise (1-2 sentences describing the story's core question):")
    premise = typer.prompt("", type=str).strip()
    
    # Protagonist: name and archetype are asked separately and on purpose.
    typer.echo("\nProtagonist")
    protagonist_name = typer.prompt(
        "  Name (leave blank to have one generated)",
        type=str, default="", show_default=False
    ).strip()
    protagonist_archetype = typer.prompt(
        "  Archetype (personality/role, NOT the name)",
        type=str
    ).strip()
    
    # Setting
    setting = typer.prompt(
        "Setting (time/place/world)",
        type=str
    ).strip()
    
    # Tone
    tone = typer.prompt(
        "Tone (mood/atmosphere)",
        type=str
    ).strip()
    
    # Themes (optional)
    themes_input = typer.prompt(
        "Themes (optional, comma-separated)",
        default="",
        type=str
    ).strip()
    
    themes = [t.strip() for t in themes_input.split(",") if t.strip()] if themes_input else []
    
    # Primary goal (optional)
    primary_goal = typer.prompt(
        "Primary story goal (optional, will auto-emerge if not specified)",
        default="",
        type=str
    ).strip()
    
    primary_goal = primary_goal if primary_goal else None
    
    # Plot-First Mode Configuration
    typer.echo("\n" + "━" * 60)
    typer.echo("📋 Plot-First Mode Configuration")
    typer.echo("━" * 60)
    typer.echo("\nPlot-first mode generates plot beats that guide scene generation.")
    typer.echo("This provides forward momentum and reduces repetition.\n")
    
    use_plot_first = typer.confirm(
        "Enable plot-first mode? (Recommended for structured stories)",
        default=False
    )
    
    plot_config = {}
    
    if use_plot_first:
        typer.echo("\n📖 Plot-First Settings:")
        
        # Enforcement level
        typer.echo("\nEnforcement level:")
        typer.echo("  1. Lenient - Beats guide but don't block (fallback to reactive)")
        typer.echo("  2. Standard - Verify beats, allow skipping if not accomplished")
        typer.echo("  3. Strict - Beats must be accomplished, no fallback (recommended)")
        
        enforcement = typer.prompt(
            "\nSelect enforcement level",
            type=int,
            default=3
        )
        
        if enforcement == 1:
            # Lenient mode
            plot_config = {
                "use_plot_first": True,
                "plot_first_start_tick": 2,
                "plot_beats_ahead": 5,
                "plot_regeneration_threshold": 2,
                "verify_beat_execution": True,
                "allow_beat_skip": True,
                "fallback_to_reactive": True
            }
        elif enforcement == 2:
            # Standard mode
            plot_config = {
                "use_plot_first": True,
                "plot_first_start_tick": 2,
                "plot_beats_ahead": 5,
                "plot_regeneration_threshold": 2,
                "verify_beat_execution": True,
                "allow_beat_skip": True,
                "fallback_to_reactive": False
            }
        else:
            # Strict mode (default)
            plot_config = {
                "use_plot_first": True,
                "plot_first_start_tick": 2,
                "plot_beats_ahead": 5,
                "plot_regeneration_threshold": 2,
                "verify_beat_execution": True,
                "allow_beat_skip": False,
                "fallback_to_reactive": False
            }
        
        # Advanced options
        if typer.confirm("\nCustomize advanced settings?", default=False):
            plot_config["plot_beats_ahead"] = typer.prompt(
                "  Beats to generate at once",
                type=int,
                default=5
            )
            plot_config["plot_regeneration_threshold"] = typer.prompt(
                "  Regenerate when pending beats drop below",
                type=int,
                default=2
            )
    else:
        # Plot-first disabled
        plot_config = {
            "use_plot_first": False
        }
    
    # Confirmation
    typer.echo("\n" + "━" * 60)
    typer.echo("📋 Foundation Summary:")
    typer.echo(f"  Genre: {genre}")
    typer.echo(f"  Premise: {premise}")
    typer.echo(f"  Protagonist: {protagonist_name or '(name to be generated)'}"
               f" - {protagonist_archetype}")
    typer.echo(f"  Setting: {setting}")
    typer.echo(f"  Tone: {tone}")
    if themes:
        typer.echo(f"  Themes: {', '.join(themes)}")
    if primary_goal:
        typer.echo(f"  Primary Goal: {primary_goal}")
    
    typer.echo("\n📖 Plot Configuration:")
    if plot_config.get("use_plot_first"):
        if not plot_config.get("allow_beat_skip") and not plot_config.get("fallback_to_reactive"):
            typer.echo("  Mode: Strict (beats enforced)")
        elif plot_config.get("allow_beat_skip"):
            typer.echo("  Mode: Lenient/Standard (beats guide)")
        typer.echo(f"  Beats ahead: {plot_config.get('plot_beats_ahead', 5)}")
        typer.echo(f"  Regeneration threshold: {plot_config.get('plot_regeneration_threshold', 2)}")
    else:
        typer.echo("  Mode: Reactive (no plot beats)")
    typer.echo("━" * 60)
    
    confirm = typer.confirm("\nProceed with this configuration?", default=True)
    if not confirm:
        typer.echo("Setup cancelled.")
        raise typer.Abort()
    
    foundation = StoryFoundation(
        genre=genre,
        premise=premise,
        protagonist_archetype=protagonist_archetype,
        protagonist_name=protagonist_name,
        setting=setting,
        tone=tone,
        themes=themes,
        primary_goal=primary_goal
    )
    
    return foundation, plot_config


def load_foundation_from_file(file_path: Path) -> StoryFoundation:
    """Load story foundation from YAML file.
    
    Args:
        file_path: Path to YAML file containing foundation
    
    Returns:
        StoryFoundation object
    
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is invalid or missing required fields
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Foundation file not found: {file_path}")
    
    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML file: {e}")
    
    # Validate required fields
    required_fields = ["genre", "premise", "protagonist_archetype", "setting", "tone"]
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        raise ValueError(f"Missing required fields in foundation file: {', '.join(missing_fields)}")
    
    # Parse themes if present
    themes = data.get("themes", [])
    if isinstance(themes, str):
        themes = [t.strip() for t in themes.split(",") if t.strip()]
    elif not isinstance(themes, list):
        themes = []
    
    # Get primary goal if present
    primary_goal = data.get("primary_goal")
    
    return StoryFoundation(
        genre=data["genre"],
        premise=data["premise"],
        protagonist_archetype=data["protagonist_archetype"],
        setting=data["setting"],
        tone=data["tone"],
        themes=themes,
        primary_goal=primary_goal
    )


def create_foundation_from_args(
    genre: Optional[str] = None,
    premise: Optional[str] = None,
    protagonist: Optional[str] = None,
    setting: Optional[str] = None,
    tone: Optional[str] = None,
    themes: Optional[str] = None
) -> Optional[StoryFoundation]:
    """Create foundation from command-line arguments.
    
    Args:
        genre: Story genre
        premise: Story premise
        protagonist: Protagonist archetype
        setting: Story setting
        tone: Story tone
        themes: Comma-separated themes
    
    Returns:
        StoryFoundation if all required fields provided, None otherwise
    """
    # Check if any foundation args were provided
    if not any([genre, premise, protagonist, setting, tone]):
        return None
    
    # If some but not all are provided, prompt for missing ones
    if not all([genre, premise, protagonist, setting, tone]):
        typer.echo("⚠️  Some foundation fields provided but not all. Please provide all required fields:")
        typer.echo("   --genre, --premise, --protagonist, --setting, --tone")
        raise typer.Exit(1)
    
    # Parse themes
    theme_list = [t.strip() for t in themes.split(",") if t.strip()] if themes else []
    
    return StoryFoundation(
        genre=genre,
        premise=premise,
        protagonist_archetype=protagonist,
        setting=setting,
        tone=tone,
        themes=theme_list
    )


def format_foundation_display(foundation: StoryFoundation) -> str:
    """Format foundation for display in status command.
    
    Args:
        foundation: StoryFoundation object
    
    Returns:
        Formatted string for display
    """
    lines = [
        "📚 Story Foundation",
        "━" * 60,
        f"Genre: {foundation.genre}",
        f"Premise: {foundation.premise}",
        f"Protagonist: {foundation.protagonist_archetype}",
        f"Setting: {foundation.setting}",
        f"Tone: {foundation.tone}",
    ]
    
    if foundation.themes:
        lines.append(f"Themes: {', '.join(foundation.themes)}")
    
    return "\n".join(lines)
