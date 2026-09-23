"""Loops command - display the aged open-loop ledger (Phase 3, loop-aging Slice L1).

Read-only, and deliberately reads memory/open_loops.json and state.json directly
rather than through MemoryManager (the `novel threads` precedent), so inspecting
a project never creates directories, backfills counters or rewrites the ledger.
The ages and horizons shown here are derived on the fly by agent/loop_aging.py,
which is the same code path the tick loop and the metrics record use.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from novel_agent.agent.loop_aging import (
    HORIZONS,
    birth_tick,
    classify_horizon,
    importance_rank,
    loop_age,
    stale_threshold,
    staleness,
)
from novel_agent.configs.config import Config


class _Loop:
    """Attribute view over a raw loop dict, for the loop_aging helpers."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        for key, value in (data or {}).items():
            setattr(self, key, value)
        for key in ("id", "status", "importance", "description", "category",
                    "created_in_scene", "created_tick", "horizon"):
            if not hasattr(self, key):
                setattr(self, key, None)
        if self.status is None:
            self.status = "open"


def get_loops_info(project_dir: Path, status: Optional[str] = "open") -> Dict[str, Any]:
    """Gather the open-loop ledger with ages and horizons (read-only).

    Args:
        project_dir: Path to project directory
        status: Status filter, or None for every loop regardless of status

    Returns:
        Dictionary with the ledger path, the current tick, the staleness
        threshold, and one record per loop sorted oldest first.
    """
    project_dir = Path(project_dir)
    loops_file = project_dir / "memory" / "open_loops.json"
    state_file = project_dir / "state.json"

    raw: List[Dict[str, Any]] = []
    if loops_file.exists():
        try:
            with open(loops_file, "r", encoding="utf-8") as f:
                raw = json.load(f).get("loops", [])
        except (json.JSONDecodeError, ValueError, OSError):
            raw = []

    current_tick = None
    goal_description = None
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            current_tick = state.get("current_tick")
            goal_description = ((state.get("story_goals") or {}).get("primary") or {}).get("description")
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    config = Config(str(project_dir / "config.yaml"))

    records: List[Dict[str, Any]] = []
    for data in raw:
        loop = _Loop(data)
        if status and loop.status != status:
            continue
        report = staleness(loop, current_tick, config, goal_description)
        records.append({
            "id": loop.id,
            "status": loop.status,
            "importance": loop.importance,
            "category": loop.category,
            "description": loop.description,
            "created_in_scene": loop.created_in_scene,
            "created_tick": birth_tick(loop),
            "age": report["age"],
            "fraction": report["fraction"],
            "horizon": report["horizon"],
            "overdue": report["overdue"],
            "resolved_in_scene": data.get("resolved_in_scene"),
        })

    # Oldest first: this listing exists to make the aging problem readable, and
    # the oldest loop is the one the pressure slice will point at.
    records.sort(key=lambda r: (r["age"] if r["age"] is not None else -1,
                                importance_rank(_Loop(r))),
                 reverse=True)

    counts = {h: sum(1 for r in records if r["horizon"] == h) for h in HORIZONS}
    return {
        "project_dir": str(project_dir),
        "loops_file": str(loops_file),
        "current_tick": current_tick,
        "stale_threshold": stale_threshold(config),
        "status_filter": status,
        "count": len(records),
        "horizon_counts": counts,
        "overdue_count": sum(1 for r in records if r["overdue"]),
        "loops": records,
    }


HORIZON_NOTE = {
    "scene": "suspense with a one-scene lifespan; never debt",
    "arc": "a payable question; the only kind that can be overdue",
    "throughline": "the story's central question; stays open to the finale",
}


def display_loops(info: Dict[str, Any], use_color: bool = True):
    """Display the aged ledger, oldest loop first."""
    def bold(text):
        return f"\033[1m{text}\033[0m" if use_color else text

    loops = info.get("loops", [])
    tick = info.get("current_tick")
    print()
    filter_text = info.get("status_filter") or "all"
    print(f"🔗 {bold('Open Loops')} ({info['count']} {filter_text}) at tick "
          f"{tick if tick is not None else '?'}")
    print(f"📍 {info['loops_file']}")

    if not loops:
        print("\n   No loops recorded yet.")
        print()
        return

    counts = info.get("horizon_counts") or {}
    threshold = info.get("stale_threshold")
    print(f"   horizons: " + "  ".join(f"{h}={counts.get(h, 0)}" for h in HORIZONS))
    print(f"   overdue: {info.get('overdue_count', 0)}"
          + (f" (an arc loop is overdue at {threshold}+ ticks)" if threshold else ""))
    print()

    for record in loops:
        marker = "🔴" if record["overdue"] else "⚪"
        age = record["age"]
        age_text = (f"{age} tick{'' if age == 1 else 's'}"
                    if age is not None else "age unknown")
        print(f"   {marker} {bold(record['id'] or '?')}  {age_text}"
              f"  [{record['horizon']}]  {record['importance']}"
              f"  born {record['created_in_scene'] or '?'}")
        print(f"        {record['description'] or ''}")
    print()
    print(f"   scene: {HORIZON_NOTE['scene']}")
    print(f"   arc: {HORIZON_NOTE['arc']}")
    print(f"   throughline: {HORIZON_NOTE['throughline']}")
    print()


def display_loops_json(info: Dict[str, Any]):
    """Display the aged ledger as JSON."""
    print(json.dumps(info, indent=2))
