"""Selective paragraph revision (DSL Slice 5, the repair-pass half).

Rewriting a whole scene to move its tension was destroying the paragraph plan
that produced it: observed live on 2026-09-12, two of four scenes lost roughly
half their paragraphs (64 -> 36, 57 -> 28) and a fifth of their prose, because
the revision prompt saw only prose and compression is a natural way to take
heat out of a scene.

Revising only the paragraphs that carry the tension fixes that by
construction: untouched paragraphs are byte-identical, so structure, length
and marker compliance survive whatever the revision does. It is also the
"selective per-block repair pass" the landing sketch names as Slice 5's entry
point, now that the [n] marker protocol gives every paragraph an address.

Which paragraphs carry the heat is read off the corpus rather than guessed.
The masters' tension-band shares (study section 6) say which block modes rise
with tension: ACTION 1.33x from the calm band to the high band, against LORE
0.56x and INTERIORITY 0.83x. Those rising modes are the levers, whether the
scene needs turning up or down.

Pure logic: no LLM calls, no I/O. Every entry point is guarded by the caller.
"""

import logging
import re
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# A mode must rise with tension AND carry enough of the corpus to be a lever.
# TRANSITION has the highest ratio (1.46) but is 1.2% of blocks and ten words
# long, so it is noise rather than a place tension lives.
HEAT_RATIO_FLOOR = 1.05
MIN_MODE_SHARE = 0.03

DEFAULT_MAX_BLOCKS = 8       # cap on paragraphs revised in one pass
MAX_SCENE_FRACTION = 0.34    # never rewrite most of a scene: that is the old bug


def heat_ratios() -> Dict[str, float]:
    """Per-mode high-band share divided by calm-band share, from the grammar."""
    from .scene_skeleton import _grammar
    try:
        g = _grammar()
        bands = g.get("tension_bands") or {}
        calm, high = bands.get("calm(<=3)"), bands.get("high(>=7)")
        base = g.get("base_rates") or {}
        if not calm or not high:
            return {}
        out = {}
        for mode in g.get("modes", []):
            c = calm.get(mode) or 0.0
            if c <= 0 or (base.get(mode) or 0.0) < MIN_MODE_SHARE:
                continue
            out[mode] = (high.get(mode) or 0.0) / c
        return out
    except Exception as e:                                  # pragma: no cover
        logger.warning(f"heat ratios unavailable: {e}")
        return {}


def heat_modes() -> List[str]:
    """Modes that carry tension, hottest first."""
    ratios = {m: r for m, r in heat_ratios().items() if r >= HEAT_RATIO_FLOOR}
    return sorted(ratios, key=lambda m: ratios[m], reverse=True)


def select_blocks(skeleton: Sequence[str], max_blocks: int = DEFAULT_MAX_BLOCKS
                  ) -> List[int]:
    """1-based plan indices to revise, in scene order.

    Prefers the hottest modes and, within a mode, spreads the choice across
    the scene rather than taking a contiguous clump, so a revision adjusts the
    scene's whole arc instead of rewriting one passage into a different register
    from its neighbours.
    """
    if not skeleton:
        return []
    cap = max(1, min(int(max_blocks or DEFAULT_MAX_BLOCKS),
                     int(len(skeleton) * MAX_SCENE_FRACTION) or 1))
    ranked = heat_modes()
    if not ranked:
        return []
    chosen: List[int] = []
    for mode in ranked:
        hits = [i + 1 for i, m in enumerate(skeleton) if m == mode]
        if not hits:
            continue
        room = cap - len(chosen)
        if room <= 0:
            break
        if len(hits) > room:                 # spread evenly over the scene
            step = len(hits) / float(room)
            hits = [hits[int(k * step)] for k in range(room)]
        chosen.extend(hits)
    return sorted(set(chosen))[:cap]


_MARKED = re.compile(r"^[ \t]*\[(\d+)\][ \t]*", re.M)


def parse_revised_blocks(response: str) -> Dict[int, str]:
    """Marker-addressed paragraphs from a revision response.

    Returns {plan index: prose}. A response without markers yields {}, which
    the caller treats as a failed revision rather than splicing blind.
    """
    if not response or not isinstance(response, str):
        return {}
    out: Dict[int, str] = {}
    parts = [p.strip() for p in re.split(r"\n\s*\n", response) if p.strip()]
    for part in parts:
        m = _MARKED.match(part)
        if not m:
            continue
        body = _MARKED.sub("", part, count=1).strip()
        if body:
            out[int(m.group(1))] = body
    return out


def splice(paragraphs: Sequence[str], revised: Dict[int, str]
           ) -> Tuple[List[str], int]:
    """Replace selected paragraphs; everything else stays byte-identical.

    Indices outside the scene are ignored rather than appended: a revision
    inventing paragraph 99 must not lengthen the scene.
    """
    out = list(paragraphs)
    applied = 0
    for idx, prose in revised.items():
        if 1 <= idx <= len(out) and prose and out[idx - 1] != prose:
            out[idx - 1] = prose
            applied += 1
    return out, applied
