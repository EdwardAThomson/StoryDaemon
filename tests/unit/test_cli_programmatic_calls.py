"""`resume()` calls `tick()` and `run()` as plain Python functions.

Declared the older Typer way (`x: int = typer.Option(10, ...)`), an argument the
caller leaves out arrives as the `OptionInfo` object itself, not its default:
`novel resume --n 2` crashed on `checkpoint_interval > 0`, and plain `novel
resume` turned on `--save-prompts` because an `OptionInfo` is truthy. Both
commands now declare options with `Annotated`, so their defaults are real values.
"""

import inspect
import json
from unittest.mock import MagicMock

import pytest
from typer.models import ParameterInfo
from typer.testing import CliRunner

import novel_agent.cli.main as cli_main
import novel_agent.memory.checkpoint as cli_checkpoint

runner = CliRunner()


class _FakeConfig:
    def get(self, key, default=None):
        return default


@pytest.mark.parametrize("command", [cli_main.tick, cli_main.run])
def test_programmatically_called_commands_have_real_defaults(command):
    # Guards the next option added to tick()/run(): a Typer marker as a Python
    # default is exactly what resume() would receive for it.
    for name, param in inspect.signature(command).parameters.items():
        assert not isinstance(param.default, ParameterInfo), (
            f"{command.__name__}({name}=...) defaults to a Typer OptionInfo; "
            f"declare it as Annotated[..., typer.Option(...)] = <default>"
        )


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text(json.dumps({"current_tick": 0, "novel_name": "N"}))
    for name in [
        "initialize_llm_with_persona", "ToolRegistry", "MemoryManager", "VectorStore",
        "NameGeneratorTool", "MemorySearchTool", "CharacterGenerateTool",
        "LocationGenerateTool", "RelationshipCreateTool", "RelationshipUpdateTool",
        "RelationshipQueryTool", "FactionGenerateTool", "FactionUpdateTool",
        "FactionQueryTool", "_show_stage_stats", "_show_story_stats",
    ]:
        monkeypatch.setattr(cli_main, name, MagicMock())
    recent = MagicMock()
    recent.get_most_recent.return_value = str(tmp_path)
    monkeypatch.setattr(cli_main, "RecentProjects", MagicMock(return_value=recent))
    monkeypatch.setattr(cli_main, "find_project_dir", lambda p=None: str(tmp_path))
    monkeypatch.setattr(cli_main, "load_project_state",
                        lambda d: {"current_tick": 0, "novel_name": "N", "story_foundation": {}})
    monkeypatch.setattr(cli_main, "get_project_config", lambda d: _FakeConfig())
    monkeypatch.setattr(cli_checkpoint, "list_checkpoints", lambda d: [])

    agent = MagicMock()
    agent.tick.return_value = {
        "plan_file": "plans/p.json", "scene_file": "scenes/scene_000.md",
        "word_count": 100, "actions_executed": 0,
    }
    factory = MagicMock(return_value=agent)
    monkeypatch.setattr(cli_main, "StoryAgent", factory)
    return factory


def test_resume_multiple_ticks_uses_run_defaults(project):
    result = runner.invoke(cli_main.app, ["resume", "--n", "2"])

    assert result.exit_code == 0, result.output
    assert "Checkpoints enabled (every 10 ticks)" in result.output
    assert "Completed 2/2 ticks" in result.output


def test_resume_single_tick_does_not_save_prompts(project):
    result = runner.invoke(cli_main.app, ["resume"])

    assert result.exit_code == 0, result.output
    assert project.call_args.kwargs["save_prompts"] is False
    assert "Saving prompts" not in result.output


def test_cli_flags_still_parse_after_annotated_declarations(project):
    result = runner.invoke(cli_main.app, ["tick", "-p", ".", "--save-prompts"])
    assert result.exit_code == 0, result.output
    assert project.call_args.kwargs["save_prompts"] is True

    result = runner.invoke(cli_main.app, ["run", "-n", "1", "--checkpoint-interval", "0"])
    assert result.exit_code == 0, result.output
    assert "Checkpoints disabled" in result.output
