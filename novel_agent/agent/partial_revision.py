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

# A revised paragraph beyond this multiple of its planned length is not a
# revision of that paragraph, it is the model writing something else in its
# place. Paragraph length is part of the plan (study section 5b), so letting
# one block come back at five times its target would break the very
# distribution the plan exists to hold, quietly and one paragraph at a time.
MAX_LENGTH_MULTIPLE = 3.0
MIN_LENGTH_FRACTION = 0.25


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

    Returns {plan index: prose}. A response with no markers at all yields {},
    which the caller treats as a failed revision rather than splicing blind.

    Structure is repaired here rather than requested. A marker addresses one
    plan item and a plan item is one paragraph by definition, so a revision
    the model split across blank lines is re-joined into its marked owner, and
    line breaks inside a block are collapsed. The previous version kept only
    the parts that began with a marker, which silently deleted the rest of a
    split paragraph: strictly worse than the split it was trying to avoid.
    Text before the first marker is preamble and is dropped.
    """
    if not response or not isinstance(response, str):
        return {}
    out: Dict[int, List[str]] = {}
    current: Optional[int] = None
    for part in re.split(r"\n\s*\n", response):
        if not part.strip():
            continue
        m = _MARKED.match(part)
        if m:
            current = int(m.group(1))
            body = _MARKED.sub("", part, count=1).strip()
            out.setdefault(current, [])
            if body:
                out[current].append(body)
        elif current is not None:
            out[current].append(part.strip())
    # One block = one paragraph: collapse any internal line breaks.
    return {k: " ".join(" ".join(v).split()) for k, v in out.items()
            if " ".join(v).strip()}


def check_lengths(revised: Dict[int, str], targets: Sequence[int],
                  originals: Sequence[str]) -> Tuple[Dict[int, str], List[int]]:
    """Drop revisions whose length says they are not revisions.

    Bounded against the paragraph being REPLACED, with the plan's target as a
    fallback. That way round deliberately: a revision should be about the size
    of what it replaces, and the writer already lands somewhat under the plan,
    so bounding against the plan would reject revisions that faithfully match
    the prose actually on the page. Returns the kept revisions and the indices
    rejected, so the caller can record how often the guard fires rather than
    hiding it.
    """
    kept, rejected = {}, []
    for idx, prose in revised.items():
        want = None
        if 1 <= idx <= len(originals):
            want = len(originals[idx - 1].split())
        if not want and 1 <= idx <= len(targets):
            want = targets[idx - 1]
        got = len(prose.split())
        if want and (got > want * MAX_LENGTH_MULTIPLE
                     or got < want * MIN_LENGTH_FRACTION):
            rejected.append(idx)
            continue
        kept[idx] = prose
    return kept, sorted(rejected)


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
