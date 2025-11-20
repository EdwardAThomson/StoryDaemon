from pathlib import Path
from typing import Dict, Any, Optional

from ...memory.plot_outline import PlotOutlineManager
from ...memory.entities import PlotBeat, PlotOutline


def get_plot_status(project_dir: Path) -> Dict[str, Any]:
    manager = PlotOutlineManager(project_dir)
    outline: PlotOutline = manager.load_outline()
    issues = manager.validate_outline(outline)

    total_beats = len(outline.beats)
    pending = sum(1 for b in outline.beats if b.status == "pending")
    in_progress = sum(1 for b in outline.beats if b.status == "in_progress")
    completed = sum(1 for b in outline.beats if b.status == "completed")
    skipped = sum(1 for b in outline.beats if b.status == "skipped")

    return {
        "project_dir": str(project_dir),
        "total_beats": total_beats,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "skipped": skipped,
        "current_arc": outline.current_arc,
        "arc_progress": outline.arc_progress,
        "created_at": outline.created_at,
        "last_updated": outline.last_updated,
        "duplicate_ids": issues.get("duplicate_ids", []),
        "missing_prerequisites": issues.get("missing_prerequisites", []),
    }


def display_plot_status(info: Dict[str, Any]) -> None:
    print()
    print(f"📍 Project: {info['project_dir']}")
    print(f"📈 Plot Beats: {info['total_beats']} (pending: {info['pending']}, in_progress: {info['in_progress']}, completed: {info['completed']}, skipped: {info['skipped']})")
    if info.get("current_arc"):
        print(f"🎭 Current Arc: {info['current_arc']} (progress: {info['arc_progress']:.2f})")
    print(f"🕒 Outline Created: {info['created_at']}")
    print(f"🕒 Last Updated: {info['last_updated']}")

    duplicates = info.get("duplicate_ids") or []
    missing = info.get("missing_prerequisites") or []
    if duplicates or missing:
        print()
        print("⚠️  Validation issues detected:")
        if duplicates:
            print(f"   Duplicate beat IDs: {', '.join(duplicates)}")
        if missing:
            for item in missing:
                print(f"   Beat {item['beat_id']} has missing prerequisite {item['prerequisite']}")
    else:
        print()
        print("✅ No validation issues detected.")


def get_next_beat(project_dir: Path) -> Optional[PlotBeat]:
    manager = PlotOutlineManager(project_dir)
    return manager.get_next_beat()


def display_next_beat(beat: Optional[PlotBeat]) -> None:
    if not beat:
        print("No pending plot beats in outline.")
        return

    print()
    print(f"Next Beat: {beat.id} [{beat.status}]")
    print(f"Description: {beat.description}")
    if beat.characters_involved:
        print(f"Characters: {', '.join(beat.characters_involved)}")
    if beat.location:
        print(f"Location: {beat.location}")
    if beat.plot_threads:
        print(f"Threads: {', '.join(beat.plot_threads)}")
    if beat.tension_target is not None:
        print(f"Tension Target: {beat.tension_target}/10")
    if beat.prerequisites:
        print(f"Prerequisites: {', '.join(beat.prerequisites)}")
