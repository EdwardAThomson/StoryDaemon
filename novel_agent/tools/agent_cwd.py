"""Compatibility shim over the llm-backends package; will eventually be dropped.

``neutral_cwd()`` now lives in the shared `llm-backends` package (see
docs/LLM_BACKENDS_INVENTORY.md section 7.4, step 2). This module aliases
itself to ``llm_backends.agent_cwd`` in ``sys.modules``, so the process-wide
neutral scratch directory is the package's own single instance regardless of
which import path a caller uses. New code should import from
``llm_backends``.
"""
import sys

from llm_backends import agent_cwd as _impl

sys.modules[__name__] = _impl
