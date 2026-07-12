"""Sacred finale (Phase 3): Python owns the story's final scene.

Policy under test (docs/progress_report_20260710.md addenda 4 and 5): the finale
tick gets a guaranteed genuine ask (pending-beat screen, then an authored finale
beat, then a deterministic template), a bounded full re-roll against the finale
tension cap in place of the prose rewrite, and settled-ending loop quarantine.
The coherence.sacred_finale gate off restores existing behavior exactly.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.agent import StoryAgent
from novel_agent.agent.arc_pressure import ARC_PHASE_MANDATES, FINAL_BEAT_DIRECTIVE
from novel_agent.agent.finale import (
    beat_satisfies_finale_tension,
    ending_instruction,
    finale_target_tension,
    finale_tension_cap,
    hook_ending_instruction,
    is_finale_tick,
    screen_beat_for_finale,
    settled_ending_instruction,
    suppress_finale_loops,
    template_finale_beat,
)
from novel_agent.configs.config import Config
from novel_agent.memory.entities import Character, Location
from novel_agent.memory.manager import MemoryManager
from novel_agent.plot.entities import PlotBeat, PlotOutline
from novel_agent.plot.manager import PlotOutlineManager


def _config(**overrides):
    """Plot-first config with a 15-tick story (default curve endpoint 4, cap 5)."""
    config = Config()
    config.set("generation.use_plot_first", True)
    config.set("coherence.target_story_length", 15)
    for key, value in overrides.items():
        config.set(key, value)
    return config


class _ScriptedLLM:
    """Returns queued responses in order; an Exception in the queue is raised."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt, max_tokens=2000):
        self.prompts.append(prompt)
        out = self.responses.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_finale_tick_detected():
    assert is_finale_tick(15, _config()) is True


def test_mid_story_tick_is_not_finale():
    assert is_finale_tick(10, _config()) is False


def test_overtime_tick_keeps_existing_behavior():
    assert is_finale_tick(16, _config()) is False


def test_gate_off_disables_detection():
    assert is_finale_tick(15, _config(**{"coherence.sacred_finale": False})) is False


def test_no_plot_first_disables_detection():
    assert is_finale_tick(15, _config(**{"generation.use_plot_first": False})) is False


def test_finale_before_plot_first_start_is_not_finale():
    # Plot-first is not active yet at tick 1 (start tick defaults to 2).
    assert is_finale_tick(1, _config(**{"coherence.target_story_length": 1})) is False


def test_unconfigured_length_disables_detection():
    assert is_finale_tick(15, _config(**{"coherence.target_story_length": None})) is False


def test_sacred_finale_config_defaults():
    config = Config()
    assert config.get("coherence.sacred_finale") is True
    assert config.get("coherence.finale_retries") == 2
    assert config.get("coherence.ending_hook") is False


# ---------------------------------------------------------------------------
# Finale target and cap
# ---------------------------------------------------------------------------

def test_finale_target_and_cap_come_from_curve_endpoint():
    assert finale_target_tension(_config()) == 4.0  # default curve ends [1.0, 4]
    assert finale_tension_cap(_config()) == 5.0


def test_finale_target_defaults_when_curve_disabled():
    config = _config(**{"coherence.target_tension_curve": None})
    assert finale_target_tension(config) == 4.0


def test_beat_tension_precheck():
    config = _config()
    calm = PlotBeat(id="PB1", description="d", tension_target=4)
    edge = PlotBeat(id="PB2", description="d", tension_target=5)
    hot = PlotBeat(id="PB3", description="d", tension_target=7)
    unknown = PlotBeat(id="PB4", description="d", tension_target=None)
    assert beat_satisfies_finale_tension(calm, config) is True
    assert beat_satisfies_finale_tension(edge, config) is True
    assert beat_satisfies_finale_tension(hot, config) is False
    assert beat_satisfies_finale_tension(unknown, config) is False


# ---------------------------------------------------------------------------
# The pending-beat screen
# ---------------------------------------------------------------------------

def test_screen_parses_verdict_and_prompts_with_description():
    llm = _ScriptedLLM(['{"denouement": true, "reason": "a time-skip epilogue"}'])
    beat = PlotBeat(id="PB1", description="a quiet aftermath, weeks later")
    verdict = screen_beat_for_finale(llm, beat, _config())
    assert verdict == {"denouement": True, "reason": "a time-skip epilogue"}
    assert "a quiet aftermath, weeks later" in llm.prompts[0]


def test_screen_accepts_yes_no_strings():
    llm = _ScriptedLLM(['{"denouement": "no", "reason": "an ultimatum is an event"}'])
    verdict = screen_beat_for_finale(llm, PlotBeat(id="PB1", description="d"), _config())
    assert verdict["denouement"] is False


def test_screen_retries_once_on_parse_failure():
    llm = _ScriptedLLM(["not json at all", '{"denouement": true, "reason": "ok"}'])
    verdict = screen_beat_for_finale(llm, PlotBeat(id="PB1", description="d"), _config())
    assert verdict["denouement"] is True
    assert len(llm.prompts) == 2


def test_screen_double_failure_returns_none_never_raises():
    llm = _ScriptedLLM([RuntimeError("backend down"), "still not json"])
    assert screen_beat_for_finale(llm, PlotBeat(id="PB1", description="d"), _config()) is None


# ---------------------------------------------------------------------------
# Ask chain (agent shim over a real project dir)
# ---------------------------------------------------------------------------

@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({
        "current_tick": 15,
        "novel_name": "N",
        "active_character": "C000",
        "story_foundation": {"genre": "scifi", "premise": "p"},
    }))
    memory = MemoryManager(d)
    memory.save_character(Character(id="C000", first_name="Vela", family_name="Sorn",
                                    role="protagonist"))
    memory.save_location(Location(id="L000", name="The Herb Garden"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


class _AskShim:
    """Borrow the real StoryAgent ask-chain methods over minimal state."""

    _sacred_finale_beat = StoryAgent._sacred_finale_beat
    _note_finale_bypass = StoryAgent._note_finale_bypass

    def __init__(self, project_dir, config, llm):
        self.config = config
        self.llm = llm
        self.memory = MemoryManager(project_dir)
        self.state = json.loads((project_dir / "state.json").read_text())
        self.plot_manager = PlotOutlineManager(project_dir, llm, config)


def _seed_pending(project_dir, config, description="a hot mid-arc beat", **beat_kwargs):
    manager = PlotOutlineManager(project_dir, None, config)
    beat = PlotBeat(id="PB001", description=description, status="pending", **beat_kwargs)
    outline = PlotOutline(beats=[beat], created_at=PlotOutline.now_iso(),
                          last_updated=PlotOutline.now_iso())
    manager.save_outline(outline)
    return beat


def _outline_beats(shim):
    return {b.id: b for b in shim.plot_manager.load_outline().beats}


_AUTHORED = json.dumps({"beats": [{
    "description": "Weeks later, Vela tends the herb garden and the matter is settled",
    "characters_involved": ["C000"],
    "location": "L000",
    "plot_threads": [],
    "tension_target": 4,
}]})


def test_pending_beat_passing_screen_flows_through(project):
    llm = _ScriptedLLM(['{"denouement": true, "reason": "aftermath"}'])
    config = _config()
    _seed_pending(project, config, description="Vela tends her herb boxes weeks later",
                  tension_target=4)
    shim = _AskShim(project, config, llm)

    beat, source = shim._sacred_finale_beat(15)

    assert source == "pending_beat"
    assert beat.id == "PB001"
    stored = _outline_beats(shim)["PB001"]
    assert stored.status == "pending"                    # completion happens at step 11.5
    assert "Superseded" not in (stored.execution_notes or "")
    assert len(llm.prompts) == 1                         # only the screen was called


def test_hot_pending_beat_bypassed_to_authored(project):
    # tension_target 7 fails the precheck, so the screen is never consulted:
    # the single scripted response is the authoring call.
    llm = _ScriptedLLM([_AUTHORED])
    config = _config()
    _seed_pending(project, config, tension_target=7)
    shim = _AskShim(project, config, llm)

    beat, source = shim._sacred_finale_beat(15)

    assert source == "authored"
    beats = _outline_beats(shim)
    # The bypassed beat stays pending with the supersession note.
    assert beats["PB001"].status == "pending"
    assert "Superseded by the sacred finale at tick 15" in beats["PB001"].execution_notes
    # The authored beat is persisted with the Python-owned finale contract.
    assert beat.id in beats and beats[beat.id].status == "pending"
    assert beat.tension_target == 4
    assert beat.postconditions == [{"check": "tension_at_most", "value": 5}]
    assert beat.characters_involved == ["C000"] and beat.location == "L000"


def test_screen_rejection_falls_to_authored(project):
    llm = _ScriptedLLM(['{"denouement": false, "reason": "an ultimatum"}', _AUTHORED])
    config = _config()
    _seed_pending(project, config, tension_target=4)
    shim = _AskShim(project, config, llm)

    beat, source = shim._sacred_finale_beat(15)

    assert source == "authored"
    assert "Superseded" in _outline_beats(shim)["PB001"].execution_notes


def test_authoring_retries_once_before_succeeding(project):
    llm = _ScriptedLLM(["garbage", _AUTHORED])
    config = _config()
    shim = _AskShim(project, config, llm)   # no pending beat: straight to authoring

    beat, source = shim._sacred_finale_beat(15)

    assert source == "authored"
    assert len(llm.prompts) == 2


def test_authoring_double_failure_falls_to_template(project):
    llm = _ScriptedLLM(["garbage", RuntimeError("backend down")])
    config = _config()
    shim = _AskShim(project, config, llm)

    beat, source = shim._sacred_finale_beat(15)

    assert source == "template"
    # Well-formed from canon: protagonist name, known location, time skip, contract.
    assert "Vela" in beat.description
    assert "The Herb Garden" in beat.description
    assert "Weeks later" in beat.description
    assert beat.tension_target == 4
    assert beat.postconditions == [{"check": "tension_at_most", "value": 5}]
    assert beat.characters_involved == ["C000"] and beat.location == "L000"
    # Persisted to the outline so step 11.5 verification works on a real beat.
    stored = _outline_beats(shim)[beat.id]
    assert stored.status == "pending"


def test_template_beat_degrades_without_canon(project):
    memory = MemoryManager(project)
    beat = template_finale_beat(memory, {}, _config())   # no active character
    assert "the protagonist" in beat.description
    assert beat.characters_involved == []
    assert beat.tension_target == 4


# ---------------------------------------------------------------------------
# Bounded finale retry (full re-roll, not the revision pass)
# ---------------------------------------------------------------------------

class _FakeWriter:
    def __init__(self):
        self.calls = 0

    def write_scene(self, ctx):
        self.calls += 1
        return {"text": f"render {self.calls}", "word_count": 2, "title": "T"}


class _ScriptedTension:
    """Scores for the re-rolls only; the first render's score is passed in."""

    def __init__(self, levels):
        self.levels = list(levels)

    def evaluate_tension(self, text, ctx):
        return {"enabled": True, "tension_level": self.levels.pop(0),
                "tension_category": "x"}


class _RerollShim:
    _finale_reroll_for_tension = StoryAgent._finale_reroll_for_tension
    _control_scene_tension = StoryAgent._control_scene_tension

    def __init__(self, config, writer, tension):
        self.config = config
        self.writer = writer
        self.tension_evaluator = tension


def _tr(level):
    return {"enabled": True, "tension_level": level, "tension_category": "x"}


def _info():
    return {"ask_source": "template", "retries_used": 0, "loops_suppressed": 0}


def test_reroll_keeps_first_passing_render():
    # Scores [7, 4] at cap 5: the second render passes, one retry used.
    writer = _FakeWriter()
    shim = _RerollShim(_config(), writer, _ScriptedTension([4]))
    info = _info()
    scene, tr = shim._finale_reroll_for_tension(
        {"text": "hot", "word_count": 1}, _tr(7), {}, info)
    assert scene["text"] == "render 1"
    assert tr["tension_level"] == 4
    assert info["retries_used"] == 1
    assert writer.calls == 1


def test_reroll_all_failing_keeps_lowest():
    # Scores [7, 7, 7]: nothing passes, the tie keeps the first render, both retries used.
    writer = _FakeWriter()
    shim = _RerollShim(_config(), writer, _ScriptedTension([7, 7]))
    info = _info()
    scene, tr = shim._finale_reroll_for_tension(
        {"text": "hot", "word_count": 1}, _tr(7), {}, info)
    assert scene["text"] == "hot"
    assert tr["tension_level"] == 7
    assert info["retries_used"] == 2
    assert writer.calls == 2


def test_reroll_keeps_lowest_scoring_render():
    # Scores [8, 6, 7]: none pass the cap, the 6 wins.
    writer = _FakeWriter()
    shim = _RerollShim(_config(), writer, _ScriptedTension([6, 7]))
    info = _info()
    scene, tr = shim._finale_reroll_for_tension(
        {"text": "hot", "word_count": 1}, _tr(8), {}, info)
    assert scene["text"] == "render 1"
    assert tr["tension_level"] == 6
    assert info["retries_used"] == 2


def test_passing_first_render_uses_zero_retries():
    writer = _FakeWriter()
    shim = _RerollShim(_config(), writer, _ScriptedTension([]))
    info = _info()
    scene, tr = shim._finale_reroll_for_tension(
        {"text": "calm", "word_count": 1}, _tr(4), {}, info)
    assert scene["text"] == "calm"
    assert info["retries_used"] == 0
    assert writer.calls == 0


def test_scorer_unavailable_keeps_first_render():
    writer = _FakeWriter()
    shim = _RerollShim(_config(), writer, _ScriptedTension([]))
    info = _info()
    scene, tr = shim._finale_reroll_for_tension(
        {"text": "x", "word_count": 1}, {"enabled": False}, {}, info)
    assert scene["text"] == "x"
    assert writer.calls == 0 and info["retries_used"] == 0


def test_reroll_never_raises_on_writer_failure():
    class _BoomWriter:
        calls = 0

        def write_scene(self, ctx):
            raise RuntimeError("writer down")

    shim = _RerollShim(_config(), _BoomWriter(), _ScriptedTension([]))
    scene, tr = shim._finale_reroll_for_tension(
        {"text": "hot", "word_count": 1}, _tr(7), {}, _info())
    assert scene["text"] == "hot" and tr["tension_level"] == 7


def test_finale_tick_skips_rewrite_path():
    # With finale_info set, step 7.6 dispatches to the re-roll, never the rewrite.
    writer = _FakeWriter()
    shim = _RerollShim(_config(), writer, _ScriptedTension([4]))
    rewrite_calls = []
    shim._maybe_rewrite_for_tension = (
        lambda scene, tr, tick, ctx: rewrite_calls.append(tick) or (scene, tr))
    scene, tr = shim._control_scene_tension(
        {"text": "hot", "word_count": 1}, _tr(7), 15, {}, _info())
    assert rewrite_calls == []
    assert writer.calls == 1 and scene["text"] == "render 1"


def test_normal_tick_uses_rewrite_path():
    writer = _FakeWriter()
    shim = _RerollShim(_config(), writer, _ScriptedTension([]))
    rewrite_calls = []
    shim._maybe_rewrite_for_tension = (
        lambda scene, tr, tick, ctx: rewrite_calls.append(tick) or (scene, tr))
    shim._control_scene_tension({"text": "x", "word_count": 1}, _tr(7), 8, {}, None)
    assert rewrite_calls == [8]
    assert writer.calls == 0


# ---------------------------------------------------------------------------
# Ending-mode loop discipline
# ---------------------------------------------------------------------------

class _LoopShim:
    _quarantine_finale_loops = StoryAgent._quarantine_finale_loops

    def __init__(self, config):
        self.config = config


def _facts():
    return {
        "character_updates": [{"id": "C000", "changes": {}}],
        "open_loops_created": [
            {"description": "a mysterious dossier arrives"},
            {"description": "who sent the message"},
        ],
        "open_loops_resolved": ["OL1"],
    }


def test_settled_finale_quarantines_new_loops(capsys):
    shim = _LoopShim(_config())
    info = _info()
    facts = shim._quarantine_finale_loops(_facts(), info)
    # The entity updater sees a facts dict without the new loops...
    assert facts["open_loops_created"] == []
    # ...but every other update survives untouched.
    assert facts["character_updates"] == [{"id": "C000", "changes": {}}]
    assert facts["open_loops_resolved"] == ["OL1"]
    assert info["loops_suppressed"] == 2
    out = capsys.readouterr().out
    assert "suppressed 2 finale loop(s)" in out
    assert "a mysterious dossier arrives" in out


def test_hook_mode_lets_loops_through():
    shim = _LoopShim(_config(**{"coherence.ending_hook": True}))
    info = _info()
    facts = shim._quarantine_finale_loops(_facts(), info)
    assert len(facts["open_loops_created"]) == 2
    assert info["loops_suppressed"] == 0


def test_suppress_finale_loops_does_not_mutate_original():
    original = _facts()
    filtered, suppressed = suppress_finale_loops(original)
    assert len(original["open_loops_created"]) == 2
    assert filtered["open_loops_created"] == []
    assert suppressed == ["a mysterious dossier arrives", "who sent the message"]


def test_suppress_finale_loops_noop_without_loops():
    facts = {"character_updates": []}
    filtered, suppressed = suppress_finale_loops(facts)
    assert filtered is facts and suppressed == []


# ---------------------------------------------------------------------------
# Ending-mode writer instructions
# ---------------------------------------------------------------------------

def test_settled_instruction_composes_shared_vocabulary():
    text = settled_ending_instruction()
    # Single source of truth: the shared constants appear verbatim, not paraphrased.
    assert FINAL_BEAT_DIRECTIVE in text
    assert ARC_PHASE_MANDATES["resolution"] in text
    # The structural rules cover the hook shapes the sunshine test observed.
    for banned in ("threats", "arrivals", "messages", "revelations",
                   "unanswered questions"):
        assert banned in text
    assert "ENDS here" in text


def test_hook_instruction_allows_exactly_one_hook():
    text = hook_ending_instruction()
    assert "ONE deliberate hook" in text
    assert "everything else is settled" in text


def test_ending_instruction_dispatch():
    assert ending_instruction("settled") == settled_ending_instruction()
    assert ending_instruction("hook") == hook_ending_instruction()
    assert ending_instruction("") == ""
    assert ending_instruction("unknown") == ""


def test_writer_context_injects_finale_section():
    from novel_agent.agent.writer_context import WriterContextBuilder
    builder = WriterContextBuilder.__new__(WriterContextBuilder)
    assert builder._build_finale_section({}) == ""
    assert builder._build_finale_section({"finale_mode": "settled"}) == settled_ending_instruction()
    assert builder._build_finale_section({"finale_mode": "hook"}) == hook_ending_instruction()


# ---------------------------------------------------------------------------
# Coherence rubric fields
# ---------------------------------------------------------------------------

class _FakeVector:
    def compute_semantic_similarity(self, a, b):
        return 0.5


def test_metrics_record_finale_fields(project):
    from novel_agent.agent.coherence_metrics import CoherenceMetrics

    metrics = CoherenceMetrics(project, MemoryManager(project), _FakeVector(), Config())

    record = metrics.record_tick(
        tick=15, scene_id="S015",
        finale_result={"ask_source": "template", "retries_used": 1,
                       "loops_suppressed": 3,
                       "screen_refusal": "an active courtroom event"})
    assert record["finale_ask_source"] == "template"
    assert record["finale_retries_used"] == 1
    assert record["finale_loops_suppressed"] == 3
    assert record["finale_screen_refusal"] == "an active courtroom event"

    record = metrics.record_tick(tick=8, scene_id="S008")
    assert record["finale_ask_source"] is None
    assert record["finale_retries_used"] is None
    assert record["finale_loops_suppressed"] is None
    assert record["finale_screen_refusal"] is None


# ---------------------------------------------------------------------------
# Screen-refusal observability (Phase 3 hardening, 2026-07-12 section 8.4: the
# screen's negative reason used to vanish)
# ---------------------------------------------------------------------------

def test_screen_refusal_reason_persisted_and_printed(project, capsys):
    llm = _ScriptedLLM(['{"denouement": false, "reason": "an ultimatum"}', _AUTHORED])
    config = _config()
    _seed_pending(project, config, tension_target=4)
    shim = _AskShim(project, config, llm)

    beat, source = shim._sacred_finale_beat(15)

    assert source == "authored"
    # The reason rides the supersession note on the bypassed beat...
    notes = _outline_beats(shim)["PB001"].execution_notes
    assert "Superseded by the sacred finale at tick 15" in notes
    assert "finale screen refusal: an ultimatum" in notes
    # ...is printed at tick level...
    assert "fails the finale screen: an ultimatum" in capsys.readouterr().out
    # ...and is staged for the finale result dict / metrics trail.
    assert shim._finale_screen_refusal == "an ultimatum"


def test_screen_refusal_without_reason_gets_placeholder(project):
    llm = _ScriptedLLM(['{"denouement": false}', _AUTHORED])
    config = _config()
    _seed_pending(project, config, tension_target=4)
    shim = _AskShim(project, config, llm)

    shim._sacred_finale_beat(15)

    assert shim._finale_screen_refusal == "(no reason given)"
    assert "finale screen refusal: (no reason given)" in \
        _outline_beats(shim)["PB001"].execution_notes


def test_precheck_bypass_carries_no_refusal(project):
    # tension_target 7 fails the precheck, so the screen never ran: there is
    # no refusal to persist, only the plain supersession note.
    llm = _ScriptedLLM([_AUTHORED])
    config = _config()
    _seed_pending(project, config, tension_target=7)
    shim = _AskShim(project, config, llm)

    shim._sacred_finale_beat(15)

    assert shim._finale_screen_refusal is None
    notes = _outline_beats(shim)["PB001"].execution_notes
    assert "Superseded" in notes
    assert "finale screen refusal" not in notes


def test_screen_double_failure_is_not_a_refusal(project):
    # An unavailable screen (double parse failure returns None) is a fallback,
    # not a "no": nothing to persist.
    llm = _ScriptedLLM(["garbage", "garbage", _AUTHORED])
    config = _config()
    _seed_pending(project, config, tension_target=4)
    shim = _AskShim(project, config, llm)

    shim._sacred_finale_beat(15)

    assert shim._finale_screen_refusal is None
    assert "finale screen refusal" not in \
        _outline_beats(shim)["PB001"].execution_notes


def test_screen_pass_leaves_refusal_unset(project):
    llm = _ScriptedLLM(['{"denouement": true, "reason": "aftermath"}'])
    config = _config()
    _seed_pending(project, config, description="Vela tends her herb boxes weeks later",
                  tension_target=4)
    shim = _AskShim(project, config, llm)

    beat, source = shim._sacred_finale_beat(15)

    assert source == "pending_beat"
    assert shim._finale_screen_refusal is None


# ---------------------------------------------------------------------------
# End-marker guarantee (Phase 3 hardening, 2026-07-12 section 5: the settled
# finale was complete but markerless; the marker was luck, now a guarantee)
# ---------------------------------------------------------------------------

class _MarkerShim:
    _ensure_finale_end_marker = StoryAgent._ensure_finale_end_marker

    def __init__(self, project_dir):
        self.project_path = Path(project_dir)


def _write_scene(project_dir, tick, body):
    scenes = Path(project_dir) / "scenes"
    scenes.mkdir(parents=True, exist_ok=True)
    path = scenes / f"scene_{tick:03d}.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_end_marker_appended_to_committed_finale(project, capsys):
    body = ("# The Last Day\n\n*Scene ID: S015*\n*Tick: 15*\n\n---\n\n"
            "Everything except what it would cost.\n")
    path = _write_scene(project, 15, body)
    shim = _MarkerShim(project)
    info = {}

    shim._ensure_finale_end_marker(15, info)

    content = path.read_text(encoding="utf-8")
    assert content.rstrip().splitlines()[-1] == "THE END"
    assert content.startswith(body.rstrip())
    assert info["end_marker_appended"] is True
    assert "Appended the end marker" in capsys.readouterr().out

    # The completion heuristic agrees the marked file is a detected ending.
    from novel_agent.agent.segments import scene_incomplete
    assert scene_incomplete(content) is False


def test_end_marker_not_duplicated_when_writer_emitted_one(project):
    body = "The story wound down.\n\nEND OF NOVEL\n"
    path = _write_scene(project, 15, body)
    shim = _MarkerShim(project)
    info = {}

    shim._ensure_finale_end_marker(15, info)

    assert path.read_text(encoding="utf-8") == body
    assert info["end_marker_appended"] is False


def test_end_marker_append_is_idempotent_at_file_level(project):
    path = _write_scene(project, 15, "A settled last line.\n")
    shim = _MarkerShim(project)

    first, second = {}, {}
    shim._ensure_finale_end_marker(15, first)
    after_first = path.read_text(encoding="utf-8")
    shim._ensure_finale_end_marker(15, second)

    assert first["end_marker_appended"] is True
    assert second["end_marker_appended"] is False
    assert path.read_text(encoding="utf-8") == after_first


def test_end_marker_missing_file_never_raises(project):
    shim = _MarkerShim(project)
    info = {}
    shim._ensure_finale_end_marker(99, info)  # no scenes/scene_099.md
    assert "end_marker_appended" not in info
