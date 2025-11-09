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
        themes: Optional[List[str]] = None
    ):
        self.genre = genre
        self.premise = premise
        self.protagonist_archetype = protagonist_archetype
        self.setting = setting
        self.tone = tone
        self.themes = themes or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for state.json."""
        return {
            "genre": self.genre,
            "premise": self.premise,
            "protagonist_archetype": self.protagonist_archetype,
            "setting": self.setting,
            "tone": self.tone,
            "themes": self.themes
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
            themes=data.get("themes", [])
        )


def prompt_for_foundation() -> StoryFoundation:
    """Interactively prompt user for story foundation.
    
    Returns:
        StoryFoundation object with user inputs
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
    
    # Protagonist archetype
    protagonist_archetype = typer.prompt(
        "\nProtagonist archetype (personality/role)",
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
    
    # Confirmation
    typer.echo("\n" + "━" * 60)
    typer.echo("📋 Foundation Summary:")
    typer.echo(f"  Genre: {genre}")
    typer.echo(f"  Premise: {premise}")
    typer.echo(f"  Protagonist: {protagonist_archetype}")
    typer.echo(f"  Setting: {setting}")
    typer.echo(f"  Tone: {tone}")
    if themes:
        typer.echo(f"  Themes: {', '.join(themes)}")
    typer.echo("━" * 60)
    
    confirm = typer.confirm("\nProceed with this foundation?", default=True)
    if not confirm:
        typer.echo("Foundation setup cancelled.")
        raise typer.Abort()
    
    return StoryFoundation(
        genre=genre,
        premise=premise,
        protagonist_archetype=protagonist_archetype,
        setting=setting,
        tone=tone,
        themes=themes
    )


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
    
    return StoryFoundation(
        genre=data["genre"],
        premise=data["premise"],
        protagonist_archetype=data["protagonist_archetype"],
        setting=data["setting"],
        tone=data["tone"],
        themes=themes
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
