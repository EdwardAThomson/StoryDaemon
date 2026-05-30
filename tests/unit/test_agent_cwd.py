"""Tests for shared neutral-cwd isolation across the CLI-agent backends."""
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

from novel_agent.tools.agent_cwd import neutral_cwd


def test_neutral_cwd_idempotent_and_empty():
    d = neutral_cwd()
    assert d == neutral_cwd()  # same dir on every call (process-wide)
    p = Path(d)
    assert p.is_dir()
    # The whole point: no repo/agent files for the CLI agent to latch onto.
    assert not (p / ".git").exists()
    assert not (p / "CLAUDE.md").exists()
    assert not (p / "AGENTS.md").exists()


class _Cap:
    cmd = None
    cwd = None


def _patch(monkeypatch, *, stdout="", last_message=None):
    """Patch subprocess.run + shutil.which; capture the command and cwd."""
    cap = _Cap()

    def fake_run(cmd, **kw):
        cap.cmd = cmd
        cap.cwd = kw.get("cwd")
        # Emulate codex's --output-last-message by writing the clean final text.
        if last_message is not None and "--output-last-message" in cmd:
            path = cmd[cmd.index("--output-last-message") + 1]
            with open(path, "w", encoding="utf-8") as f:
                f.write(last_message)
        return SimpleNamespace(stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")
    return cap


def test_codex_safe_flags_neutral_cwd_and_clean_output(monkeypatch):
    cap = _patch(monkeypatch, stdout="VERBOSE EXEC LOG", last_message="clean final prose")
    from novel_agent.tools.codex_interface import CodexInterface

    out = CodexInterface().generate("write a sentence")

    assert cap.cwd == neutral_cwd()
    # The dangerous flag is gone; replaced by read-only + never-prompt.
    assert "--dangerously-bypass-approvals-and-sandbox" not in cap.cmd
    assert cap.cmd[cap.cmd.index("--sandbox") + 1] == "read-only"
    assert cap.cmd[cap.cmd.index("--ask-for-approval") + 1] == "never"
    # Output comes from the final-message file, not the polluted exec log.
    assert out == "clean final prose"


def test_claude_cli_uses_neutral_cwd(monkeypatch):
    cap = _patch(monkeypatch, stdout='{"result": "ok"}')
    from novel_agent.tools.claude_cli_interface import ClaudeCliInterface

    out = ClaudeCliInterface().generate("hi")

    assert cap.cwd == neutral_cwd()
    assert out == "ok"


def test_gemini_cli_uses_neutral_cwd(monkeypatch):
    cap = _patch(monkeypatch, stdout="some prose")
    from novel_agent.tools.gemini_cli_interface import GeminiCliInterface

    out = GeminiCliInterface().generate("hi")

    assert cap.cwd == neutral_cwd()
    assert out == "some prose"
