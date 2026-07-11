"""Coherence rubric (Phase 3, Emergent Coherence — instrumentation only).

Phase 3 layers *pressures* (throughline gate, arc-pressure, loop-aging, contradiction
enforcement) onto the emergent tick loop. Those pressures are empirical — build, run a
batch of ticks, read the story, tune — so we need a way to *measure* coherence before we
start dialing them. This module is that measuring stick.

It records, once per tick, a handful of deterministic signals that already exist in the
system (open-loop churn, contradictions detected, tension, goal relevance). It makes NO
generation-behavior change, performs NO enforcement, and issues NO extra chat-LLM calls.

Storage is append-only JSONL at ``<project>/memory/metrics.jsonl`` (one record per line):
O(1) appends, partial-write damage confined to the last line, and trivially plottable.
Records are read back **last-wins per tick**, so a re-run tick or a checkpoint-restore
replay never produces duplicate data points.

All recorded counts are *post-tick* snapshots — they reflect state after the scene's
entity/lore updates have been applied, because the recorder runs at the end of the tick.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arc_pressure import compute_arc_phase, compute_target_tension

logger = logging.getLogger(__name__)


GOAL_RELEVANCE_PROMPT = """You are rating how much a single scene SERVES the story's primary goal (its throughline), 0 to 10.

Rate whether the scene advances, complicates, deepens, or meaningfully bears on the goal — NOT mere topical or vocabulary overlap. A scene set in the same world with the same characters but doing nothing for the goal is LOW. A scene that moves the goal forward (even subtly, even by raising the cost of pursuing it) is HIGH.

0-1   none: no bearing on the goal
2-3   tangential: same world/characters, but does not touch the goal
4-6   connected: relates to or sets up the goal without advancing it much
7-8   advances: meaningfully moves the goal forward, or complicates/raises the stakes of it
9-10  pivotal: a decisive beat for the goal

Primary goal: {goal}

Scene:
\"\"\"
{scene_text}
\"\"\"

Respond with JSON only, no other text:
{{"relevance": <integer 0-10>, "rationale": "<one short sentence>"}}"""


def read_metrics(metrics_file: Path) -> List[Dict[str, Any]]:
    """Read a metrics JSONL file, last-wins per ``tick``, sorted by tick.

    Blank or corrupt lines are skipped, so a truncated final write never breaks reads.
    """
    metrics_file = Path(metrics_file)
    if not metrics_file.exists():
        return []

    by_tick: Dict[Any, Dict[str, Any]] = {}
    with open(metrics_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            by_tick[record.get("tick")] = record  # last-wins

    return sorted(
        by_tick.values(),
        key=lambda r: r.get("tick") if r.get("tick") is not None else -1,
    )


class CoherenceMetrics:
    """Computes and persists per-tick coherence signals. Read-only against story state."""

    def __init__(self, project_path, memory_manager, vector_store, config, llm_interface=None):
        self.project_path = Path(project_path)
        self.memory = memory_manager
        self.vector = vector_store
        self.config = config
        self.llm = llm_interface  # optional; enables the LLM goal-relevance judge
        self.metrics_file = self.project_path / "memory" / "metrics.jsonl"

    def record_tick(
        self,
        *,
        tick: int,
        scene_id: Optional[str],
        scene_text: Optional[str] = None,
        word_count: int = 0,
        tension_result: Optional[Dict[str, Any]] = None,
        goal_description: Optional[str] = None,
        contract_result: Optional[Dict[str, Any]] = None,
        finale_result: Optional[Dict[str, Any]] = None,
        loops_closed_by_beat: Optional[int] = None,
        loops_deduped: Optional[int] = None,
        loops_capped: Optional[int] = None,
        loops_expired: Optional[int] = None,
        dangling_threads: Optional[int] = None,
        thread_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute one coherence record, append it to the JSONL log, and return it."""
        loops = self.memory.load_open_loops()
        loops_opened = sum(1 for l in loops if scene_id and l.created_in_scene == scene_id)
        # "closed" means resolved: an expired loop (left open at story end) also
        # carries resolved_in_scene for the audit trail, but it was never answered
        # on the page and must not count as a closure (Phase 3, Slice 0 follow-ups).
        loops_closed = sum(1 for l in loops if scene_id and l.resolved_in_scene == scene_id
                           and l.status == "resolved")
        open_loops_total = sum(1 for l in loops if l.status == "open")

        all_lore = self.memory.load_all_lore()
        disputed_lore_total = sum(1 for l in all_lore if getattr(l, "status", "active") == "disputed")

        tension_level = None
        tension_category = None
        rewritten = False
        tension_pre_rewrite = None
        # The rubric is the instrument panel: record the scored tension whenever a
        # result exists, regardless of whether the rewrite path ran (Phase 3). Only
        # an evaluator that explicitly reports enabled=False (tension tracking off)
        # yields null; a result that never set the flag still carries the scored
        # level and must not be dropped. Rewrite-produced fields keep their
        # no-rewrite convention: rewritten stays False and tension_pre_rewrite
        # stays null unless a kept rewrite set them.
        if tension_result and tension_result.get("enabled", True):
            tension_level = tension_result.get("tension_level")
            tension_category = tension_result.get("tension_category")
            rewritten = bool(tension_result.get("rewritten", False))
            tension_pre_rewrite = tension_result.get("tension_pre_rewrite")

        # Arc-pressure adherence: target tension for this position, and the gap to actual.
        target_tension = compute_target_tension(tick, self.config)
        tension_delta = None
        if target_tension is not None and tension_level is not None:
            tension_delta = round(tension_level - target_tension, 1)

        goal_relevance, goal_relevance_method, goal_relevance_rationale = self._goal_relevance(
            tick, goal_description, scene_text
        )

        record = {
            "tick": tick,
            "scene_id": scene_id,
            "word_count": word_count,
            "loops_opened": loops_opened,
            "loops_closed": loops_closed,
            "open_loops_total": open_loops_total,
            "contradictions_detected": self._count_contradictions(tick, all_lore),
            "disputed_lore_total": disputed_lore_total,
            "tension_level": tension_level,
            "tension_category": tension_category,
            "tension_rewritten": rewritten,
            "tension_pre_rewrite": tension_pre_rewrite,
            "target_tension": target_tension,
            "tension_delta": tension_delta,
            # Arc phase (Phase 3 arc-phase mandate): lets validation runs correlate the
            # phase against achieved tension (did the resolution phase actually land calm).
            "arc_phase": compute_arc_phase(tick, self.config),
            "goal_relevance": goal_relevance,
            "goal_relevance_method": goal_relevance_method,
            "goal_relevance_rationale": goal_relevance_rationale,
            # Beat-contract adherence (Phase 3, contracts Slice 1): counts from the
            # step 11.5 postcondition check. None (not 0) when no contract ran this
            # tick (gate off, no beat, or beat without conditions), so "checked
            # nothing" and "checked and all passed" stay distinguishable.
            "contract_conditions_checked": (contract_result or {}).get("checked"),
            "contract_conditions_failed": (contract_result or {}).get("failed"),
            # Sacred finale (Phase 3): which ask-chain step produced the finale beat
            # (pending_beat | authored | template), how many fresh re-rolls were spent,
            # and how many settled-ending loops were quarantined. All None on
            # non-finale ticks, so finale ticks stay identifiable in the series.
            "finale_ask_source": (finale_result or {}).get("ask_source"),
            "finale_retries_used": (finale_result or {}).get("retries_used"),
            "finale_loops_suppressed": (finale_result or {}).get("loops_suppressed"),
            # Judged loop closure and creation hygiene (Phase 3, Slice 0 of the
            # interleaving design). Complements the loops_opened/loops_closed churn
            # counts above: loops_closed_by_beat is how many of a completed beat's
            # resolves_loops claims the judge confirmed and closed this tick;
            # loops_deduped is how many near-duplicate creations the hygiene pass
            # skipped. Both None (not 0) when the machinery did not run this tick
            # (gate off, no completed beat with claims, no creations attempted),
            # matching the contract-counter convention.
            "loops_closed_by_beat": loops_closed_by_beat,
            "loops_deduped": loops_deduped,
            # loops_capped completes the creation-hygiene picture (Phase 3, Slice 0
            # follow-ups; the 2026-07-11 validation flagged log-only cap counts):
            # how many over-cap creations were dropped this tick, None when the
            # hygiene machinery did not run.
            "loops_capped": loops_capped,
            # Finale expiry (Phase 3, Slice 0 follow-ups): on the finale tick, how
            # many still-open loops were marked expired ("left open at story end")
            # and how many of those were high/critical importance (dangling
            # threads, the story's honest unanswered-questions number). Both None
            # on every other tick, and on finale ticks with the gate off.
            "loops_expired": loops_expired,
            "dangling_threads": dangling_threads,
            # Thread registry (Phase 3, interleaving Slice T1): which thread this
            # scene served (normalized name), how many threads the registry
            # tracks, and the current consecutive same-thread run. All None
            # when attribution did not run this tick (registry failure), the
            # None-when-unavailable convention.
            "active_thread": (thread_result or {}).get("thread_name"),
            "thread_count": (thread_result or {}).get("thread_count"),
            "thread_run_length": (thread_result or {}).get("run_length"),
            # Thread identity grounding (Phase 3, interleaving Slice T1.5): how
            # this scene's thread attribution was decided (selected = the
            # beat's sanitized thread_id, label_fallback = the T1 first-label
            # path, main = the implicit fallback). None when attribution did
            # not run this tick or coherence.thread_identity is off, so
            # selection adoption is measurable per run.
            "thread_selection_source": (thread_result or {}).get("source"),
            "recorded_at": datetime.utcnow().isoformat() + "Z",
        }
        self._append(record)
        return record

    def _goal_relevance(self, tick, goal_description, scene_text):
        """How much the scene serves the primary goal, on a 0-10 scale.

        Preferred path is an LLM judge (rates *advancing the goal*, not topical overlap);
        the embedding-similarity gauge (scaled to 0-10) is the no-LLM fallback. Returns
        ``(score, method, rationale)`` — all ``None``/``""`` when there is no goal/scene.
        """
        if not (goal_description and scene_text):
            return None, None, ""

        limit = self.config.get("coherence.goal_relevance_chars", 3000)
        text = scene_text[:limit]

        if self.llm is not None and self.config.get("coherence.use_llm_goal_relevance", True):
            judged = self._llm_goal_relevance(goal_description, text)
            if judged is not None:
                return judged["score"], "llm", judged.get("rationale", "")
            # LLM unavailable/failed for this scene — fall through to the embedding gauge.

        try:
            sim = float(self.vector.compute_semantic_similarity(goal_description, text))
            return round(max(0.0, min(1.0, sim)) * 10, 1), "embedding", ""
        except Exception as e:  # similarity is best-effort; never block the record
            logger.warning(f"goal_relevance computation failed (tick {tick}): {e}")
            return None, None, ""

    def _llm_goal_relevance(self, goal_description, scene_text) -> Optional[Dict[str, Any]]:
        """Rate goal-relevance with the LLM. Returns None on failure (graceful).

        Retries once, mirroring the tension scorer / contradiction judge, so a transient
        failure falls back to the embedding gauge rather than dropping the signal.
        """
        prompt = GOAL_RELEVANCE_PROMPT.format(goal=goal_description, scene_text=scene_text)
        max_tokens = self.config.get("coherence.goal_relevance_max_tokens", 200)

        for attempt in (1, 2):
            try:
                response = self.llm.generate(prompt, max_tokens=max_tokens)
                return self._parse_goal_relevance(response)
            except Exception as e:
                if attempt == 1:
                    logger.warning(f"LLM goal-relevance judge failed, retrying: {e}")
                else:
                    logger.error(f"LLM goal-relevance judge failed after retry: {e}")
        return None

    @staticmethod
    def _parse_goal_relevance(response: str) -> Dict[str, Any]:
        """Parse the judge's JSON into ``{score, rationale}`` (score clamped 0-10)."""
        start = response.find("{")
        end = response.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("no JSON object in goal-relevance rating")
        data = json.loads(response[start:end])
        score = int(round(float(data["relevance"])))
        score = max(0, min(10, score))
        return {"score": score, "rationale": str(data.get("rationale", "")).strip()}

    def load_metrics(self) -> List[Dict[str, Any]]:
        """Return the recorded series (last-wins per tick, sorted by tick)."""
        return read_metrics(self.metrics_file)

    def _count_contradictions(self, tick: int, all_lore) -> int:
        """Count distinct contradiction pairs first detected on ``tick``.

        The detector records a verdict on *both* lore items, each stamped with its own
        ``lore.tick``; for a pair found this tick only the freshly-saved side carries
        ``detected_tick == tick``. De-duping by unordered pair counts each contradiction
        exactly once.
        """
        pairs = set()
        for lore in all_lore:
            for detail in getattr(lore, "contradiction_details", None) or []:
                if detail.get("detected_tick") == tick:
                    pairs.add(frozenset((lore.id, detail.get("with"))))
        return len(pairs)

    def _append(self, record: Dict[str, Any]) -> None:
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
