"""Unit tests for the Phase 3 bridge: arc-pressure (target + phase) into plot beat
generation, so beats are AUTHORED phase-appropriately, not only planned that way."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.arc_pressure import (
    ARC_PHASE_BEAT_DIRECTIVES,
    FINAL_BEAT_DIRECTIVE,
    arc_guidance_for_beats,
    beat_tension_schedule,
    cap_beat_count,
    reconcile_beat_tension_targets,
    remaining_story_ticks,
)
from novel_agent.agent.prompts import format_plot_generation_prompt
from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Character
from novel_agent.plot.manager import PlotOutlineManager
from novel_agent.plot.entities import PlotBeat


class FakeConfig:
    """Minimal dot-notation config for testing."""

    def __init__(self, values):
        self._v = values

    def get(self, key, default=None):
        return self._v.get(key, default)


# Same representative curves as test_arc_phase.py.
DEFAULT_CURVE = [[0.0, 3], [0.25, 5], [0.5, 6], [0.75, 8], [0.9, 9], [1.0, 4]]
EARLY_PEAK_CURVE = [[0.0, 3], [0.5, 9], [1.0, 2]]


def _cfg(curve=DEFAULT_CURVE, length=20, **extra):
    values = {"coherence.target_tension_curve": curve,
              "coherence.target_story_length": length}
    values.update(extra)
    return FakeConfig(values)


# ---- per-beat schedule computation --------------------------------------------

def test_schedule_positions_targets_and_phases_on_the_climb():
    # Generating 5 beats at tick 10 of 20 schedules them at ticks 11..15
    # (one beat per tick), on the DEFAULT_CURVE climb from 6 to 8.
    schedule = beat_tension_schedule(10, 5, _cfg())
    assert [e["index"] for e in schedule] == [1, 2, 3, 4, 5]
    assert [e["tick"] for e in schedule] == [11, 12, 13, 14, 15]
    assert [e["target"] for e in schedule] == [6.4, 6.8, 7.2, 7.6, 8.0]
    assert all(e["phase"] == "rising" for e in schedule)
    assert schedule[0]["band"] == "high"
    assert schedule[-1]["band"] == "very high"


def test_schedule_spans_falling_and_resolution():
    # An early peak leaves the batch straddling the descent into the tail.
    schedule = beat_tension_schedule(15, 5, _cfg(curve=EARLY_PEAK_CURVE))
    assert [e["phase"] for e in schedule] == [
        "falling", "resolution", "resolution", "resolution", "resolution"]
    targets = [e["target"] for e in schedule]
    assert targets == sorted(targets, reverse=True)  # de-escalating
    assert targets[-1] == 2.0


def test_schedule_clamps_past_the_intended_end():
    # Positions beyond target_story_length clamp to the curve's endpoint.
    schedule = beat_tension_schedule(19, 3, _cfg())
    assert [e["tick"] for e in schedule] == [20, 21, 22]
    assert all(e["progress"] == 1.0 for e in schedule)
    assert all(e["target"] == 4.0 for e in schedule)
    assert all(e["phase"] == "resolution" for e in schedule)


def test_schedule_disabled_by_gate_curve_or_count():
    assert beat_tension_schedule(10, 5, _cfg(**{"coherence.arc_phase_mandate": False})) == []
    assert beat_tension_schedule(10, 5, _cfg(curve=None)) == []
    assert beat_tension_schedule(10, 5, _cfg(curve=[])) == []
    assert beat_tension_schedule(10, 0, _cfg()) == []
    # Malformed curve degrades to disabled, never raises.
    assert beat_tension_schedule(10, 5, _cfg(curve=[["x", "y"]])) == []


def test_schedule_phase_none_for_flat_curve_but_targets_still_scheduled():
    schedule = beat_tension_schedule(10, 2, _cfg(curve=[[0.0, 5], [1.0, 5]]))
    assert [e["target"] for e in schedule] == [5.0, 5.0]
    assert all(e["phase"] is None for e in schedule)


# ---- slot alignment: runway helper + batch cap (Phase 3) ------------------------

def test_remaining_story_ticks_configured():
    assert remaining_story_ticks(12, _cfg(length=15)) == 3
    assert remaining_story_ticks(0, _cfg(length=15)) == 15


def test_remaining_story_ticks_unconfigured():
    assert remaining_story_ticks(12, FakeConfig({})) is None
    assert remaining_story_ticks(12, FakeConfig({"coherence.target_story_length": None})) is None
    assert remaining_story_ticks(12, FakeConfig({"coherence.target_story_length": 0})) is None
    assert remaining_story_ticks(12, FakeConfig({"coherence.target_story_length": "soon"})) is None


def test_remaining_story_ticks_boundary_and_overtime():
    assert remaining_story_ticks(14, _cfg(length=15)) == 1
    assert remaining_story_ticks(15, _cfg(length=15)) == 0   # exact boundary
    assert remaining_story_ticks(20, _cfg(length=15)) == 0   # overtime clamps to 0


def test_cap_beat_count_caps_to_runway():
    # The arbiter run's shape: a 5-beat batch requested at tick 12 of a 15-tick
    # story spanned ticks 13-17 and stranded the denouement past the end.
    assert cap_beat_count(12, 5, _cfg(length=15)) == 3
    assert cap_beat_count(12, 3, _cfg(length=15)) == 3   # already within runway


def test_cap_beat_count_overtime_keeps_requested():
    # At or past the intended length the requested count is KEPT: open-ended runs
    # keep working, and every overtime slot clamps to the curve endpoint anyway.
    assert cap_beat_count(15, 5, _cfg(length=15)) == 5
    assert cap_beat_count(20, 5, _cfg(length=15)) == 5


def test_cap_beat_count_gate_off_or_unconfigured_keeps_requested():
    assert cap_beat_count(12, 5, _cfg(length=15, **{"coherence.arc_phase_mandate": False})) == 5
    assert cap_beat_count(12, 5, FakeConfig({})) == 5


# ---- slot alignment: final-slot marker (Phase 3) ---------------------------------

def test_schedule_marks_final_slot_at_boundary_only():
    schedule = beat_tension_schedule(12, 3, _cfg(length=15))
    assert [e["tick"] for e in schedule] == [13, 14, 15]
    assert [e["final"] for e in schedule] == [False, False, True]


def test_schedule_final_absent_off_boundary():
    # A batch ending before the boundary carries no final slot...
    assert all(not e["final"] for e in beat_tension_schedule(5, 3, _cfg(length=15)))
    # ...and neither does an overtime batch entirely past it.
    assert all(not e["final"] for e in beat_tension_schedule(15, 3, _cfg(length=15)))


def test_final_beat_directive_shares_resolution_vocabulary():
    assert "denouement" in FINAL_BEAT_DIRECTIVE and "aftermath" in FINAL_BEAT_DIRECTIVE
    shared = "do NOT introduce new threats, complications, or confrontations"
    assert shared in FINAL_BEAT_DIRECTIVE
    assert shared in ARC_PHASE_BEAT_DIRECTIVES["resolution"]


def test_arc_guidance_final_clause_once_on_the_boundary_line():
    section = arc_guidance_for_beats(12, 3, _cfg(length=15))
    assert section.count(FINAL_BEAT_DIRECTIVE) == 1
    final_lines = [l for l in section.splitlines() if FINAL_BEAT_DIRECTIVE in l]
    assert len(final_lines) == 1 and final_lines[0].startswith("- Beat 3")


def test_arc_guidance_no_final_clause_when_batch_misses_boundary():
    assert FINAL_BEAT_DIRECTIVE not in arc_guidance_for_beats(5, 3, _cfg(length=15))
    assert "FINAL SCENE" not in arc_guidance_for_beats(15, 3, _cfg(length=15))


# ---- beat-authoring directives (single source of truth) ------------------------

def test_beat_directives_are_event_level():
    assert set(ARC_PHASE_BEAT_DIRECTIVES) == {"rising", "peak", "falling", "resolution"}
    assert "escalate" in ARC_PHASE_BEAT_DIRECTIVES["rising"]
    assert "confront" in ARC_PHASE_BEAT_DIRECTIVES["peak"]
    for phase in ("falling", "resolution"):
        d = ARC_PHASE_BEAT_DIRECTIVES[phase]
        assert "aftermath" in d and "open loops" in d and "time-skips" in d
        assert "do NOT introduce new threats" in d
    assert "denouement" in ARC_PHASE_BEAT_DIRECTIVES["resolution"]


# ---- section rendering ----------------------------------------------------------

def test_arc_guidance_section_renders_schedule_lines():
    section = arc_guidance_for_beats(15, 5, _cfg(curve=EARLY_PEAK_CURVE))
    assert section.startswith("# Arc schedule for these beats")
    assert '"tension_target"' in section
    assert "supersedes the general instruction" in section
    assert section.count("- Beat ") == 5
    assert "Beat 1 of this batch" in section and "Beat 5 of this batch" in section
    # The per-phase directive text comes from the shared table, not a copy.
    assert "phase FALLING" in section and "phase RESOLUTION" in section
    assert ARC_PHASE_BEAT_DIRECTIVES["resolution"] in section


def test_arc_guidance_section_empty_when_disabled():
    assert arc_guidance_for_beats(10, 5, _cfg(curve=None)) == ""
    assert arc_guidance_for_beats(10, 5, _cfg(**{"coherence.arc_phase_mandate": False})) == ""


def test_arc_guidance_flat_curve_omits_phase_clause():
    section = arc_guidance_for_beats(10, 2, _cfg(curve=[[0.0, 5], [1.0, 5]]))
    assert "target tension 5/10" in section
    assert "phase" not in section.split("- Beat 1")[1].split("\n")[0]


def test_template_renders_without_arc_section_key():
    # Callers that predate the section (or run with it disabled) must still render.
    ctx = {"count": 2, "novel_name": "N", "current_tick": 1, "genre": "g",
           "premise": "p", "setting": "s", "tone": "t", "characters": "None",
           "locations": "None", "open_loops": "None", "recent_scenes": "None",
           "tension_history": "None", "recent_beats": "None"}
    prompt = format_plot_generation_prompt(ctx)
    assert "Arc schedule" not in prompt
    ctx["arc_guidance_section"] = arc_guidance_for_beats(10, 2, _cfg())
    assert "# Arc schedule for these beats" in format_plot_generation_prompt(ctx)


# ---- post-parse reconciliation (sanitize-not-trust) ------------------------------

def _beats(*targets):
    return [PlotBeat(id=f"PB{i:03d}", description="x", tension_target=t)
            for i, t in enumerate(targets, start=1)]


def test_reconcile_fills_missing_targets_from_schedule():
    beats = _beats(None, None)
    warnings = reconcile_beat_tension_targets(beats, 10, _cfg())
    assert warnings == []  # a fill is not a conflict
    # Scheduled 6.4 and 6.8 round to the beat field's integer scale.
    assert [b.tension_target for b in beats] == [6, 7]


def test_reconcile_keeps_targets_within_the_allowed_band():
    beats = _beats(7, 5)  # scheduled 6.4 / 6.8, both within +/-2
    warnings = reconcile_beat_tension_targets(beats, 10, _cfg())
    assert warnings == []
    assert [b.tension_target for b in beats] == [7, 5]


def test_reconcile_clamps_deviant_targets_toward_schedule():
    # Scheduled 6.4 / 6.8: authored 10 clamps down to 8 (6.4 + 2), authored 1
    # up to 5 (6.8 - 2, rounded).
    beats = _beats(10, 1)
    warnings = reconcile_beat_tension_targets(beats, 10, _cfg())
    assert len(warnings) == 2
    assert "PB001" in warnings[0] and "clamped to 8" in warnings[0]
    assert "PB002" in warnings[1] and "clamped to 5" in warnings[1]
    assert [b.tension_target for b in beats] == [8, 5]


def test_reconcile_replaces_unusable_target():
    beats = _beats("very tense")
    warnings = reconcile_beat_tension_targets(beats, 10, _cfg())
    assert len(warnings) == 1 and "unusable" in warnings[0]
    assert beats[0].tension_target == 6


def test_reconcile_aligns_with_capped_batch():
    # A capped batch reconciles against the same leading slots the full batch
    # would occupy: schedule positions are relative to current_tick, so index
    # alignment survives the cap.
    full = beat_tension_schedule(12, 5, _cfg(length=15))
    beats = _beats(None, None, None)
    assert reconcile_beat_tension_targets(beats, 12, _cfg(length=15)) == []
    assert [b.tension_target for b in beats] == [int(round(e["target"])) for e in full[:3]]
    # The arbiter run's slots verbatim: 8.8, 7.3, 4.0.
    assert [b.tension_target for b in beats] == [9, 7, 4]


def test_reconcile_noop_when_gated_off_or_curve_none():
    for cfg in (_cfg(**{"coherence.arc_phase_mandate": False}), _cfg(curve=None)):
        beats = _beats(None, 10)
        assert reconcile_beat_tension_targets(beats, 10, cfg) == []
        assert [b.tension_target for b in beats] == [None, 10]


# ---- both context-assembly paths populate the section -----------------------------

class _FakeLLM:
    """Returns a canned beats payload and records the prompt it saw."""

    def __init__(self, beats=None):
        self._beats = beats if beats is not None else [{"description": "fresh beat"}]
        self.prompt = None

    def generate(self, prompt, max_tokens=1000):
        self.prompt = prompt
        return json.dumps({"beats": self._beats})


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 10, "novel_name": "N"}))
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Joran", family_name="Vell",
                                role="protagonist", description="lead"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_agent_path_context_carries_arc_section(project):
    mgr = PlotOutlineManager(project, _FakeLLM(), config=_cfg())
    ctx = mgr._build_generation_context(count=3)
    assert "# Arc schedule for these beats" in ctx["arc_guidance_section"]
    assert ctx["arc_guidance_section"].count("- Beat ") == 3
    prompt = format_plot_generation_prompt(ctx)
    assert "# Arc schedule for these beats" in prompt


def test_agent_path_generation_prompt_and_reconciliation(project):
    # The rendered prompt carries the schedule, and the parsed beats are
    # reconciled against it: missing target filled, deviant target clamped.
    llm = _FakeLLM(beats=[{"description": "calm walk"},
                          {"description": "sudden war", "tension_target": 10}])
    mgr = PlotOutlineManager(project, llm, config=_cfg())
    beats = mgr.generate_next_beats(count=2)
    assert "# Arc schedule for these beats" in llm.prompt
    assert beats[0].tension_target == 6      # filled from scheduled 6.4
    assert beats[1].tension_target == 9      # 10 clamped to 6.8 + 2 (rounded)


def test_agent_path_defaults_to_project_config(project):
    # No config passed and no config.yaml: the manager falls back to defaults,
    # where the curve and mandate are on, so the section still renders.
    mgr = PlotOutlineManager(project, _FakeLLM())
    ctx = mgr._build_generation_context(count=2)
    assert "# Arc schedule for these beats" in ctx["arc_guidance_section"]


def test_agent_path_section_empty_when_disabled(project):
    mgr = PlotOutlineManager(project, _FakeLLM(), config=_cfg(curve=None))
    ctx = mgr._build_generation_context(count=3)
    assert ctx["arc_guidance_section"] == ""
    assert "Arc schedule" not in format_plot_generation_prompt(ctx)


def test_cli_path_prompt_carries_arc_section(project):
    from novel_agent.cli.commands.plot import _build_plot_generation_prompt

    prompt = _build_plot_generation_prompt(project, count=3)
    assert "# Arc schedule for these beats" in prompt
    assert prompt.count("- Beat ") == 3


def test_cli_path_section_respects_project_config(project):
    from novel_agent.cli.commands.plot import _build_plot_generation_prompt

    (project / "config.yaml").write_text(
        "coherence:\n  target_tension_curve: null\n")
    prompt = _build_plot_generation_prompt(project, count=3)
    assert "Arc schedule" not in prompt


# ---- slot alignment: both authoring paths cap to the runway -----------------------

def _set_tick(project, tick):
    (project / "state.json").write_text(json.dumps({"current_tick": tick, "novel_name": "N"}))


def test_agent_path_caps_batch_to_runway(project):
    # The arbiter run's shape: 5 beats requested at tick 12 of a 15-tick story.
    _set_tick(project, 12)
    llm = _FakeLLM(beats=[{"description": f"beat {i}"} for i in range(3)])
    mgr = PlotOutlineManager(project, llm, config=_cfg(length=15))
    beats = mgr.generate_next_beats(count=5)
    # The prompt's schedule has exactly 3 entries and the last is the final slot.
    assert llm.prompt.count("- Beat ") == 3
    assert llm.prompt.count(FINAL_BEAT_DIRECTIVE) == 1
    assert "generate the next 3 factual plot beats" in llm.prompt
    # The returned beats reconcile against the capped schedule (ticks 13-15).
    assert [b.tension_target for b in beats] == [9, 7, 4]


def test_agent_path_overtime_keeps_requested_count(project):
    _set_tick(project, 20)
    llm = _FakeLLM(beats=[{"description": f"beat {i}"} for i in range(5)])
    mgr = PlotOutlineManager(project, llm, config=_cfg(length=15))
    beats = mgr.generate_next_beats(count=5)
    assert llm.prompt.count("- Beat ") == 5
    assert FINAL_BEAT_DIRECTIVE not in llm.prompt
    # Every overtime slot clamps to the curve endpoint.
    assert [b.tension_target for b in beats] == [4, 4, 4, 4, 4]


def test_agent_path_gate_off_keeps_requested_count(project):
    _set_tick(project, 12)
    llm = _FakeLLM(beats=[{"description": "b"}])
    cfg = _cfg(length=15, **{"coherence.arc_phase_mandate": False})
    mgr = PlotOutlineManager(project, llm, config=cfg)
    mgr.generate_next_beats(count=5)
    assert "Arc schedule" not in llm.prompt
    assert "generate the next 5 factual plot beats" in llm.prompt


def test_agent_path_unconfigured_length_keeps_requested_count(project):
    _set_tick(project, 12)
    llm = _FakeLLM(beats=[{"description": "b"}])
    cfg = FakeConfig({"coherence.target_tension_curve": DEFAULT_CURVE})
    mgr = PlotOutlineManager(project, llm, config=cfg)
    mgr.generate_next_beats(count=5)
    # Schedule still renders (length falls back to its default) but nothing caps.
    assert llm.prompt.count("- Beat ") == 5


def test_cli_path_caps_batch_to_runway(project, monkeypatch):
    from novel_agent.cli.commands import plot as plot_cmd

    _set_tick(project, 12)
    (project / "config.yaml").write_text("coherence:\n  target_story_length: 15\n")
    seen = {}

    def fake_send(prompt, max_tokens=2000):
        seen["prompt"] = prompt
        return json.dumps({"beats": [{"description": f"beat {i}"} for i in range(5)]})

    monkeypatch.setattr(plot_cmd, "send_prompt_with_retry", fake_send)
    result = plot_cmd.generate_and_append_beats_cli(project, count=5)
    assert seen["prompt"].count("- Beat ") == 3
    assert seen["prompt"].count(FINAL_BEAT_DIRECTIVE) == 1
    # The over-returned payload is trimmed to the capped count and reconciled
    # against the same slots as the agent path (default curve, ticks 13-15).
    assert len(result["beats"]) == 3
    assert [b.tension_target for b in result["beats"]] == [9, 7, 4]


def test_cli_revise_path_caps_batch_to_runway(project, monkeypatch):
    from novel_agent.cli.commands import plot as plot_cmd

    _set_tick(project, 12)
    (project / "config.yaml").write_text("coherence:\n  target_story_length: 15\n")
    seen = {}

    def fake_send(prompt, max_tokens=2000):
        seen["prompt"] = prompt
        return json.dumps({"beats": [{"description": f"beat {i}"} for i in range(5)]})

    monkeypatch.setattr(plot_cmd, "send_prompt_with_retry", fake_send)
    result = plot_cmd.revise_and_regenerate_beats_cli(project, count=5)
    assert seen["prompt"].count("- Beat ") == 3
    assert len(result["beats"]) == 3


def test_cli_path_reconciles_generated_beats(project, monkeypatch):
    from novel_agent.cli.commands import plot as plot_cmd

    payload = json.dumps({"beats": [
        {"description": "calm walk"},
        {"description": "sudden war", "tension_target": 10},
    ]})
    monkeypatch.setattr(plot_cmd, "send_prompt_with_retry",
                        lambda prompt, max_tokens=2000: payload)
    result = plot_cmd.generate_and_append_beats_cli(project, count=2)
    beats = result["beats"]
    # State tick 10, default config (length 40, default curve): ticks 11 and 12
    # sit at progress 0.275 / 0.3, scheduling targets 5.1 / 5.2.
    assert beats[0].tension_target == 5       # filled (round of 5.1)
    assert beats[1].tension_target == 7       # 10 clamped to 5.2 + 2 (rounded)
