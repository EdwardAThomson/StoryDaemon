"""Canonical 0-10 dramatic-tension scale — the single source of truth.

Both the tension *scorer* (how a written scene is graded, `tension_evaluator.py`) and the
arc-pressure *writer* guidance (what tension to aim for, `arc_pressure.py`) must speak the
SAME scale — otherwise "target 4/10" means one thing to the writer and another to the grader,
and steering is uncalibrated (observed: scenes pinned at 8 while targets sat at 4-6). Define
the bands once here; the scorer renders its rubric from them and the writer is shown the same
scale, so the number is grounded identically on both sides.
"""
from typing import List, NamedTuple


class TensionBand(NamedTuple):
    lo: int
    hi: int
    name: str
    definition: str   # how the SCORER grades a scene in this band
    directive: str    # how the WRITER should land prose in this band


# Anchors adopted from the (good) scorer rubric; directives carried alongside.
# Each `directive` lists *situational* ingredients (kinds of plot-points, stakes, pacing) that
# produce the band — NOT a vocabulary list. The scorer rates stakes/threat, not scary words, so
# tension comes from what HAPPENS and how it's paced, not from dramatic word choice.
TENSION_ANCHORS: List[TensionBand] = [
    TensionBand(0, 1, "none", "calm, safe, no stakes or conflict",
                "quiet routine and world/sensory texture, comfortable interaction, no open "
                "threat; slow pacing and longer sentences. Avoid danger, deadlines, or hard choices"),
    TensionBand(2, 3, "minimal", "routine, faint unease or anticipation",
                "ordinary activity with a faint undercurrent — a small unanswered question or "
                "mild unease; unhurried pacing. Avoid physical threat or urgent stakes"),
    TensionBand(4, 5, "rising", "complications or open questions, outcome uncertain",
                "introduce a complication or open question with an uncertain outcome and moderate "
                "stakes pressing on the POV; steady pacing — no resolution yet"),
    TensionBand(6, 7, "high", "active conflict, real danger, or significant stakes pressing now",
                "an active confrontation, a concrete danger or deadline, or a hard decision pressed "
                "on the POV now; tighter pacing and shorter beats. Avoid drifting/reflective digression"),
    TensionBand(8, 9, "very high",
                "imminent threat, violence, or a critical irreversible decision happening now",
                "an imminent threat, violence, or an irreversible decision happening now with the "
                "POV's core goals on the line; urgent, clipped pacing"),
    TensionBand(10, 10, "peak climax",
                "a story-defining, life-or-death moment at its breaking point",
                "the story's defining life-or-death moment at its breaking point — the central "
                "conflict resolves now"),
]


def band_for(level: float) -> TensionBand:
    """Return the band a 0-10 tension level falls in (clamped to range)."""
    lvl = max(0, min(10, int(round(level))))
    for band in TENSION_ANCHORS:
        if band.lo <= lvl <= band.hi:
            return band
    return TENSION_ANCHORS[-1]


def _range_label(band: TensionBand) -> str:
    return str(band.lo) if band.lo == band.hi else f"{band.lo}-{band.hi}"


def scorer_anchor_block() -> str:
    """The 'Anchors:' lines for the tension-scorer rubric prompt."""
    lines = ["Anchors:"]
    for b in TENSION_ANCHORS:
        lines.append(f"- {_range_label(b):<4} {b.name}: {b.definition}")
    return "\n".join(lines)


def scale_overview() -> str:
    """Compact full-scale block shown to the writer so it knows how every level is graded."""
    lines = ["Tension is graded 0-10 on this scale (same scale used to score the scene afterwards):"]
    for b in TENSION_ANCHORS:
        lines.append(f"- {_range_label(b):<4} {b.name}: {b.definition}")
    return "\n".join(lines)
