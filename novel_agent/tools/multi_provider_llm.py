"""Compatibility shim over the llm-backends package; will eventually be dropped.

The multi-provider API layer now lives in the shared `llm-backends` package
(sibling checkout / pinned git dependency; see docs/LLM_BACKENDS_INVENTORY.md
section 7.4, step 2). This module aliases itself to
``llm_backends.multi_provider_llm`` in ``sys.modules``, so every name under the
old import path (public API, provider send functions, the registries, and the
private client singletons that tests monkeypatch) resolves to the package
module itself. New code should import from ``llm_backends`` directly.
"""
import sys

from llm_backends import multi_provider_llm as _impl

sys.modules[__name__] = _impl
