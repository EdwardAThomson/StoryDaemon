"""Metrics command - display the per-tick coherence rubric (Phase 3 instrumentation)."""
import json
from pathlib import Path
from typing import Any, Dict


def get_metrics_info(project_dir: Path) -> Dict[str, Any]:
    """Gather the recorded coherence-metrics series for a project.

    Args:
        project_dir: Path to project directory

    Returns:
        Dictionary with the metrics file path and the loaded series (last-wins per tick).
    """
    from ...agent.coherence_metrics import read_metrics

    metrics_file = Path(project_dir) / "memory" / "metrics.jsonl"
    series = read_metrics(metrics_file)
    return {
        "project_dir": str(project_dir),
        "metrics_file": str(metrics_file),
        "count": len(series),
        "series": series,
    }


def display_metrics(info: Dict[str, Any], use_color: bool = True):
    """Display the coherence-metrics series in a readable per-tick table."""
    def bold(text):
        return f"\033[1m{text}\033[0m" if use_color else text

    series = info.get("series", [])
    print()
    print(f"📊 {bold('Coherence Metrics')} ({info['count']} ticks recorded)")
    print(f"📍 {info['metrics_file']}")

    if not series:
        print("\n   No metrics recorded yet. Run a tick to start collecting.")
        print()
        return

    print()
    header = f"   {'Tick':>4}  {'Words':>6}  {'Loops(+/-/open)':>16}  {'Contra':>6}  {'Tension':>9}  {'GoalRel':>7}"
    print(bold(header))
    for r in series:
        tick = r.get("tick")
        words = r.get("word_count") or 0
        loops = f"{r.get('loops_opened', 0)}/{r.get('loops_closed', 0)}/{r.get('open_loops_total', 0)}"
        contra = r.get("contradictions_detected", 0)
        level = r.get("tension_level")
        category = r.get("tension_category") or ""
        tension = f"{level}/10" if level is not None else "—"
        rel = r.get("goal_relevance")
        rel_str = f"{rel:.2f}" if isinstance(rel, (int, float)) else "—"
        print(f"   {tick:>4}  {words:>6}  {loops:>16}  {contra:>6}  {tension:>5} {category:<3}  {rel_str:>7}")

    # Tension sparkline over the run (reuses the status.py bar idiom)
    levels = [r.get("tension_level") for r in series if r.get("tension_level") is not None]
    if levels:
        spark = "▁▂▃▄▅▆▇█"
        bar = "".join(spark[min(7, max(0, int(l)) * (len(spark) - 1) // 10)] for l in levels)
        print()
        print(f"   {bold('Tension:')} {bar}  (min {min(levels)} / max {max(levels)})")
    print()


def display_metrics_json(info: Dict[str, Any]):
    """Display the metrics series as JSON."""
    print(json.dumps(info.get("series", []), indent=2))
