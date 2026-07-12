"""Threads command - display the story-thread registry (Phase 3, interleaving Slice T1)."""
import json
from pathlib import Path
from typing import Any, Dict, List


def get_threads_info(project_dir: Path) -> Dict[str, Any]:
    """Gather the thread registry for a project (read-only).

    Reads memory/threads.json directly (no MemoryManager, so the command never
    creates directories or backfills counters in the project it inspects).

    Args:
        project_dir: Path to project directory

    Returns:
        Dictionary with the registry file path and the thread records.
    """
    threads_file = Path(project_dir) / "memory" / "threads.json"
    threads: List[Dict[str, Any]] = []
    if threads_file.exists():
        try:
            with open(threads_file, "r", encoding="utf-8") as f:
                threads = json.load(f).get("threads", [])
        except (json.JSONDecodeError, ValueError, OSError):
            threads = []
    return {
        "project_dir": str(project_dir),
        "threads_file": str(threads_file),
        "count": len(threads),
        "threads": threads,
    }


def _tension_range(trace: List[Any]) -> str:
    """Compact min-max of a thread's tension trace ("—" when no scored entries)."""
    levels = [e[1] for e in (trace or []) if e and len(e) > 1 and e[1] is not None]
    if not levels:
        return "—"
    low, high = min(levels), max(levels)
    return f"{low:g}" if low == high else f"{low:g}-{high:g}"


def _run_pattern(trace: List[Any]) -> str:
    """The ticks this thread served, grouped into consecutive-tick runs
    (e.g. "2-4, 7, 9-10"). Compact enough for a listing line."""
    ticks = sorted({e[0] for e in (trace or []) if e and e[0] is not None})
    if not ticks:
        return "—"
    runs: List[str] = []
    start = prev = ticks[0]
    for tick in ticks[1:]:
        if tick == prev + 1:
            prev = tick
            continue
        runs.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = tick
    runs.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(runs)


def display_threads(info: Dict[str, Any], use_color: bool = True):
    """Display the thread registry as a per-thread listing."""
    def bold(text):
        return f"\033[1m{text}\033[0m" if use_color else text

    threads = info.get("threads", [])
    print()
    print(f"🧵 {bold('Story Threads')} ({info['count']} tracked)")
    print(f"📍 {info['threads_file']}")

    if not threads:
        print("\n   No threads tracked yet. Threads seed from beat plot_threads"
              " labels as scenes commit.")
        print()
        return

    print()
    for t in threads:
        name = t.get("name") or "?"
        tag = " (implicit)" if t.get("implicit") else ""
        scenes = len(t.get("scene_ids") or [])
        last = t.get("last_active_tick")
        last_str = str(last) if last is not None else "—"
        print(f"   {bold(t.get('id', '?'))}  {name}{tag}")
        print(f"         scenes: {scenes}  ticks: {_run_pattern(t.get('tension_trace'))}"
              f"  tension: {_tension_range(t.get('tension_trace'))}"
              f"  run: {t.get('run_count', 0)}  last active: tick {last_str}")
        members = t.get("member_characters") or []
        if members:
            print(f"         members: {', '.join(members)}")
        locations = t.get("home_locations") or []
        if locations:
            print(f"         locations: {', '.join(locations)}")
        labels = t.get("labels") or []
        if len(labels) > 1:
            print(f"         label variants: {', '.join(labels)}")
        beats = t.get("beats_served") or []
        if beats:
            print(f"         beats: {', '.join(beats)}")
        print()


def display_threads_json(info: Dict[str, Any]):
    """Display the thread registry as JSON."""
    print(json.dumps(info.get("threads", []), indent=2))
