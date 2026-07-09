"""Arc-pressure (Phase 3 Emergent Coherence pressure).

Python owns *where the tension should be* at a given story position; the LLM owns
*how* to get there. We define a target tension trajectory (a curve over story
progress) and nudge the planner toward the target for the current position. It is
a soft pressure injected into the strategic prompt — not a hard gate; the planner
may deviate when the story strongly pulls otherwise.

"Story position" has no natural denominator in an emergent story (no known end),
so we use a configurable intended length: ``progress = current_tick /
coherence.target_story_length`` (clamped to [0, 1]). That length reflects what the
author wants — a short story vs. a novel — and is the main knob to tune.

The target curve is a list of ``[progress_fraction, tension_level]`` control
points, linearly interpolated. Setting ``coherence.target_tension_curve`` to None
disables arc-pressure entirely (returns no target, injects nothing).
"""

from typing import Any, List, Optional, Sequence

from .tension_scale import band_for, scale_overview

# Arc-phase derivation constants (Phase 3 arc-phase mandate). Validation
# (docs/progress_report_20260602.md) showed the planner reads the numeric target as "how
# tense should the prose feel" and keeps choosing tense events at a low target; the phase
# tells it what KIND of events to choose (escalate / confront / resolve).
ARC_PHASE_RESOLUTION_START = 0.85  # progress fraction where post-peak "falling" becomes "resolution"
_ARC_PHASE_PEAK_MARGIN = 0.5       # target within this of the curve max counts as the peak
_ARC_PHASE_FLAT_RANGE = 0.5        # a curve spanning less than this has no arc shape to phase
_ARC_PHASE_LOOKAHEAD = 0.05        # progress lookahead for the local-slope check
_ARC_PHASE_SLOPE_TOL = 0.05        # target change below this over the lookahead reads as flat


def _progress(current_tick: int, target_story_length: int) -> float:
    """Fraction through the intended arc, clamped to [0, 1]."""
    if not target_story_length or target_story_length <= 0:
        return 1.0
    return max(0.0, min(1.0, current_tick / float(target_story_length)))


def _parse_curve(curve: Optional[Sequence[Sequence[float]]]) -> List[List[float]]:
    """Coerce a curve to sorted ``[fraction, level]`` float pairs, dropping malformed points."""
    points: List[List[float]] = []
    for pt in curve or []:
        try:
            frac, level = float(pt[0]), float(pt[1])
        except (TypeError, ValueError, IndexError):
            continue
        points.append([frac, level])
    points.sort(key=lambda p: p[0])
    return points


def interpolate_curve(progress: float, curve: Sequence[Sequence[float]]) -> Optional[float]:
    """Linearly interpolate a tension target at ``progress`` over a curve.

    ``curve`` is a sequence of ``[fraction, level]`` control points. Points need
    not be pre-sorted. Progress outside the control range clamps to the nearest
    endpoint. Returns None for an empty/malformed curve.
    """
    points = _parse_curve(curve)
    if not points:
        return None

    if progress <= points[0][0]:
        return points[0][1]
    if progress >= points[-1][0]:
        return points[-1][1]

    for (f0, l0), (f1, l1) in zip(points, points[1:]):
        if f0 <= progress <= f1:
            if f1 == f0:
                return l1
            t = (progress - f0) / (f1 - f0)
            return l0 + t * (l1 - l0)
    return points[-1][1]


def compute_target_tension(current_tick: int, config) -> Optional[float]:
    """Target tension (0-10) for the current story position, or None if disabled."""
    curve = config.get('coherence.target_tension_curve', None)
    if not curve:
        return None
    length = config.get('coherence.target_story_length', 40)
    progress = _progress(current_tick, length)
    target = interpolate_curve(progress, curve)
    return round(target, 1) if target is not None else None


def derive_arc_phase(
    progress: float,
    curve: Optional[Sequence[Sequence[float]]],
    resolution_start: float = ARC_PHASE_RESOLUTION_START,
) -> Optional[str]:
    """Arc phase at ``progress``: "rising", "peak", "falling", or "resolution"; None if unphased.

    Derived purely from the target curve's shape. A target at/near the curve maximum is
    the peak; locally climbing (or not yet past the peak) is rising; locally descending
    or past the peak is falling, which hardens into "resolution" in the final tail
    (``progress >= resolution_start`` and past the peak), because winding down mid-story
    and ending the book want different mandates. Returns None for a missing, malformed,
    or flat curve (no arc shape to phase).
    """
    points = _parse_curve(curve)
    if not points:
        return None
    levels = [level for _, level in points]
    max_level = max(levels)
    if max_level - min(levels) < _ARC_PHASE_FLAT_RANGE:
        return None

    progress = max(0.0, min(1.0, progress))
    target = interpolate_curve(progress, points)
    if target is None:
        return None

    if target >= max_level - _ARC_PHASE_PEAK_MARGIN:
        return "peak"

    # Past the last control point at the curve maximum, or on a locally descending slope.
    peak_frac = max(frac for frac, level in points if level == max_level)
    ahead = interpolate_curve(min(1.0, progress + _ARC_PHASE_LOOKAHEAD), points)
    descending = ahead is not None and (ahead - target) < -_ARC_PHASE_SLOPE_TOL
    if descending or progress > peak_frac:
        if progress > peak_frac and progress >= resolution_start:
            return "resolution"
        return "falling"
    return "rising"


def compute_arc_phase(current_tick: int, config) -> Optional[str]:
    """Arc phase for the current story position, or None when arc-pressure is disabled.

    Deliberately NOT gated by ``coherence.arc_phase_mandate``: metrics record the phase
    even when the mandate injection is off, so mandate-on/off runs stay comparable.
    """
    curve = config.get('coherence.target_tension_curve', None)
    if not curve:
        return None
    length = config.get('coherence.target_story_length', 40)
    return derive_arc_phase(_progress(current_tick, length), curve)


# Per-phase event mandates for the planner (Phase 3 arc-phase mandate). Firm and
# event-level on purpose: a soft numeric nudge cannot make the planner de-escalate,
# because tension lives in the EVENTS it picks, not the prose. Vocabulary is anchored to
# the tension_scale bands (complications, stakes, threat, confrontation, aftermath).
ARC_PHASE_MANDATES = {
    "rising": (
        "Arc phase: RISING. Escalate: introduce or sharpen a complication, raise the "
        "stakes, or bring an existing threat closer. Leave outcomes uncertain; do not "
        "resolve the central conflict yet."
    ),
    "peak": (
        "Arc phase: PEAK. Confront: bring the central conflict to a head now. Plan the "
        "decisive confrontation or an irreversible decision; spend threats already "
        "established rather than planting new ones."
    ),
    "falling": (
        "Arc phase: FALLING. Resolve: the peak is behind us, so wind the story down. "
        "Plan aftermath and consequence events, close an existing open loop rather than "
        "opening new ones, and allow a time-skip or change of scene. Do NOT introduce "
        "new threats, dangers, or confrontations."
    ),
    "resolution": (
        "Arc phase: RESOLUTION. End the story: plan denouement events only. Show the "
        "aftermath and the cost of what happened, close the remaining open loops, and "
        "let characters settle into their changed situation; a time-skip is encouraged. "
        "Do NOT introduce new threats, complications, or confrontations. Progress on "
        "the story goal here means consequences and closure, not escalation."
    ),
}


def arc_phase_mandate(phase: Optional[str]) -> str:
    """Mandate text for an arc phase, or "" for an unknown/None phase."""
    return ARC_PHASE_MANDATES.get(phase, "")


def arc_pressure_guidance(current_tick: int, config) -> str:
    """One-line planner nudge toward the target tension, or "" when disabled."""
    target = compute_target_tension(current_tick, config)
    if target is None:
        return ""
    length = config.get('coherence.target_story_length', 40)
    pct = int(round(_progress(current_tick, length) * 100))
    return (
        f"\nArc Target: ~{pct}% through the intended arc — tension here should be "
        f"around {target:g}/10. Steer the scene toward that (raise stakes if below, "
        f"ease off if above), unless the story strongly pulls otherwise."
    )


def last_scene_tension(memory) -> Optional[int]:
    """Tension level of the most recent scored scene, or None. The continuity signal for
    deciding whether a target change is a step (gradual) or a jump (needs a transition)."""
    try:
        scene_ids = sorted(memory.list_scenes())
    except Exception:
        return None
    for sid in reversed(scene_ids):
        scene = memory.load_scene(sid)
        level = getattr(scene, "tension_level", None) if scene else None
        if level is not None:
            return level
    return None


def arc_pressure_guidance_for_planner(current_tick: int, config, prev_tension: Optional[float] = None) -> str:
    """Continuity-aware planner guidance: set the scene's EVENTS toward the target, and stage a
    transition when the target is a big jump from the previous scene. "" when disabled."""
    target = compute_target_tension(current_tick, config)
    if target is None:
        return ""
    length = config.get('coherence.target_story_length', 40)
    pct = int(round(_progress(current_tick, length) * 100))
    band = band_for(target)
    lines = [
        f"\n## Arc Pressure (~{pct}% through the intended arc)",
        f"Plan the scene's EVENTS to land near tension {target:g}/10 ({band.name}): {band.directive}.",
    ]
    # Phase 3 arc-phase mandate: tell the planner what KIND of events the arc position
    # demands (escalate / confront / resolve), not just the scalar target.
    if config.get('coherence.arc_phase_mandate', True):
        mandate = arc_phase_mandate(compute_arc_phase(current_tick, config))
        if mandate:
            lines.append(mandate)
    step = config.get('coherence.tension_step_for_transition', 3)
    if prev_tension is not None:
        if prev_tension - target >= step:
            lines.append(
                f"This is a deliberate drop from the previous scene's {prev_tension:g}/10. Stage a "
                f"transition that justifies the calm — a scene break to a new location, the aftermath "
                f"of the prior scene, a time skip, or a beat after an open loop resolves — and plan "
                f"low-stakes events. Do not continue the prior scene's high-stakes action.")
        elif target - prev_tension >= step:
            lines.append(
                f"Escalate from the previous scene's {prev_tension:g}/10 — raise the stakes or bring a "
                f"concrete threat or decision to a head now.")
        else:
            lines.append(
                f"Move gradually from the previous scene's {prev_tension:g}/10 toward the target.")
    return "\n".join(lines)


def needs_tension_rewrite(current: Optional[float], target: Optional[float], threshold: float) -> bool:
    """True when a scored scene is far enough off the target to warrant a revision."""
    if current is None or target is None:
        return False
    return abs(current - target) > threshold


def rewrite_futile(current: Optional[float], target: Optional[float], step: float) -> bool:
    """True when hitting the target needs a downward move too big for a prose rewrite.

    A rewrite can only re-word the scene; it cannot turn a confrontation into a
    denouement (validated: the scorer correctly rates a real confrontation 7-8 no matter
    the wording). A drop of a full transition step or more needs different EVENTS, which
    is the planner's job, so the revision pass should be skipped to save the LLM calls.
    """
    if current is None or target is None:
        return False
    return (current - target) >= step


def rewrite_improved(new: Optional[float], current: float, target: float) -> bool:
    """True when the revised scene's tension is strictly closer to the target."""
    if new is None:
        return False
    return abs(new - target) < abs(current - target)


def arc_pressure_guidance_for_writer(current_tick: int, config) -> str:
    """Firm, band-specific tension instruction for the writer prompt, or "" when disabled.

    Stronger than the planner nudge: the writer gets a concrete target level, the story-
    position context, and an actionable directive. Crucially it uses the SAME 0-10 scale the
    scene is graded against afterwards (`tension_scale`) and shows the writer that full scale,
    so "target 4/10" is calibrated identically on both sides.
    """
    target = compute_target_tension(current_tick, config)
    if target is None:
        return ""
    length = config.get('coherence.target_story_length', 40)
    pct = int(round(_progress(current_tick, length) * 100))
    band = band_for(target)
    return (
        f"**TENSION TARGET FOR THIS SCENE: {target:g}/10 ({band.name}: {band.definition}).** "
        f"You are ~{pct}% through the intended story arc. Write the scene's events, pacing, and "
        f"prose to land near this tension level — {band.directive}. Treat this as a strong guide; "
        f"deviate only if the established story makes it impossible.\n\n{scale_overview()}"
    )
