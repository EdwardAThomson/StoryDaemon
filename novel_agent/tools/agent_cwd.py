"""Shared neutral working directory for CLI-agent LLM backends.

The `codex`, `claude` and `gemini` CLIs are full repo-aware *agents*, not completion
APIs: run from the StoryDaemon repo they load agent instructions (CLAUDE.md / AGENTS.md)
and the codebase and start *acting on the repo* instead of answering the prompt — they
derail and time out (proven with `claude -p`). Running them from an empty scratch
directory (no `.git`, no agent files, no source) keeps them pure text generators.

This is deliberately backend-independent: every CLI backend runs from the *same* neutral
cwd, created once per process.
"""

import tempfile
from typing import Optional

_neutral_cwd: Optional[str] = None


def neutral_cwd() -> str:
    """Return a process-wide empty scratch directory for CLI-agent subprocesses."""
    global _neutral_cwd
    if _neutral_cwd is None:
        _neutral_cwd = tempfile.mkdtemp(prefix="storydaemon-agent-")
    return _neutral_cwd
