"""Wrapper for calling Gemini CLI from Python.

Provides a subprocess-based interface to the `gemini` CLI so StoryDaemon can
use Gemini models via the local tool, similar to the Codex CLI backend.
"""

import shutil
import subprocess
from typing import Optional

from .agent_cwd import neutral_cwd


class GeminiCliInterface:
    """Interface for calling Gemini CLI to access Gemini models."""

    def __init__(self, model: str = "gemini-3-flash-preview", gemini_bin: str = "gemini",
                 default_timeout: int = 300):
        """Initialize Gemini CLI interface.

        Args:
            model: Gemini model identifier. Use a current Gemini 3 name —
                "gemini-3-flash-preview" (fast) or "gemini-3-pro-preview".
                Note: the bare "gemini-3-flash"/"gemini-3-pro" names are NOT valid.
            gemini_bin: Path to `gemini` binary (default: "gemini" in PATH).

        Raises:
            RuntimeError: If Gemini CLI is not installed or not in PATH.
        """
        self.model = model
        self.gemini_bin = gemini_bin
        self.default_timeout = default_timeout
        self._verify_gemini_installed()

    def _verify_gemini_installed(self) -> None:
        """Check if Gemini CLI is installed and accessible.

        Raises:
            RuntimeError: If Gemini CLI cannot be found.
        """
        if not shutil.which(self.gemini_bin):
            raise RuntimeError(
                f"Gemini CLI not found at '{self.gemini_bin}'. "
                "Install it from https://github.com/google-gemini/gemini-cli and "
                "ensure 'gemini' is on your PATH."
            )

    def generate(self, prompt: str, max_tokens: int = 2000, timeout: Optional[int] = None) -> str:  # noqa: ARG002
        """Generate text using Gemini CLI.

        Note: `max_tokens` is currently not forwarded; Gemini CLI will use its
        own defaults based on the configured model.

        Args:
            prompt: The prompt to send to Gemini.
            max_tokens: Maximum tokens to generate (not currently forwarded).
            timeout: Per-call timeout in seconds (default: self.default_timeout).

        Returns:
            Generated text from the Gemini CLI.

        Raises:
            RuntimeError: If Gemini CLI returns an error.
            subprocess.TimeoutExpired: If generation times out.
        """
        eff_timeout = timeout or self.default_timeout
        try:
            # Non-interactive call, similar to `gemini -p "..." -m <model>`
            result = subprocess.run(
                [
                    self.gemini_bin,
                    # We run from a neutral scratch dir (agent_cwd), which Gemini treats
                    # as an untrusted folder and would refuse headless; --skip-trust
                    # opts out of the trusted-folder gate for this non-interactive call.
                    "--skip-trust",
                    "-p",
                    prompt,
                    "-m",
                    self.model,
                ],
                capture_output=True,
                text=True,
                timeout=eff_timeout,
                check=True,
                # Neutral cwd: `gemini` is also a repo-aware agent; keep it isolated.
                cwd=neutral_cwd(),
            )
            return result.stdout.strip()

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else "Unknown error"
            raise RuntimeError(f"Gemini CLI error: {error_msg}") from e

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Gemini CLI timed out after {eff_timeout}s. "
                "Try increasing timeout or simplifying the prompt."
            )

    def generate_with_retry(
        self,
        prompt: str,
        max_tokens: int = 2000,
        timeout: Optional[int] = None,
        max_retries: int = 3,
    ) -> str:
        """Generate text with automatic retry on failure.

        Args:
            prompt: The prompt to send to Gemini.
            max_tokens: Maximum tokens to generate (not currently forwarded).
            timeout: Timeout in seconds.
            max_retries: Maximum number of retry attempts.

        Returns:
            Generated text from Gemini CLI.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                return self.generate(prompt, max_tokens, timeout)
            except RuntimeError as e:
                last_error = e
                if attempt < max_retries - 1:
                    continue

        raise RuntimeError(
            f"Gemini CLI failed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )
