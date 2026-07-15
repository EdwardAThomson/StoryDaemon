"""Compatibility shim over the llm-backends package; will eventually be dropped.

``CodexInterface`` now lives in the shared `llm-backends` package (see
docs/LLM_BACKENDS_INVENTORY.md section 7.4, step 2), which adds the analyzer's
hardening: OPENAI_API_KEY is stripped from the subprocess env by default
(assumption A4, subscription billing fix) and the bubblewrap/user-namespace
workaround for hardened Linux. This module aliases itself to
``llm_backends.codex_interface`` in ``sys.modules`` so every name under the
old import path keeps working. New code should import from ``llm_backends``.
"""
import sys

from llm_backends import codex_interface as _impl

sys.modules[__name__] = _impl
