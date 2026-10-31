"""Running story synopsis: the tier of memory that scales with the novel.

Every scene gets five summary bullets at commit, and that used to be the only
summary tier: the writer saw the last five scenes and the planner none, so a
promise, a death or a destroyed ship from scene N-6 was simply gone. This
module adds the missing tier, in two levels, both bounded:

- an **arc** summary, one paragraph, written when ``generation.synopsis_arc_size``
  scenes (default 8) have accumulated past the last arc;
- a single running **synopsis**, folded from the previous synopsis and each new
  arc under a word ceiling (``generation.synopsis_max_words``), so its length
  stays flat however long the novel runs.

Both prompts are told to keep irreversible changes (deaths, destruction,
revealed secrets, broken alliances), because those are what continuity most
needs and a compressor most likes to drop.

Storage is ``memory/synopsis.json`` through MemoryManager. Rendering lives in
``agent/story_context.py:story_so_far``. ``update_synopsis`` never raises: a
failed call leaves the arc unrecorded and the next tick tries again.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SYNOPSIS_VERSION = 1

_KEEP_RULE = (
    "Keep every irreversible change: deaths, injuries that last, things "
    "destroyed or lost, secrets revealed and to whom, alliances made or "
    "broken, promises and debts. Keep who is where at the end. Drop "
    "atmosphere, scene-by-scene blow-by-blow and anything later scenes "
    "already superseded."
)

ARC_SUMMARY_PROMPT = """Summarize this stretch of a novel in ONE paragraph of at most {max_words} words.

{keep_rule}

Use the characters' names exactly as written. Plain prose, past tense, no headings, no bullet points.

{ground_truth}Scenes (in order):
{scenes}

Paragraph:"""

FOLD_PROMPT = """Below is the synopsis of a novel so far, followed by what happened in its latest stretch. Write the updated synopsis of the WHOLE story so far, at most {max_words} words.

{keep_rule}

Compress the oldest material hardest and give the latest stretch the most detail. Use the characters' names exactly as written. Plain prose, past tense, no headings, no bullet points.

{ground_truth}Synopsis so far:
{synopsis}

Latest stretch:
{arc}

Updated synopsis:"""


def load_synopsis(memory) -> Dict[str, Any]:
    """The stored synopsis record, normalized; an empty record on any failure."""
    try:
        data = memory.load_synopsis() or {}
    except Exception:
        data = {}
    data.setdefault("version", SYNOPSIS_VERSION)
    data.setdefault("arcs", [])
    data.setdefault("synopsis", "")
    return data


def _scene_block(scenes: List[Any]) -> str:
    lines = []
    for scene in scenes:
        summary = getattr(scene, "summary", None) or []
        if isinstance(summary, str):
            summary = [summary]
        body = " ".join(summary) if summary else "(no summary)"
        lines.append(f"- Tick {getattr(scene, 'tick', '?')}, {getattr(scene, 'title', '') or scene.id}: {body}")
    return "\n".join(lines)


def confirmed_changes(memory, scene_ids: List[str]) -> str:
    """The ground-truth block for a summary covering ``scene_ids`` (and
    everything before them): every confirmed death, disappearance or loss of
    a place up to the last of those scenes, from the judged status records.

    Scene summaries are written per scene and can misread an outcome: a live
    run's S012 summary said a character "bleeds out" when the scene left him
    alive, and the arc summary carried that into the synopsis for three
    scenes until he really died in S015. The status records are judged
    against the page, so they are the authority here. Never raises; "" when
    nothing is known.
    """
    try:
        from .entity_status import is_unavailable, status_record
        order = list(memory.list_scenes())
        last = order.index(scene_ids[-1]) if scene_ids and scene_ids[-1] in order else len(order) - 1
        covered = set(order[:last + 1])
        lines = []
        for list_ids, load in ((memory.list_characters, memory.load_character),
                               (memory.list_locations, memory.load_location)):
            for entity_id in sorted(list_ids()):
                entity = load(entity_id)
                if entity is None or not is_unavailable(entity):
                    continue
                record = status_record(entity)
                if record.get("scene_id") not in covered:
                    continue
                name = getattr(entity, "display_name", None) or getattr(entity, "name", entity_id)
                lines.append(f"- {name}: {record.get('status')} in {record.get('scene_id')}")
        if lines:
            head = ("Confirmed changes (checked against the scenes themselves; trust these over "
                    "the scene notes below). No other named character died or vanished and no "
                    "other named place was destroyed in this part of the story:")
        else:
            head = ("Confirmed changes: none. No named character has died or vanished and no "
                    "named place has been destroyed so far; a scene note that says otherwise "
                    "describes a threat or an injury, not a death.")
        return head + ("\n" + "\n".join(lines) if lines else "") + "\n\n"
    except Exception as e:
        logger.debug(f"Confirmed-change block skipped: {e}")
        return ""


def _clean(text: str) -> str:
    text = (text or "").strip()
    for lead in ("Paragraph:", "Updated synopsis:"):
        if text.startswith(lead):
            text = text[len(lead):].strip()
    return text


def pending_arc(memory, arc_size: int) -> List[str]:
    """The next ``arc_size`` scene ids past the last recorded arc, or []."""
    data = load_synopsis(memory)
    covered = set()
    for arc in data["arcs"]:
        covered.update(arc.get("scene_ids", []))
    try:
        uncovered = [sid for sid in memory.list_scenes() if sid not in covered]
    except Exception:
        return []
    return uncovered[:arc_size] if len(uncovered) >= arc_size else []


def update_synopsis(memory, llm, config) -> Dict[str, Any]:
    """Close any full arcs and fold them into the running synopsis.

    Catches up at most ``generation.synopsis_catchup_arcs`` arcs per call, so
    a legacy project with sixty scenes is backfilled over a few ticks rather
    than in one long stall. Returns ``{"arcs_closed": n}``; never raises.
    """
    result = {"arcs_closed": 0}
    try:
        if not config.get("generation.story_synopsis", True) or llm is None:
            return result
        arc_size = max(2, int(config.get("generation.synopsis_arc_size", 8)))
        max_words = int(config.get("generation.synopsis_max_words", 350))
        arc_words = max(60, max_words // 2)
        max_tokens = int(config.get("generation.synopsis_max_tokens", 1000))
        catchup = max(1, int(config.get("generation.synopsis_catchup_arcs", 3)))

        for _ in range(catchup):
            scene_ids = pending_arc(memory, arc_size)
            if not scene_ids:
                break
            scenes = [s for s in (memory.load_scene(sid) for sid in scene_ids) if s]
            if not scenes:
                break
            ground_truth = (confirmed_changes(memory, scene_ids)
                            if config.get("coherence.entity_status", True) else "")
            arc_text = _clean(llm.generate(
                ARC_SUMMARY_PROMPT.format(max_words=arc_words, keep_rule=_KEEP_RULE,
                                          ground_truth=ground_truth,
                                          scenes=_scene_block(scenes)),
                max_tokens=max_tokens))
            if not arc_text:
                logger.warning("Arc summary came back empty; will retry next tick")
                break

            data = load_synopsis(memory)
            previous = data["synopsis"].strip()
            if previous:
                folded = _clean(llm.generate(
                    FOLD_PROMPT.format(max_words=max_words, keep_rule=_KEEP_RULE,
                                       ground_truth=ground_truth,
                                       synopsis=previous, arc=arc_text),
                    max_tokens=max_tokens))
                if not folded:
                    logger.warning("Synopsis fold came back empty; will retry next tick")
                    break
            else:
                folded = arc_text

            data["arcs"].append({
                "scene_ids": scene_ids,
                "from_tick": getattr(scenes[0], "tick", None),
                "to_tick": getattr(scenes[-1], "tick", None),
                "summary": arc_text,
            })
            data["synopsis"] = folded
            data["synopsis_through_scene"] = scene_ids[-1]
            memory.save_synopsis(data)
            result["arcs_closed"] += 1
    except Exception as e:
        logger.warning(f"Story synopsis update failed (will retry next tick): {e}")
    return result
