"""Plot outline management for emergent plot-first architecture (PlotBeat Phase 3).

This module defines a PlotOutlineManager responsible for loading, saving, and
inspecting PlotBeat/PlotOutline data backed by a single JSON file at the
project root (plot_outline.json).

Phase 3 scope: data-layer only, no agent integration. CLI and LLM-based beat
generation will build on top of this manager.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .entities import PlotBeat, PlotOutline


class PlotOutlineManager:
    """Manage the plot outline (beats) for a project.

    This is intentionally non-agent-facing in PlotBeat Phase 3: it just provides
    load/save and simple operations on PlotOutline so that CLI commands and
    later agent integrations can build on a stable data layer.
    """

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.outline_file = self.project_path / "plot_outline.json"

    # ------------------------------------------------------------------
    # Core load/save
    # ------------------------------------------------------------------

    def load_outline(self) -> PlotOutline:
        """Load the current plot outline from disk.

        Returns an empty PlotOutline if no file exists yet.
        """
        if not self.outline_file.exists():
            return PlotOutline()

        with open(self.outline_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PlotOutline.from_dict(data)

    def save_outline(self, outline: PlotOutline) -> None:
        """Persist the plot outline to disk.

        Updates the last_updated timestamp before saving.
        """
        outline.last_updated = datetime.utcnow().isoformat() + "Z"
        data = outline.to_dict()
        with open(self.outline_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Beat operations
    # ------------------------------------------------------------------

    def list_beats(self) -> List[PlotBeat]:
        """Return all beats in the outline in order."""
        outline = self.load_outline()
        return list(outline.beats)

    def get_next_beat(self, status: str = "pending") -> Optional[PlotBeat]:
        """Return the next beat with the given status (default: pending)."""
        outline = self.load_outline()
        for beat in outline.beats:
            if beat.status == status:
                return beat
        return None

    def add_beats(self, beats: List[PlotBeat]) -> PlotOutline:
        """Append new beats to the outline and save it.

        Returns the updated PlotOutline instance.
        """
        outline = self.load_outline()
        outline.beats.extend(beats)
        self.save_outline(outline)
        return outline

    def replace_outline(self, outline: PlotOutline) -> None:
        """Replace the current outline entirely with the provided one."""
        self.save_outline(outline)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate_outline(self, outline: Optional[PlotOutline] = None) -> Dict[str, Any]:
        """Perform basic validation on the outline.

        Checks for duplicate beat IDs and prerequisites that do not exist.
        Returns a dictionary with lists of issues for inspection by CLI or
        higher layers.
        """
        if outline is None:
            outline = self.load_outline()

        issues: Dict[str, Any] = {
            "duplicate_ids": [],
            "missing_prerequisites": [],
        }

        id_counts: Dict[str, int] = {}
        for beat in outline.beats:
            id_counts[beat.id] = id_counts.get(beat.id, 0) + 1

        issues["duplicate_ids"] = [bid for bid, count in id_counts.items() if count > 1]

        known_ids = set(id_counts.keys())
        missing_prereqs: List[Dict[str, Any]] = []
        for beat in outline.beats:
            for prereq in beat.prerequisites:
                if prereq not in known_ids:
                    missing_prereqs.append({"beat_id": beat.id, "prerequisite": prereq})

        issues["missing_prerequisites"] = missing_prereqs
        return issues
