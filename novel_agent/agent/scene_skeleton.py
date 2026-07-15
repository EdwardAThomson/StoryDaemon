"""Scene skeletons (Slice 4 of the block/sub-block DSL, experimental).

Samples an ordered, typed paragraph plan for one scene from the block
grammar measured on the 21-masterwork corpus, renders it as writer-prompt
guidance with the [n] marker protocol, and strips the markers from the
returned prose.

Provenance and evidence:
- grammar data: novel_agent/data/block_grammar_v1.json, exported by
  scripts/block_grammar_tables.py --json from the nd1 judge sidecars
  (docs/MASTERS_BLOCK_GRAMMAR_STUDY.md has every table and caveat).
- the sampling architecture and its parameters passed Gate A of
  experiments/block_grammar_poc/ (25/25 statistical checks against the
  masters); the marker protocol passed Gate B (0.83 label agreement);
  skeleton guidance passed Gate C (the guided arm converged on the
  masters' statistics where the unguided arm drifted).

Kept stdlib-only and side-effect free; every entry point used on the scene
path is guarded by the caller (a skeleton failure must never cost a scene).
Gated by generation.enable_scene_skeleton (default off).
"""

import json
import os
import random
import re
from typing import Dict, List, Optional, Tuple

_GRAMMAR_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "block_grammar_v1.json")

CARRIERS = ("DIALOGUE", "ACTION", "INTERIORITY")

# One-line glosses for the writer prompt (worded as in the annotation rubric)
MODE_GUIDE = {
    "SETTING": "description of place, atmosphere, weather, light, objects",
    "CHARACTER_DESC": "a character's appearance, dress, manner, bearing",
    "LORE": "history, backstory, world facts, how things came to be",
    "DIALOGUE": "dominated by quoted speech between characters",
    "ACTION": "events happening now: movement, physical or procedural activity",
    "INTERIORITY": "a character's thoughts, feelings, reasoning, judgments",
    "TRANSITION": "brief connective tissue moving time or place",
}

WORDS_PER_BLOCK = 90        # matches the Gate C word-budget convention
MIN_BLOCKS, MAX_BLOCKS = 4, 60

# Hand-defined scene layer (Gate A): each type anchors a carrier mode and a
# mean length in blocks; freq is the pick weight at scene boundaries.
_SCENE_TYPES = [
    ("DIALOGUE_SCENE", "DIALOGUE", 21.0, 0.46),
    ("ACTION_SEQUENCE", "ACTION", 9.0, 0.25),
    ("REFLECTIVE_PASSAGE", "INTERIORITY", 3.8, 0.18),
    ("EXPOSITION", "LORE", 3.8, 0.11),
]

_grammar_cache: Optional[dict] = None


def _grammar() -> dict:
    global _grammar_cache
    if _grammar_cache is None:
        with open(os.path.normpath(_GRAMMAR_PATH)) as f:
            _grammar_cache = json.load(f)
        g = _grammar_cache
        g["_kernel2"] = {tuple(k.split("|")): v["next"]
                         for k, v in g.get("second_order", {}).items()}
    return _grammar_cache


def _weighted(rng: random.Random, dist: Dict[str, float]) -> str:
    total = sum(dist.values())
    x = rng.random() * total
    for k, w in dist.items():
        x -= w
        if x <= 0:
            return k
    return k


def _tension_ratio(tension: Optional[float]) -> Optional[Dict[str, float]]:
    """Per-mode multiplier from the measured tension-band shares.

    High-tension chapters in the masters carry more ACTION and less LORE and
    INTERIORITY (study Section 6); the ratio band_share/base_rate applies
    that shift to the sampling distribution.
    """
    if tension is None:
        return None
    g = _grammar()
    band = ("calm(<=3)" if tension <= 3
            else "high(>=7)" if tension >= 7 else "mid(4-6)")
    shares = g.get("tension_bands", {}).get(band)
    if not shares:
        return None
    return {m: shares[m] / g["base_rates"][m]
            for m in g["modes"] if g["base_rates"].get(m)}


def _next_dist(prev: Optional[str], cur: str,
               ratio: Optional[Dict[str, float]]) -> Dict[str, float]:
    g = _grammar()
    dist = g["_kernel2"].get((prev, cur)) if prev is not None else None
    dist = dict(dist) if dist else dict(g["transition"][cur])
    if ratio:
        dist = {m: w * ratio.get(m, 1.0) for m, w in dist.items()}
    return dist


def generate_skeleton(word_target: int, tension: Optional[float] = None,
                      seed: Optional[int] = None) -> List[str]:
    """Sample a typed paragraph plan sized for ``word_target`` words.

    The generative stack is the Gate-A sampler: measured opener
    distribution, a persistent scene layer, within-scene steps from the
    measured second-order kernel (optionally reweighted by the scene's
    tension target), and a measured closer bias on the final block.
    """
    g = _grammar()
    rng = random.Random(seed)
    ratio = _tension_ratio(tension)
    n = max(MIN_BLOCKS, min(MAX_BLOCKS,
                            round((word_target or 1400) / WORDS_PER_BLOCK)))

    def scene_for(mode):
        for name, carrier, mean_len, _ in _SCENE_TYPES:
            if carrier == mode:
                return (name, carrier, mean_len)
        return None

    def pick_scene(previous=None):
        opts = {name: freq for name, _, _, freq in _SCENE_TYPES
                if name != previous}
        name = _weighted(rng, opts)
        row = next(t for t in _SCENE_TYPES if t[0] == name)
        return (row[0], row[1], row[2])

    def scene_len(mean_len):
        return max(2, round(rng.expovariate(1.0 / mean_len)))

    out = [_weighted(rng, g["unit_openers"])]
    scene = scene_for(out[0])
    remaining = scene_len(scene[2]) if scene else 0

    while len(out) < n:
        prev = out[-2] if len(out) >= 2 else None
        cur = out[-1]
        if len(out) == n - 1:
            out.append(_weighted(rng, g["unit_closers"]))
            break
        if scene is None:
            nxt = _weighted(rng, _next_dist(prev, cur, ratio))
            out.append(nxt)
            scene = scene_for(nxt)
            if scene:
                remaining = scene_len(scene[2])
            continue
        if remaining <= 0 and cur == scene[1]:
            scene = pick_scene(previous=scene[0])
            remaining = scene_len(scene[2])
            if rng.random() < 0.04:
                out.append("TRANSITION")
                continue
            if rng.random() < 0.18:
                out.append(_weighted(rng, {"SETTING": 0.5,
                                           "CHARACTER_DESC": 0.2,
                                           "LORE": 0.3}))
                continue
            out.append(scene[1])
            remaining -= 1
            continue
        out.append(_weighted(rng, _next_dist(prev, cur, ratio)))
        remaining -= 1
    return out


def skeleton_prompt_section(skeleton: List[str]) -> str:
    """Writer-prompt guidance carrying the plan with the [n] marker protocol.

    The marker rules are the Gate B lessons verbatim: per-item markers (the
    naive exactly-N-paragraphs instruction failed 0/4), one item = one
    paragraph, and an explicit no-compression rule.
    """
    lines = [f"{i + 1}. {m}: {MODE_GUIDE[m]}"
             for i, m in enumerate(skeleton)]
    return f"""

**Paragraph Plan (structural guidance):** follow this {len(skeleton)}-item
paragraph plan EXACTLY; each numbered item names the single dominant mode
that paragraph must have.

{chr(10).join(lines)}

Plan rules:
- Begin every paragraph with its plan number in square brackets and a
  space, e.g. "[7] ", then the prose. Every item appears exactly once, in
  order. The markers are removed mechanically afterwards; never refer to
  them in the prose.
- One plan item = one paragraph. Never split an item into several
  paragraphs; a DIALOGUE paragraph may hold several exchanges of quoted
  speech inside one paragraph.
- Do not compress, summarize, or wrap the scene up early: all
  {len(skeleton)} items, one paragraph each.
- Write full paragraphs, roughly 60-130 words each: reach the scene's
  word target through paragraph fullness, never by adding paragraphs.
- A paragraph's dominant mode must match its plan item."""


_MARKER = re.compile(r"^[ \t]*\[(\d+)\][ \t]*", re.M)


def strip_skeleton_markers(text: str) -> Tuple[str, Dict[str, int]]:
    """Remove [n] paragraph markers; report what was found.

    Returns (clean_text, stats) where stats carries markers_found (total)
    and markers_distinct (unique plan numbers seen), for compliance
    recording. Text without markers passes through unchanged.
    """
    nums = [int(m.group(1)) for m in _MARKER.finditer(text)]
    clean = _MARKER.sub("", text)
    return clean, {"markers_found": len(nums),
                   "markers_distinct": len(set(nums))}
