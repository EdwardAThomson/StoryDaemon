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


def _progress(current_tick: int, target_story_length: int) -> float:
    """Fraction through the intended arc, clamped to [0, 1]."""
    if not target_story_length or target_story_length <= 0:
        return 1.0
    return max(0.0, min(1.0, current_tick / float(target_story_length)))


def interpolate_curve(progress: float, curve: Sequence[Sequence[float]]) -> Optional[float]:
    """Linearly interpolate a tension target at ``progress`` over a curve.

    ``curve`` is a sequence of ``[fraction, level]`` control points. Points need
    not be pre-sorted. Progress outside the control range clamps to the nearest
    endpoint. Returns None for an empty/malformed curve.
    """
    points: List[List[float]] = []
    for pt in curve or []:
        try:
            frac, level = float(pt[0]), float(pt[1])
        except (TypeError, ValueError, IndexError):
            continue
        points.append([frac, level])
    if not points:
        return None

    points.sort(key=lambda p: p[0])
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
