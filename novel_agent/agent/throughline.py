"""Throughline pressure — keep scenes serving the story's primary goal.

The coherence rubric already *measures* throughline adherence as `goal_relevance` (semantic
similarity of the scene to the primary goal). This module supplies the matching *pressure*:
a firm planner instruction to keep the next scene tied to the primary goal. Like arc-pressure,
relevance is decided by *what the scene is about*, so the lever lives at the planner, not in a
post-hoc prose pass.

Dormant until a primary goal exists (auto-promoted around tick 10-15, or user-specified).
"""

from typing import Any, Dict, Optional


def primary_goal(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The story's primary goal dict (``story_goals.primary``), or None.

    Note: the planner historically read ``state['story_goal']`` (singular), which is never
    set — the goal lives under ``story_goals.primary``. Read it here so both stay in sync.
    """
    return (state.get("story_goals") or {}).get("primary")


def throughline_guidance(state: Dict[str, Any], config) -> str:
    """Firm planner instruction to keep the scene serving the primary goal, or "" when there
    is no primary goal yet or ``coherence.throughline_pressure`` is disabled."""
    if not config.get("coherence.throughline_pressure", True):
        return ""
    goal = primary_goal(state)
    description = (goal or {}).get("description") if goal else None
    if not description:
        return ""
    return (
        f"\n## Throughline — the story's primary goal: {description}\n"
        "The next scene must advance, complicate, deepen, or meaningfully connect to this "
        "throughline. Avoid scenes that don't touch it; if a tangent is needed, bend it back "
        "toward the throughline."
    )
