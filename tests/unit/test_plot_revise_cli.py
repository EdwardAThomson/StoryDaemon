"""`novel plot revise`: manual rolling-horizon trigger via the CLI plot system."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.plot_outline import PlotOutlineManager
from novel_agent.memory.entities import PlotBeat, PlotOutline
import novel_agent.cli.commands.plot as plot_cli


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 4, "novel_name": "N"}))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _seed(project_dir, beats):
    mgr = PlotOutlineManager(project_dir)
    mgr.save_outline(PlotOutline(beats=beats))


def _fake_response(beats):
    return json.dumps({"beats": beats})


def test_revise_abandons_pending_and_regenerates(project, monkeypatch):
    _seed(project, [
        PlotBeat(id="PB001", description="done", status="completed"),
        PlotBeat(id="PB002", description="stale", status="pending"),
    ])
    monkeypatch.setattr(plot_cli, "send_prompt_with_retry",
                        lambda *a, **k: _fake_response([{"description": "fresh"}]))

    result = plot_cli.revise_and_regenerate_beats_cli(project, count=2, reason="diverged")

    assert result["abandoned"] == ["PB002"]
    assert len(result["beats"]) == 1

    by_id = {b.id: b for b in PlotOutlineManager(project).load_outline().beats}
    assert by_id["PB001"].status == "completed"          # untouched
    assert by_id["PB002"].status == "abandoned"
    assert by_id["PB002"].abandoned_reason == "diverged"
    assert by_id["PB002"].revised_at_tick == 4
    new_id = result["beats"][0].id
    assert new_id not in {"PB001", "PB002"}               # no ID reuse
    assert by_id[new_id].status == "pending"


def test_revise_failure_leaves_outline_untouched(project, monkeypatch):
    _seed(project, [PlotBeat(id="PB002", description="stale", status="pending")])

    def _boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(plot_cli, "send_prompt_with_retry", _boom)

    with pytest.raises(RuntimeError):
        plot_cli.revise_and_regenerate_beats_cli(project, count=2)

    # Pending beat must survive so the story still has something to execute.
    assert PlotOutlineManager(project).load_outline().beats[0].status == "pending"


def test_revise_command_registered():
    from novel_agent.cli.main import plot_app
    names = {c.name for c in plot_app.registered_commands}
    assert "revise" in names
