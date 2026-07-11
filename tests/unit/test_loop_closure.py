"""Judged loop closure and creation hygiene (Phase 3, Slice 0 of the interleaving design).

Policy under test (docs/THREAD_INTERLEAVING_DESIGN.md Slice 0, evidence in
docs/progress_report_20260710.md): beat completion NOMINATES the loops its
author claimed it resolves, a focused one-loop, one-scene judge CONFIRMS each
claim, and every closure carries an auditable summary. Claims are sanitized at
authoring (phantom loop IDs dropped) in both beat-generation paths. The
coherence.loop_closure gate defaults False for its first validation run.
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
    judge_loop_resolution,
    sanitize_beat_loop_claims,
)
from novel_agent.configs.config import Config
from novel_agent.memory.entities import OpenLoop
from novel_agent.memory.manager import MemoryManager
from novel_agent.plot.entities import PlotBeat, PlotOutline
from novel_agent.plot.manager import PlotOutlineManager


def _config(**overrides):
    """Gate-on config unless a test overrides it (the default gate is False)."""
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
                      "judged": 1, "closed": ["OL001"]}
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


def test_gate_defaults_off():
    assert Config().get("coherence.loop_closure") is False
    assert Config().get("coherence.loop_dedup") is True


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
