"""Compatibility shim over the llm-backends package; will eventually be dropped.

``ClaudeCliInterface`` now lives in the shared `llm-backends` package (see
docs/LLM_BACKENDS_INVENTORY.md section 7.4, step 2), which adds the analyzer's
hardening: ANTHROPIC_API_KEY / CLAUDE_API_KEY are stripped from the subprocess
env by default (assumption A4) so `claude -p` bills the subscription login,
and the model heuristic accepts "fable". This module aliases itself to
``llm_backends.claude_cli_interface`` in ``sys.modules`` so every name under
the old import path keeps working. New code should import from
``llm_backends``.
"""
import sys

from llm_backends import claude_cli_interface as _impl

sys.modules[__name__] = _impl
