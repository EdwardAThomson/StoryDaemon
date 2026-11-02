"""Tests for per-novel version history (novel_agent/history.py).

Real git in temporary folders, no LLM. The agent hook is exercised through
StoryAgent.tick on a stub, so the real wrapper and _record_history run.
"""
import json
import subprocess
import types
from pathlib import Path

import pytest

from novel_agent import history
from novel_agent.agent.agent import StoryAgent

pytestmark = pytest.mark.skipif(not history.git_available(), reason="git not installed")


@pytest.fixture(autouse=True)
def isolated_git(tmp_path, monkeypatch):
    """No user-level or system git config: no identity, nothing inherited."""
    empty = tmp_path / "empty_gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL", "GIT_DIR", "GIT_WORK_TREE"):
        monkeypatch.delenv(var, raising=False)


def _log(repo):
    out = subprocess.run(["git", f"--git-dir={Path(repo) / '.git'}", "log", "--format=%s%x1f%an"],
                         capture_output=True, text=True).stdout
    return [line.split("\x1f") for line in out.splitlines()]


def _novel(tmp_path, name="novel"):
    d = tmp_path / name
    (d / "memory").mkdir(parents=True)
    (d / "scenes").mkdir()
    (d / "state.json").write_text(json.dumps({"current_tick": 0}))
    return d


def _stub_agent(project_dir, normal_tick, config=None):
    agent = types.SimpleNamespace(
        state={"current_tick": 3},
        project_path=Path(project_dir),
        config=config or {},
        memory=None,
    )
    agent._normal_tick = normal_tick
    agent._first_tick = normal_tick
    agent._record_history = types.MethodType(StoryAgent._record_history, agent)
    return agent


def test_init_makes_repo_with_gitignore_and_first_commit(tmp_path):
    d = _novel(tmp_path)
    (d / "memory" / "index").mkdir()
    (d / "memory" / "index" / "chroma.bin").write_bytes(b"\x00")
    out = history.init(d)
    assert out["ok"] and out["created"] and out["commit"]
    assert history.has_repo(d)
    assert "memory/index/" in (d / ".gitignore").read_text()
    assert _log(d) == [["novel created", "StoryDaemon"]]
    tracked = subprocess.run(["git", f"--git-dir={d / '.git'}", "ls-files"],
                             capture_output=True, text=True).stdout
    assert "state.json" in tracked and "chroma.bin" not in tracked


def test_init_twice_is_a_no_op(tmp_path):
    d = _novel(tmp_path)
    history.init(d)
    again = history.init(d)
    assert again["ok"] and again["created"] is False
    assert len(_log(d)) == 1


def test_successful_tick_makes_one_commit(tmp_path):
    d = _novel(tmp_path)
    history.init(d)

    def tick():
        (d / "scenes" / "scene_003.md").write_text("prose")
        return {"tick": 3, "scene_id": "S003", "word_count": 2840,
                "entities_updated": {"loops_created": 2, "loops_resolved": 1}}

    result = StoryAgent.tick(_stub_agent(d, tick))
    assert result["history_commit"]
    subjects = [s for s, _ in _log(d)]
    assert subjects[0] == "tick 3: S003, 2,840 words | loops +2 -1"
    assert len(subjects) == 2


def test_failed_tick_commits_partial_writes_and_still_raises(tmp_path):
    d = _novel(tmp_path)
    history.init(d)

    def tick():
        (d / "memory" / "C007.json").write_text("{}")
        raise ValueError("Scene evaluation failed: ['dead character speaks']")

    with pytest.raises(ValueError, match="Scene evaluation failed"):
        StoryAgent.tick(_stub_agent(d, tick))
    assert _log(d)[0][0] == "tick 3 FAILED: Scene evaluation failed: ['dead character speaks']"


def test_failed_tick_that_wrote_nothing_makes_no_commit(tmp_path):
    d = _novel(tmp_path)
    history.init(d)

    def tick():
        raise RuntimeError("planner timed out")

    with pytest.raises(RuntimeError):
        StoryAgent.tick(_stub_agent(d, tick))
    assert len(_log(d)) == 1


def test_no_commit_when_switched_off(tmp_path):
    d = _novel(tmp_path)
    history.init(d)

    def tick():
        (d / "scenes" / "scene_003.md").write_text("prose")
        return {"tick": 3}

    result = StoryAgent.tick(_stub_agent(d, tick, config={"history.git": False}))
    assert "history_commit" not in result
    assert len(_log(d)) == 1


def test_no_commit_and_tick_succeeds_without_repo(tmp_path):
    d = _novel(tmp_path)

    def tick():
        (d / "scenes" / "scene_003.md").write_text("prose")
        return {"tick": 3}

    assert StoryAgent.tick(_stub_agent(d, tick))["tick"] == 3
    assert not history.has_repo(d)


def test_no_commit_and_tick_succeeds_without_git(tmp_path, monkeypatch):
    d = _novel(tmp_path)
    history.init(d)
    monkeypatch.setattr(history.shutil, "which", lambda name: None)

    def tick():
        (d / "scenes" / "scene_003.md").write_text("prose")
        return {"tick": 3}

    assert StoryAgent.tick(_stub_agent(d, tick))["tick"] == 3
    monkeypatch.undo()
    assert len(_log(d)) == 1


def test_never_commits_into_a_parent_repository(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    subprocess.run(["git", "init", "-q", str(parent)], check=True)
    d = _novel(parent, "novel")  # inside the parent repo, no .git of its own

    assert history.commit(d, "should not happen")["ok"] is False
    assert history.tag(d, "checkpoint_tick_010")["ok"] is False
    assert history.commit_tick(d, 3, {"tick": 3}) is None
    assert history.commit_failed(d, 3, RuntimeError("x")) is None
    head = subprocess.run(["git", "-C", str(parent), "rev-parse", "--verify", "HEAD"],
                          capture_output=True, text=True)
    assert head.returncode != 0  # the parent still has no commits
    staged = subprocess.run(["git", "-C", str(parent), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True).stdout
    assert staged == ""


def test_commits_ignore_user_signing_config(tmp_path, monkeypatch):
    cfg = tmp_path / "signing_gitconfig"
    cfg.write_text("[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    d = _novel(tmp_path)
    assert history.init(d)["commit"]
    (d / "scenes" / "scene_000.md").write_text("prose")
    assert history.commit(d, "tick 0")["commit"]


def test_project_config_can_switch_history_off(tmp_path):
    d = _novel(tmp_path)
    history.init(d)
    (d / "config.yaml").write_text("history:\n  git: false\n")
    (d / "scenes" / "scene_000.md").write_text("prose")
    assert history.commit(d, "x")["ok"] is False
    assert len(_log(d)) == 1


def test_tick_message_reads_scene_and_status():
    class Rec:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    scene = Rec(title="The Vent", pov_character_id="C000", location_id="L005")
    moren = Rec(id="C001", type="character",
                metadata={"status": {"status": "dead", "tick": 15, "scene_id": "S015"}})
    elor = Rec(id="C000", type="character", metadata={})
    vent = Rec(id="L005", type="location",
               metadata={"status": {"status": "destroyed", "tick": 9}})
    chars = {"C000": elor, "C001": moren}
    memory = types.SimpleNamespace(
        load_scene=lambda sid: scene,
        list_characters=lambda: list(chars),
        load_character=chars.get,
        list_locations=lambda: ["L005"],
        load_location=lambda lid: vent,
    )
    msg = history.tick_message(15, {"scene_id": "S015", "word_count": 2840,
                                    "entities_updated": {"loops_created": 0,
                                                         "loops_resolved": 1}}, memory)
    assert msg == 'tick 15: S015 "The Vent" (pov C000, L005), 2,840 words | C001 died | loops +0 -1'


def test_failed_message_is_one_line_and_bounded():
    msg = history.failed_message(4, RuntimeError("line one\nline two " + "x" * 300))
    assert "\n" not in msg and msg.startswith("tick 4 FAILED: line one line two")
    assert len(msg) <= len("tick 4 FAILED: ") + 160


def test_recent_lists_newest_first(tmp_path):
    d = _novel(tmp_path)
    history.init(d)
    (d / "scenes" / "scene_000.md").write_text("prose")
    history.commit(d, "tick 0: S000")
    rows = history.recent(d, 5)
    assert [r["subject"] for r in rows] == ["tick 0: S000", "novel created"]


def test_new_project_is_a_repository(tmp_path):
    from novel_agent.cli.project import create_novel_project
    project_dir = Path(create_novel_project("history-test", str(tmp_path)))
    assert history.has_repo(project_dir)
    assert _log(project_dir) == [["novel created", "StoryDaemon"]]


def test_enable_on_existing_novel(tmp_path, capsys):
    from novel_agent.cli.commands.history import enable_history_cmd
    d = _novel(tmp_path)
    (d / "state.json").write_text(json.dumps({"current_tick": 23}))
    assert enable_history_cmd(d)
    assert _log(d)[0][0] == "history enabled at tick 23"
    assert enable_history_cmd(d)  # second run is a no-op
    assert len(_log(d)) == 1
    assert "already on" in capsys.readouterr().out


def test_checkpoint_is_tagged_and_restore_is_committed(tmp_path):
    from novel_agent.memory.checkpoint import create_checkpoint, restore_checkpoint
    d = _novel(tmp_path)
    history.init(d)
    create_checkpoint(d, 10, "test")
    tags = subprocess.run(["git", f"--git-dir={d / '.git'}", "tag"],
                          capture_output=True, text=True).stdout.split()
    assert "checkpoint_tick_010" in tags
    (d / "scenes" / "scene_010.md").write_text("later prose")
    history.commit(d, "tick 10: S010")
    restore_checkpoint(d, "checkpoint_tick_010", backup_current=False)
    assert _log(d)[0][0] == "restored checkpoint_tick_010"
