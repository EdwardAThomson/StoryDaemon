"""Judged loop closure and creation hygiene (Phase 3, Slice 0 of the interleaving design).

Policy under test (docs/THREAD_INTERLEAVING_DESIGN.md Slice 0, evidence in
docs/progress_report_20260710.md): beat completion NOMINATES the loops its
author claimed it resolves, a focused one-loop, one-scene judge CONFIRMS each
claim, and every closure carries an auditable summary. Claims are sanitized at
authoring (phantom loop IDs dropped) in both beat-generation paths. The
coherence.loop_closure gate defaults True since its validation run passed
(docs/progress_report_20260711.md).

Phase 3, Slice 0 follow-ups (same validation run): beats split loop claims into
resolves_loops (answered on the page) vs advances_loops (moved forward, not
answered); the extractor's open_loops_resolved claims face the same judge,
bounded per tick, instead of the unaudited finale mass-sweep; and on the finale
tick still-open loops expire ("left open at story end") as
terminal-but-distinct from resolved.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.agent import StoryAgent
from novel_agent.agent.loop_closure import (
    MAX_CLAIMS_JUDGED,
    claimed_open_loops,
    close_claimed_loops,
    expire_open_loops_at_finale,
    judge_extractor_resolutions,
    judge_loop_resolution,
    sanitize_beat_loop_claims,
)
from novel_agent.configs.config import Config
from novel_agent.memory.entities import OpenLoop
from novel_agent.memory.manager import MemoryManager
from novel_agent.plot.entities import PlotBeat, PlotOutline
from novel_agent.plot.manager import PlotOutlineManager


def _config(**overrides):
    """Gate-on config unless a test overrides it (explicit, though the gate
    now defaults True)."""
    config = Config()
    config.set("coherence.loop_closure", True)
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


_YES = '{"resolved": true, "reason": "the sender is revealed on the page"}'
_NO = '{"resolved": false, "reason": "the scene only mentions the tip"}'


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 9, "novel_name": "N"}))
    memory = MemoryManager(d)
    memory.add_open_loop(OpenLoop(id="OL001", description="Who sent the anonymous tip?"))
    memory.add_open_loop(OpenLoop(id="OL002", description="Where is the missing ledger?"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _beat(**kwargs):
    kwargs.setdefault("id", "PB007")
    kwargs.setdefault("description", "The tipster steps forward")
    return PlotBeat(**kwargs)


def _loop(memory, loop_id):
    return {l.id: l for l in memory.load_open_loops()}[loop_id]


# ---------------------------------------------------------------------------
# The focused judge: confirmed yes closes, with the audit summary
# ---------------------------------------------------------------------------

def test_confirmed_claim_closes_with_audit_summary(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([_YES])
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(llm, memory, beat, "S009", "scene prose", _config())

    assert result == {"beat_id": "PB007", "claimed": ["OL001"],
                      "judged": 1, "closed": ["OL001"], "refused": []}
    loop = _loop(memory, "OL001")
    assert loop.status == "resolved"
    assert loop.resolved_in_scene == "S009"
    assert loop.resolution_summary == (
        "closed via beat PB007; judge: the sender is revealed on the page")


def test_judge_sees_one_loop_and_the_scene(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([_YES])
    beat = _beat(resolves_loops=["OL001"])

    close_claimed_loops(llm, memory, beat, "S009", "the confession scene", _config())

    assert len(llm.prompts) == 1
    assert "Who sent the anonymous tip?" in llm.prompts[0]
    assert "the confession scene" in llm.prompts[0]
    # Focused by design: the other open loop never enters the prompt.
    assert "Where is the missing ledger?" not in llm.prompts[0]


def test_denied_claim_leaves_loop_open(project):
    memory = MemoryManager(project)
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(
        _ScriptedLLM([_NO]), memory, beat, "S009", "prose", _config())

    assert result["judged"] == 1 and result["closed"] == []
    # The judge's "no" reason persists in the result dict (observability:
    # the 2026-07-11 run flagged info-level-only refusal reasons as a gap).
    assert result["refused"] == [
        {"loop": "OL001", "reason": "the scene only mentions the tip"}]
    assert _loop(memory, "OL001").status == "open"


def test_malformed_reply_retries_once_then_leaves_open(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM(["not json at all", "still not json"])
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(llm, memory, beat, "S009", "prose", _config())

    assert len(llm.prompts) == 2                 # one retry, then give up
    assert result["judged"] == 1 and result["closed"] == []
    assert _loop(memory, "OL001").status == "open"


def test_retry_recovers_and_closes(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM(["garbage", _YES])
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(llm, memory, beat, "S009", "prose", _config())

    assert result["closed"] == ["OL001"]
    assert len(llm.prompts) == 2


def test_llm_exception_never_raises_and_leaves_open(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([RuntimeError("backend down"), RuntimeError("still down")])
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(llm, memory, beat, "S009", "prose", _config())

    assert result["judged"] == 1 and result["closed"] == []
    assert _loop(memory, "OL001").status == "open"


def test_resolve_failure_never_raises(project):
    class _BrokenResolve:
        def __init__(self, inner):
            self._inner = inner

        def load_open_loops(self):
            return self._inner.load_open_loops()

        def resolve_open_loop(self, **kwargs):
            raise RuntimeError("disk full")

    memory = _BrokenResolve(MemoryManager(project))
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(
        _ScriptedLLM([_YES]), memory, beat, "S009", "prose", _config())

    assert result["judged"] == 1 and result["closed"] == []


def test_gate_off_means_no_judge_calls(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([])
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(
        llm, memory, beat, "S009", "prose", _config(**{"coherence.loop_closure": False}))

    assert result is None
    assert llm.prompts == []
    assert _loop(memory, "OL001").status == "open"


def test_gate_defaults_on():
    # Flipped after the validation run passed (docs/progress_report_20260711.md).
    assert Config().get("coherence.loop_closure") is True
    assert Config().get("coherence.loop_dedup") is True
    assert Config().get("coherence.extractor_resolutions_judged_cap") == 5


def test_zero_claims_zero_calls(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([])

    result = close_claimed_loops(llm, memory, _beat(), "S009", "prose", _config())

    assert result is None
    assert llm.prompts == []


def test_partial_confirmation_closes_only_the_yes(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([_YES, _NO])
    beat = _beat(resolves_loops=["OL001", "OL002"])

    result = close_claimed_loops(llm, memory, beat, "S009", "prose", _config())

    assert result["judged"] == 2 and result["closed"] == ["OL001"]
    assert _loop(memory, "OL001").status == "resolved"
    assert _loop(memory, "OL002").status == "open"


def test_yes_no_string_verdicts_accepted(project):
    llm = _ScriptedLLM(['{"resolved": "yes", "reason": "answered"}'])
    verdict = judge_loop_resolution(llm, "q", "scene", _config())
    assert verdict == {"resolved": True, "reason": "answered"}

    llm = _ScriptedLLM(['{"resolved": "no", "reason": "only mentioned"}'])
    verdict = judge_loop_resolution(llm, "q", "scene", _config())
    assert verdict["resolved"] is False


def test_judge_without_llm_returns_none():
    assert judge_loop_resolution(None, "q", "scene", _config()) is None


# ---------------------------------------------------------------------------
# Nomination: which claims actually reach the judge
# ---------------------------------------------------------------------------

def test_phantom_claim_skipped_without_judge_call(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([])
    beat = _beat(resolves_loops=["OL39_corul_meeting_setup"])

    result = close_claimed_loops(llm, memory, beat, "S009", "prose", _config())

    assert result["judged"] == 0 and result["closed"] == []
    assert llm.prompts == []


def test_already_resolved_claim_skipped(project):
    memory = MemoryManager(project)
    memory.resolve_open_loop("OL001", "S005", "earlier")
    llm = _ScriptedLLM([])
    beat = _beat(resolves_loops=["OL001"])

    result = close_claimed_loops(llm, memory, beat, "S009", "prose", _config())

    assert result["judged"] == 0
    assert llm.prompts == []


def test_duplicate_claims_judged_once(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([_YES])
    beat = _beat(resolves_loops=["OL001", "OL001"])

    result = close_claimed_loops(llm, memory, beat, "S009", "prose", _config())

    assert result["judged"] == 1 and result["closed"] == ["OL001"]


def test_nominations_capped(project):
    memory = MemoryManager(project)
    for i in range(3, 8):
        memory.add_open_loop(OpenLoop(id=f"OL{i:03d}", description=f"question {i}"))
    beat = _beat(resolves_loops=["OL001", "OL002", "OL003", "OL004", "OL005"])

    nominated = claimed_open_loops(beat, memory)

    assert len(nominated) == MAX_CLAIMS_JUDGED
    assert [l.id for l in nominated] == ["OL001", "OL002", "OL003"]


# ---------------------------------------------------------------------------
# The agent hook: nomination only on beats completed against THIS scene
# ---------------------------------------------------------------------------

class _AgentShim:
    """Borrow the real StoryAgent hook methods over minimal state."""

    _close_claimed_loops = StoryAgent._close_claimed_loops
    _beat_completed_in_scene = StoryAgent._beat_completed_in_scene

    def __init__(self, project_dir, config, llm):
        self.config = config
        self.llm = llm
        self.memory = MemoryManager(project_dir)
        self.plot_manager = PlotOutlineManager(project_dir, llm, config)


def _seed_outline(project_dir, config, **beat_kwargs):
    beat_kwargs.setdefault("id", "PB007")
    beat_kwargs.setdefault("description", "The tipster steps forward")
    beat = PlotBeat(**beat_kwargs)
    manager = PlotOutlineManager(project_dir, None, config)
    outline = PlotOutline(beats=[beat], created_at=PlotOutline.now_iso(),
                          last_updated=PlotOutline.now_iso())
    manager.save_outline(outline)
    return beat


def test_hook_closes_on_completed_beat(project):
    config = _config()
    beat = _seed_outline(project, config, status="completed",
                         executed_in_scene="S009", resolves_loops=["OL001"])
    shim = _AgentShim(project, config, _ScriptedLLM([_YES]))

    result = shim._close_claimed_loops(beat, "S009", "prose")

    assert result["closed"] == ["OL001"]
    assert _loop(shim.memory, "OL001").status == "resolved"


def test_hook_skips_pending_beat(project):
    config = _config()
    beat = _seed_outline(project, config, status="pending", resolves_loops=["OL001"])
    llm = _ScriptedLLM([])
    shim = _AgentShim(project, config, llm)

    assert shim._close_claimed_loops(beat, "S009", "prose") is None
    assert llm.prompts == []
    assert _loop(shim.memory, "OL001").status == "open"


def test_hook_skips_beat_completed_against_another_scene(project):
    config = _config()
    beat = _seed_outline(project, config, status="completed",
                         executed_in_scene="S005", resolves_loops=["OL001"])
    llm = _ScriptedLLM([])
    shim = _AgentShim(project, config, llm)

    assert shim._close_claimed_loops(beat, "S009", "prose") is None
    assert llm.prompts == []


def test_hook_gate_off_short_circuits(project):
    config = _config(**{"coherence.loop_closure": False})
    beat = _seed_outline(project, config, status="completed",
                         executed_in_scene="S009", resolves_loops=["OL001"])
    llm = _ScriptedLLM([])
    shim = _AgentShim(project, config, llm)

    assert shim._close_claimed_loops(beat, "S009", "prose") is None
    assert llm.prompts == []


def test_hook_zero_claims_zero_calls(project):
    config = _config()
    beat = _seed_outline(project, config, status="completed",
                         executed_in_scene="S009")
    llm = _ScriptedLLM([])
    shim = _AgentShim(project, config, llm)

    assert shim._close_claimed_loops(beat, "S009", "prose") is None
    assert llm.prompts == []


def test_hook_never_raises_on_outline_failure(project):
    config = _config()
    beat = _beat(resolves_loops=["OL001"])
    shim = _AgentShim(project, config, _ScriptedLLM([]))

    class _BrokenPlotManager:
        def load_outline(self):
            raise RuntimeError("outline unreadable")

    shim.plot_manager = _BrokenPlotManager()

    assert shim._close_claimed_loops(beat, "S009", "prose") is None


# ---------------------------------------------------------------------------
# Claim sanitization at authoring (both paths, shared helper)
# ---------------------------------------------------------------------------

def test_sanitize_drops_phantom_claims_keeps_real(project):
    memory = MemoryManager(project)
    beat = _beat(resolves_loops=["OL001", "OL39_corul_meeting_setup"])

    warnings = sanitize_beat_loop_claims([beat], memory)

    assert beat.resolves_loops == ["OL001"]
    assert len(warnings) == 1
    assert "OL39_corul_meeting_setup" in warnings[0]
    assert "no such loop ID" in warnings[0]


def test_sanitize_normalizes_colon_suffixed_claims(project):
    # Live finding (2026-07-11 validation, chunk 1): the model copies the
    # prompt's rendered loop line ("OL4: description") instead of the bare ID,
    # which stripped valid claims and silently disarmed judged closure.
    memory = MemoryManager(project)
    beat = _beat(resolves_loops=["OL001: What is Kessler-Vex Holdings really doing?"])

    warnings = sanitize_beat_loop_claims([beat], memory)

    assert beat.resolves_loops == ["OL001"]
    assert warnings == []  # normalization is not a drop


def test_sanitize_normalization_dedups_and_still_drops_phantoms(project):
    memory = MemoryManager(project)
    beat = _beat(resolves_loops=[
        "OL001",
        "OL001: the same loop with its description appended",
        "OL39_corul_meeting_setup",  # invented label, no word boundary: phantom
        "OL999: description of a loop that does not exist",
    ])

    warnings = sanitize_beat_loop_claims([beat], memory)

    assert beat.resolves_loops == ["OL001"]
    assert len(warnings) == 1
    assert "OL39_corul_meeting_setup" in warnings[0]
    assert "OL999" in warnings[0]


def test_sanitize_leaves_creates_loops_alone(project):
    memory = MemoryManager(project)
    beat = _beat(resolves_loops=["OL001"], creates_loops=["kaelus_detained"])

    warnings = sanitize_beat_loop_claims([beat], memory)

    assert warnings == []
    assert beat.creates_loops == ["kaelus_detained"]


def test_sanitize_keeps_claims_when_ledger_unreadable(project):
    class _BrokenLedger:
        def load_open_loops(self):
            raise RuntimeError("unreadable")

    beat = _beat(resolves_loops=["OL001", "phantom"])
    warnings = sanitize_beat_loop_claims([beat], _BrokenLedger())

    assert warnings == []
    assert beat.resolves_loops == ["OL001", "phantom"]


def test_agent_authoring_path_sanitizes_claims(project, capsys):
    manager = PlotOutlineManager(project, None, _config())
    beat = _beat(id="", resolves_loops=["OL001", "OL39_corul_meeting_setup"])

    added = manager.add_beats([beat])

    assert added[0].resolves_loops == ["OL001"]
    assert "OL39_corul_meeting_setup" in capsys.readouterr().out
    # The persisted outline carries the sanitized claim list.
    stored = manager.load_outline().beats[0]
    assert stored.resolves_loops == ["OL001"]


def test_cli_authoring_path_sanitizes_claims(project, capsys):
    from novel_agent.cli.commands.plot import _sanitize_loop_claims

    beat = _beat(resolves_loops=["OL002", "OL99_phantom"])
    _sanitize_loop_claims(project, [beat])

    assert beat.resolves_loops == ["OL002"]
    assert "OL99_phantom" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Coherence rubric fields
# ---------------------------------------------------------------------------

class _FakeVector:
    def compute_semantic_similarity(self, a, b):
        return 0.5


def test_metrics_record_loop_closure_fields(project):
    from novel_agent.agent.coherence_metrics import CoherenceMetrics

    metrics = CoherenceMetrics(project, MemoryManager(project), _FakeVector(), Config())

    record = metrics.record_tick(tick=9, scene_id="S009",
                                 loops_closed_by_beat=2, loops_deduped=1)
    assert record["loops_closed_by_beat"] == 2
    assert record["loops_deduped"] == 1

    # None (not 0) when the machinery did not run, the contract-counter convention.
    record = metrics.record_tick(tick=10, scene_id="S010")
    assert record["loops_closed_by_beat"] is None
    assert record["loops_deduped"] is None


class _RecorderShim:
    _record_coherence_metrics = StoryAgent._record_coherence_metrics
    _loops_deduped_metric = StoryAgent._loops_deduped_metric
    _loops_capped_metric = StoryAgent._loops_capped_metric

    class _CapturingMetrics:
        def __init__(self):
            self.kwargs = None

        def record_tick(self, **kwargs):
            self.kwargs = kwargs
            return kwargs

    def __init__(self, config):
        self.config = config
        self.state = {}
        self.coherence_metrics = self._CapturingMetrics()


def test_agent_passes_closed_count_to_the_rubric():
    shim = _RecorderShim(_config())
    shim._record_coherence_metrics(
        9, "S009", {"text": "x", "word_count": 1}, None,
        loop_closure_result={"beat_id": "PB007", "claimed": ["OL001", "OL002"],
                             "judged": 2, "closed": ["OL001"]})
    assert shim.coherence_metrics.kwargs["loops_closed_by_beat"] == 1

    shim._record_coherence_metrics(10, "S010", {"text": "x", "word_count": 1}, None)
    assert shim.coherence_metrics.kwargs["loops_closed_by_beat"] is None


def test_loops_deduped_metric_conventions():
    shim = _RecorderShim(_config())
    facts = {"open_loops_created": [{"description": "q"}]}

    # Machinery ran: the count is recorded, 0 included.
    assert shim._loops_deduped_metric(facts, {"loops_deduped": 1}) == 1
    assert shim._loops_deduped_metric(facts, {"loops_deduped": 0}) == 0
    # Nothing happened: no creations attempted, or no facts at all.
    assert shim._loops_deduped_metric({"open_loops_created": []}, {}) is None
    assert shim._loops_deduped_metric(None, {}) is None
    # Gate off.
    off = _RecorderShim(_config(**{"coherence.loop_dedup": False}))
    assert off._loops_deduped_metric(facts, {"loops_deduped": 1}) is None


def test_loops_capped_metric_conventions():
    # The observability follow-up from the 2026-07-11 run: cap counts were
    # log-only. Same conventions as loops_deduped.
    shim = _RecorderShim(_config())
    facts = {"open_loops_created": [{"description": "q"}]}

    assert shim._loops_capped_metric(facts, {"loops_capped": 3}) == 3
    assert shim._loops_capped_metric(facts, {"loops_capped": 0}) == 0
    assert shim._loops_capped_metric({"open_loops_created": []}, {}) is None
    assert shim._loops_capped_metric(None, {}) is None
    off = _RecorderShim(_config(**{"coherence.loop_dedup": False}))
    assert off._loops_capped_metric(facts, {"loops_capped": 3}) is None


def test_metrics_record_capped_and_expiry_fields(project):
    from novel_agent.agent.coherence_metrics import CoherenceMetrics

    metrics = CoherenceMetrics(project, MemoryManager(project), _FakeVector(), Config())

    record = metrics.record_tick(tick=15, scene_id="S015", loops_capped=2,
                                 loops_expired=47, dangling_threads=40)
    assert record["loops_capped"] == 2
    assert record["loops_expired"] == 47
    assert record["dangling_threads"] == 40

    # None on ticks where the machinery did not run (every non-finale tick for
    # the expiry fields), the contract-counter convention.
    record = metrics.record_tick(tick=9, scene_id="S009")
    assert record["loops_capped"] is None
    assert record["loops_expired"] is None
    assert record["dangling_threads"] is None


def test_agent_passes_expiry_and_cap_to_the_rubric():
    shim = _RecorderShim(_config())
    facts = {"open_loops_created": [{"description": "q"}]}

    shim._record_coherence_metrics(
        15, "S015", {"text": "x", "word_count": 1}, None,
        loops_capped=shim._loops_capped_metric(facts, {"loops_capped": 2}),
        expiry_result={"expired": ["OL001", "OL002"], "dangling_threads": 1})
    assert shim.coherence_metrics.kwargs["loops_capped"] == 2
    assert shim.coherence_metrics.kwargs["loops_expired"] == 2
    assert shim.coherence_metrics.kwargs["dangling_threads"] == 1

    # Non-finale tick: no expiry payload, both fields None.
    shim._record_coherence_metrics(9, "S009", {"text": "x", "word_count": 1}, None)
    assert shim.coherence_metrics.kwargs["loops_expired"] is None
    assert shim.coherence_metrics.kwargs["dangling_threads"] is None


def test_metrics_loops_closed_excludes_expired(project):
    from novel_agent.agent.coherence_metrics import CoherenceMetrics

    memory = MemoryManager(project)
    memory.resolve_open_loop("OL001", "S015", "answered on the page")
    expire_open_loops_at_finale(memory, "S015")  # OL002 expires

    metrics = CoherenceMetrics(project, memory, _FakeVector(), Config())
    record = metrics.record_tick(tick=15, scene_id="S015")

    # Only the genuinely resolved loop counts as closed; the expired one is
    # terminal-but-distinct even though it carries resolved_in_scene.
    assert record["loops_closed"] == 1
    assert record["open_loops_total"] == 0


# ---------------------------------------------------------------------------
# advances_loops (Phase 3, Slice 0 follow-ups: the resolves-vs-advances reframe)
# ---------------------------------------------------------------------------

def test_advances_loops_round_trips_on_both_dataclasses():
    from novel_agent.memory.entities import PlotBeat as MemoryPlotBeat

    plot_beat = _beat(advances_loops=["OL001", "OL002"])
    assert PlotBeat.from_dict(plot_beat.to_dict()).advances_loops == ["OL001", "OL002"]

    memory_beat = MemoryPlotBeat(id="PB007", description="d",
                                 advances_loops=["OL001"])
    assert MemoryPlotBeat.from_dict(memory_beat.to_dict()).advances_loops == ["OL001"]


def test_legacy_beat_dicts_load_without_advances_loops():
    from novel_agent.memory.entities import PlotBeat as MemoryPlotBeat

    legacy = {"id": "PB001", "description": "old outline beat",
              "resolves_loops": ["OL001"]}
    for cls in (PlotBeat, MemoryPlotBeat):
        beat = cls.from_dict(dict(legacy))
        assert beat.resolves_loops == ["OL001"]
        assert beat.advances_loops == []


def test_prompt_shape_example_and_rule_cover_advances_loops():
    from novel_agent.agent.prompts import PLOT_GENERATION_PROMPT_TEMPLATE as tmpl

    assert '"advances_loops": [],' in tmpl
    # The resolve/advance line the judge holds (2026-07-11 run: all 10 refusals
    # were beats that merely advanced their claimed loop).
    assert 'ANSWER that loop ON THE PAGE' in tmpl
    assert '"advances_loops" instead' in tmpl
    assert 'For "resolves_loops" and "advances_loops", use ONLY the bare loop IDs' in tmpl


def test_sanitize_covers_advances_loops(project):
    memory = MemoryManager(project)
    beat = _beat(
        resolves_loops=["OL001"],
        advances_loops=["OL002: colon-suffixed line", "OL77_phantom_label"],
    )

    warnings = sanitize_beat_loop_claims([beat], memory)

    assert beat.resolves_loops == ["OL001"]
    assert beat.advances_loops == ["OL002"]  # normalized, not dropped
    assert len(warnings) == 1
    assert "advances_loops" in warnings[0]  # the warning names the field
    assert "OL77_phantom_label" in warnings[0]


def test_sanitize_warnings_name_the_right_field(project):
    memory = MemoryManager(project)
    beat = _beat(resolves_loops=["OL88_phantom"], advances_loops=["OL99_phantom"])

    warnings = sanitize_beat_loop_claims([beat], memory)

    assert len(warnings) == 2
    resolves_warning = next(w for w in warnings if "OL88_phantom" in w)
    advances_warning = next(w for w in warnings if "OL99_phantom" in w)
    assert "resolves_loops" in resolves_warning
    assert "advances_loops" in advances_warning
    assert beat.resolves_loops == [] and beat.advances_loops == []


def test_agent_parse_path_populates_advances_loops(project):
    manager = PlotOutlineManager(project, None, _config())
    response = json.dumps({"beats": [{
        "description": "Elaraora presses Haler about the warning without an answer",
        "resolves_loops": [],
        "advances_loops": ["OL001"],
    }]})

    beats = manager._extract_beats_json(response)

    assert beats is not None
    assert beats[0].advances_loops == ["OL001"]


def test_cli_parse_path_populates_advances_loops(project):
    from novel_agent.cli.commands.plot import _assign_new_beat_ids
    from novel_agent.memory.entities import PlotOutline as MemoryPlotOutline

    beat_dicts = [{"description": "She traces the export log",
                   "advances_loops": ["OL002"]}]
    new_beats = _assign_new_beat_ids(MemoryPlotOutline(), beat_dicts)

    assert new_beats[0].advances_loops == ["OL002"]


# ---------------------------------------------------------------------------
# Extractor-claimed resolutions: the same judge, before anything closes
# (Phase 3, Slice 0 follow-ups; the 2026-07-11 finale sweep closed 47 unaudited)
# ---------------------------------------------------------------------------

def test_extractor_claim_confirmed_closes_with_extractor_audit_summary(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([_YES])

    result = judge_extractor_resolutions(
        llm, memory, ["OL001"], "S015", "the reveal scene", _config())

    assert result == {"claimed": ["OL001"], "judged": 1, "closed": ["OL001"],
                      "refused": [], "capped": []}
    loop = _loop(memory, "OL001")
    assert loop.status == "resolved"
    assert loop.resolved_in_scene == "S015"
    assert loop.resolution_summary == (
        "closed via extractor claim; judge: the sender is revealed on the page")


def test_extractor_claim_refused_leaves_open_with_reason(project):
    memory = MemoryManager(project)

    result = judge_extractor_resolutions(
        _ScriptedLLM([_NO]), memory, ["OL001"], "S015", "prose", _config())

    assert result["closed"] == []
    assert result["refused"] == [
        {"loop": "OL001", "reason": "the scene only mentions the tip"}]
    assert _loop(memory, "OL001").status == "open"


def test_extractor_judge_failure_leaves_loop_open(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([RuntimeError("backend down"), RuntimeError("still down")])

    result = judge_extractor_resolutions(
        llm, memory, ["OL001"], "S015", "prose", _config())

    assert result["judged"] == 1 and result["closed"] == []
    assert result["refused"] == [{"loop": "OL001", "reason": "judge unavailable"}]
    assert _loop(memory, "OL001").status == "open"


def test_extractor_claims_normalized_like_beat_claims(project):
    memory = MemoryManager(project)
    llm = _ScriptedLLM([_YES])

    result = judge_extractor_resolutions(
        llm, memory,
        ["OL001: Who sent the anonymous tip?", "OL77_phantom_label"],
        "S015", "prose", _config())

    # Colon-suffixed lines normalize to the bare ID; phantoms never reach the judge.
    assert result["closed"] == ["OL001"]
    assert result["judged"] == 1
    assert len(llm.prompts) == 1


def test_extractor_cap_bounds_the_judged_count(project, caplog):
    memory = MemoryManager(project)
    for i in range(3, 10):
        memory.add_open_loop(OpenLoop(id=f"OL{i:03d}", description=f"question {i}"))
    claims = [f"OL{i:03d}" for i in range(1, 8)]
    llm = _ScriptedLLM([_YES] * 5)

    with caplog.at_level("WARNING"):
        result = judge_extractor_resolutions(
            llm, memory, claims, "S015", "prose", _config())

    assert result["judged"] == 5           # the default cap
    assert result["capped"] == ["OL006", "OL007"]
    assert len(llm.prompts) == 5
    # The warning names the ignored claims.
    assert any("OL006, OL007" in r.message for r in caplog.records)
    assert _loop(memory, "OL006").status == "open"


def test_extractor_cap_is_configurable_and_disableable(project):
    memory = MemoryManager(project)
    memory.add_open_loop(OpenLoop(id="OL003", description="question 3"))
    llm = _ScriptedLLM([_YES, _YES, _YES])

    result = judge_extractor_resolutions(
        llm, memory, ["OL001", "OL002", "OL003"], "S015", "prose",
        _config(**{"coherence.extractor_resolutions_judged_cap": None}))

    assert result["judged"] == 3 and result["capped"] == []


def test_extractor_no_claims_returns_none(project):
    memory = MemoryManager(project)
    assert judge_extractor_resolutions(
        _ScriptedLLM([]), memory, [], "S015", "prose", _config()) is None


def test_extractor_judging_never_raises(project):
    class _BrokenLedger:
        def load_open_loops(self):
            raise RuntimeError("ledger unreadable")

    result = judge_extractor_resolutions(
        _ScriptedLLM([]), _BrokenLedger(), ["OL001"], "S015", "prose", _config())

    # Ledger unreadable: nothing judged, nothing closed, no exception.
    assert result["judged"] == 0 and result["closed"] == []


class _ExtractorShim:
    """Borrow the real StoryAgent extractor-judging hook over minimal state."""

    _judge_extractor_resolutions = StoryAgent._judge_extractor_resolutions

    def __init__(self, project_dir, config, llm):
        self.config = config
        self.llm = llm
        self.memory = MemoryManager(project_dir)


def test_agent_hook_strips_claims_and_closes_judged_yes(project):
    shim = _ExtractorShim(project, _config(), _ScriptedLLM([_YES]))
    facts = {"open_loops_resolved": ["OL001"], "character_updates": []}

    new_facts, result = shim._judge_extractor_resolutions(facts, "S015", "prose")

    # EntityUpdater's unjudged path never sees the claims.
    assert new_facts["open_loops_resolved"] == []
    assert new_facts["character_updates"] == []
    assert result["closed"] == ["OL001"]
    assert _loop(shim.memory, "OL001").status == "resolved"


def test_agent_hook_gate_off_restores_unjudged_behavior(project):
    llm = _ScriptedLLM([])
    shim = _ExtractorShim(project, _config(**{"coherence.loop_closure": False}), llm)
    facts = {"open_loops_resolved": ["OL001", "OL002"]}

    new_facts, result = shim._judge_extractor_resolutions(facts, "S015", "prose")

    # Facts pass through untouched (the old unjudged path stays exact for A/B)
    # and the judge is never consulted.
    assert new_facts is facts
    assert new_facts["open_loops_resolved"] == ["OL001", "OL002"]
    assert result is None
    assert llm.prompts == []


def test_gate_off_unjudged_path_still_sweeps(project):
    # The A/B promise, end to end: with the gate off the extractor claims flow
    # into EntityUpdater and close unjudged, exactly the old behavior.
    from novel_agent.agent.entity_updater import EntityUpdater

    config = _config(**{"coherence.loop_closure": False})
    memory = MemoryManager(project)
    shim = _ExtractorShim(project, config, _ScriptedLLM([]))
    facts = {"open_loops_resolved": ["OL001"]}
    facts, _ = shim._judge_extractor_resolutions(facts, "S015", "prose")

    stats = EntityUpdater(memory, config).apply_updates(facts, tick=15, scene_id="S015")

    assert stats["loops_resolved"] == 1
    loop = _loop(memory, "OL001")
    assert loop.status == "resolved"
    assert loop.resolution_summary == "Resolved in scene S015"


def test_agent_hook_no_claims_passthrough(project):
    llm = _ScriptedLLM([])
    shim = _ExtractorShim(project, _config(), llm)
    facts = {"open_loops_resolved": []}

    new_facts, result = shim._judge_extractor_resolutions(facts, "S015", "prose")

    assert new_facts is facts and result is None
    assert llm.prompts == []


# ---------------------------------------------------------------------------
# Finale expiry: honest end-of-story accounting (Phase 3, Slice 0 follow-ups)
# ---------------------------------------------------------------------------

def test_expiry_marks_open_loops_expired_with_the_summary(project):
    memory = MemoryManager(project)

    result = expire_open_loops_at_finale(memory, "S015")

    assert result["expired"] == ["OL001", "OL002"]
    for loop_id in ("OL001", "OL002"):
        loop = _loop(memory, loop_id)
        assert loop.status == "expired"
        assert loop.resolution_summary == "left open at story end"
        assert loop.resolved_in_scene == "S015"


def test_expiry_leaves_already_resolved_loops_untouched(project):
    memory = MemoryManager(project)
    memory.resolve_open_loop("OL001", "S014", "answered on the page")

    result = expire_open_loops_at_finale(memory, "S015")

    assert result["expired"] == ["OL002"]
    loop = _loop(memory, "OL001")
    assert loop.status == "resolved"
    assert loop.resolved_in_scene == "S014"
    assert loop.resolution_summary == "answered on the page"


def test_expiry_dangling_threads_counts_high_and_critical_only(project):
    memory = MemoryManager(project)
    memory.add_open_loop(OpenLoop(id="OL003", description="q3", importance="high"))
    memory.add_open_loop(OpenLoop(id="OL004", description="q4", importance="critical"))
    memory.add_open_loop(OpenLoop(id="OL005", description="q5", importance="low"))

    result = expire_open_loops_at_finale(memory, "S015")

    # OL001/OL002 are medium (the fixture default); only high and critical count.
    assert len(result["expired"]) == 5
    assert result["dangling_threads"] == 2


def test_expired_excluded_from_open_queries_and_planner_context(project):
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner

    memory = MemoryManager(project)
    expire_open_loops_at_finale(memory, "S015")
    memory.add_open_loop(OpenLoop(id="OL003", description="a fresh question"))

    # "expired" never leaks into "open" queries...
    assert [l.id for l in memory.get_open_loops(status="open")] == ["OL003"]
    # ...but stays queryable as its own terminal status.
    assert {l.id for l in memory.get_open_loops(status="expired")} == {"OL001", "OL002"}

    # The planner's loop feed (stage 2 semantic context) sees open loops only.
    class _PlannerShim:
        _open_loops = MultiStagePlanner._open_loops

        def __init__(self, mem):
            self.memory = mem

    assert [l.id for l in _PlannerShim(memory)._open_loops()] == ["OL003"]


def test_expiry_never_raises(project):
    class _BrokenLedger:
        def load_open_loops(self):
            raise RuntimeError("ledger unreadable")

    assert expire_open_loops_at_finale(_BrokenLedger(), "S015") is None


class _ExpiryShim:
    """Borrow the real StoryAgent expiry hook over minimal state."""

    _expire_finale_loops = StoryAgent._expire_finale_loops

    def __init__(self, project_dir, config):
        self.config = config
        self.memory = MemoryManager(project_dir)


def test_agent_expiry_hook_expires_and_reports(project):
    shim = _ExpiryShim(project, _config())

    result = shim._expire_finale_loops("S015")

    assert result["expired"] == ["OL001", "OL002"]
    assert _loop(shim.memory, "OL001").status == "expired"


def test_agent_expiry_hook_gate_off_leaves_loops_open(project):
    shim = _ExpiryShim(project, _config(**{"coherence.loop_closure": False}))

    assert shim._expire_finale_loops("S015") is None
    assert _loop(shim.memory, "OL001").status == "open"
    assert _loop(shim.memory, "OL002").status == "open"


def test_expiry_runs_only_on_the_finale_tick():
    # The step 11.7 guard is the sacred-finale detection helper: mid-story and
    # overtime ticks never expire anything.
    from novel_agent.agent.finale import is_finale_tick

    config = _config(**{
        "generation.use_plot_first": True,
        "coherence.target_story_length": 15,
    })
    assert is_finale_tick(15, config) is True
    assert is_finale_tick(9, config) is False
    assert is_finale_tick(16, config) is False
