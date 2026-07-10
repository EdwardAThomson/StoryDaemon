"""BeatContract: a standalone bundle of conditions for a single plot beat.

Since contracts Slice 1 the canonical store for conditions is the beat itself
(``PlotBeat.preconditions`` / ``PlotBeat.postconditions`` inside
``plot_outline.json``), evaluated via ``evaluate_conditions`` at beat
verification. ``BeatContract`` remains as a convenience wrapper for grouping,
round-tripping, and manually authoring condition sets outside the outline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .conditions import Condition, CheckContext, ValidationResult, evaluate_conditions


@dataclass
class BeatContract:
    beat_id: str
    description: str = ""
    preconditions: List[Condition] = field(default_factory=list)
    postconditions: List[Condition] = field(default_factory=list)

    # Requirement metadata, mirrored from the beat for inspection/authoring.
    # These are descriptive; the enforceable checks live in pre/postconditions.
    required_characters: List[str] = field(default_factory=list)
    required_location: Optional[str] = None

    def validate_preconditions(self, ctx: CheckContext) -> ValidationResult:
        return evaluate_conditions(self.preconditions, ctx)

    def validate_postconditions(self, ctx: CheckContext) -> ValidationResult:
        return evaluate_conditions(self.postconditions, ctx)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "description": self.description,
            "preconditions": [c.to_dict() for c in self.preconditions],
            "postconditions": [c.to_dict() for c in self.postconditions],
            "required_characters": list(self.required_characters),
            "required_location": self.required_location,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BeatContract":
        return cls(
            beat_id=data["beat_id"],
            description=data.get("description", ""),
            preconditions=[Condition.from_dict(c) for c in data.get("preconditions", [])],
            postconditions=[Condition.from_dict(c) for c in data.get("postconditions", [])],
            required_characters=list(data.get("required_characters", [])),
            required_location=data.get("required_location"),
        )

    @classmethod
    def from_beat(cls, beat) -> "BeatContract":
        """Seed an (empty-condition) contract from a PlotBeat's requirement fields.

        Useful as a starting point for authoring; the caller is expected to fill
        in pre/postconditions.
        """
        return cls(
            beat_id=beat.id,
            description=getattr(beat, "description", ""),
            required_characters=list(getattr(beat, "characters_involved", []) or []),
            required_location=getattr(beat, "location", None),
        )
