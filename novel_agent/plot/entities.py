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
    status: str = "pending"  # pending, in_progress, completed, skipped
    created_at: str = ""
    executed_in_scene: Optional[str] = None
    execution_notes: str = ""
    advances_character_arcs: List[str] = field(default_factory=list)
    resolves_loops: List[str] = field(default_factory=list)
    creates_loops: List[str] = field(default_factory=list)

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
