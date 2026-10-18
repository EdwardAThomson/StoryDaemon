"""Story-so-far context shared by the planner, the writer and beat generation.

The default multi-stage planner used to decide what happens next without
seeing a single scene: Stage 1 had the foundation, the goal and tension
numbers, and Stage 3 only the scenes a vector search matched to an intention
written blind. The writer saw the last five scenes and nothing older. These
readers give every prompt the same chronological view: a bounded running
synopsis (``memory/synopsis.py``), the scenes since it, the recent scenes in
order, and rosters with the exact ids the plan must use.

Pure readers over MemoryManager. Every function degrades to "" rather than
raising, because a context section must never cost a tick.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _scene_ids(memory) -> List[str]:
    try:
        return list(memory.list_scenes())
    except Exception:
        return []


def _load_scene(memory, scene_id):
    try:
        return memory.load_scene(scene_id)
    except Exception:
        return None


def _first_bullet(scene) -> str:
    summary = getattr(scene, "summary", None)
    if isinstance(summary, list):
        return summary[0] if summary else ""
    return str(summary or "")


def recent_scene_summaries(memory, count: int) -> str:
    """The last ``count`` scenes' summaries, oldest first; "" with no scenes."""
    if not count or count <= 0:
        return ""
    lines = []
    for scene_id in _scene_ids(memory)[-count:]:
        scene = _load_scene(memory, scene_id)
        if not scene:
            continue
        title = getattr(scene, "title", "") or f"Scene {scene_id}"
        summary = getattr(scene, "summary", None) or []
        if isinstance(summary, str):
            summary = [summary]
        body = "\n  - ".join(summary) if summary else "(no summary)"
        lines.append(f"**{title}** (Tick {getattr(scene, 'tick', '?')}):\n  - {body}")
    return "\n\n".join(lines)


def story_so_far(memory, config, recent_window: int) -> str:
    """The running synopsis plus a line per scene it does not cover yet.

    ``recent_window`` is how many of the latest scenes the caller already
    shows in more detail; those are left out here so nothing is said twice.
    Bounded by construction: the synopsis has a word ceiling and the
    uncovered tail is shorter than one arc. "" when the feature is off or
    there is nothing older than the caller's window.
    """
    try:
        if not config.get("generation.story_synopsis", True):
            return ""
        from ..memory.synopsis import load_synopsis
        data = load_synopsis(memory)
        covered = set()
        for arc in data.get("arcs", []):
            covered.update(arc.get("scene_ids", []))
        scene_ids = _scene_ids(memory)
        older = scene_ids[:-recent_window] if recent_window > 0 else scene_ids
        tail = [sid for sid in older if sid not in covered]

        parts = []
        synopsis = (data.get("synopsis") or "").strip()
        if synopsis:
            parts.append(synopsis)
        if tail:
            lines = []
            for sid in tail:
                scene = _load_scene(memory, sid)
                if scene:
                    lines.append(f"- Tick {getattr(scene, 'tick', '?')}: {_first_bullet(scene) or getattr(scene, 'title', '')}")
            if lines:
                lead = "Since then:" if synopsis else "Earlier scenes:"
                parts.append(lead + "\n" + "\n".join(lines))
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning(f"Story-so-far context unavailable: {e}")
        return ""


def _status_note(entity) -> str:
    """" (deceased, S012)" for an entity whose status is no longer the default."""
    try:
        from ..memory.entity_status import status_note
        return status_note(entity)
    except Exception:
        return ""


def cast_roster(memory) -> str:
    """Every character as ``C000: Name (role)``, with any terminal status."""
    lines = []
    try:
        ids = sorted(memory.list_characters())
    except Exception:
        return ""
    for cid in ids:
        try:
            c = memory.load_character(cid)
        except Exception:
            c = None
        if c:
            lines.append(f"- {c.id}: {c.display_name} ({c.role}){_status_note(c)}")
    return "\n".join(lines)


def location_roster(memory) -> str:
    """Every location as ``L000: Name``, with any terminal status."""
    lines = []
    try:
        ids = sorted(memory.list_locations())
    except Exception:
        return ""
    for lid in ids:
        try:
            loc = memory.load_location(lid)
        except Exception:
            loc = None
        if loc:
            lines.append(f"- {loc.id}: {loc.name}{_status_note(loc)}")
    return "\n".join(lines)


def entity_name(memory, entity_id: Optional[str], kind: str) -> str:
    """``Name (ID)`` for a character or location id; the bare id if unknown."""
    if not entity_id:
        return ""
    try:
        loader = memory.load_character if kind == "character" else memory.load_location
        entity = loader(entity_id)
    except Exception:
        entity = None
    if not entity:
        return str(entity_id)
    name = getattr(entity, "display_name", None) or getattr(entity, "name", "") or entity_id
    return f"{name} ({entity_id})"
