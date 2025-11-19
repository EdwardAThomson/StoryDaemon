"""LLM interface for StoryDaemon.

Provides a backend-agnostic interface for LLM access.

Backends:
- "codex"       → Codex CLI (GPT-5 via codex exec)
- "api"         → Multi-provider API backend (OpenAI, Gemini, Claude) using
                   an ai_helper-style model registry.
- "gemini-cli"  → Gemini CLI backend using the local `gemini` binary.
- "claude-cli"  → Claude Code CLI backend using the local `claude` binary.

The API backend uses model names (e.g. "gpt-5.1", "claude-4.5",
"gemini-2.5-pro") to route to the correct provider.
"""
from typing import Optional, Union

from .codex_interface import CodexInterface
from .multi_provider_llm import MultiProviderInterface
from .gemini_cli_interface import GeminiCliInterface
from .claude_cli_interface import ClaudeCliInterface


LLMClient = Union[CodexInterface, MultiProviderInterface, GeminiCliInterface, ClaudeCliInterface]


# Global LLM client instance used by helper functions
_llm_client: Optional[LLMClient] = None


def initialize_llm(
    backend: str = "codex",
    codex_bin: str = "codex",
    model: str = "gpt-5.1",
) -> LLMClient:
    """Initialize the LLM client for the given backend.

    Args:
        backend: LLM backend identifier ("codex", "api", "gemini-cli", or "claude-cli").
        codex_bin: Path to Codex CLI binary (for backend="codex").
        model: Model identifier for API-like backends (for backend="api" or "gemini-cli").

    Returns:
        An initialized LLM client instance.

    Raises:
        RuntimeError: If the requested backend cannot be initialized.
    """
    global _llm_client

    backend_normalized = backend.lower().strip()

    if backend_normalized == "codex":
        _llm_client = CodexInterface(codex_bin)
    elif backend_normalized in {"api", "openai"}:
        # "openai" kept for backward compatibility; it now means
        # "use the API backend" with the configured model.
        _llm_client = MultiProviderInterface(model=model)
    elif backend_normalized in {"gemini-cli", "gemini"}:
        _llm_client = GeminiCliInterface(model=model)
    elif backend_normalized in {"claude-cli", "claude"}:
        _llm_client = ClaudeCliInterface()
    else:
        raise RuntimeError(
            f"Unsupported LLM backend: {backend}. Supported backends are: 'codex', 'api', 'gemini-cli', 'claude-cli'."
        )

    return _llm_client


def send_prompt(prompt: str, max_tokens: int = 2000) -> str:
    """Send a prompt using the initialized LLM client.

    Args:
        prompt: The prompt to send.
        max_tokens: Maximum tokens to generate.

    Returns:
        Generated text from the configured LLM backend.

    Raises:
        RuntimeError: If no backend is initialized or generation fails.
    """
    if _llm_client is None:
        # Default to Codex if nothing has been explicitly initialized
        initialize_llm(backend="codex")

    return _llm_client.generate(prompt, max_tokens=max_tokens)  # type: ignore[union-attr]


def send_prompt_with_retry(
    prompt: str,
    max_tokens: int = 2000,
    max_retries: int = 3,
) -> str:
    """Send prompt with automatic retry on failure.

    Args:
        prompt: The prompt to send.
        max_tokens: Maximum tokens to generate.
        max_retries: Maximum retry attempts.

    Returns:
        Generated text from the configured LLM backend.

    Raises:
        RuntimeError: If all retry attempts fail or no backend is initialized.
    """
    if _llm_client is None:
        # Default to Codex if nothing has been explicitly initialized
        initialize_llm(backend="codex")

    return _llm_client.generate_with_retry(  # type: ignore[union-attr]
        prompt,
        max_tokens=max_tokens,
        max_retries=max_retries,
    )


def is_initialized() -> bool:
    """Check if an LLM backend has been initialized.

    Returns:
        True if initialized, False otherwise.
    """
    return _llm_client is not None
