"""Tests for PlotOutlineManager and PlotBeat/PlotOutline round-trips."""
import json
from pathlib import Path

import pytest

from novel_agent.memory.entities import PlotBeat, PlotOutline
from novel_agent.memory.plot_outline import PlotOutlineManager


# ---------------------------------------------------------------------------
# Dataclass round-trips
# ---------------------------------------------------------------------------

def test_plotbeat_round_trip_defaults():
    """A PlotBeat survives to_dict/from_dict with defaults intact."""
    beat = PlotBeat(id="B001", description="Hero leaves home")

    # __post_init__ stamps created_at
    assert beat.created_at.endswith("Z")
    assert beat.status == "pending"

    restored = PlotBeat.from_dict(beat.to_dict())
    assert restored == beat


def test_plotbeat_round_trip_full():
    """All non-default PlotBeat fields survive a round-trip."""
    beat = PlotBeat(
        id="B042",
        description="The confrontation",
        characters_involved=["C000", "C001"],
        location="L000",
        plot_threads=["revenge"],
        tension_target=9,
        prerequisites=["B001", "S003"],
        status="completed",
        created_at="2026-01-01T00:00:00Z",
        executed_in_scene="S010",
        execution_notes="went well",
        verification_score=0.87,
        verification_method="semantic",
        abandoned_reason="",
        revised_at_tick=5,
        advances_character_arcs=["C000"],
        resolves_loops=["OL1"],
        creates_loops=["OL2"],
    )
    restored = PlotBeat.from_dict(beat.to_dict())
    assert restored == beat
    assert restored.tension_target == 9
    assert restored.verification_score == 0.87


def test_plotbeat_post_init_preserves_explicit_created_at():
    """An explicitly-provided created_at is not overwritten."""
    beat = PlotBeat(id="B1", description="x", created_at="2025-12-31T12:00:00Z")
    assert beat.created_at == "2025-12-31T12:00:00Z"


def test_plotoutline_round_trip():
    """A PlotOutline with beats survives to_dict/from_dict."""
    outline = PlotOutline(
        beats=[
            PlotBeat(id="B001", description="one"),
            PlotBeat(id="B002", description="two"),
        ],
        current_arc="rising",
        arc_progress=0.25,
    )
    restored = PlotOutline.from_dict(outline.to_dict())
    assert restored.current_arc == "rising"
    assert restored.arc_progress == 0.25
    assert [b.id for b in restored.beats] == ["B001", "B002"]
    assert restored.beats[0] == outline.beats[0]


def test_plotoutline_post_init_timestamps():
    """An empty PlotOutline stamps created_at and mirrors it to last_updated."""
    outline = PlotOutline()
    assert outline.created_at.endswith("Z")
    assert outline.last_updated == outline.created_at
    assert outline.beats == []


def test_plotoutline_from_dict_empty():
    """from_dict on an empty dict yields an empty outline with defaults."""
    outline = PlotOutline.from_dict({})
    assert outline.beats == []
    assert outline.current_arc == ""
    assert outline.arc_progress == 0.0


# ---------------------------------------------------------------------------
# PlotOutlineManager: load/save
# ---------------------------------------------------------------------------

def test_load_outline_missing_returns_empty(tmp_path: Path):
    """load_outline returns a fresh empty PlotOutline when no file exists."""
    mgr = PlotOutlineManager(tmp_path)
    outline = mgr.load_outline()
    assert isinstance(outline, PlotOutline)
    assert outline.beats == []
    assert not mgr.outline_file.exists()


def test_save_then_load_round_trip(tmp_path: Path):
    """save_outline persists to disk and load_outline reads it back."""
    mgr = PlotOutlineManager(tmp_path)
    outline = PlotOutline(beats=[PlotBeat(id="B001", description="start")])

    mgr.save_outline(outline)
    assert mgr.outline_file.exists()

    loaded = mgr.load_outline()
    assert [b.id for b in loaded.beats] == ["B001"]
    assert loaded.beats[0].description == "start"


def test_save_outline_updates_last_updated(tmp_path: Path):
    """save_outline refreshes last_updated and writes pretty UTF-8 JSON."""
    mgr = PlotOutlineManager(tmp_path)
    outline = PlotOutline(
        beats=[PlotBeat(id="B001", description="Café showdown 東京")],
        last_updated="OLD",
    )
    mgr.save_outline(outline)

    assert outline.last_updated != "OLD"
    assert outline.last_updated.endswith("Z")

    # File is indented and preserves unicode (ensure_ascii=False)
    raw = mgr.outline_file.read_text(encoding="utf-8")
    assert "\n  " in raw  # indent=2
    assert "東京" in raw
    assert "\\u" not in raw

    # And the on-disk JSON parses to the expected structure
    on_disk = json.loads(raw)
    assert on_disk["beats"][0]["id"] == "B001"


def test_constructor_accepts_str_path(tmp_path: Path):
    """The constructor coerces a string path to a Path."""
    mgr = PlotOutlineManager(str(tmp_path))
    assert isinstance(mgr.project_path, Path)
    assert mgr.outline_file == tmp_path / "plot_outline.json"


# ---------------------------------------------------------------------------
# PlotOutlineManager: beat operations
# ---------------------------------------------------------------------------

def test_list_beats_empty(tmp_path: Path):
    """list_beats returns an empty list when there is no outline."""
    mgr = PlotOutlineManager(tmp_path)
    assert mgr.list_beats() == []


def test_list_beats_returns_all_in_order(tmp_path: Path):
    """list_beats returns all beats in stored order."""
    mgr = PlotOutlineManager(tmp_path)
    mgr.save_outline(
        PlotOutline(
            beats=[
                PlotBeat(id="B001", description="a"),
                PlotBeat(id="B002", description="b"),
                PlotBeat(id="B003", description="c"),
            ]
        )
    )
    assert [b.id for b in mgr.list_beats()] == ["B001", "B002", "B003"]


def test_get_next_beat_default_pending(tmp_path: Path):
    """get_next_beat returns the first pending beat by default."""
    mgr = PlotOutlineManager(tmp_path)
    mgr.save_outline(
        PlotOutline(
            beats=[
                PlotBeat(id="B001", description="done", status="completed"),
                PlotBeat(id="B002", description="next", status="pending"),
                PlotBeat(id="B003", description="later", status="pending"),
            ]
        )
    )
    nxt = mgr.get_next_beat()
    assert nxt is not None
    assert nxt.id == "B002"


def test_get_next_beat_custom_status(tmp_path: Path):
    """get_next_beat honors a custom status filter."""
    mgr = PlotOutlineManager(tmp_path)
    mgr.save_outline(
        PlotOutline(
            beats=[
                PlotBeat(id="B001", description="done", status="completed"),
                PlotBeat(id="B002", description="active", status="in_progress"),
            ]
        )
    )
    nxt = mgr.get_next_beat(status="in_progress")
    assert nxt is not None
    assert nxt.id == "B002"


def test_get_next_beat_none_when_no_match(tmp_path: Path):
    """get_next_beat returns None when no beat matches the status."""
    mgr = PlotOutlineManager(tmp_path)
    mgr.save_outline(
        PlotOutline(beats=[PlotBeat(id="B001", description="done", status="completed")])
    )
    assert mgr.get_next_beat() is None


def test_add_beats_appends_and_persists(tmp_path: Path):
    """add_beats appends to the existing outline, saves, and returns it."""
    mgr = PlotOutlineManager(tmp_path)
    mgr.save_outline(PlotOutline(beats=[PlotBeat(id="B001", description="first")]))

    returned = mgr.add_beats(
        [PlotBeat(id="B002", description="second"), PlotBeat(id="B003", description="third")]
    )

    assert isinstance(returned, PlotOutline)
    assert [b.id for b in returned.beats] == ["B001", "B002", "B003"]
    # Persisted to disk too
    assert [b.id for b in mgr.list_beats()] == ["B001", "B002", "B003"]


def test_add_beats_on_empty_outline(tmp_path: Path):
    """add_beats works when there is no prior outline file."""
    mgr = PlotOutlineManager(tmp_path)
    returned = mgr.add_beats([PlotBeat(id="B001", description="only")])
    assert [b.id for b in returned.beats] == ["B001"]
    assert mgr.outline_file.exists()


def test_replace_outline(tmp_path: Path):
    """replace_outline overwrites the stored outline entirely."""
    mgr = PlotOutlineManager(tmp_path)
    mgr.save_outline(
        PlotOutline(beats=[PlotBeat(id="B001", description="old1"),
                           PlotBeat(id="B002", description="old2")])
    )

    new_outline = PlotOutline(beats=[PlotBeat(id="B100", description="new")])
    mgr.replace_outline(new_outline)

    assert [b.id for b in mgr.list_beats()] == ["B100"]


# ---------------------------------------------------------------------------
# PlotOutlineManager: validation
# ---------------------------------------------------------------------------

def test_validate_outline_clean(tmp_path: Path):
    """A well-formed outline reports no issues."""
    mgr = PlotOutlineManager(tmp_path)
    outline = PlotOutline(
        beats=[
            PlotBeat(id="B001", description="a"),
            PlotBeat(id="B002", description="b", prerequisites=["B001"]),
        ]
    )
    issues = mgr.validate_outline(outline)
    assert issues["duplicate_ids"] == []
    assert issues["missing_prerequisites"] == []


def test_validate_outline_duplicate_ids(tmp_path: Path):
    """Duplicate beat IDs are flagged."""
    mgr = PlotOutlineManager(tmp_path)
    outline = PlotOutline(
        beats=[
            PlotBeat(id="B001", description="a"),
            PlotBeat(id="B001", description="dup"),
        ]
    )
    issues = mgr.validate_outline(outline)
    assert issues["duplicate_ids"] == ["B001"]


def test_validate_outline_missing_prerequisite(tmp_path: Path):
    """A prerequisite that is not a known beat ID is flagged."""
    mgr = PlotOutlineManager(tmp_path)
    outline = PlotOutline(
        beats=[PlotBeat(id="B002", description="b", prerequisites=["B999"])]
    )
    issues = mgr.validate_outline(outline)
    assert issues["missing_prerequisites"] == [
        {"beat_id": "B002", "prerequisite": "B999"}
    ]


def test_validate_outline_scene_prerequisites_allowed(tmp_path: Path):
    """Scene IDs (S###) are valid prerequisites and not flagged as missing."""
    mgr = PlotOutlineManager(tmp_path)
    outline = PlotOutline(
        beats=[PlotBeat(id="B001", description="a", prerequisites=["S003", "S012"])]
    )
    issues = mgr.validate_outline(outline)
    assert issues["missing_prerequisites"] == []


def test_validate_outline_malformed_scene_id_flagged(tmp_path: Path):
    """An S-prefixed but non-numeric prerequisite is treated as missing."""
    mgr = PlotOutlineManager(tmp_path)
    outline = PlotOutline(
        beats=[PlotBeat(id="B001", description="a", prerequisites=["Sabc"])]
    )
    issues = mgr.validate_outline(outline)
    assert issues["missing_prerequisites"] == [
        {"beat_id": "B001", "prerequisite": "Sabc"}
    ]


def test_validate_outline_loads_from_disk_when_none(tmp_path: Path):
    """validate_outline(None) loads the outline from disk."""
    mgr = PlotOutlineManager(tmp_path)
    mgr.save_outline(
        PlotOutline(
            beats=[
                PlotBeat(id="B001", description="a"),
                PlotBeat(id="B001", description="dup"),
            ]
        )
    )
    issues = mgr.validate_outline()  # no argument -> load from disk
    assert issues["duplicate_ids"] == ["B001"]
