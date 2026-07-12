"""Sacred finale (Phase 3): Python owns the story's final scene.

Evidence base (docs/progress_report_20260710.md, addenda 4 and 5): a hand-forced
calm finale ask through the unmodified pipeline is deliverable (target-4 samples
scored 4, 4, 2, 7), but a single sample is a coin flip because the model stages
leftover story material either as quiet reflection or as a hot event, and the
tension_at_most contract referees those flips perfectly. Meanwhile the delivery
pipeline keeps failing to place a genuine denouement ask on the finale slot at
all (addendum 4: a wedged rising-phase beat governed the finale seven ticks
running). So Python guarantees the ask, bounds a full re-roll against the finale
tension cap, and structurally quarantines the near-universal hook pivot (4 of 5
denouement samples minted 3-5 new loops despite "nothing is at stake"; telling
does not work).

This module holds the pure logic; agent.py keeps only thin hooks. Everything is
gated by ``coherence.sacred_finale`` (default True); False restores existing
behavior exactly. Graceful degradation throughout: no function here may kill a
tick.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .arc_pressure import (
    ARC_PHASE_MANDATES,
    FINAL_BEAT_DIRECTIVE,
    interpolate_curve,
    resolve_tension_curve,
)
from .prompts import format_finale_beat_prompt, format_finale_screen_prompt
from ..plot.entities import PlotBeat

logger = logging.getLogger(__name__)

# The finale target used when arc-pressure is disabled (no curve to take an
# endpoint from): the sunshine direct test's target-4 ask, the one calm ask the
# pipeline has proven deliverable end to end (addendum 5).
FINALE_DEFAULT_TARGET = 4.0


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_finale_tick(tick: int, config) -> bool:
    """True only on the story's single finale tick (the sacred path applies).

    Requires the ``coherence.sacred_finale`` gate (default True), plot-first
    active at this tick (``generation.use_plot_first`` and tick at or past
    ``generation.plot_first_start_tick``), and ``tick`` landing exactly on
    ``coherence.target_story_length``. Overtime ticks past the intended length
    keep existing behavior (the schedule already clamps them to the curve
    endpoint); mid-story ticks are untouched. Never raises.
    """
    try:
        if not config.get('coherence.sacred_finale', True):
            return False
        if not config.get('generation.use_plot_first', False):
            return False
        if tick < config.get('generation.plot_first_start_tick', 2):
            return False
        length = config.get('coherence.target_story_length', None)
        try:
            length = int(length)
        except (TypeError, ValueError):
            return False
        return length > 0 and tick == length
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Finale target and cap
# ---------------------------------------------------------------------------

def finale_target_tension(config) -> float:
    """The finale scene's target tension: the curve endpoint, or the calm default.

    The endpoint is the target curve interpolated at progress 1.0 (the last
    control point's level). With arc-pressure disabled (curve None/empty) the
    sunshine default keeps the sacred path meaningful. Reads the curve through
    ``resolve_tension_curve`` (Slice T4a presets), so an opted-in preset's
    ending mode governs the finale coherently: a thriller-register preset ends
    at its 9-point climax instead of being re-rolled toward calm, while the
    default house preset keeps today's calm finale exactly.
    """
    curve = resolve_tension_curve(config)
    endpoint = interpolate_curve(1.0, curve) if curve else None
    return float(endpoint) if endpoint is not None else FINALE_DEFAULT_TARGET


def finale_tension_cap(config) -> float:
    """The finale contract ceiling: endpoint + 1, the tension_at_most value that
    refereed the sunshine flips perfectly (addendum 5)."""
    return finale_target_tension(config) + 1.0


def beat_satisfies_finale_tension(beat, config) -> bool:
    """True when a beat's ``tension_target`` sits at or under the finale cap.

    A missing or non-numeric target fails: a beat that cannot be confirmed calm
    is not allowed to govern the finale on trust.
    """
    try:
        return float(getattr(beat, "tension_target", None)) <= finale_tension_cap(config)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Ask chain step (a): the pending-beat screen
# ---------------------------------------------------------------------------

def screen_beat_for_finale(llm, beat, config) -> Optional[Dict[str, Any]]:
    """One-call LLM screen: is this beat a genuine denouement/aftermath/time-skip event?

    Deliberately not a keyword heuristic: surface-vocabulary checks have twice
    proven blind in this repo (the keyword tension scorer and the embedding goal
    gauge), and a hot event can be worded calmly. Retries once on parse failure;
    a double failure returns None, which the caller must treat as NOT satisfying.
    Never raises. Returns ``{"denouement": bool, "reason": str}`` on success.
    """
    if llm is None:
        return None
    prompt = format_finale_screen_prompt(getattr(beat, "description", "") or "")
    max_tokens = config.get('coherence.finale_screen_max_tokens', 200)
    for attempt in (1, 2):
        try:
            response = llm.generate(prompt, max_tokens=max_tokens)
            return _parse_finale_screen(response)
        except Exception as e:
            if attempt == 1:
                logger.warning(f"Finale screen failed, retrying: {e}")
            else:
                logger.error(f"Finale screen failed after retry: {e}")
    return None


def _parse_finale_screen(response: str) -> Dict[str, Any]:
    """Parse the screen's JSON verdict into ``{denouement, reason}``.

    Accepts a bool or a yes/no/true/false string for the verdict; anything else
    raises (so the caller's retry-once policy applies).
    """
    start = response.find("{")
    end = response.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("no JSON object in finale screen response")
    data = json.loads(response[start:end])
    verdict = data["denouement"]
    if isinstance(verdict, str):
        lowered = verdict.strip().lower()
        if lowered in ("true", "yes"):
            verdict = True
        elif lowered in ("false", "no"):
            verdict = False
    if not isinstance(verdict, bool):
        raise ValueError(f"unusable finale screen verdict {data['denouement']!r}")
    return {"denouement": verdict, "reason": str(data.get("reason", "")).strip()}


# ---------------------------------------------------------------------------
# Ask chain step (b): author a dedicated finale beat
# ---------------------------------------------------------------------------

def author_finale_beat(llm, plot_manager, memory, state, config) -> Optional[PlotBeat]:
    """Author a dedicated finale beat with the strict denouement prompt.

    Parses with the outline manager's beat-JSON machinery (same shape as normal
    beat generation) and retries once on a malformed response. The beat's
    ``tension_target`` and its ``tension_at_most`` postcondition are stamped in
    Python regardless of what the LLM emitted: Python owns the finale contract.
    Returns an unpersisted PlotBeat, or None after a double failure (the caller
    falls back to the deterministic template). Never raises.
    """
    try:
        if llm is None:
            return None
        context = _finale_beat_context(memory, state, config)
        prompt = format_finale_beat_prompt(context)
        max_tokens = config.get('generation.beat_max_tokens', 2000)
        for attempt in (1, 2):
            beats = None
            try:
                response = llm.generate(prompt, max_tokens=max_tokens)
                beats = plot_manager._extract_beats_json(response)
            except Exception as e:
                logger.warning(f"Finale beat authoring call failed (attempt {attempt}): {e}")
            beat = beats[0] if beats else None
            if beat is not None and (beat.description or "").strip():
                return _stamp_finale_contract(beat, config)
            if attempt == 1:
                print("        Finale beat JSON malformed; retrying once...")
        return None
    except Exception as e:
        logger.warning(f"Finale beat authoring failed: {e}")
        return None


def _finale_beat_context(memory, state, config) -> Dict[str, Any]:
    """Context dict for the finale beat-authoring prompt. Best-effort throughout."""
    state = state or {}
    foundation = state.get("story_foundation") or {}
    protagonist_id, protagonist_name = _protagonist(memory, state)

    loc_lines: List[str] = []
    try:
        for lid in sorted(memory.list_locations()):
            loc = memory.load_location(lid)
            if loc:
                loc_lines.append(f"{loc.id}: {loc.name}")
    except Exception:
        pass

    recent_lines: List[str] = []
    try:
        for sid in sorted(memory.list_scenes())[-3:]:
            scene = memory.load_scene(sid)
            if not scene:
                continue
            summary = getattr(scene, "summary", None)
            summ = "; ".join(summary) if isinstance(summary, list) else (summary or "")
            recent_lines.append(f"{sid}: {getattr(scene, 'title', '') or ''} : {summ}")
    except Exception:
        pass

    return {
        "novel_name": state.get("novel_name", "Untitled Novel"),
        "genre": foundation.get("genre", "unknown"),
        "premise": foundation.get("premise", "unknown"),
        "protagonist_id": protagonist_id or "C000",
        "protagonist_name": protagonist_name,
        "locations": "\n".join(loc_lines) if loc_lines else "None",
        "recent_scenes": "\n".join(recent_lines) if recent_lines else "None",
        "tension_target": int(round(finale_target_tension(config))),
    }


# ---------------------------------------------------------------------------
# Ask chain step (c): the deterministic template beat
# ---------------------------------------------------------------------------

def template_finale_beat(memory, state, config) -> PlotBeat:
    """Deterministic Python finale beat built from canon: the unconditional guarantee.

    Modeled on the hand-written sunshine beat (addendum 5), the one calm ask the
    unmodified pipeline proved deliverable: a time-skip, the protagonist in a
    known calm place, the central matter settled, nothing at stake.
    """
    protagonist_id, protagonist_name = _protagonist(memory, state)
    location_id, location_name = _calm_location(memory)
    where = f" at {location_name}" if location_name else ""
    description = (
        f"Weeks later, {protagonist_name} passes a quiet ordinary day{where}; "
        f"the central matter is settled and nothing is at stake."
    )
    beat = PlotBeat(
        id="",
        description=description,
        characters_involved=[protagonist_id] if protagonist_id else [],
        location=location_id,
        plot_threads=[],
    )
    return _stamp_finale_contract(beat, config)


def _stamp_finale_contract(beat: PlotBeat, config) -> PlotBeat:
    """Force the finale contract onto a beat: target = curve endpoint, postcondition
    tension_at_most endpoint + 1. Python-owned; whatever the LLM authored is replaced."""
    beat.tension_target = int(round(finale_target_tension(config)))
    beat.postconditions = [
        {"check": "tension_at_most", "value": int(round(finale_tension_cap(config)))}
    ]
    return beat


def _protagonist(memory, state) -> Tuple[Optional[str], str]:
    """The active character's (id, display name); name falls back to a role phrase."""
    cid = (state or {}).get("active_character")
    if not cid:
        return None, "the protagonist"
    character = None
    try:
        character = memory.load_character(cid)
    except Exception:
        pass
    name = (getattr(character, "display_name", "") or "").strip() if character else ""
    return cid, (name or "the protagonist")


def _calm_location(memory) -> Tuple[Optional[str], str]:
    """A known location's (id, name) for the template beat; (None, "") when none exist."""
    try:
        loc_ids = sorted(memory.list_locations())
    except Exception:
        return None, ""
    for lid in loc_ids:
        try:
            loc = memory.load_location(lid)
        except Exception:
            continue
        name = (getattr(loc, "name", "") or "").strip() if loc else ""
        if name:
            return lid, name
    return (loc_ids[0], "") if loc_ids else (None, "")


# ---------------------------------------------------------------------------
# Ending-mode writer instructions
# ---------------------------------------------------------------------------

def ending_instruction(mode: str) -> str:
    """Writer instruction for the finale's ending mode ("settled" or "hook"), else ""."""
    if mode == "hook":
        return hook_ending_instruction()
    if mode == "settled":
        return settled_ending_instruction()
    return ""


def settled_ending_instruction() -> str:
    """Firm settled-ending instruction for the finale's writer prompt.

    Composes the shared resolution vocabulary directly (FINAL_BEAT_DIRECTIVE and
    ARC_PHASE_MANDATES["resolution"] are the single source of truth, not
    paraphrased here), then adds the structural rules the sunshine test showed
    are needed: the hook pivots share one shape (incoming information or
    persons), and they survive plain instruction, so the same rules are also
    enforced structurally by the loop quarantine.
    """
    return (
        f"**{FINAL_BEAT_DIRECTIVE}.**\n\n"
        f"{ARC_PHASE_MANDATES['resolution']}\n\n"
        "Firm structural rules for this final scene: no new threats, no arrivals, "
        "no incoming messages or calls, no revelations, and no unanswered "
        "questions. Do not pivot to unfinished business and do not plant a hook. "
        "The story ENDS here; leave the reader settled."
    )


def hook_ending_instruction() -> str:
    """Hook-ending instruction: a denouement that ends on exactly one deliberate hook."""
    return (
        "**THIS IS THE STORY'S FINAL SCENE (hook ending).** Write a denouement or "
        "aftermath event, and end on exactly ONE deliberate hook: a single "
        "unresolved thread, arrival, or question for the reader to carry out of "
        "the book. One hook only; everything else is settled."
    )


# ---------------------------------------------------------------------------
# Ending-mode loop discipline (settled endings)
# ---------------------------------------------------------------------------

def suppress_finale_loops(facts: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Quarantine ``open_loops_created`` from a facts dict (settled-ending discipline).

    Returns ``(filtered_facts, suppressed_descriptions)``. The original dict is
    not mutated, and the filter lives at the agent level so extraction itself
    stays honest: the extractor still reports the loops, they are just not
    applied on a settled finale tick.
    """
    loops = (facts or {}).get("open_loops_created") or []
    if not loops:
        return facts, []
    filtered = dict(facts)
    filtered["open_loops_created"] = []
    descriptions: List[str] = []
    for loop in loops:
        if isinstance(loop, dict):
            descriptions.append(str(loop.get("description") or "(no description)"))
        else:
            descriptions.append(str(loop))
    return filtered, descriptions
