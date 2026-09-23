"""Loop-aging gauge tests (Phase 3, loop-aging Slice L1).

Policy under test: loop-aging ships as a GAUGE, not a pressure. Every tick the
system records how old each open loop is, which KIND of question it asks
("scene" suspense, "arc" debt, the "throughline" restated), how many arc loops
are overdue against the story's remaining runway, and which loops the planner
was actually shown. Nothing reads any of it for decisions in this slice, so the
tests below also pin the instrument-only property: selection is unchanged and a
gauge failure can never break a tick.

Two repairs ride along and are pinned here too: importance now sorts
critical-first (a raw string sort with reverse=True put critical LAST), and the
planner's loop list carries an age.
"""

import json
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.coherence_metrics import CoherenceMetrics
from novel_agent.agent.context import ContextBuilder
from novel_agent.agent.loop_aging import (
    GOAL_MATCH_THRESHOLD,
    HORIZON_ARC,
    HORIZON_SCENE,
    HORIZON_THROUGHLINE,
    age_report,
    birth_tick,
    classify_horizon,
    horizon_of,
    importance_rank,
    is_open,
    loop_age,
    stale_threshold,
    staleness,
)
from novel_agent.agent.multi_stage_planner import MultiStagePlanner
from novel_agent.cli.commands.loops import get_loops_info, display_loops, display_loops_json
from novel_agent.configs.config import Config
from novel_agent.memory.entities import OpenLoop
from novel_agent.memory.manager import MemoryManager


@pytest.fixture
def project():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _loop(loop_id="OL0", description="What happened to the ledger?", **kwargs):
    return OpenLoop(id=loop_id, description=description, **kwargs)


def _config(**overrides):
    config = Config()
    config.config.setdefault("coherence", {}).update(overrides)
    return config


# ---------------------------------------------------------------------------
# Birth tick and age
# ---------------------------------------------------------------------------

def test_birth_tick_prefers_the_recorded_field():
    assert birth_tick(_loop(created_tick=4, created_in_scene="S009")) == 4


def test_birth_tick_falls_back_to_the_scene_id():
    # Exact, not an approximation: scene ids are allocated one per tick, which is
    # what makes the legacy backfill trustworthy.
    assert birth_tick(_loop(created_in_scene="S007")) == 7
    assert birth_tick(_loop(created_in_scene="S000")) == 0


def test_birth_tick_unknown_is_none_not_zero():
    assert birth_tick(_loop()) is None
    assert birth_tick(_loop(created_in_scene="scene-7")) is None
    assert birth_tick(_loop(created_in_scene="S00x")) is None


def test_loop_age_never_negative_and_none_when_unknown():
    assert loop_age(_loop(created_tick=3), 10) == 7
    # A checkpoint restore can rewind the tick; an age below zero is not a thing.
    assert loop_age(_loop(created_tick=8), 3) == 0
    assert loop_age(_loop(), 10) is None
    assert loop_age(_loop(created_tick=3), None) is None


def test_is_open_excludes_resolved_and_expired():
    assert is_open(_loop())
    assert not is_open(_loop(status="resolved"))
    # "expired" is terminal-but-distinct: left open at story end, never answered.
    assert not is_open(_loop(status="expired"))


# ---------------------------------------------------------------------------
# Horizon classification (real corpus strings)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("description", [
    "Will security personnel intercept Vela before she leaves the building, "
    "or has she escaped the immediate threat?",
    "Will Vela sign the false statement, or will she refuse and face criminal prosecution?",
    "Will the emergency preservation notice halt the destruction protocol before the "
    "2-4 hour window completes?",
    "Aryn filed the FBI complaint this morning; the investigation opens within 48 hours.",
])
def test_scene_horizon_on_suspense_with_a_deadline(description):
    assert classify_horizon(description) == HORIZON_SCENE


@pytest.mark.parametrize("description", [
    "What were the three redacted entries in the March 8th data export, and why were "
    "they deleted without logging?",
    "Who is the person on the unredacted March 8th files list that Vela knows?",
    "How did Tyrux Tyxun obtain the files that were supposedly permanently deleted?",
    # Mechanism trivia is still an arc question as far as the gauge is concerned:
    # arc is the default on purpose, because a misfiled arc loop is a missed
    # payoff while a misfiled scene loop is a wasted demand.
    "How does Tyrux maintain contact with Vela if Vela cannot initiate contact?",
])
def test_arc_horizon_on_payable_questions(description):
    assert classify_horizon(description) == HORIZON_ARC


@pytest.mark.parametrize("description", [
    "What is the full scope of the conspiracy, and how many executives are involved?",
    "What does Galen Yoraen know about the redacted entries, and how high does the "
    "conspiracy extend?",
    "What is the ultimate purpose and recipient of the exported data?",
])
def test_throughline_horizon_on_the_central_question(description):
    assert classify_horizon(description) == HORIZON_THROUGHLINE


def test_throughline_wins_over_scene():
    # The central question often also reads as a binary either/or, and must never
    # be filed as scene-local suspense.
    assert classify_horizon(
        "Is the full scope of the conspiracy limited to Dexex, or does it extend "
        "further before the merger closes?"
    ) == HORIZON_THROUGHLINE


def test_a_loop_restating_the_primary_goal_is_the_throughline():
    goal = "Expose the Holtwick data conspiracy before the merger closes"
    assert classify_horizon("Expose the Holtwick data conspiracy before the merger closes?",
                            goal) == HORIZON_THROUGHLINE
    # A merely related loop is not the throughline; the bar is deliberately higher
    # than loop dedup's 0.75, because a false throughline call exempts a real loop
    # from every future pressure.
    assert GOAL_MATCH_THRESHOLD > 0.75
    assert classify_horizon("Who signed the export authorisation?", goal) == HORIZON_ARC


def test_keywords_match_at_a_word_boundary():
    # A substring test is what let "roman" swallow "romance" in the name banks.
    # "before" must not fire inside "beforehand"-style compounds.
    assert classify_horizon("What did the beforehand arrangement cover?") == HORIZON_ARC
    assert classify_horizon("Will she reach the dock before dawn, or be caught?") == HORIZON_SCENE


def test_classify_horizon_degrades_on_unusable_input():
    assert classify_horizon(None) == HORIZON_ARC
    assert classify_horizon("") == HORIZON_ARC
    assert classify_horizon(42) == HORIZON_ARC


def test_horizon_of_prefers_a_stored_value():
    # A stored horizon survives, so a hand-correction is not overwritten.
    assert horizon_of(_loop(horizon="scene", description="What happened to the ledger?")) == "scene"
    assert horizon_of(_loop(horizon="nonsense")) == HORIZON_ARC
    assert horizon_of(_loop(description="Will he run before dawn, or stay?")) == HORIZON_SCENE


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

def test_stale_threshold_is_a_fraction_of_story_length():
    config = _config(target_story_length=40, loop_stale_fraction=0.3,
                     loop_stale_floor_ticks=3)
    assert stale_threshold(config) == 12


def test_stale_threshold_respects_the_absolute_floor():
    # Without the floor, a 6-tick run would call a 2-tick-old loop overdue.
    config = _config(target_story_length=6, loop_stale_fraction=0.3,
                     loop_stale_floor_ticks=3)
    assert stale_threshold(config) == 3


def test_stale_threshold_none_without_a_story_length():
    assert stale_threshold(_config(target_story_length=None)) is None
    assert stale_threshold(_config(target_story_length=0)) is None


def test_only_arc_loops_can_be_overdue():
    config = _config(target_story_length=20, loop_stale_fraction=0.3)  # threshold 6
    old = dict(created_tick=0)
    arc = staleness(_loop("OL1", "What happened to the ledger?", **old), 10, config)
    scene = staleness(_loop("OL2", "Will he run before dawn, or stay?", **old), 10, config)
    through = staleness(_loop("OL3", "What is the full scope of the conspiracy?", **old), 10, config)
    assert arc["overdue"] is True
    # Suspense the prose already walked past is not debt, and the story's central
    # question is meant to stay open to the last page.
    assert scene["overdue"] is False
    assert through["overdue"] is False


def test_a_closed_loop_is_never_overdue():
    config = _config(target_story_length=20)
    loop = _loop(created_tick=0, status="resolved")
    assert staleness(loop, 19, config)["overdue"] is False


def test_staleness_reports_the_story_fraction():
    config = _config(target_story_length=20)
    report = staleness(_loop(created_tick=2), 8, config)
    assert report["age"] == 6
    assert report["fraction"] == 0.3


def test_staleness_degrades_without_an_age():
    config = _config(target_story_length=20)
    report = staleness(_loop(), 8, config)
    assert report["age"] is None
    assert report["fraction"] is None
    assert report["overdue"] is False


# ---------------------------------------------------------------------------
# The metrics payload
# ---------------------------------------------------------------------------

def _ledger():
    return [
        _loop("OL0", "What were the three redacted entries?", created_tick=0),
        _loop("OL1", "Will he run before dawn, or stay?", created_tick=1),
        _loop("OL2", "What is the full scope of the conspiracy?", created_tick=2),
        _loop("OL3", "Who signed the export authorisation?", created_tick=8),
        _loop("OL4", "Answered already.", created_tick=0, status="resolved"),
    ]


def test_age_report_counts_open_loops_by_horizon():
    report = age_report(_ledger(), 10, _config(target_story_length=20))
    assert report["open_total"] == 4  # the resolved loop is not debt
    assert report["by_horizon"] == {HORIZON_SCENE: 1, HORIZON_ARC: 2,
                                    HORIZON_THROUGHLINE: 1}
    assert report["oldest_age"] == 10
    assert report["oldest_id"] == "OL0"
    assert report["median_age"] == 8.5


def test_age_report_overdue_is_arc_only():
    report = age_report(_ledger(), 10, _config(target_story_length=20))  # threshold 6
    # OL0 (age 10, arc) is overdue; OL3 (age 2) is young; the scene and
    # throughline loops are exempt by construction.
    assert report["overdue_total"] == 1
    assert report["overdue_ids"] == ["OL0"]


def test_age_report_separates_shown_from_withheld():
    # The decisive pair for the pressure design: if what the planner never sees
    # is systematically older, the fix is the selector, not a mandate.
    report = age_report(_ledger(), 10, _config(target_story_length=20),
                        shown_ids=["OL3"])
    assert report["shown_total"] == 1
    assert report["shown_oldest_age"] == 2
    assert report["unshown_oldest_age"] == 10
    assert report["shown"] == [{"id": "OL3", "age": 2, "horizon": HORIZON_ARC}]


def test_age_report_disabled_by_the_gate():
    assert age_report(_ledger(), 10, _config(loop_aging=False)) == {"enabled": False}


def test_age_report_never_raises_on_junk():
    class Broken:
        status = "open"

        @property
        def description(self):
            raise RuntimeError("boom")

    report = age_report([Broken()], 3, _config())
    assert report["enabled"] is True


class FakeVector:
    def compute_semantic_similarity(self, a, b):
        return 0.5


def _metrics(project_dir, config=None):
    return CoherenceMetrics(project_dir, MemoryManager(project_dir), FakeVector(),
                            config or Config())


def test_metrics_record_carries_the_loop_age_fields(project):
    memory = MemoryManager(project)
    memory.save_open_loops(_ledger())
    config = Config()
    config.config["coherence"]["target_story_length"] = 20
    record = CoherenceMetrics(project, memory, FakeVector(), config).record_tick(
        tick=10, scene_id="S010", loop_ids_shown=["OL3"],
    )
    assert record["loop_oldest_age"] == 10
    assert record["loop_oldest_id"] == "OL0"
    assert record["loop_overdue_total"] == 1
    assert record["loop_stale_threshold"] == 6
    assert record["loop_shown_oldest_age"] == 2
    assert record["loop_unshown_oldest_age"] == 10
    assert record["loop_horizon_counts"][HORIZON_ARC] == 2


def test_metrics_record_with_the_gauge_off(project):
    memory = MemoryManager(project)
    memory.save_open_loops(_ledger())
    config = Config()
    config.config["coherence"]["loop_aging"] = False
    record = CoherenceMetrics(project, memory, FakeVector(), config).record_tick(
        tick=10, scene_id="S010",
    )
    # Off means "no data", not a crash and not a zero.
    assert record["loop_oldest_age"] is None
    assert record["loop_overdue_total"] is None
    assert record["loops_opened"] == 0  # the pre-L1 churn counts still work


# ---------------------------------------------------------------------------
# Persistence and the legacy backfill
# ---------------------------------------------------------------------------

def test_new_loops_round_trip_the_aging_fields(project):
    memory = MemoryManager(project)
    memory.save_open_loops([_loop(created_tick=4, horizon=HORIZON_ARC)])
    loaded = memory.load_open_loops()[0]
    assert loaded.created_tick == 4
    assert loaded.horizon == HORIZON_ARC


def test_legacy_loops_are_backfilled_on_load(project):
    memory = MemoryManager(project)
    # A loop dict as written before this slice: neither field exists.
    legacy = {
        "id": "OL0",
        "type": "open_loop",
        "created_in_scene": "S006",
        "status": "open",
        "category": "mystery",
        "description": "Will she reach the dock before dawn, or be caught?",
        "importance": "high",
    }
    (project / "memory").mkdir(exist_ok=True)
    (project / "memory" / "open_loops.json").write_text(json.dumps({"loops": [legacy]}))
    loaded = memory.load_open_loops()[0]
    assert loaded.created_tick == 6
    assert loaded.horizon == HORIZON_SCENE


def test_loop_creation_stamps_tick_and_horizon(project):
    from novel_agent.agent.entity_updater import EntityUpdater

    memory = MemoryManager(project)
    updater = EntityUpdater(memory, Config())
    result = updater._create_open_loop(
        {"description": "What were the three redacted entries?",
         "importance": "critical"},
        tick=5, scene_id="S005",
    )
    assert result == "created"
    created = memory.load_open_loops()[0]
    assert created.created_tick == 5
    assert created.horizon == HORIZON_ARC


# ---------------------------------------------------------------------------
# The two repairs
# ---------------------------------------------------------------------------

def test_importance_rank_puts_critical_first():
    order = sorted([_loop("a", importance="medium"), _loop("b", importance="critical"),
                    _loop("c", importance="low"), _loop("d", importance="high")],
                   key=importance_rank, reverse=True)
    assert [l.id for l in order] == ["b", "d", "a", "c"]


def test_importance_rank_tolerates_an_unknown_value():
    assert importance_rank(_loop(importance="urgent")) == -1
    assert importance_rank(_loop(importance=None)) == -1


def test_planner_loop_list_is_ordered_and_aged(project):
    memory = MemoryManager(project)
    memory.save_open_loops([
        _loop("OL0", "What happened to the ledger?", created_tick=0, importance="medium"),
        _loop("OL1", "Who signed the authorisation?", created_tick=1, importance="critical"),
    ])
    (project / "state.json").write_text(json.dumps({"current_tick": 9}))
    config = Config()
    config.config["coherence"]["target_story_length"] = 20
    builder = ContextBuilder(memory, FakeVector(), None, config)
    rendered = builder._format_open_loops()
    lines = rendered.splitlines()
    # Critical first (a raw string sort used to put it last), with the age shown.
    assert "OL1" in lines[0]
    assert "OL0" in lines[1]
    assert "8 ticks old" in lines[0]
    assert "🔴" in lines[1]  # OL0 is an overdue arc loop at age 9


def test_planner_loop_list_without_a_state_file(project):
    memory = MemoryManager(project)
    memory.save_open_loops([_loop("OL0", "What happened to the ledger?", created_tick=0)])
    builder = ContextBuilder(memory, FakeVector(), None, Config())
    rendered = builder._format_open_loops()
    assert "OL0" in rendered
    assert "ticks old" not in rendered  # no tick, so no age claimed


# ---------------------------------------------------------------------------
# Instrument-only: selection is untouched
# ---------------------------------------------------------------------------

class FakeMemory:
    """The narrow slice of MemoryManager stage 2 touches."""

    def __init__(self, loops):
        self._loops = loops

    def load_open_loops(self):
        return list(self._loops)

    def load_all_lore(self):
        return []

    def load_character(self, char_id):
        return None

    def get_character_relationships(self, char_id):
        return []


class FakeSearch:
    def search_scenes(self, query, limit=3):
        return []

    def compute_semantic_similarity(self, a, b):
        return 0.5


def _stage2_planner(loops):
    planner = MultiStagePlanner.__new__(MultiStagePlanner)
    planner.memory = FakeMemory(loops)
    planner.vector = FakeSearch()
    planner.stage_stats = {"loop_ids_shown": ["OL9"]}  # a stale value from last tick
    return planner


def test_stage2_records_exactly_the_loops_it_showed():
    loops = _ledger()
    planner = _stage2_planner(loops)
    context = planner._gather_relevant_context("the redacted entries", {})
    shown = planner.stage_stats["loop_ids_shown"]
    # Reports the selection, and nothing but the selection.
    assert shown == [l.id for l in context["relevant_loops"]]
    assert "OL9" not in shown  # last tick's set was cleared
    # Terminal loops never reach the planner, so they can never be "shown".
    assert "OL4" not in shown


def test_the_gauge_does_not_re_rank_selection():
    # Instrument-only: the selector's output is a pure function of the intention
    # and the ledger, unchanged by this slice. _filter_relevant_loops is the code
    # the pressure slice may later change; L1 must not have touched it.
    loops = _ledger()
    planner = _stage2_planner(loops)
    ranked = planner._filter_relevant_loops("the redacted entries", loops, top_k=3)
    # Pure word overlap with the intention: OL0 names the redacted entries, and
    # the rest are ordered by the same crude score, nothing else.
    assert [l.id for l in ranked] == ["OL0", "OL2", "OL3"]
    # Age plays no part, which is the thing L1 exists to measure: OL3 (age 2) is
    # shown while OL1 (age 9) is withheld.
    assert loop_age(ranked[2], 10) == 2
    assert "OL1" not in [l.id for l in ranked]


# ---------------------------------------------------------------------------
# novel loops
# ---------------------------------------------------------------------------

def test_loops_command_reports_ages_oldest_first(project, capsys):
    memory = MemoryManager(project)
    memory.save_open_loops(_ledger())
    (project / "state.json").write_text(json.dumps({"current_tick": 10}))
    info = get_loops_info(project)
    assert info["count"] == 4  # open only by default
    assert info["loops"][0]["id"] == "OL0"
    assert info["loops"][0]["age"] == 10
    assert info["horizon_counts"][HORIZON_ARC] == 2
    display_loops(info, use_color=False)
    display_loops_json(info)
    out = capsys.readouterr().out
    assert "OL0" in out


def test_loops_command_all_statuses(project):
    memory = MemoryManager(project)
    memory.save_open_loops(_ledger())
    (project / "state.json").write_text(json.dumps({"current_tick": 10}))
    assert get_loops_info(project, status=None)["count"] == 5


def test_loops_command_on_a_project_with_no_ledger(project, capsys):
    info = get_loops_info(project)
    assert info["count"] == 0
    display_loops(info, use_color=False)
    assert "No loops recorded yet" in capsys.readouterr().out
