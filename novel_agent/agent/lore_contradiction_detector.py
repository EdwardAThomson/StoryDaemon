"""Lore contradiction detection (Phase 7A.4; LLM-judged in Phase 1 Emergent Coherence).

Detection pipeline:
  1. Candidate pre-filter — semantic similarity within the same category
     (cheap, recall-oriented; empirically the genuine contradictions surface as
     the nearest neighbours).
  2. Judgement — an LLM decides whether a candidate pair *logically* contradicts.
     Similarity alone cannot tell "X is passive" / "X destroys things" (a
     contradiction) from "X is trackable" / "X is trackable by its signature" (a
     restatement); both sit in the same distance band. The old type/category
     heuristic is kept only as a no-LLM fallback — it structurally misses the
     common case (fact-vs-fact contradictions).

This phase only *records* verdicts (which item is canon, and why). Enforcement —
quarantining the non-canon item out of the context the planner sees — is Phase 3.
Canon policy: the OLDER statement wins (lower tick, then lower ID). This is right
in the common case; a newer statement that corrects an erroneous older one is a
known corner case left for Phase 3 to handle.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


LORE_CONTRADICTION_JUDGE_PROMPT = """You are checking a fictional world's lore for logical contradictions.

Two world-building statements from the SAME story are below. Decide whether they LOGICALLY CONTRADICT — i.e. they cannot both be true at the same time in the same fictional world. Overlapping topics, added detail, or two different-but-compatible facts are NOT contradictions.

Statement A: {a}
Statement B: {b}

Respond with JSON only, no other text:
{{"contradicts": true or false, "reason": "one short sentence explaining why"}}"""


class LoreContradictionDetector:
    """Detects contradictions in world lore: similarity pre-filter + LLM judge."""

    def __init__(self, memory_manager, vector_store, config, llm_interface=None):
        """Initialize contradiction detector.

        Args:
            memory_manager: Memory manager for accessing lore
            vector_store: Vector store for semantic search
            config: Configuration object
            llm_interface: Optional LLM interface used to judge candidate pairs.
                When absent, the detector falls back to the type/category heuristic.
        """
        self.memory = memory_manager
        self.vector = vector_store
        self.config = config
        self.llm = llm_interface

        # Distance threshold for the candidate pre-filter
        # (lower distance = more similar; 0.0 = identical, ~2.0 = unrelated).
        self.similarity_threshold = config.get('lore.contradiction_threshold', 0.5)

    # ------------------------------------------------------------------ #
    # Detection
    # ------------------------------------------------------------------ #
    def check_for_contradictions(self, lore_id: str) -> List[Dict[str, Any]]:
        """Find lore that genuinely contradicts the given item.

        Args:
            lore_id: ID of lore to check

        Returns:
            A list of verdict dicts, one per confirmed contradiction:
            ``{"id": other_id, "reason": str, "method": "llm" | "heuristic"}``
        """
        if not self.config.get('generation.enable_lore_tracking', True):
            return []

        lore = self.memory.load_lore(lore_id)
        if not lore:
            logger.warning(f"Lore {lore_id} not found")
            return []

        # Stage 1: candidate pre-filter by semantic similarity (same category).
        similar_lore = self.vector.find_similar_lore(lore, n_results=10)

        verdicts: List[Dict[str, Any]] = []
        for similar in similar_lore:
            if similar['id'] == lore_id:
                continue
            if similar.get('distance', 1.0) >= self.similarity_threshold:
                continue

            other = self.memory.load_lore(similar['id'])
            if not other:
                continue

            # Stage 2: judge whether the candidate pair truly contradicts.
            contradicts, reason, method = self._judge_pair(lore, other)
            if contradicts:
                verdicts.append({"id": other.id, "reason": reason, "method": method})
                logger.info(
                    f"Confirmed contradiction ({method}): {lore_id} <-> {other.id} "
                    f"(distance: {similar.get('distance', -1):.3f}) — {reason}"
                )

        return verdicts

    def _judge_pair(self, lore1, lore2) -> Tuple[bool, str, str]:
        """Decide whether two candidate lore items contradict.

        Returns ``(contradicts, reason, method)``. Uses the LLM when available
        and enabled; otherwise the type/category heuristic. Any LLM failure
        degrades to "no contradiction recorded" so a tick is never broken.
        """
        use_llm = self.llm is not None and self.config.get('lore.llm_contradiction_check', True)
        if use_llm:
            verdict = self._llm_judge(lore1, lore2)
            if verdict is not None:
                contradicts, reason = verdict
                return contradicts, reason, "llm"
            # LLM unavailable/failed for this pair — graceful degradation: skip
            # rather than fall back to the unreliable heuristic and risk noise.
            return False, "", "llm_failed"

        return self._might_contradict(lore1, lore2), "type/category heuristic", "heuristic"

    def _llm_judge(self, lore1, lore2) -> Optional[Tuple[bool, str]]:
        """Ask the LLM whether two statements contradict. ``None`` on failure.

        Retries once, mirroring the extractor degradation pattern; returns None
        after a second failure so the caller can skip the pair without raising.
        """
        prompt = LORE_CONTRADICTION_JUDGE_PROMPT.format(a=lore1.content, b=lore2.content)
        max_tokens = self.config.get('lore.contradiction_max_tokens', 200)

        for attempt in (1, 2):
            try:
                response = self.llm.generate(prompt, max_tokens=max_tokens)
                return self._parse_judgement(response)
            except Exception as e:
                if attempt == 1:
                    logger.warning(f"Contradiction judge failed, retrying: {e}")
                else:
                    logger.error(f"Contradiction judge failed after retry: {e}")
        return None

    @staticmethod
    def _parse_judgement(response: str) -> Optional[Tuple[bool, str]]:
        """Parse the judge's JSON response into ``(contradicts, reason)``."""
        start = response.find('{')
        end = response.rfind('}') + 1
        if start == -1 or end == 0:
            raise ValueError("no JSON object in contradiction judgement")
        data = json.loads(response[start:end])
        contradicts = bool(data.get("contradicts", False))
        reason = str(data.get("reason", "")).strip()
        return contradicts, reason

    def _might_contradict(self, lore1, lore2) -> bool:
        """Heuristic fallback when no LLM is available.

        Coarse and known to miss fact-vs-fact contradictions — used only when
        LLM judging is disabled or unwired.
        """
        if lore1.category != lore2.category:
            return False
        if lore1.lore_type in ['rule', 'constraint'] and lore2.lore_type in ['rule', 'constraint']:
            return True
        if lore1.lore_type in ['capability', 'limitation'] and lore2.lore_type in ['capability', 'limitation']:
            return True
        return False

    # ------------------------------------------------------------------ #
    # Recording (no enforcement yet — that's Phase 3)
    # ------------------------------------------------------------------ #
    def update_contradictions(self, lore_id: str):
        """Detect and record contradictions for a freshly saved lore item.

        Records, on both items: the partner ID (``potential_contradictions``)
        and a verdict (``contradiction_details``) naming the canon (older) item
        and the reason.

        Phase 3 enforcement (``lore.enforce_contradictions``): the non-canon
        (newer) item is marked ``status = "disputed"`` so it is filtered out of
        the context the planner sees. Disputed lore is kept on disk for audit;
        the canon (older) item stays ``active``.
        """
        verdicts = self.check_for_contradictions(lore_id)
        if not verdicts:
            return

        lore = self.memory.load_lore(lore_id)
        if not lore:
            return

        enforce = self.config.get('lore.enforce_contradictions', True)

        for verdict in verdicts:
            other = self.memory.load_lore(verdict["id"])
            if not other:
                continue

            canon = self._older(lore, other)
            reason = verdict["reason"]
            method = verdict["method"]

            self._record(lore, other.id, canon.id, reason, method)
            self._record(other, lore.id, canon.id, reason, method)

            if enforce:
                # The loser is whichever item is not canon (the newer one).
                loser = other if canon.id == lore.id else lore
                loser.status = "disputed"

            self.memory.save_lore(other)

        self.memory.save_lore(lore)

    @staticmethod
    def _record(lore, other_id: str, canon_id: str, reason: str, method: str) -> None:
        """Add a contradiction link + verdict to ``lore`` (idempotent)."""
        if other_id not in lore.potential_contradictions:
            lore.potential_contradictions.append(other_id)
        if any(d.get("with") == other_id for d in lore.contradiction_details):
            return
        lore.contradiction_details.append({
            "with": other_id,
            "canon": canon_id,
            "reason": reason,
            "detected_tick": lore.tick,
            "method": method,
        })

    def _older(self, lore1, lore2):
        """Return the older lore item (canon). Lower tick wins; ties break on ID."""
        key1 = (lore1.tick, self._id_ord(lore1.id))
        key2 = (lore2.tick, self._id_ord(lore2.id))
        return lore1 if key1 <= key2 else lore2

    @staticmethod
    def _id_ord(lore_id: str) -> int:
        """Numeric ordinal of an ``L###`` id for age comparison; large on parse failure."""
        digits = ''.join(ch for ch in lore_id if ch.isdigit())
        return int(digits) if digits else 10**9

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #
    def get_contradiction_report(self) -> Dict[str, Any]:
        """Generate a report of all lore contradictions.

        Returns:
            Dictionary with contradiction information
        """
        all_lore = self.memory.load_all_lore()

        # Find all lore with contradictions
        contradicted_lore = [l for l in all_lore if l.potential_contradictions]

        # Build contradiction pairs (avoid duplicates)
        pairs = []
        seen = set()

        for lore in contradicted_lore:
            for contradiction_id in lore.potential_contradictions:
                pair_key = tuple(sorted([lore.id, contradiction_id]))
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                other_lore = self.memory.load_lore(contradiction_id)
                if other_lore:
                    pairs.append({
                        'lore_a': {
                            'id': lore.id,
                            'content': lore.content,
                            'type': lore.lore_type,
                            'category': lore.category,
                            'scene': lore.source_scene_id
                        },
                        'lore_b': {
                            'id': other_lore.id,
                            'content': other_lore.content,
                            'type': other_lore.lore_type,
                            'category': other_lore.category,
                            'scene': other_lore.source_scene_id
                        }
                    })

        return {
            'total_lore': len(all_lore),
            'contradicted_count': len(contradicted_lore),
            'contradiction_pairs': len(pairs),
            'pairs': pairs
        }
