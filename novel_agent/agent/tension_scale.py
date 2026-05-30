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
TENSION_ANCHORS: List[TensionBand] = [
    TensionBand(0, 1, "none", "calm, safe, no stakes or conflict",
                "keep stakes low and the pace easy — reflection, quiet character or world "
                "texture, breathing room; no danger or hard conflict"),
    TensionBand(2, 3, "minimal", "routine, faint unease or anticipation",
                "keep tension mild — small frictions, lingering questions or unease; "
                "no major threat yet"),
    TensionBand(4, 5, "rising", "complications or open questions, outcome uncertain",
                "build rising tension — a complication or growing stake, an uncertain "
                "outcome pressing on the POV"),
    TensionBand(6, 7, "high", "active conflict, real danger, or significant stakes pressing now",
                "write high tension — active conflict, real danger or hard pressure on the "
                "POV; tighten the pacing and sentences"),
    TensionBand(8, 9, "very high",
                "imminent threat, violence, or a critical irreversible decision happening now",
                "write very high tension — an imminent threat or an irreversible decision "
                "happening now; maximum pressure"),
    TensionBand(10, 10, "peak climax",
                "a story-defining, life-or-death moment at its breaking point",
                "write peak-climax intensity — a story-defining, life-or-death breaking point"),
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
