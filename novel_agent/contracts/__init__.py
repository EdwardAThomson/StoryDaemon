"""Contract validation layer (Phase 3, docs/BLOCKS_CONTRACTS_LANDING_SKETCH.md).

Contracts answer "did we accomplish what we needed to?" via serializable,
declarative conditions attached to plot beats (preconditions and postconditions).
Conditions are JSON, not Python callables, so they ride inside plot_outline.json
next to their beat, live and die with it under the rolling horizon, and can be
emitted by the beat-generation LLM (Slice 1: authored at beat generation,
sanitized in Python, checked at beat verification). The former separate
``contracts.json`` store (ContractManager) is retired: two contract stores
disagreeing about the same beat is the durability bug the beat-embedded path fixes.
"""

from .conditions import (
    Condition,
    CheckContext,
    ValidationResult,
    ConditionError,
    evaluate_conditions,
    register_checker,
    get_checker,
    list_checkers,
)
from .beat_contract import BeatContract
from .authoring import (
    MAX_CONDITIONS_PER_BEAT,
    contract_authoring_section,
    sanitize_beat_conditions,
    describe_condition,
)

__all__ = [
    "Condition",
    "CheckContext",
    "ValidationResult",
    "ConditionError",
    "evaluate_conditions",
    "register_checker",
    "get_checker",
    "list_checkers",
    "BeatContract",
    "MAX_CONDITIONS_PER_BEAT",
    "contract_authoring_section",
    "sanitize_beat_conditions",
    "describe_condition",
]
