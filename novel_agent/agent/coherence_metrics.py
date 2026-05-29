"""Coherence rubric (Phase 3, Emergent Coherence — instrumentation only).

Phase 3 layers *pressures* (throughline gate, arc-pressure, loop-aging, contradiction
enforcement) onto the emergent tick loop. Those pressures are empirical — build, run a
batch of ticks, read the story, tune — so we need a way to *measure* coherence before we
start dialing them. This module is that measuring stick.

It records, once per tick, a handful of deterministic signals that already exist in the
system (open-loop churn, contradictions detected, tension, goal relevance). It makes NO
generation-behavior change, performs NO enforcement, and issues NO extra chat-LLM calls.

Storage is append-only JSONL at ``<project>/memory/metrics.jsonl`` (one record per line):
O(1) appends, partial-write damage confined to the last line, and trivially plottable.
Records are read back **last-wins per tick**, so a re-run tick or a checkpoint-restore
replay never produces duplicate data points.

All recorded counts are *post-tick* snapshots — they reflect state after the scene's
entity/lore updates have been applied, because the recorder runs at the end of the tick.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def read_metrics(metrics_file: Path) -> List[Dict[str, Any]]:
    """Read a metrics JSONL file, last-wins per ``tick``, sorted by tick.

    Blank or corrupt lines are skipped, so a truncated final write never breaks reads.
    """
    metrics_file = Path(metrics_file)
    if not metrics_file.exists():
        return []

    by_tick: Dict[Any, Dict[str, Any]] = {}
    with open(metrics_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            by_tick[record.get("tick")] = record  # last-wins

    return sorted(
        by_tick.values(),
        key=lambda r: r.get("tick") if r.get("tick") is not None else -1,
    )


class CoherenceMetrics:
    """Computes and persists per-tick coherence signals. Read-only against story state."""

    def __init__(self, project_path, memory_manager, vector_store, config):
        self.project_path = Path(project_path)
        self.memory = memory_manager
        self.vector = vector_store
        self.config = config
        self.metrics_file = self.project_path / "memory" / "metrics.jsonl"

    def record_tick(
        self,
        *,
        tick: int,
        scene_id: Optional[str],
        scene_text: Optional[str] = None,
        word_count: int = 0,
        tension_result: Optional[Dict[str, Any]] = None,
        goal_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute one coherence record, append it to the JSONL log, and return it."""
        loops = self.memory.load_open_loops()
        loops_opened = sum(1 for l in loops if scene_id and l.created_in_scene == scene_id)
        loops_closed = sum(1 for l in loops if scene_id and l.resolved_in_scene == scene_id)
        open_loops_total = sum(1 for l in loops if l.status == "open")

        tension_level = None
        tension_category = None
        if tension_result and tension_result.get("enabled"):
            tension_level = tension_result.get("tension_level")
            tension_category = tension_result.get("tension_category")

        goal_relevance = None
        if goal_description and scene_text:
            limit = self.config.get("coherence.goal_relevance_chars", 3000)
            try:
                goal_relevance = round(
                    float(self.vector.compute_semantic_similarity(goal_description, scene_text[:limit])),
                    4,
                )
            except Exception as e:  # similarity is best-effort; never block the record
                logger.warning(f"goal_relevance computation failed (tick {tick}): {e}")

        record = {
            "tick": tick,
            "scene_id": scene_id,
            "word_count": word_count,
            "loops_opened": loops_opened,
            "loops_closed": loops_closed,
            "open_loops_total": open_loops_total,
            "contradictions_detected": self._count_contradictions(tick),
            "tension_level": tension_level,
            "tension_category": tension_category,
            "goal_relevance": goal_relevance,
            "recorded_at": datetime.utcnow().isoformat() + "Z",
        }
        self._append(record)
        return record

    def load_metrics(self) -> List[Dict[str, Any]]:
        """Return the recorded series (last-wins per tick, sorted by tick)."""
        return read_metrics(self.metrics_file)

    def _count_contradictions(self, tick: int) -> int:
        """Count distinct contradiction pairs first detected on ``tick``.

        The detector records a verdict on *both* lore items, each stamped with its own
        ``lore.tick``; for a pair found this tick only the freshly-saved side carries
        ``detected_tick == tick``. De-duping by unordered pair counts each contradiction
        exactly once.
        """
        pairs = set()
        for lore in self.memory.load_all_lore():
            for detail in getattr(lore, "contradiction_details", None) or []:
                if detail.get("detected_tick") == tick:
                    pairs.add(frozenset((lore.id, detail.get("with"))))
        return len(pairs)

    def _append(self, record: Dict[str, Any]) -> None:
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
