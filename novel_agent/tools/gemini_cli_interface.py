"""Compatibility shim over the llm-backends package; will eventually be dropped.

``GeminiCliInterface`` now lives in the shared `llm-backends` package (see
docs/LLM_BACKENDS_INVENTORY.md section 7.4, step 2), which adds the analyzer's
hardening: GEMINI_API_KEY / GOOGLE_API_KEY are stripped from the subprocess
env by default (assumption A4). This module aliases itself to
``llm_backends.gemini_cli_interface`` in ``sys.modules`` so every name under
the old import path keeps working. New code should import from
``llm_backends``.
"""
import sys

from llm_backends import gemini_cli_interface as _impl

sys.modules[__name__] = _impl
