"""Authoring surface for beat-embedded contracts (Phase 3, contracts Slice 1).

Conditions are authored by the same LLM call that writes the beat, inside
``PLOT_GENERATION_PROMPT_TEMPLATE``, then held to the closed checker vocabulary
here. Sanitize-not-trust, the same pattern as ``_resolve_beat_references`` and
``reconcile_beat_tension_targets``: the prompt documents the vocabulary, Python
drops anything outside it, and beat generation never fails over a bad condition.

This module is shared by BOTH beat-generation paths (``plot/manager.py`` and
``cli/commands/plot.py``) so their sanitization cannot drift, exactly like the
arc-pressure tension reconciliation bridge.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .conditions import list_checkers

# A beat with ten conditions is an outline pretending to be a guardrail; the
# authoring prompt asks for 1-3 and the sanitizer enforces it. A system-derived
# tension condition (see _reconcile_tension_conditions) may sit on top of the cap.
MAX_CONDITIONS_PER_BEAT = 3

_TENSION_CHECKS = ("tension_at_least", "tension_at_most")

# Checks the LLM may not author, because they are structurally unsatisfiable
# today (Phase 3; proven live, docs/progress_report_20260710.md section 5):
# char_at_location reads character.current_state.location_id, which nothing in
# the fact-extraction pipeline ever populates, and loop_resolved requires a loop
# status of "resolved", which the pipeline never sets in practice (0 of 70 loops
# on the 2026-07-10 run). An authored condition on either wedges the beat queue
# indefinitely. Both checkers stay registered in conditions.py and BeatContract
# evaluation still supports them (a hand-written outline may use them); lift the
# gate per check when the pipeline actually writes the state it reads (loop
# resolution is part of the planned loop-aging work). For loop_resolved the
# judged closure path (Phase 3, Slice 0 of the interleaving design:
# agent/loop_closure.py, gated by coherence.loop_closure) is what will actually
# write loop status at step 11.6; it is the prerequisite for un-gating this
# check, once validated on a measured run. Deliberately NOT un-gated in Slice 0.
GATED_AUTHORING_CHECKS = {"char_at_location", "loop_resolved"}

# The LLM tension scorer's practical ceiling (Phase 3; measured across all four
# descent validation arms, docs/progress_report_20260710.md addendum): climax
# scenes fairly score 7, and 8 has been granted exactly once, at the last tick
# of the clean re-run. A tension_at_least floor above 7 is therefore
# unsatisfiable in practice and wedges the beat queue (the re-run's peak beat,
# authored tension_at_least 8, stayed pending through the whole resolution
# window). Floors above this cap are clamped down to it, authored and derived
# alike. Ceilings (tension_at_most) are satisfiable and never clamped: the
# failure mode is floors.
TENSION_FLOOR_CAP = 7


# ---------------------------------------------------------------------------
# Prompt section (beat generation)
# ---------------------------------------------------------------------------

_CONTRACT_PROMPT_SECTION = """# Scene contracts (postconditions)

Each beat MAY also carry a "postconditions" list: 1-3 machine-checkable conditions
that must hold AFTER the beat's scene is written. Each condition is a flat JSON
object {"check": "<name>", ...params} using ONLY these checks:

- entity_exists: an entity is established in canon. Example: {"check": "entity_exists", "id": "C001"}
- char_in_prose: the character appears in the scene. Example: {"check": "char_in_prose", "char": "C001"}
- tension_at_least: the scene's tension score (0-10) is at least the value. Example: {"check": "tension_at_least", "value": 6}
- tension_at_most: the scene's tension score (0-10) is at most the value. Example: {"check": "tension_at_most", "value": 4}
- prose_contains: the prose literally contains a term. Example: {"check": "prose_contains", "any": ["Skyvault Accord"]}

Postcondition rules:
- Check the beat's JOB (what must be true of the story afterward), not the scene's wording.
- Prefer entity_exists, char_in_prose, and the tension checks.
- AVOID prose_contains except for a required proper noun: a scene can depict an event
  without any given word, and contain the word without the event.
- Use ONLY the exact entity/loop IDs listed above; conditions referencing unknown IDs are dropped.
- Any tension condition must be consistent with the beat's own "tension_target".
- Omit "postconditions" entirely when nothing needs machine-checking.
"""


def contract_authoring_section(config) -> str:
    """The beat-generation prompt's contract section, or "" when contracts are off.

    Rendered into ``PLOT_GENERATION_PROMPT_TEMPLATE``'s ``{contract_section}`` by
    both beat-generation paths. Gated by ``generation.use_contracts`` (default
    False): when off, the LLM is never asked for conditions.
    """
    if not config.get('generation.use_contracts', False):
        return ""
    return _CONTRACT_PROMPT_SECTION


# The field the LLM actually emits is governed by the prompt's authoritative
# "must have this shape" JSON block, not by section text further down: with
# postconditions absent from that block, a schema-obedient model omitted them
# every time (proven live, 2026-07-10 smoke run). This fragment is injected
# right after "creates_loops" in the shape example when contracts are on. The
# example check must not name a GATED_AUTHORING_CHECKS member, or the shape
# block itself would steer authoring toward a condition the sanitizer drops.
_CONTRACT_SCHEMA_EXAMPLE = ',\n      "postconditions": [{"check": "char_in_prose", "char": "C001"}]'


def contract_schema_example(config) -> str:
    """The shape-example fragment for postconditions, or "" when contracts are off.

    Rendered into ``PLOT_GENERATION_PROMPT_TEMPLATE``'s ``{contract_schema_example}``
    placeholder (inside the authoritative JSON shape block) by both beat-generation
    paths, alongside ``contract_authoring_section``.
    """
    if not config.get('generation.use_contracts', False):
        return ""
    return _CONTRACT_SCHEMA_EXAMPLE


# ---------------------------------------------------------------------------
# Sanitization (after parsing, before the beats are persisted)
# ---------------------------------------------------------------------------

def sanitize_beat_conditions(beats, memory, config) -> List[str]:
    """Hold freshly authored beats' conditions to the checker vocabulary, in place.

    Drops (with a warning, never a failure): non-object conditions, unknown check
    names, checks in ``GATED_AUTHORING_CHECKS`` (structurally unsatisfiable today,
    authoring-only gate), conditions referencing entities/loops that do not exist,
    malformed checker params, and anything past ``MAX_CONDITIONS_PER_BEAT``. Then reconciles
    tension conditions against each beat's own ``tension_target`` (see
    ``_reconcile_tension_conditions``). Returns human-readable warnings.

    No-op (returns []) when ``generation.use_contracts`` is off: the prompt never
    asked for conditions, so there is nothing trustworthy to keep.
    """
    if not config.get('generation.use_contracts', False):
        return []

    warnings: List[str] = []
    known_checks = set(list_checkers())
    known_chars = _known_ids(memory, "list_characters")
    known_locs = _known_ids(memory, "list_locations")
    known_loops = _known_loop_ids(memory)

    for beat in beats:
        label = getattr(beat, "id", "") or "?"
        for attr in ("preconditions", "postconditions"):
            conditions = getattr(beat, attr, None) or []
            kept: List[Dict[str, Any]] = []
            for cond in conditions:
                check = cond.get("check") if isinstance(cond, dict) else None
                if check in GATED_AUTHORING_CHECKS:
                    warnings.append(
                        f"beat {label}: dropped {attr[:-1]} {cond!r}: check "
                        f"{check!r} is gated from authoring (structurally "
                        f"unsatisfiable until the pipeline writes the state it reads)"
                    )
                    continue
                problem = _condition_problem(
                    cond, known_checks, known_chars, known_locs, known_loops
                )
                if problem:
                    warnings.append(
                        f"beat {label}: dropped {attr[:-1]} {cond!r}: {problem}"
                    )
                else:
                    kept.append(cond)
            if len(kept) > MAX_CONDITIONS_PER_BEAT:
                warnings.append(
                    f"beat {label}: {len(kept)} {attr} authored; keeping the "
                    f"first {MAX_CONDITIONS_PER_BEAT}"
                )
                kept = kept[:MAX_CONDITIONS_PER_BEAT]
            setattr(beat, attr, kept)

        warnings.extend(_reconcile_tension_conditions(beat, config))

    return warnings


def _known_ids(memory, lister: str) -> Optional[set]:
    """IDs from a MemoryManager list method, or None when unavailable (skip the check)."""
    try:
        return set(getattr(memory, lister)())
    except Exception:
        return None


def _known_loop_ids(memory) -> Optional[set]:
    try:
        return {loop.id for loop in memory.load_open_loops()}
    except Exception:
        return None


def _condition_problem(cond, known_checks, known_chars, known_locs, known_loops) -> Optional[str]:
    """Why a raw condition dict must be dropped, or None to keep it.

    A ``known_*`` set of None means the roster could not be read; existence checks
    are then skipped rather than dropping everything (graceful degradation).
    """
    if not isinstance(cond, dict):
        return "not a JSON object"
    check = cond.get("check")
    if not isinstance(check, str) or check not in known_checks:
        return f"unknown check {check!r}"

    def missing_char(key: str) -> Optional[str]:
        ref = cond.get(key)
        if not isinstance(ref, str) or (known_chars is not None and ref not in known_chars):
            return f"unresolvable character ref {ref!r}"
        return None

    if check == "entity_exists":
        ref = cond.get("id")
        if not isinstance(ref, str):
            return f"unresolvable entity ref {ref!r}"
        if ref.startswith("C"):
            if known_chars is not None and ref not in known_chars:
                return f"unresolvable entity ref {ref!r}"
        elif ref.startswith("L"):
            if known_locs is not None and ref not in known_locs:
                return f"unresolvable entity ref {ref!r}"
        else:
            return f"unsupported entity id {ref!r} (expected C* or L*)"
    elif check == "char_at_location":
        problem = missing_char("char")
        if problem:
            return problem
        loc = cond.get("location")
        if not isinstance(loc, str) or (known_locs is not None and loc not in known_locs):
            return f"unresolvable location ref {loc!r}"
    elif check == "char_in_prose":
        problem = missing_char("char")
        if problem:
            return problem
    elif check == "loop_resolved":
        ref = cond.get("loop")
        if not isinstance(ref, str) or (known_loops is not None and ref not in known_loops):
            return f"unresolvable loop ref {ref!r}"
    elif check == "prose_contains":
        terms = cond.get("any") or cond.get("all")
        if not isinstance(terms, list) or not terms or not all(isinstance(t, str) for t in terms):
            return "prose_contains needs a non-empty 'any' or 'all' list of strings"
    elif check in _TENSION_CHECKS:
        value = _as_float(cond.get("value"))
        if value is None or not 0 <= value <= 10:
            return f"tension value {cond.get('value')!r} is not a number in 0-10"
    return None


def _as_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reconcile_tension_conditions(beat, config) -> List[str]:
    """Keep a beat's tension conditions consistent with its own ``tension_target``.

    Composition rule 3 of the landing sketch: the beat's author may author tension
    conditions (they are emergent, same LLM call), but beat and contract must not
    disagree about the same scene. With band = ``coherence.tension_rewrite_threshold``:

    - ``tension_at_least`` above ``target + band`` contradicts the target (it demands
      more tension than the beat even aims for); reconciled down to ``target - band``.
    - ``tension_at_most`` below ``target - band`` contradicts; reconciled up to
      ``target + band``.
    - When no tension condition was authored and the beat has a target, derive one
      (target 8 with band 2 yields ``tension_at_least: 6``); Python owns where the
      tension should be, so the check always exists once a target does.
    - Finally, any ``tension_at_least`` above ``TENSION_FLOOR_CAP`` (authored or
      derived) is clamped down to the cap: the scorer almost never grants 8+, so a
      higher floor is unsatisfiable in practice (2026-07-10 report addendum).

    Beats without a ``tension_target`` are left alone (nothing to reconcile against).
    """
    warnings: List[str] = []
    target = _as_float(getattr(beat, "tension_target", None))
    if target is None:
        return warnings

    band = _as_float(config.get('coherence.tension_rewrite_threshold', 2))
    if band is None or band < 0:
        band = 2.0
    floor = int(round(max(0.0, min(10.0, target - band))))
    ceiling = int(round(max(0.0, min(10.0, target + band))))
    label = getattr(beat, "id", "") or "?"

    postconditions = getattr(beat, "postconditions", None) or []
    tension_conds = [c for c in postconditions if c.get("check") in _TENSION_CHECKS]

    for cond in tension_conds:
        value = _as_float(cond.get("value"))
        if value is None:
            continue  # already dropped by _condition_problem in the normal flow
        if cond["check"] == "tension_at_least" and value > target + band:
            warnings.append(
                f"beat {label}: tension_at_least {value:g} contradicts "
                f"tension_target {target:g} (band ±{band:g}); reconciled to {floor}"
            )
            cond["value"] = floor
        elif cond["check"] == "tension_at_most" and value < target - band:
            warnings.append(
                f"beat {label}: tension_at_most {value:g} contradicts "
                f"tension_target {target:g} (band ±{band:g}); reconciled to {ceiling}"
            )
            cond["value"] = ceiling

    if not tension_conds:
        derived = (
            {"check": "tension_at_least", "value": floor}
            if target >= 5
            else {"check": "tension_at_most", "value": ceiling}
        )
        postconditions.append(derived)
        beat.postconditions = postconditions
        tension_conds = [derived]

    # Cap tension floors at the scorer's practical ceiling (see TENSION_FLOOR_CAP),
    # authored and derived alike. tension_at_most is deliberately left alone:
    # ceilings are satisfiable, only floors wedge the queue.
    for cond in tension_conds:
        if cond["check"] != "tension_at_least":
            continue
        value = _as_float(cond.get("value"))
        if value is not None and value > TENSION_FLOOR_CAP:
            warnings.append(
                f"beat {label}: tension_at_least {value:g} is above the scorer's "
                f"practical ceiling (scenes rarely score 8+, so a floor above "
                f"{TENSION_FLOOR_CAP} is unsatisfiable in practice and wedges "
                f"the beat queue); clamped to {TENSION_FLOOR_CAP}"
            )
            cond["value"] = TENSION_FLOOR_CAP

    return warnings


# ---------------------------------------------------------------------------
# Plain-language rendering (writer prompt)
# ---------------------------------------------------------------------------

_ENTITY_ID_RE = re.compile(r"^[CL]\d+$")


def entity_label(entity_id, memory) -> Optional[str]:
    """``"Name (ID)"`` for a canonical character/location id, or None when unresolvable.

    Phase 1 grounded identity on the contract surface: the writer can only be
    steered by names it has seen. "character C003 appears in the scene" is
    unactionable when the writer was never told C003 is Grimax Texyx (the
    descent-run4 wedge: seven consecutive contract failures while the writer
    staffed the role with freshly invented characters). Character names assemble
    from first_name + family_name; locations use their ``name``. Best-effort by
    design: no memory, a non-id string, an unknown id, an empty name, or a read
    error all return None so the caller keeps its bare-id phrasing.
    """
    if memory is None or not isinstance(entity_id, str) or not _ENTITY_ID_RE.match(entity_id):
        return None
    try:
        if entity_id.startswith("C"):
            entity = memory.load_character(entity_id)
            name = " ".join(
                part for part in (
                    (getattr(entity, "first_name", "") or "").strip(),
                    (getattr(entity, "family_name", "") or "").strip(),
                ) if part
            ) if entity else ""
        else:
            entity = memory.load_location(entity_id)
            name = (getattr(entity, "name", "") or "").strip() if entity else ""
    except Exception:
        return None
    return f"{name} ({entity_id})" if name else None


def describe_condition(cond, memory=None) -> str:
    """One plain-language line for a condition dict, for the writer prompt.

    The writer must aim at exactly what the checker grades (the tension_scale
    lesson), so each checker gets a faithful, non-technical phrasing. An authored
    ``description`` wins when present. When ``memory`` is given, character and
    location ids render with their canonical names ("Grimax Texyx (C003) appears
    in the scene"); without it, or when a lookup fails, the bare-id phrasing is
    kept (see ``entity_label``).
    """
    if not isinstance(cond, dict):
        return str(cond)
    description = cond.get("description")
    if description:
        return str(description)
    check = cond.get("check")
    if check == "entity_exists":
        label = entity_label(cond.get("id"), memory)
        if label:
            return f"{label} is established in the story"
        return f"entity {cond.get('id')} is established in the story"
    if check == "char_at_location":
        char = entity_label(cond.get("char"), memory) or f"character {cond.get('char')}"
        loc = entity_label(cond.get("location"), memory) or f"location {cond.get('location')}"
        return f"{char} is at {loc}"
    if check == "char_in_prose":
        label = entity_label(cond.get("char"), memory)
        if label:
            return f"{label} appears in the scene"
        return f"character {cond.get('char')} appears in the scene"
    if check == "loop_resolved":
        return f"open loop {cond.get('loop')} has been resolved"
    if check == "tension_at_least":
        return f"the scene's dramatic tension is at least {cond.get('value')}/10"
    if check == "tension_at_most":
        return f"the scene's dramatic tension is at most {cond.get('value')}/10"
    if check == "prose_contains":
        if cond.get("all"):
            terms = ", ".join(str(t) for t in cond["all"])
            return f"the prose mentions all of: {terms}"
        terms = ", ".join(str(t) for t in cond.get("any") or [])
        return f"the prose mentions: {terms}"
    return f"condition '{check}' holds"
