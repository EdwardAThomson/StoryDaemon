import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..project import load_project_state
from ...memory.manager import MemoryManager
from ...memory.plot_outline import PlotOutlineManager
from ...memory.entities import PlotBeat, PlotOutline
from ...tools.llm_interface import send_prompt_with_retry


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

        # Main line: ID, status, and description
        print(f"  {beat.id} [{status}]: {beat.description}")

        # Secondary line: execution metadata, if any
        if executed_in_scene or execution_notes:
            parts = []
            if executed_in_scene:
                parts.append(f"executed_in_scene={executed_in_scene}")
            if execution_notes:
                parts.append(f"notes={execution_notes}")
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

    schema_example = """{
  "beats": [
    {
      "description": "...",
      "characters_involved": ["C0", "C1"],
      "location": "L2",
      "plot_threads": ["thread_a"],
      "tension_target": 7,
      "prerequisites": [],
      "advances_character_arcs": [],
      "resolves_loops": [],
      "creates_loops": []
    }
  ]
}"""

    open_loops_block = "\n".join(open_loop_lines) if open_loop_lines else "None"
    recent_summaries_block = "\n".join(reversed(recent_summaries)) if recent_summaries else "None"
    tension_block = "\n".join(tension_lines) if tension_lines else "None"
    recent_beats_block = "\n".join(recent_beats_lines) if recent_beats_lines else "None"

    prompt = f"""You are a plot architect for a long-form story. Your job is to generate the next {count} factual plot beats.

Return your answer as JSON only, with no explanations, no markdown fences, and no extra text. The JSON must have this shape:

{schema_example}

Do not include the fields id, status, created_at, executed_in_scene, or execution_notes. The system will set those fields.

# Current story state

Novel: {novel_name}
Current tick: {current_tick}

Genre: {foundation.get("genre", "unknown")}
Premise: {foundation.get("premise", "unknown")}
Setting: {foundation.get("setting", "unknown")}
Tone: {foundation.get("tone", "unknown")}

## Open loops
{open_loops_block}

## Recent scenes (most recent first)
{recent_summaries_block}

## Recent tension history
{tension_block}

## Existing outline beats (last few)
{recent_beats_block}

# Beat style and granularity rules

Each beat must follow these constraints:
- The "description" is a single short sentence (roughly 10–20 words) with at most one comma or conjunction ("and", "but", "so").
- Each beat describes one primary story move: one decision, one action, or one clear consequence. If you feel multiple things happen, split them into multiple beats instead of compressing them.
- Do not compress long sequences (for example, "over the next few weeks...") into one beat. Focus on the next concrete step.
- Avoid more than 2–3 proper nouns or technical terms in a single description.
- Favor concrete external actions and observable changes over vague summaries or internal monologue.
- The "plot_threads" field should list at most 3 concise thread names per beat; pick only the most relevant threads.

# Your task

Generate {count} new plot beats that:
- Are small and atomic, following the style rules above.
- Are factual (no prose or dialogue).
- Advance existing threads and character arcs.
- Maintain or increase overall story tension appropriately.
- Avoid repeating previous beats or scenes.

Remember: respond with JSON only.
"""
    return prompt


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
