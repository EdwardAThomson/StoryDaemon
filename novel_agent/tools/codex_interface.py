"""Wrapper for calling Codex CLI from Python.

Provides subprocess-based interface to Codex CLI for zero-cost access to GPT-5.
"""
import os
import subprocess
import shutil
import tempfile
from typing import Optional

from .agent_cwd import neutral_cwd

# Safety posture for `codex exec`. StoryDaemon only needs codex to *generate text*,
# so it needs zero write/exec access — a read-only sandbox that never prompts is
# both non-interactive and safe. This replaces the old
# `--dangerously-bypass-approvals-and-sandbox` (an unsandboxed agent pointed at the
# repo). Flag names target codex-cli ~0.118; adjust here if a future version renames them.
CODEX_SANDBOX = "read-only"
CODEX_APPROVAL = "never"


class CodexInterface:
    """Interface for calling Codex CLI to access GPT-5."""
    
    def __init__(self, codex_bin: str = "codex", default_timeout: int = 300):
        """Initialize Codex interface.

        Args:
            codex_bin: Path to codex binary (default: 'codex' in PATH)
            default_timeout: Per-call timeout in seconds for `codex exec`.

        Raises:
            RuntimeError: If Codex CLI is not installed or not in PATH
        """
        self.codex_bin = codex_bin
        self.default_timeout = default_timeout
        self._verify_codex_installed()
    
    def _verify_codex_installed(self):
        """Check if Codex CLI is installed and accessible.
        
        Raises:
            RuntimeError: If Codex CLI cannot be found
        """
        if not shutil.which(self.codex_bin):
            raise RuntimeError(
                f"Codex CLI not found at '{self.codex_bin}'. "
                "Install with: npm install -g @openai/codex-cli\n"
                "Then authenticate with: codex auth"
            )
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 2000,
        timeout: Optional[int] = None
    ) -> str:
        """Generate text using Codex CLI.
        
        Args:
            prompt: The prompt to send to Codex
            max_tokens: Maximum tokens to generate (default: 2000)
            timeout: Timeout in seconds (default: 120)
            
        Returns:
            Generated text from GPT-5
            
        Raises:
            RuntimeError: If Codex CLI returns an error
            subprocess.TimeoutExpired: If generation times out
        """
        eff_timeout = timeout or self.default_timeout
        msg_file = None
        try:
            # codex writes ONLY the final assistant message to this file, so we don't
            # have to dig the answer out of the agent's verbose exec log on stdout.
            fd, msg_file = tempfile.mkstemp(prefix="codex-msg-", suffix=".txt")
            os.close(fd)
            # Non-interactive text generation: read-only sandbox + never-prompt. Run
            # from a neutral cwd so codex stays a text generator, not a repo agent.
            result = subprocess.run(
                [
                    self.codex_bin,
                    'exec',
                    '--sandbox', CODEX_SANDBOX,
                    '--ask-for-approval', CODEX_APPROVAL,
                    '--skip-git-repo-check',
                    '--output-last-message', msg_file,
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=eff_timeout,
                check=True,
                cwd=neutral_cwd(),
            )
            try:
                with open(msg_file, 'r', encoding='utf-8') as f:
                    last_message = f.read().strip()
            except OSError:
                last_message = ""
            return last_message or result.stdout.strip()

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else "Unknown error"
            raise RuntimeError(f"Codex CLI error: {error_msg}")

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Codex CLI timed out after {eff_timeout}s. "
                "Try increasing timeout or simplifying the prompt."
            )
        finally:
            if msg_file:
                try:
                    os.unlink(msg_file)
                except OSError:
                    pass
    
    def generate_with_retry(
        self,
        prompt: str,
        max_tokens: int = 2000,
        timeout: Optional[int] = None,
        max_retries: int = 3
    ) -> str:
        """Generate text with automatic retry on failure.
        
        Args:
            prompt: The prompt to send to Codex
            max_tokens: Maximum tokens to generate
            timeout: Timeout in seconds
            max_retries: Maximum number of retry attempts
            
        Returns:
            Generated text from GPT-5
            
        Raises:
            RuntimeError: If all retry attempts fail
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return self.generate(prompt, max_tokens, timeout)
            except RuntimeError as e:
                last_error = e
                if attempt < max_retries - 1:
                    # Could add exponential backoff here if needed
                    continue
        
        raise RuntimeError(
            f"Codex CLI failed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )
