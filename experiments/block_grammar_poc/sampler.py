#!/usr/bin/env python3
"""Gate A skeleton sampler: hierarchical chapter -> scene -> block generator.

Emits block-label sequences (no prose, no LLM) from the layered design in
docs/MASTERS_BLOCK_GRAMMAR_STUDY.md, parameterized by the measured grammar in
grammar_reference.json (regenerate via scripts/block_grammar_tables.py --json).

Levels implemented here:
  L1 chapter: empirical length, measured opener distribution, closer bias.
  L2 scene:   hand-defined types (DIALOGUE_SCENE, ACTION_SEQUENCE,
              REFLECTIVE_PASSAGE, EXPOSITION), each anchored to a carrier
              mode; scenes persist for a sampled number of blocks.
  L3 block:   within a scene, carrier runs sampled from the measured
              first-order rows; excursions return to the carrier with the
              MEASURED excursion-return probabilities (the aba table), which
              is what a flat Markov chain cannot reproduce.

Usage:
    python sampler.py --chapters 3 --seed 7          # print skeletons
    python sampler.py --chapters 2000 --stats        # quick self-summary
"""

import argparse
import json
import os
import random
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
CARRIERS = ("DIALOGUE", "ACTION", "INTERIORITY")
TEXTURES = ("SETTING", "CHARACTER_DESC", "LORE", "TRANSITION")


@dataclass
class SceneType:
    name: str
    carrier: str
    mean_len: float          # blocks per scene (exponential)
    freq: float              # relative pick weight at scene boundaries


@dataclass
class Params:
    """Tunable knobs; defaults tuned against Gate A (see gate_a.py)."""
    scene_types: list = field(default_factory=lambda: [
        SceneType("DIALOGUE_SCENE", "DIALOGUE", 21.0, 0.46),
        SceneType("ACTION_SEQUENCE", "ACTION", 9.0, 0.25),
        SceneType("REFLECTIVE_PASSAGE", "INTERIORITY", 3.8, 0.18),
        SceneType("EXPOSITION", "LORE", 3.8, 0.11),
    ])
    allow_same_scene_repeat: bool = False
    p_boundary_transition: float = 0.04   # TRN block at a scene seam
    p_boundary_texture: float = 0.18      # texture lead-in block at a seam
    min_chapter_blocks: int = 3
    reanchor_gain: float = 1.0            # >1 pulls drifted excursions home


class Grammar:
    def __init__(self, path):
        with open(path) as f:
            g = json.load(f)
        self.modes = g["modes"]
        self.row = g["transition"]
        self.base = g["base_rates"]
        self.openers = g["unit_openers"]
        self.closers = g["unit_closers"]
        self.unit_lengths = g["unit_lengths_blocks"]
        self.kernel2 = {}
        for key, v in g.get("second_order", {}).items():
            a, b = key.split("|")
            self.kernel2[(a, b)] = v["next"]
        self.raw = g

    def next_dist(self, prev, cur):
        """Measured P(next | prev, current); first-order row as fallback."""
        if prev is not None and (prev, cur) in self.kernel2:
            return self.kernel2[(prev, cur)]
        return self.row[cur]


def weighted(rng, dist):
    """Sample a key from {key: weight}; weights need not be normalized."""
    total = sum(dist.values())
    x = rng.random() * total
    for k, w in dist.items():
        x -= w
        if x <= 0:
            return k
    return k  # float slack


class Sampler:
    def __init__(self, grammar, params=None, seed=None):
        self.g = grammar
        self.p = params or Params()
        self.rng = random.Random(seed)

    # -- L3: block steps ----------------------------------------------------

    def _scene_step(self, prev, cur, carrier):
        """One block step inside a scene.

        Dynamics come from the measured second-order kernel (excursion and
        return is a second-order statistic, so the kernel carries it for
        free). The scene's contribution here is a gentle re-anchor: if an
        excursion has drifted two blocks away from the carrier, nudge the
        distribution toward the carrier so scene intent survives long scenes.
        """
        dist = dict(self.g.next_dist(prev, cur))
        if (cur != carrier and prev is not None and prev != carrier
                and carrier in dist):
            dist[carrier] = dist[carrier] * self.p.reanchor_gain
        return weighted(self.rng, dist)

    # -- L2: scenes ----------------------------------------------------------

    def _pick_scene(self, previous=None):
        opts = {st.name: st.freq for st in self.p.scene_types
                if self.p.allow_same_scene_repeat or previous is None
                or st.name != previous}
        name = weighted(self.rng, opts)
        return next(st for st in self.p.scene_types if st.name == name)

    def _scene_for_carrier(self, mode):
        for st in self.p.scene_types:
            if st.carrier == mode:
                return st
        return None

    def _scene_len(self, st):
        return max(2, round(self.rng.expovariate(1.0 / st.mean_len)))

    # -- L1: chapters ----------------------------------------------------------

    def chapter(self):
        L = max(self.p.min_chapter_blocks,
                self.rng.choice(self.g.unit_lengths))
        out = [weighted(self.rng, self.g.openers)]
        scene = self._scene_for_carrier(out[0])
        remaining = self._scene_len(scene) if scene else 0

        while len(out) < L:
            prev = out[-2] if len(out) >= 2 else None
            cur = out[-1]
            last = len(out) == L - 1
            if last:
                # final block drawn straight from the measured closer
                # distribution: masters end chapters at scene ends, which the
                # running scene state does not know about (1 off-model
                # transition per ~58 blocks, negligible for the matrix check)
                out.append(weighted(self.rng, self.g.closers))
                break
            if scene is None:
                # preamble drift on the measured kernel until a carrier appears
                nxt = weighted(self.rng, self.g.next_dist(prev, cur))
                out.append(nxt)
                scene = self._scene_for_carrier(nxt)
                if scene:
                    remaining = self._scene_len(scene)
                continue
            if remaining <= 0 and cur == scene.carrier:
                # scene boundary: optional seam blocks, then next scene
                scene = self._pick_scene(previous=scene.name)
                remaining = self._scene_len(scene)
                if self.rng.random() < self.p.p_boundary_transition:
                    out.append("TRANSITION")
                    continue
                if self.rng.random() < self.p.p_boundary_texture:
                    out.append(weighted(
                        self.rng, {"SETTING": 0.5, "CHARACTER_DESC": 0.2,
                                   "LORE": 0.3}))
                    continue
                out.append(scene.carrier)
                remaining -= 1
                continue
            nxt = self._scene_step(prev, cur, scene.carrier)
            out.append(nxt)
            remaining -= 1
        return out

    def chapters(self, n):
        return [self.chapter() for _ in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", type=int, default=3)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--stats", action="store_true",
                    help="print a quick mode-share summary instead of skeletons")
    ap.add_argument("--grammar",
                    default=os.path.join(HERE, "grammar_reference.json"))
    args = ap.parse_args()

    s = Sampler(Grammar(args.grammar), seed=args.seed)
    chs = s.chapters(args.chapters)
    if args.stats:
        from collections import Counter
        c = Counter(m for ch in chs for m in ch)
        tot = sum(c.values())
        for m in s.g.modes:
            print(f"{m:15s} {c[m]/tot:.3f}")
        print(f"blocks: {tot}, chapters: {len(chs)}")
    else:
        short = {"SETTING": "SET", "CHARACTER_DESC": "CHR", "LORE": "LOR",
                 "DIALOGUE": "DLG", "ACTION": "ACT", "INTERIORITY": "INT",
                 "TRANSITION": "TRN"}
        for i, ch in enumerate(chs):
            print(f"chapter {i} ({len(ch)} blocks): "
                  + " ".join(short[m] for m in ch))


if __name__ == "__main__":
    main()
