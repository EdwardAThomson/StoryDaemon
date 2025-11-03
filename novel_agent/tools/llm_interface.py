"""LLM interface for StoryDaemon.

Provides a simple interface to GPT-5 via Codex CLI.
Can be extended to support direct API calls if needed.
"""
from typing import Optional
from .codex_interface import CodexInterface


# Global Codex interface instance
_codex_interface: Optional[CodexInterface] = None


def initialize_llm(codex_bin: str = "codex"):
    """Initialize the LLM interface.
    
    Args:
        codex_bin: Path to Codex CLI binary
        
    Raises:
        RuntimeError: If Codex CLI is not available
    """
    global _codex_interface
    _codex_interface = CodexInterface(codex_bin)


def send_prompt(prompt: str, max_tokens: int = 2000) -> str:
    """Send prompt to GPT-5 via Codex CLI.
    
    Args:
        prompt: The prompt to send
        max_tokens: Maximum tokens to generate
        
    Returns:
        Generated text from GPT-5
        
    Raises:
        RuntimeError: If LLM interface not initialized or generation fails
    """
    if _codex_interface is None:
        initialize_llm()
    
    return _codex_interface.generate(prompt, max_tokens=max_tokens)


def send_prompt_with_retry(
    prompt: str,
    max_tokens: int = 2000,
    max_retries: int = 3
) -> str:
    """Send prompt with automatic retry on failure.
    
    Args:
        prompt: The prompt to send
        max_tokens: Maximum tokens to generate
        max_retries: Maximum retry attempts
        
    Returns:
        Generated text from GPT-5
        
    Raises:
        RuntimeError: If all retry attempts fail
    """
    if _codex_interface is None:
        initialize_llm()
    
    return _codex_interface.generate_with_retry(
        prompt,
        max_tokens=max_tokens,
        max_retries=max_retries
    )


def is_initialized() -> bool:
    """Check if LLM interface is initialized.
    
    Returns:
        True if initialized, False otherwise
    """
    return _codex_interface is not None
