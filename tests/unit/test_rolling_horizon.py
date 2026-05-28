"""Phase 2 rolling horizon: pending beats are revisable/abandonable and
re-derived from current canon, never reusing IDs or stranding the story."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Character
from novel_agent.plot.manager import PlotOutlineManager
from novel_agent.plot.entities import PlotBeat, PlotOutline


class _FakeLLM:
    """Returns a canned beats payload, or raises if `fail` is set."""

    def __init__(self, beats=None, fail=False):
        self._beats = beats if beats is not None else [{"description": "fresh beat"}]
        self.fail = fail
        self.calls = 0

    def generate(self, prompt, max_tokens=1000):
        self.calls += 1
        if self.fail:
            raise RuntimeError("llm down")
        return json.dumps({"beats": self._beats})


def _project_with_character():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 3, "novel_name": "N"}))
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Joran", family_name="Vell",
                               role="protagonist", description="lead"))
    return d, mm


@pytest.fixture
def project():
    d, _ = _project_with_character()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _seed_outline(mgr, beats):
    outline = PlotOutline(beats=beats, created_at=PlotOutline.now_iso(),
                          last_updated=PlotOutline.now_iso())
    mgr.save_outline(outline)


def test_revise_abandons_pending_keeps_completed(project):
    mgr = PlotOutlineManager(project, _FakeLLM(beats=[{"description": "react to scene"}]))
    _seed_outline(mgr, [
        PlotBeat(id="PB001", description="done", status="completed"),
        PlotBeat(id="PB002", description="stale", status="pending"),
        PlotBeat(id="PB003", description="also stale", status="pending"),
    ])

    result = mgr.revise_horizon(reason="diverged", current_tick=3, count=2)

    assert set(result["abandoned"]) == {"PB002", "PB003"}
    assert len(result["generated"]) == 1

    outline = mgr.load_outline()
    by_id = {b.id: b for b in outline.beats}
    assert by_id["PB001"].status == "completed"          # untouched
    assert by_id["PB002"].status == "abandoned"
    assert by_id["PB002"].abandoned_reason == "diverged"
    assert by_id["PB002"].revised_at_tick == 3
    # A fresh pending beat now leads the horizon, with a non-colliding ID.
    new_id = result["generated"][0]
    assert new_id not in {"PB001", "PB002", "PB003"}
    assert by_id[new_id].status == "pending"
    assert mgr.get_next_beat().id == new_id


def test_generation_failure_propagates_and_horizon_intact(project):
    # The manager abandons only *after* successful generation, so an LLM failure
    # propagates with the pending horizon untouched (the agent layer swallows it).
    mgr = PlotOutlineManager(project, _FakeLLM(fail=True))
    _seed_outline(mgr, [PlotBeat(id="PB002", description="stale", status="pending")])

    with pytest.raises(RuntimeError):
        mgr.revise_horizon(reason="diverged", current_tick=3)

    assert mgr.load_outline().beats[0].status == "pending"


def test_agent_revise_horizon_swallows_failure(project):
    # StoryAgent._revise_horizon must never let a revision failure kill the tick.
    from novel_agent.agent.agent import StoryAgent
    from novel_agent.configs.config import Config

    mgr = PlotOutlineManager(project, _FakeLLM(fail=True))
    _seed_outline(mgr, [PlotBeat(id="PB002", description="stale", status="pending")])

    class _Shim:
        config = Config()
        plot_manager = mgr

    result = StoryAgent._revise_horizon(_Shim(), reason="diverged", tick=3)
    assert result is None
    assert mgr.load_outline().beats[0].status == "pending"


def test_empty_generation_does_not_abandon(project):
    mgr = PlotOutlineManager(project, _FakeLLM(beats=[]))
    _seed_outline(mgr, [PlotBeat(id="PB002", description="stale", status="pending")])

    result = mgr.revise_horizon(reason="diverged")

    assert result == {"abandoned": [], "generated": []}
    assert mgr.load_outline().beats[0].status == "pending"


def test_cli_manager_reads_agent_written_outline(project):
    # The agent (plot.manager) and the CLI (memory.plot_outline) share
    # plot_outline.json and both parse via cls(**data); a beat carrying the new
    # rolling-horizon fields must not break the CLI's `novel plot status`.
    from novel_agent.memory.plot_outline import PlotOutlineManager as CliManager

    mgr = PlotOutlineManager(project, _FakeLLM(beats=[{"description": "react"}]))
    _seed_outline(mgr, [PlotBeat(id="PB001", description="stale", status="pending")])
    mgr.revise_horizon(reason="diverged", current_tick=3, count=1)

    cli_outline = CliManager(project).load_outline()  # must not raise
    statuses = {b.id: b.status for b in cli_outline.beats}
    assert statuses["PB001"] == "abandoned"


def test_new_fields_round_trip(project):
    mgr = PlotOutlineManager(project, _FakeLLM())
    beat = PlotBeat(id="PB001", description="x", status="abandoned",
                    abandoned_reason="diverged", revised_at_tick=4,
                    verification_score=0.42, verification_method="semantic")
    _seed_outline(mgr, [beat])

    reloaded = mgr.load_outline().beats[0]
    assert reloaded.abandoned_reason == "diverged"
    assert reloaded.revised_at_tick == 4
    assert reloaded.verification_score == 0.42
    assert reloaded.verification_method == "semantic"
