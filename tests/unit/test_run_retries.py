"""`novel run --retries`: a failed tick is retried before the run gives up.

CLI-agent backends (gemini-cli / claude-cli) occasionally time out on a heavy
planner call, and the same tick usually succeeds on a fresh attempt. The run loop
retries up to ``--retries`` times before stopping, so one transient failure no
longer ends a multi-tick run.
"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import novel_agent.cli.main as cli_main
import novel_agent.memory.checkpoint as cli_checkpoint

runner = CliRunner()


class _FakeConfig:
    def get(self, key, default=None):
        return default


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text(json.dumps({"current_tick": 0, "novel_name": "N"}))

    # Stub out every heavy collaborator the run loop constructs; the only behavior
    # under test is the retry control flow around agent.tick().
    for name in [
        "initialize_llm", "ToolRegistry", "MemoryManager", "VectorStore",
        "NameGeneratorTool", "MemorySearchTool", "CharacterGenerateTool",
        "LocationGenerateTool", "RelationshipCreateTool", "RelationshipUpdateTool",
        "RelationshipQueryTool", "FactionGenerateTool", "RecentProjects",
    ]:
        monkeypatch.setattr(cli_main, name, MagicMock())
    monkeypatch.setattr(cli_main, "find_project_dir", lambda p=None: str(tmp_path))
    monkeypatch.setattr(cli_main, "load_project_state",
                        lambda d: {"current_tick": 0, "novel_name": "N", "story_foundation": {}})
    monkeypatch.setattr(cli_main, "get_project_config", lambda d: _FakeConfig())
    # run() imports these locally from the checkpoint module at call time.
    monkeypatch.setattr(cli_checkpoint, "list_checkpoints", lambda d: [])
    return tmp_path


def _install_agent(monkeypatch, tick_side_effect):
    agent = MagicMock()
    agent.tick.side_effect = tick_side_effect
    factory = MagicMock(return_value=agent)
    monkeypatch.setattr(cli_main, "StoryAgent", factory)
    return agent


def test_transient_failure_is_retried_and_run_continues(project, monkeypatch):
    # First attempt times out, the retry succeeds.
    ok = {"scene_file": "scenes/scene_000.md", "word_count": 100}
    agent = _install_agent(monkeypatch, [TimeoutError("Gemini CLI timed out after 300s"), ok])

    result = runner.invoke(cli_main.app, ["run", "--n", "1", "--retries", "1",
                                          "--checkpoint-interval", "0"])

    assert result.exit_code == 0
    assert agent.tick.call_count == 2          # failed once, retried once
    assert "Retrying" in result.output
    assert "Completed 1/1 ticks" in result.output


def test_run_stops_after_retries_exhausted(project, monkeypatch):
    agent = _install_agent(monkeypatch, TimeoutError("boom"))  # always fails

    result = runner.invoke(cli_main.app, ["run", "--n", "3", "--retries", "1",
                                          "--checkpoint-interval", "0"])

    assert result.exit_code == 0
    assert agent.tick.call_count == 2          # 1 attempt + 1 retry, then give up
    assert "Tick failed after 2 attempts" in result.output
    assert "Stopping after 0 successful ticks" in result.output
    assert "Completed 0/3 ticks" in result.output


def test_retries_zero_preserves_old_behavior(project, monkeypatch):
    agent = _install_agent(monkeypatch, TimeoutError("boom"))

    result = runner.invoke(cli_main.app, ["run", "--n", "2", "--retries", "0",
                                          "--checkpoint-interval", "0"])

    assert result.exit_code == 0
    assert agent.tick.call_count == 1          # no retry
    assert "Stopping after 0 successful ticks" in result.output
