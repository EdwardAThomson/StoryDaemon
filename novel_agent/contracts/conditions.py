"""Declarative, serializable conditions and the checker registry.

A ``Condition`` is a flat JSON object: ``{"check": "<name>", ...params}``. Each
``check`` name maps to a registered function ``(params, ctx) -> bool``. Conditions
are evaluated against a ``CheckContext`` that exposes the memory store, the
state dict, and (for postconditions) the freshly written prose and its tension.

Keeping conditions declarative is deliberate: the original design proposed
Python lambdas, but nothing in this codebase that touches ``plot_outline.json``
can serialize a callable. Named checkers let contracts round-trip through JSON
and let the LLM author them the same way it authors plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class ConditionError(Exception):
    """Raised by a checker when a condition cannot be evaluated as written.

    Treated as a validation failure (not a crash) by the contract validator,
    so a malformed condition degrades gracefully like the rest of the agent.
    """


@dataclass
class CheckContext:
    """Everything a checker may read.

    ``prose`` and ``scene_tension`` are only populated for postcondition checks;
    a checker that needs prose must raise ``ConditionError`` when it is None.
    """

    memory: Any  # MemoryManager (duck-typed so tests can pass a stub)
    state: Dict[str, Any] = field(default_factory=dict)
    prose: Optional[str] = None
    scene_tension: Optional[int] = None


@dataclass
class Condition:
    """A single declarative check.

    Serializes flat: the ``check`` name plus arbitrary checker params live at the
    top level of the dict (``description`` is reserved, optional metadata).
    """

    check: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"check": self.check}
        if self.description:
            data["description"] = self.description
        data.update(self.params)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        data = dict(data)
        check = data.pop("check")
        description = data.pop("description", "")
        return cls(check=check, params=data, description=description)

    def evaluate(self, ctx: CheckContext) -> bool:
        return get_checker(self.check)(self.params, ctx)

    def label(self) -> str:
        return self.description or self.check


@dataclass
class ValidationResult:
    """Outcome of validating a list of conditions."""

    is_valid: bool
    passed: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "passed": list(self.passed),
            "failures": list(self.failures),
        }


def evaluate_conditions(conditions: List[Condition], ctx: CheckContext) -> ValidationResult:
    """Run every condition, aggregating pass/fail without short-circuiting.

    A checker returning False, an unknown ``check``, or a ``ConditionError`` all
    count as failures with a human-readable message; no exception escapes.
    """
    passed: List[str] = []
    failures: List[str] = []

    for cond in conditions:
        label = cond.label()
        try:
            ok = cond.evaluate(ctx)
        except ConditionError as exc:
            failures.append(f"{label}: {exc}")
            continue
        except KeyError:
            failures.append(f"{label}: unknown check '{cond.check}'")
            continue
        except Exception as exc:  # defensive: never crash a tick over a check
            failures.append(f"{label}: checker raised {type(exc).__name__}: {exc}")
            continue

        if ok:
            passed.append(label)
        else:
            failures.append(f"{label}: not satisfied")

    return ValidationResult(is_valid=not failures, passed=passed, failures=failures)


# ---------------------------------------------------------------------------
# Checker registry
# ---------------------------------------------------------------------------

Checker = Callable[[Dict[str, Any], CheckContext], bool]
_CHECKERS: Dict[str, Checker] = {}


def register_checker(name: str) -> Callable[[Checker], Checker]:
    def decorator(fn: Checker) -> Checker:
        if name in _CHECKERS:
            raise ValueError(f"Checker '{name}' already registered")
        _CHECKERS[name] = fn
        return fn

    return decorator


def get_checker(name: str) -> Checker:
    return _CHECKERS[name]


def list_checkers() -> List[str]:
    return sorted(_CHECKERS)


def _require_prose(ctx: CheckContext) -> str:
    if ctx.prose is None:
        raise ConditionError("requires scene prose (postcondition-only check)")
    return ctx.prose


def _character_names(character) -> List[str]:
    names: List[str] = []
    for attr in ("display_name", "first_name", "full_name"):
        value = getattr(character, attr, "")
        if value:
            names.append(value)
    names.extend(getattr(character, "nicknames", []) or [])
    return [n for n in names if n]


# ---------------------------------------------------------------------------
# Built-in checkers (grounded in real entity fields)
# ---------------------------------------------------------------------------

@register_checker("entity_exists")
def _entity_exists(params: Dict[str, Any], ctx: CheckContext) -> bool:
    """{"check": "entity_exists", "id": "C0"} — id prefix selects char/location."""
    entity_id = params["id"]
    if entity_id.startswith("C"):
        return ctx.memory.load_character(entity_id) is not None
    if entity_id.startswith("L"):
        return ctx.memory.load_location(entity_id) is not None
    raise ConditionError(f"unsupported entity id '{entity_id}' (expected C* or L*)")


@register_checker("char_at_location")
def _char_at_location(params: Dict[str, Any], ctx: CheckContext) -> bool:
    """{"check": "char_at_location", "char": "C0", "location": "L1"}."""
    character = ctx.memory.load_character(params["char"])
    if character is None:
        raise ConditionError(f"character '{params['char']}' not found")
    return getattr(character.current_state, "location_id", None) == params["location"]


@register_checker("char_in_prose")
def _char_in_prose(params: Dict[str, Any], ctx: CheckContext) -> bool:
    """{"check": "char_in_prose", "char": "C0"} — any known name appears."""
    prose = _require_prose(ctx).lower()
    character = ctx.memory.load_character(params["char"])
    if character is None:
        raise ConditionError(f"character '{params['char']}' not found")
    return any(name.lower() in prose for name in _character_names(character))


@register_checker("prose_contains")
def _prose_contains(params: Dict[str, Any], ctx: CheckContext) -> bool:
    """{"check": "prose_contains", "any": [...]} or {"all": [...]}."""
    prose = _require_prose(ctx).lower()
    any_terms = params.get("any")
    all_terms = params.get("all")
    if not any_terms and not all_terms:
        raise ConditionError("prose_contains needs 'any' or 'all'")
    if any_terms and not any(t.lower() in prose for t in any_terms):
        return False
    if all_terms and not all(t.lower() in prose for t in all_terms):
        return False
    return True


@register_checker("tension_at_least")
def _tension_at_least(params: Dict[str, Any], ctx: CheckContext) -> bool:
    """{"check": "tension_at_least", "value": 7}."""
    if ctx.scene_tension is None:
        raise ConditionError("scene tension unavailable")
    return ctx.scene_tension >= int(params["value"])


@register_checker("tension_at_most")
def _tension_at_most(params: Dict[str, Any], ctx: CheckContext) -> bool:
    """{"check": "tension_at_most", "value": 4}."""
    if ctx.scene_tension is None:
        raise ConditionError("scene tension unavailable")
    return ctx.scene_tension <= int(params["value"])


@register_checker("loop_resolved")
def _loop_resolved(params: Dict[str, Any], ctx: CheckContext) -> bool:
    """{"check": "loop_resolved", "loop": "OL3"} — loop status is 'resolved'."""
    loop_id = params["loop"]
    for loop in ctx.memory.load_open_loops():
        if loop.id == loop_id:
            return loop.status == "resolved"
    raise ConditionError(f"open loop '{loop_id}' not found")
