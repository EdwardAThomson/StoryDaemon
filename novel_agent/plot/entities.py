from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
from datetime import datetime


@dataclass
class PlotBeat:
    """A single plot beat (factual event)."""
    id: str
    description: str
    characters_involved: List[str] = field(default_factory=list)
    location: Optional[str] = None
    plot_threads: List[str] = field(default_factory=list)
    tension_target: Optional[int] = None
    prerequisites: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, skipped, abandoned
    created_at: str = ""
    executed_in_scene: Optional[str] = None
    execution_notes: str = ""
    advances_character_arcs: List[str] = field(default_factory=list)
    resolves_loops: List[str] = field(default_factory=list)
    # Loops the beat moves forward WITHOUT answering on the page (Phase 3,
    # Slice 0 follow-ups: the resolves-vs-advances reframe). Stored and
    # sanitized only for now (future loop-aging fuel); the closure judge sees
    # resolves_loops alone. Defaults empty so legacy outlines load unchanged.
    advances_loops: List[str] = field(default_factory=list)
    creates_loops: List[str] = field(default_factory=list)
    # Verification + rolling-horizon (Phase 2) bookkeeping
    verification_score: Optional[float] = None
    verification_method: str = ""
    abandoned_reason: str = ""
    revised_at_tick: Optional[int] = None
    # Contract conditions (Phase 3, contracts Slice 1): flat JSON condition dicts
    # ({"check": name, ...params}, vocabulary in novel_agent/contracts). Authored
    # with the beat at generation time so they live and die with it under the
    # rolling horizon. Preconditions are stored but not yet evaluated (Slice 2).
    preconditions: List[Dict[str, Any]] = field(default_factory=list)
    postconditions: List[Dict[str, Any]] = field(default_factory=list)
    # Postcondition evaluation record: written at beat verification (tick step
    # 11.5) when generation.use_contracts is on and the beat carries conditions.
    contract_results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlotBeat":
        return cls(**data)


@dataclass
class PlotOutline:
    """Collection of plot beats."""
    beats: List[PlotBeat] = field(default_factory=list)
    created_at: str = ""
    last_updated: str = ""

    def to_json(self, filepath: Path) -> None:
        data = {
            "beats": [b.to_dict() for b in self.beats],
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def from_json(cls, filepath: Path) -> "PlotOutline":
        with open(filepath) as f:
            data = json.load(f)
        beats = [PlotBeat.from_dict(b) for b in data.get("beats", [])]
        return cls(
            beats=beats,
            created_at=data.get("created_at", ""),
            last_updated=data.get("last_updated", ""),
        )

    @staticmethod
    def now_iso() -> str:
        return datetime.utcnow().isoformat() + "Z"
