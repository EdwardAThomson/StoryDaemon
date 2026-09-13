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

import hashlib
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

MIN_BLOCKS, MAX_BLOCKS = 4, 60
DEFAULT_WORD_TARGET = 1400

# Fallback paragraph lengths, used only if the grammar file predates the
# measured `paragraph_words` section. Same shape as the measured stats.
_FALLBACK_WORDS = {
    "SETTING": {"mean": 104.7, "p25": 47, "p75": 137},
    "CHARACTER_DESC": {"mean": 91.3, "p25": 32, "p75": 123},
    "LORE": {"mean": 115.0, "p25": 34, "p75": 149},
    "DIALOGUE": {"mean": 41.5, "p25": 11, "p75": 48},
    "ACTION": {"mean": 74.3, "p25": 25, "p75": 97},
    "INTERIORITY": {"mean": 93.6, "p25": 38, "p75": 122},
    "TRANSITION": {"mean": 10.2, "p25": 4, "p75": 7},
}

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


def mode_word_stats() -> Dict[str, Dict[str, float]]:
    """Measured paragraph length per block mode (words).

    A flat words-per-paragraph figure is the wrong instrument: in the masters
    a DIALOGUE paragraph runs 22 words at the median and a LORE paragraph 85,
    so one number forces short modes long and long modes short. Told "60-130
    words" for every item, the writer packed five or six speech turns into a
    single DIALOGUE paragraph, which is the craft defect Slice 4's reading
    notes flagged (docs/SLICE4_SCENE_SKELETON_RESULTS.md section 6.1).
    """
    stats = _grammar().get("paragraph_words") or {}
    return stats.get("by_mode") or _FALLBACK_WORDS


def _decile_ladder(mode: str) -> Optional[List[float]]:
    entry = mode_word_stats().get(mode) or {}
    ladder = entry.get("deciles")
    return [float(x) for x in ladder] if ladder else None


def _sample_length(mode: str, rng: random.Random) -> int:
    """One paragraph's word target, drawn from the mode's measured spread.

    Interpolates the decile ladder at a uniform quantile. Sampling per block
    rather than advertising one range per mode is the point: these
    distributions are strongly right-skewed (DIALOGUE median 22 against mean
    41.5), so a single range either brackets the median and under-sizes every
    scene, or brackets the mean and forbids the short turns that are half the
    corpus. Drawing per block reproduces the skew and keeps the plan's total
    unbiased, which a fixed range cannot do at once.
    """
    ladder = _decile_ladder(mode)
    stats = mode_word_stats().get(mode) or _FALLBACK_WORDS.get(mode, {})
    if not ladder:
        return max(5, int(round(stats.get("mean", 60.0))))
    u = rng.uniform(0.05, 0.95) * 10.0 - 1.0     # position on the ladder
    lo = max(0, min(len(ladder) - 1, int(u)))
    hi = min(len(ladder) - 1, lo + 1)
    frac = u - lo
    return max(5, int(round(ladder[lo] + (ladder[hi] - ladder[lo]) * frac)))


def block_word_targets(skeleton: List[str],
                       seed: Optional[int] = None) -> List[int]:
    """A word target per plan item, deterministic for a given plan.

    Seeded from the plan's own content when no seed is given, so the same
    skeleton always renders the same prompt.
    """
    if seed is None:
        digest = hashlib.sha256("|".join(skeleton).encode()).digest()
        seed = int.from_bytes(digest[:8], "big")
    rng = random.Random(seed)
    drawn = [_sample_length(m, rng) for m in skeleton]
    # Interpolating a decile ladder samples the SHAPE well but loses mass in
    # the upper tail, which on a right-skewed distribution is where the mean
    # lives: raw draws come in about 10% under. Rescale to the mean-based
    # total so the plan's sizing stays unbiased while keeping the variation.
    want = mean_expected_words(skeleton)
    total = float(sum(drawn))
    if total <= 0 or want <= 0:
        return drawn
    scale = want / total
    return [max(5, int(round(d * scale))) for d in drawn]


def expected_words(skeleton: List[str]) -> float:
    """The prose length a plan asks for: the sum of its per-item targets.

    Deliberately the same numbers the writer is shown. The previous version
    summed per-mode *means* while the prompt advertised the p25-p75 range,
    whose midpoint sits 20-30% below the mean on these skewed distributions,
    so a writer that obeyed the prompt undershot the scene target by
    construction. A live calibration scene came in at 2,121 words against a
    3,150 target, and dialogue accounted for about 90% of the gap.
    """
    return float(sum(block_word_targets(skeleton)))


def mean_expected_words(skeleton: List[str]) -> float:
    """Expected length over all samplings; what generate_skeleton sizes with."""
    w = mode_word_stats()
    return sum(w.get(m, {}).get("mean", 0.0) for m in skeleton)


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
    """Sample a typed paragraph plan whose measured length is ``word_target``.

    The generative stack is the Gate-A sampler: measured opener distribution,
    a persistent scene layer, within-scene steps from the measured
    second-order kernel (optionally reweighted by the scene's tension
    target), and a measured closer on the final block.

    Sizing is by *word budget*, not by a flat block count. Mode mix decides
    how many paragraphs a target buys: at measured lengths a 1400-word
    dialogue scene is roughly 34 paragraphs and the same target in exposition
    is roughly 12. The old flat divisor gave both 16, which a dialogue scene
    can only reach by overfilling paragraphs.
    """
    g = _grammar()
    rng = random.Random(seed)
    ratio = _tension_ratio(tension)
    words = mode_word_stats()
    budget = word_target or DEFAULT_WORD_TARGET

    def cost(mode):
        return words.get(mode, {}).get("mean", 0.0)

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
    spent = cost(out[0])

    # The closing paragraph is appended after the loop, so its expected cost
    # is held back rather than overshooting the target by a whole block.
    closers = g["unit_closers"]
    reserve = sum(w * cost(m) for m, w in closers.items()) / sum(closers.values())

    def room_left():
        """Budget still to fill, holding back the closing paragraph's share."""
        if len(out) < MIN_BLOCKS - 1:
            return True
        if len(out) >= MAX_BLOCKS - 1:
            return False
        return spent + reserve < budget

    while room_left():
        prev = out[-2] if len(out) >= 2 else None
        cur = out[-1]
        if scene is None:
            nxt = _weighted(rng, _next_dist(prev, cur, ratio))
            out.append(nxt)
            spent += cost(nxt)
            scene = scene_for(nxt)
            if scene:
                remaining = scene_len(scene[2])
            continue
        if remaining <= 0 and cur == scene[1]:
            scene = pick_scene(previous=scene[0])
            remaining = scene_len(scene[2])
            if rng.random() < 0.04:
                out.append("TRANSITION")
                spent += cost("TRANSITION")
                continue
            if rng.random() < 0.18:
                nxt = _weighted(rng, {"SETTING": 0.5,
                                      "CHARACTER_DESC": 0.2,
                                      "LORE": 0.3})
                out.append(nxt)
                spent += cost(nxt)
                continue
            out.append(scene[1])
            spent += cost(scene[1])
            remaining -= 1
            continue
        nxt = _weighted(rng, _next_dist(prev, cur, ratio))
        out.append(nxt)
        spent += cost(nxt)
        remaining -= 1

    out.append(_weighted(rng, g["unit_closers"]))
    return out


def _word_range(mode: str) -> Tuple[int, int]:
    """The item's word range: the measured interquartile band, rounded to 5."""
    w = mode_word_stats().get(mode) or _FALLBACK_WORDS.get(mode, {})
    lo = max(5, int(round(w.get("p25", 40) / 5.0)) * 5)
    hi = max(lo + 5, int(round(w.get("p75", 120) / 5.0)) * 5)
    return lo, hi


def skeleton_lines(skeleton: List[str], first: int = 1,
                   last: Optional[int] = None) -> str:
    """Numbered plan lines for blocks ``first``..``last`` (1-based inclusive).

    Numbers are absolute positions in the whole plan, so a section rendered on
    its own keeps the same [n] addresses the full plan would have given it.
    """
    last = len(skeleton) if last is None else last
    targets = block_word_targets(skeleton)
    out = []
    for i in range(first, last + 1):
        mode = skeleton[i - 1]
        out.append(f"{i}. {mode}, ~{targets[i - 1]} words: {MODE_GUIDE[mode]}")
    return chr(10).join(out)


def plan_rules(sectioned: bool = False) -> str:
    """The plan rules block, shared by the whole-scene and per-section prompts.

    Single source of truth deliberately: these rules encode the Gate B lessons
    (per-item markers, one item one paragraph, no compression) and the
    one-speech-turn-per-item dialogue rule, and a copy that drifted out of sync
    would silently undo either.

    Deliberately free of per-call numbers. Item counts and word totals live
    beside the plan they describe, which reads better and, more to the point,
    keeps this block byte-identical across every call of a scene so it can sit
    in the cacheable prefix (PROMPT_ARCHITECTURE_PLAN.md section 3).
    """
    scope = "section" if sectioned else "scene"
    whole = ("" if sectioned else
             "\n- Do not compress, summarize, or wrap the scene up early: write\n"
             "  every item in the plan, one paragraph each.")
    return f"""Plan rules:
- Begin every paragraph with its plan number in square brackets and a
  space, e.g. "[7] ", then the prose. Every item appears exactly once, in
  order. The markers are removed mechanically afterwards; never refer to
  them in the prose.
- One plan item = one paragraph. Never split an item into several
  paragraphs, and never merge two items into one.
- Consecutive DIALOGUE items are consecutive speech turns: each item is ONE
  character speaking, with its dialogue tag and any accompanying beat of
  business. When the speaker changes, the item changes. Never pack several
  exchanges into a single paragraph.{whole}
- Write each paragraph to its own stated length. Those lengths vary on
  purpose, from a few words to a long one. Treat each as a target to hit,
  not a ceiling to stay under, and reach this {scope}'s total through the
  plan, never by adding, dropping or merging paragraphs.
- A paragraph's dominant mode must match its plan item."""


def skeleton_prompt_section(skeleton: List[str]) -> str:
    """Writer-prompt guidance carrying the plan with the [n] marker protocol.

    The marker rules are the Gate B lessons verbatim: per-item markers (the
    naive exactly-N-paragraphs instruction failed 0/4), one item = one
    paragraph, and an explicit no-compression rule.

    Each item also carries its own measured word range, and consecutive
    DIALOGUE items are declared one-speech-turn-each. The previous flat
    "60-130 words" rule applied a single length to every mode and told the
    writer a DIALOGUE paragraph could hold several exchanges, which packed
    five or six speech turns into one paragraph: nonstandard on the page and
    the likely cause of the skeleton arm's low excursion-return rate.
    """
    return f"""

{plan_rules()}

**Paragraph Plan (structural guidance):** follow this {len(skeleton)}-item
paragraph plan EXACTLY, about {round(expected_words(skeleton))} words in total.
Each numbered item names the single dominant mode that paragraph must have,
and the length that paragraph should run.

{skeleton_lines(skeleton)}"""


_MARKER = re.compile(r"^[ \t]*\[(\d+)\][ \t]*", re.M)


_PARA_SPLIT = re.compile(r"\n\s*\n")


def strip_skeleton_markers(text: str) -> Tuple[str, Dict[str, int]]:
    """Remove [n] paragraph markers; report what was found.

    Returns (clean_text, stats) with markers_found (total), markers_distinct
    (unique plan numbers) and paragraphs (blank-line separated blocks of
    prose). Text without markers passes through unchanged.

    ``paragraphs`` exists because the marker counts alone cannot see an item
    that was split: a live scene carried all 60 markers for a 60-block plan
    and still ran to 65 paragraphs, and was recorded as fully compliant. The
    counts answer "did every plan item get written"; only the paragraph count
    answers "and nothing else was".
    """
    nums = [int(m.group(1)) for m in _MARKER.finditer(text)]
    clean = _MARKER.sub("", text)
    paragraphs = len([p for p in _PARA_SPLIT.split(clean) if p.strip()])
    return clean, {"markers_found": len(nums),
                   "markers_distinct": len(set(nums)),
                   "paragraphs": paragraphs}
