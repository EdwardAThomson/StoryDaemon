"""Contract validation layer (design: docs/CONTRACTS_AND_BLOCKS_ARCHITECTURE.md).

Contracts answer "did we accomplish what we needed to?" via serializable,
declarative conditions checked before (preconditions) and after (postconditions)
a beat is written. Conditions are JSON, not Python callables, so they persist in
the project alongside everything else and can be emitted by the planner LLM.
"""

from .conditions import (
    Condition,
    CheckContext,
    ValidationResult,
    ConditionError,
    register_checker,
    get_checker,
    list_checkers,
)
from .beat_contract import BeatContract
from .manager import ContractManager

__all__ = [
    "Condition",
    "CheckContext",
    "ValidationResult",
    "ConditionError",
    "register_checker",
    "get_checker",
    "list_checkers",
    "BeatContract",
    "ContractManager",
]
