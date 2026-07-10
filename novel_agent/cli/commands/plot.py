import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..project import load_project_state
from ...configs.config import Config
from ...memory.manager import MemoryManager
from ...memory.plot_outline import PlotOutlineManager
from ...memory.entities import PlotBeat, PlotOutline
from ...tools.llm_interface import send_prompt_with_retry
from ...agent.prompts import format_plot_generation_prompt
from ...agent.arc_pressure import arc_guidance_for_beats, reconcile_beat_tension_targets
from ...contracts.authoring import (contract_authoring_section, contract_schema_example,
                                    sanitize_beat_conditions)


def _project_config(project_dir: Path) -> Config:
    """Project-level Config (config.yaml over defaults) for arc-pressure reads."""
    return Config(str(Path(project_dir) / "config.yaml"))


def get_plot_status(project_dir: Path) -> Dict[str, Any]:
    manager = PlotOutlineManager(project_dir)
    outline: PlotOutline = manager.load_outline()
    issues = manager.validate_outline(outline)

    total_beats = len(outline.beats)
    pending = sum(1 for b in outline.beats if b.status == "pending")
    in_progress = sum(1 for b in outline.beats if b.status == "in_progress")
    # Treat legacy "executed" status as completed for summary purposes.
    completed = sum(1 for b in outline.beats if b.status in ("completed", "executed"))
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


def display_plot_status_detailed(project_dir: Path) -> None:
    """Display a detailed list of beats with execution info.

    Intended for use with the ``novel plot status --detailed`` flag.
    """
    manager = PlotOutlineManager(project_dir)
    outline: PlotOutline = manager.load_outline()

    if not outline.beats:
        print()
        print("No beats in plot outline.")
        return

    print()
    print("Detailed beats:")
    for beat in outline.beats:
        status = getattr(beat, "status", "pending")
        executed_in_scene = getattr(beat, "executed_in_scene", None)
        execution_notes = getattr(beat, "execution_notes", "") or ""
        verification_score = getattr(beat, "verification_score", None)
        verification_method = getattr(beat, "verification_method", None)

        # Main line: ID, status, and description
        print(f"  {beat.id} [{status}]: {beat.description}")

        # Secondary line: execution metadata, if any
        if executed_in_scene or execution_notes or verification_score is not None:
            parts = []
            if executed_in_scene:
                parts.append(f"scene={executed_in_scene}")
            if verification_score is not None:
                # Add warning indicator for low scores
                score_str = f"score={verification_score:.2f}"
                if verification_score < 0.4:
                    score_str += " ⚠️"
                parts.append(score_str)
            if verification_method:
                parts.append(f"method={verification_method}")
            print(f"    -> " + "; ".join(parts))


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


def _strip_json_fences(text: str) -> str:
    """Best-effort removal of Markdown code fences around JSON."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop first line (``` or ```json)
        lines = lines[1:]
        # Drop trailing ``` if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _parse_beats_json(raw: str) -> List[Dict[str, Any]]:
    """Parse LLM response into a list of beat dicts following the Beat JSON contract.

    Expects a top-level object with a "beats" key containing a list.
    """
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse beats JSON: {e}")

    if not isinstance(data, dict) or "beats" not in data:
        raise ValueError("Expected a JSON object with a 'beats' field.")

    beats = data["beats"]
    if not isinstance(beats, list):
        raise ValueError("'beats' must be a list.")
    return beats


def _assign_new_beat_ids(outline: PlotOutline, beat_dicts: List[Dict[str, Any]]) -> List[PlotBeat]:
    """Convert raw beat dicts into PlotBeat objects with fresh PBxxx IDs."""
    max_index = 0
    for beat in outline.beats:
        if beat.id and beat.id.startswith("PB"):
            suffix = beat.id[2:]
            if suffix.isdigit():
                max_index = max(max_index, int(suffix))

    new_beats: List[PlotBeat] = []
    for i, b in enumerate(beat_dicts):
        beat_id = f"PB{max_index + i + 1:03d}"
        description = (b.get("description") or "").strip()
        if not description:
            raise ValueError(f"Beat {i} is missing a non-empty 'description'.")

        new_beats.append(
            PlotBeat(
                id=beat_id,
                description=description,
                characters_involved=b.get("characters_involved", []) or [],
                location=b.get("location"),
                plot_threads=b.get("plot_threads", []) or [],
                tension_target=b.get("tension_target"),
                prerequisites=b.get("prerequisites", []) or [],
                status="pending",
                executed_in_scene=None,
                execution_notes="",
                advances_character_arcs=b.get("advances_character_arcs", []) or [],
                resolves_loops=b.get("resolves_loops", []) or [],
                creates_loops=b.get("creates_loops", []) or [],
                preconditions=b.get("preconditions", []) or [],
                postconditions=b.get("postconditions", []) or [],
            )
        )

    return new_beats


def _build_plot_generation_prompt(
    project_dir: Path,
    count: int,
) -> str:
    """Build the factual, non-prose beat generation prompt for the LLM.

    This uses current project state, recent scenes, open loops, and (optionally)
    the story foundation and existing outline to provide context.
    """
    state = load_project_state(str(project_dir))
    memory = MemoryManager(project_dir)
    manager = PlotOutlineManager(project_dir)
    outline = manager.load_outline()

    novel_name = state.get("novel_name", "Unknown Novel")
    current_tick = state.get("current_tick", 0)
    foundation = state.get("story_foundation") or {}

    # Recent scenes (summaries + tension)
    scene_ids = memory.list_scenes()
    recent_scene_ids = scene_ids[-3:] if len(scene_ids) > 3 else scene_ids
    recent_summaries: List[str] = []
    tension_lines: List[str] = []
    for sid in recent_scene_ids:
        scene = memory.load_scene(sid)
        if not scene:
            continue
        summary_val = getattr(scene, "summary", "")
        if isinstance(summary_val, list):
            summary_text = "; ".join(summary_val)
        else:
            summary_text = str(summary_val or "")
        if summary_text:
            recent_summaries.append(f"{sid}: {summary_text}")
        tension_level = getattr(scene, "tension_level", None)
        if tension_level is not None:
            tension_lines.append(f"{sid}: tension {tension_level}/10")

    # Open loops
    loops = memory.load_open_loops()
    open_loop_lines = []
    for loop in loops:
        if getattr(loop, "status", "open") != "open":
            continue
        # Prefer the canonical description field, but fall back to notes if
        # present (for older or partially populated data).
        desc = getattr(loop, "description", "") or getattr(loop, "notes", "")
        category = getattr(loop, "category", "")
        if category:
            line = f"{loop.id} ({category}): {desc}"
        else:
            line = f"{loop.id}: {desc}"
        open_loop_lines.append(line)

    # Existing outline (last few beats)
    recent_beats_lines: List[str] = []
    if outline.beats:
        for beat in outline.beats[-5:]:
            recent_beats_lines.append(f"{beat.id}: {beat.description} [status={beat.status}]")

    # Entity rosters (real IDs the beat generator must reference)
    char_lines = []
    for cid in sorted(memory.list_characters()):
        c = memory.load_character(cid)
        if not c:
            continue
        char_lines.append(f"{c.id}: {c.name} ({c.role})")
    loc_lines = []
    for lid in sorted(memory.list_locations()):
        loc = memory.load_location(lid)
        if not loc:
            continue
        loc_lines.append(f"{loc.id}: {loc.name}")

    # Arc schedule for the beats about to be authored (Phase 3 bridge); "" when
    # arc-pressure or the mandate gate is off. Never a hard failure.
    try:
        arc_guidance_section = arc_guidance_for_beats(
            current_tick, count, _project_config(project_dir)
        )
    except Exception:
        arc_guidance_section = ""

    # Contract vocabulary section plus the shape-example fragment (Phase 3,
    # contracts Slice 1); both "" when generation.use_contracts is off.
    # Never a hard failure.
    try:
        _cfg = _project_config(project_dir)
        contract_section = contract_authoring_section(_cfg)
        schema_example = contract_schema_example(_cfg)
    except Exception:
        contract_section = ""
        schema_example = ""

    # Single source of truth for the beat-generation prompt lives in
    # agent/prompts.py; this CLI path and the agent's PlotOutlineManager both
    # render the same template, only differing in how they assemble context.
    ctx = {
        "count": count,
        "novel_name": novel_name,
        "current_tick": current_tick,
        "genre": foundation.get("genre", "unknown"),
        "premise": foundation.get("premise", "unknown"),
        "setting": foundation.get("setting", "unknown"),
        "tone": foundation.get("tone", "unknown"),
        "characters": "\n".join(char_lines) if char_lines else "None",
        "locations": "\n".join(loc_lines) if loc_lines else "None",
        "open_loops": "\n".join(open_loop_lines) if open_loop_lines else "None",
        # Chronological (oldest first) so the template's "most recent last" holds.
        "recent_scenes": "\n".join(recent_summaries) if recent_summaries else "None",
        "tension_history": "\n".join(tension_lines) if tension_lines else "None",
        "recent_beats": "\n".join(recent_beats_lines) if recent_beats_lines else "None",
        "arc_guidance_section": arc_guidance_section,
        "contract_section": contract_section,
        "contract_schema_example": schema_example,
    }
    return format_plot_generation_prompt(ctx)


def _reconcile_generated_beats(project_dir: Path, beats: List[PlotBeat]) -> None:
    """Hold authored tension targets to the arc schedule (Phase 3 bridge).

    Same sanitize-not-trust reconciliation the agent path runs after parsing:
    fill missing targets from the schedule, clamp far-off ones toward it. Never
    raises; a reconciliation problem must not break beat generation.
    """
    try:
        current_tick = load_project_state(str(project_dir)).get("current_tick", 0)
        config = _project_config(project_dir)
        for warning in reconcile_beat_tension_targets(beats, current_tick, config):
            print(f"  ⚠️  {warning}")
    except Exception as e:
        print(f"  ⚠️  Beat tension reconciliation skipped: {e}")


def _sanitize_beat_conditions(project_dir: Path, beats: List[PlotBeat]) -> None:
    """Hold authored contract conditions to the checker vocabulary (Phase 3, Slice 1).

    Same sanitize-not-trust pass the agent path runs in
    PlotOutlineManager._resolve_beat_conditions, via the shared helper: drop
    unknown checks and phantom refs, reconcile tension conditions against each
    beat's tension_target. Never raises; a bad condition must not break beat
    generation.
    """
    try:
        memory = MemoryManager(project_dir)
        config = _project_config(project_dir)
        for warning in sanitize_beat_conditions(beats, memory, config):
            print(f"  ⚠️  {warning}")
    except Exception as e:
        print(f"  ⚠️  Beat condition sanitization skipped: {e}")


def generate_and_append_beats_cli(
    project_dir: Path,
    count: int,
    max_tokens: int = 2000,
) -> Dict[str, Any]:
    """Generate beats with the LLM and append them to the plot outline.

    This function assumes the LLM backend has already been initialized via
    initialize_llm in the CLI layer (e.g., inside the Typer command).
    """
    manager = PlotOutlineManager(project_dir)
    outline = manager.load_outline()

    prompt = _build_plot_generation_prompt(project_dir, count)
    raw = send_prompt_with_retry(prompt, max_tokens=max_tokens)
    beat_dicts = _parse_beats_json(raw)

    # If the model returned more beats than requested, trim; if fewer, accept.
    if len(beat_dicts) > count:
        beat_dicts = beat_dicts[:count]

    new_beats = _assign_new_beat_ids(outline, beat_dicts)
    _reconcile_generated_beats(project_dir, new_beats)
    _sanitize_beat_conditions(project_dir, new_beats)
    updated_outline = manager.add_beats(new_beats)
    issues = manager.validate_outline(updated_outline)

    return {
        "beats": new_beats,
        "issues": issues,
    }


def display_generated_beats(result: Dict[str, Any]) -> None:
    """Pretty-print summary of newly generated beats and any validation notes."""
    beats: List[PlotBeat] = result.get("beats", []) or []
    issues: Dict[str, Any] = result.get("issues", {}) or {}

    if not beats:
        print("No beats were generated.")
        return

    print()
    print(f"Generated {len(beats)} plot beats:")
    for beat in beats:
        print(f"  {beat.id}: {beat.description}")

    duplicates = issues.get("duplicate_ids") or []
    missing = issues.get("missing_prerequisites") or []
    if duplicates or missing:
        print()
        print("Validation notes:")
        if duplicates:
            print(f"  Duplicate beat IDs: {', '.join(duplicates)}")
        if missing:
            for item in missing:
                print(f"  Beat {item['beat_id']} has missing prerequisite {item['prerequisite']}")


def revise_and_regenerate_beats_cli(
    project_dir: Path,
    count: int,
    reason: str = "manual revise",
    max_tokens: int = 2000,
) -> Dict[str, Any]:
    """Rolling horizon (manual trigger): regenerate the pending beats from canon.

    Mirrors generate_and_append_beats_cli but first abandons the existing pending
    horizon, so the next few beats are re-derived from what the story has actually
    become (recent scenes, open loops, live rosters) rather than executed from a
    plan laid down before the prose existed.

    Generation runs first; only on success are pending beats abandoned, so an LLM
    failure never strands the story with no beats. Completed / in-progress beats
    are left untouched.

    Assumes the LLM backend has already been initialized via initialize_llm.
    """
    manager = PlotOutlineManager(project_dir)

    # 1. Generate first — a failure here raises before we touch the outline.
    prompt = _build_plot_generation_prompt(project_dir, count)
    raw = send_prompt_with_retry(prompt, max_tokens=max_tokens)
    beat_dicts = _parse_beats_json(raw)
    if len(beat_dicts) > count:
        beat_dicts = beat_dicts[:count]
    if not beat_dicts:
        return {"abandoned": [], "beats": [], "issues": {}}

    # 2. Abandon the stale pending horizon.
    current_tick = load_project_state(str(project_dir)).get("current_tick")
    outline = manager.load_outline()
    abandoned: List[str] = []
    for beat in outline.beats:
        if beat.status == "pending":
            beat.status = "abandoned"
            beat.abandoned_reason = reason
            beat.revised_at_tick = current_tick
            abandoned.append(beat.id)
    manager.save_outline(outline)

    # 3. Mint + append the fresh horizon. IDs are computed against the saved
    #    outline so abandoned beats are counted and never reused.
    outline = manager.load_outline()
    new_beats = _assign_new_beat_ids(outline, beat_dicts)
    _reconcile_generated_beats(project_dir, new_beats)
    _sanitize_beat_conditions(project_dir, new_beats)
    updated_outline = manager.add_beats(new_beats)
    issues = manager.validate_outline(updated_outline)

    return {"abandoned": abandoned, "beats": new_beats, "issues": issues}


def display_revised_beats(result: Dict[str, Any]) -> None:
    """Pretty-print the outcome of a manual horizon revision."""
    abandoned: List[str] = result.get("abandoned", []) or []
    if abandoned:
        print()
        print(f"Abandoned {len(abandoned)} pending beat(s): {', '.join(abandoned)}")
    else:
        print()
        print("No pending beats to abandon.")
    display_generated_beats(result)


def clear_plot_outline(project_dir: Path, confirm: bool = True) -> bool:
    """Clear all plot beats from the project.
    
    Args:
        project_dir: Path to project directory
        confirm: Whether to ask for confirmation (default: True)
    
    Returns:
        True if cleared, False if cancelled
    """
    outline_path = project_dir / "plot_outline.json"
    
    if not outline_path.exists():
        print("❌ No plot outline found.")
        return False
    
    # Load current outline to show what will be deleted
    manager = PlotOutlineManager(project_dir)
    outline = manager.load_outline()
    
    total_beats = len(outline.beats)
    pending = sum(1 for b in outline.beats if b.status == "pending")
    completed = sum(1 for b in outline.beats if b.status in ("completed", "executed"))
    
    print(f"\n⚠️  About to delete plot outline:")
    print(f"   Total beats: {total_beats}")
    print(f"   Pending: {pending}")
    print(f"   Completed: {completed}")
    
    if confirm:
        import typer
        proceed = typer.confirm("\nAre you sure you want to delete all plot beats?", default=False)
        if not proceed:
            print("❌ Cancelled.")
            return False
    
    # Delete the file
    outline_path.unlink()
    print("✅ Plot outline cleared.")
    print("   Beats will auto-regenerate when plot-first mode is active.")
    
    return True
