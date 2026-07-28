"""StoryDaemon-owned LLM initialization policy.

llm-backends 0.2.0 stopped sending a system prompt unless one is asked for
(CHANGELOG, "no system prompt unless one is asked for"): the fiction persona
StoryDaemon used to get implicitly on the api backend is now opt-in via
FICTION_ROLE. The singleton send_prompt() path has no per-call role parameter,
so the opt-in must ride initialize_llm. This wrapper is the one place that
policy lives; call sites use it instead of initialize_llm directly.

The CLI backends (codex, claude-cli, gemini-cli) have no system-prompt concept
and never carried the persona; passing role_description with them raises in
the package, hence the backend check here.
"""
from typing import Optional

from llm_backends import DEFAULT_API_MODEL, FICTION_ROLE, initialize_llm
from llm_backends.llm_interface import LLMClient


def initialize_llm_with_persona(
    backend: str = "codex",
    codex_bin: str = "codex",
    model: str = DEFAULT_API_MODEL,
    timeout: Optional[int] = None,
) -> LLMClient:
    """initialize_llm, restoring the fiction persona on the api backend."""
    is_api = backend.lower().strip() in {"api", "openai"}
    return initialize_llm(
        backend=backend,
        codex_bin=codex_bin,
        model=model,
        timeout=timeout,
        role_description=FICTION_ROLE if is_api else None,
    )
