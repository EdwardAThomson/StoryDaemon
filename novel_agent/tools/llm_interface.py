"""Compatibility shim over the llm-backends package; will eventually be dropped.

The backend-agnostic LLM dispatch layer (initialize_llm, send_prompt,
send_prompt_with_retry, is_initialized, check_cli_availability, LLMClient) now
lives in the shared `llm-backends` package (see docs/LLM_BACKENDS_INVENTORY.md
section 7.4, step 2). This module aliases itself to
``llm_backends.llm_interface`` in ``sys.modules``, so the module-level
``_llm_client`` singleton is the package's own: there is exactly one, shared
by both import paths. New code should import from ``llm_backends`` directly.
"""
import sys

from llm_backends import llm_interface as _impl

sys.modules[__name__] = _impl
