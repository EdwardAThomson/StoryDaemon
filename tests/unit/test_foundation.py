"""Tests for story foundation functionality."""
import pytest
import tempfile
import yaml
from pathlib import Path
from novel_agent.cli.foundation import (
    StoryFoundation,
    load_foundation_from_file,
    create_foundation_from_args,
    format_foundation_display
)


def test_story_foundation_creation():
    """Test creating a StoryFoundation object."""
    foundation = StoryFoundation(
        genre="science fiction",
        premise="A lone engineer discovers an alien signal",
        protagonist_archetype="Curious, isolated technical expert",
        setting="Near-future Mars colony, 2087",
        tone="Contemplative, mysterious",
        themes=["isolation", "first contact"]
    )
    
    assert foundation.genre == "science fiction"
    assert foundation.premise == "A lone engineer discovers an alien signal"
    assert foundation.protagonist_archetype == "Curious, isolated technical expert"
    assert foundation.setting == "Near-future Mars colony, 2087"
    assert foundation.tone == "Contemplative, mysterious"
    assert foundation.themes == ["isolation", "first contact"]


def test_story_foundation_to_dict():
    """Test converting StoryFoundation to dictionary."""
    foundation = StoryFoundation(
        genre="fantasy",
        premise="A young wizard must save the kingdom",
        protagonist_archetype="Reluctant hero",
        setting="Medieval fantasy realm",
        tone="Epic, adventurous"
    )
    
    data = foundation.to_dict()
    
    assert data["genre"] == "fantasy"
    assert data["premise"] == "A young wizard must save the kingdom"
    assert data["protagonist_archetype"] == "Reluctant hero"
    assert data["setting"] == "Medieval fantasy realm"
    assert data["tone"] == "Epic, adventurous"
    assert data["themes"] == []


def test_story_foundation_from_dict():
    """Test creating StoryFoundation from dictionary."""
    data = {
        "genre": "thriller",
        "premise": "A detective hunts a serial killer",
        "protagonist_archetype": "Haunted investigator",
        "setting": "Modern-day New York",
        "tone": "Dark, suspenseful",
        "themes": ["justice", "obsession"]
    }
    
    foundation = StoryFoundation.from_dict(data)
    
    assert foundation.genre == "thriller"
    assert foundation.premise == "A detective hunts a serial killer"
    assert foundation.protagonist_archetype == "Haunted investigator"
    assert foundation.setting == "Modern-day New York"
    assert foundation.tone == "Dark, suspenseful"
    assert foundation.themes == ["justice", "obsession"]


def test_load_foundation_from_yaml_file():
    """Test loading foundation from YAML file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml_content = {
            "genre": "horror",
            "premise": "A family moves into a haunted house",
            "protagonist_archetype": "Skeptical parent",
            "setting": "Isolated countryside mansion",
            "tone": "Creepy, atmospheric",
            "themes": ["fear", "family bonds"]
        }
        yaml.dump(yaml_content, f)
        temp_path = Path(f.name)
    
    try:
        foundation = load_foundation_from_file(temp_path)
        
        assert foundation.genre == "horror"
        assert foundation.premise == "A family moves into a haunted house"
        assert foundation.protagonist_archetype == "Skeptical parent"
        assert foundation.setting == "Isolated countryside mansion"
        assert foundation.tone == "Creepy, atmospheric"
        assert foundation.themes == ["fear", "family bonds"]
    finally:
        temp_path.unlink()


def test_load_foundation_missing_file():
    """Test loading foundation from non-existent file."""
    with pytest.raises(FileNotFoundError):
        load_foundation_from_file(Path("/nonexistent/file.yaml"))


def test_load_foundation_missing_required_fields():
    """Test loading foundation with missing required fields."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml_content = {
            "genre": "mystery",
            "premise": "A detective investigates"
            # Missing: protagonist_archetype, setting, tone
        }
        yaml.dump(yaml_content, f)
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError, match="Missing required fields"):
            load_foundation_from_file(temp_path)
    finally:
        temp_path.unlink()


def test_load_foundation_with_string_themes():
    """Test loading foundation with themes as comma-separated string."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml_content = {
            "genre": "romance",
            "premise": "Two rivals fall in love",
            "protagonist_archetype": "Ambitious professional",
            "setting": "Corporate New York",
            "tone": "Light, witty",
            "themes": "love, ambition, rivalry"  # String instead of list
        }
        yaml.dump(yaml_content, f)
        temp_path = Path(f.name)
    
    try:
        foundation = load_foundation_from_file(temp_path)
        assert foundation.themes == ["love", "ambition", "rivalry"]
    finally:
        temp_path.unlink()


def test_create_foundation_from_args_complete():
    """Test creating foundation from complete command-line args."""
    foundation = create_foundation_from_args(
        genre="western",
        premise="A gunslinger seeks redemption",
        protagonist="Aging outlaw",
        setting="American frontier, 1880s",
        tone="Gritty, melancholic",
        themes="redemption, violence, honor"
    )
    
    assert foundation is not None
    assert foundation.genre == "western"
    assert foundation.premise == "A gunslinger seeks redemption"
    assert foundation.protagonist_archetype == "Aging outlaw"
    assert foundation.setting == "American frontier, 1880s"
    assert foundation.tone == "Gritty, melancholic"
    assert foundation.themes == ["redemption", "violence", "honor"]


def test_create_foundation_from_args_none():
    """Test creating foundation when no args provided."""
    foundation = create_foundation_from_args()
    assert foundation is None


def test_create_foundation_from_args_incomplete():
    """Test creating foundation with incomplete args raises error."""
    import typer
    with pytest.raises(typer.Exit):
        create_foundation_from_args(
            genre="fantasy",
            premise="A quest begins"
            # Missing: protagonist, setting, tone
        )


def test_format_foundation_display():
    """Test formatting foundation for display."""
    foundation = StoryFoundation(
        genre="cyberpunk",
        premise="A hacker uncovers a corporate conspiracy",
        protagonist_archetype="Rebellious tech expert",
        setting="Dystopian megacity, 2077",
        tone="Noir, high-tech",
        themes=["technology", "freedom", "corruption"]
    )
    
    display = format_foundation_display(foundation)
    
    assert "📚 Story Foundation" in display
    assert "cyberpunk" in display
    assert "A hacker uncovers a corporate conspiracy" in display
    assert "Rebellious tech expert" in display
    assert "Dystopian megacity, 2077" in display
    assert "Noir, high-tech" in display
    assert "technology, freedom, corruption" in display


def test_format_foundation_display_no_themes():
    """Test formatting foundation without themes."""
    foundation = StoryFoundation(
        genre="literary",
        premise="A writer confronts their past",
        protagonist_archetype="Introspective artist",
        setting="Small coastal town",
        tone="Reflective, bittersweet"
    )
    
    display = format_foundation_display(foundation)
    
    assert "📚 Story Foundation" in display
    assert "literary" in display
    assert "Themes:" not in display  # No themes section


class TestBookFields:
    """The kind of book: declared by the author, optional, never guessed."""

    def _foundation(self, **extra):
        from novel_agent.cli.foundation import StoryFoundation
        return StoryFoundation(
            genre="mystery", premise="A clerk finds a ledger that should not exist.",
            protagonist_archetype="a careful clerk", setting="a harbour town",
            tone="dry", **extra)

    def test_unset_by_default_and_round_trips(self):
        from novel_agent.cli.foundation import StoryFoundation
        f = self._foundation()
        assert (f.book_kind, f.reader_age, f.cruel_world) == (None, None, None)
        again = StoryFoundation.from_dict(f.to_dict())
        assert (again.book_kind, again.reader_age, again.cruel_world) == (None, None, None)

    def test_values_are_normalised_and_round_trip(self):
        from novel_agent.cli.foundation import StoryFoundation
        f = self._foundation(book_kind=" Literary ", reader_age="young-adult", cruel_world="yes")
        assert (f.book_kind, f.reader_age, f.cruel_world) == ("literary", "young_adult", True)
        again = StoryFoundation.from_dict(f.to_dict())
        assert (again.book_kind, again.reader_age, again.cruel_world) == ("literary", "young_adult", True)

    def test_unknown_values_raise(self):
        import pytest
        with pytest.raises(ValueError):
            self._foundation(book_kind="pulp")
        with pytest.raises(ValueError):
            self._foundation(reader_age="toddlers")
        with pytest.raises(ValueError):
            self._foundation(cruel_world="sometimes")

    def test_old_foundation_without_the_fields_loads(self):
        from novel_agent.cli.foundation import StoryFoundation
        data = self._foundation().to_dict()
        for key in ("book_kind", "reader_age", "cruel_world"):
            del data[key]
        assert StoryFoundation.from_dict(data).book_kind is None

    def test_command_line_fields_are_applied_and_must_agree(self):
        import pytest
        from novel_agent.cli.foundation import apply_book_fields
        f = self._foundation(book_kind="literary")
        apply_book_fields(f, book_kind="literary", reader_age="adult", cruel_world=False)
        assert (f.book_kind, f.reader_age, f.cruel_world) == ("literary", "adult", False)
        with pytest.raises(ValueError):
            apply_book_fields(f, book_kind="commercial")

    def test_file_and_display(self, tmp_path):
        from novel_agent.cli.foundation import load_foundation_from_file, format_foundation_display
        path = tmp_path / "f.yaml"
        path.write_text(
            "genre: mystery\npremise: A clerk finds a ledger.\n"
            "protagonist_archetype: a careful clerk\nsetting: a harbour town\n"
            "tone: dry\nbook_kind: upmarket\nreader_age: adult\ncruel_world: true\n")
        f = load_foundation_from_file(path)
        assert (f.book_kind, f.reader_age, f.cruel_world) == ("upmarket", "adult", True)
        shown = format_foundation_display(f)
        assert "Kind of book: upmarket" in shown and "Cruel world: yes" in shown
