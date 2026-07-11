"""Judged loop closure and creation hygiene (Phase 3, Slice 0 of the interleaving design).

Evidence base (docs/progress_report_20260710.md): the descent validation runs
opened 70-83 loops each and closed 0-2. Beats' ``resolves_loops`` claims are
parsed, stored, and displayed, and were never applied anywhere; the fact
extractor's own ``open_loops_resolved`` path requires it to scan 70+ loops and
cite exact IDs unprompted (an impossible retrieval feat) and near-never fires.
Slice 0 inverts the task into the easy discriminative direction: beat completion
NOMINATES the loops its author claimed it resolves, and a focused one-loop,
one-scene LLM judge CONFIRMS each claim before anything is closed. Every closure
is auditable via the loop's ``resolution_summary``.

This module holds the pure logic (the finale.py pattern); agent.py keeps only
thin hooks. The judged closure is gated by ``coherence.loop_closure`` (default
False for its first validation run). Graceful degradation throughout: no
function here may kill a tick.

Interplay notes: the finale loop quarantine (finale.py, suppress_finale_loops)
is a separate, ending-only discipline and is untouched. The extractor's
``open_loops_resolved`` path stays as-is (it occasionally works). The
``loop_resolved`` contract check stays gated in authoring
(contracts/authoring.py, GATED_AUTHORING_CHECKS); this judged closure is the
prerequisite for un-gating it later, once validated.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .prompts import format_loop_closure_prompt

logger = logging.getLogger(__name__)

# Beats claim 0-3 loops in practice; a defensive cap keeps a pathological beat
# from turning one completion into a judge marathon (the MAX_CONDITIONS_PER_BEAT
# move, applied to closure nominations).
MAX_CLAIMS_JUDGED = 3


# ---------------------------------------------------------------------------
# Nomination
# ---------------------------------------------------------------------------

def claimed_open_loops(beat, memory) -> List[Any]:
    """The beat's ``resolves_loops`` claims resolved to loops that exist and are open.

    Claims are deduplicated preserving order; phantom IDs (pre-sanitized at
    authoring, but a legacy outline may still carry them) and loops that are not
    open are skipped with a log line, never an error. At most MAX_CLAIMS_JUDGED
    nominations are returned. Never raises.
    """
    claims: List[str] = []
    for claim in getattr(beat, "resolves_loops", None) or []:
        if claim not in claims:
            claims.append(claim)
    if not claims:
        return []

    try:
        loops_by_id = {loop.id: loop for loop in memory.load_open_loops()}
    except Exception as e:
        logger.warning(f"Loop closure could not read the loop ledger: {e}")
        return []

    nominated = []
    for claim in claims:
        loop = loops_by_id.get(claim)
        if loop is None:
            logger.info(f"Beat {getattr(beat, 'id', '?')} claims unknown loop {claim!r}; skipping")
            continue
        if getattr(loop, "status", "open") != "open":
            logger.info(f"Beat {getattr(beat, 'id', '?')} claims loop {claim} "
                        f"(status {getattr(loop, 'status', '?')}); skipping")
            continue
        nominated.append(loop)

    if len(nominated) > MAX_CLAIMS_JUDGED:
        logger.info(f"Beat {getattr(beat, 'id', '?')} nominates {len(nominated)} loops; "
                    f"judging the first {MAX_CLAIMS_JUDGED}")
        nominated = nominated[:MAX_CLAIMS_JUDGED]
    return nominated


# ---------------------------------------------------------------------------
# The focused judge
# ---------------------------------------------------------------------------

def judge_loop_resolution(llm, loop_description: str, scene_text: str, config) -> Optional[Dict[str, Any]]:
    """One small LLM check: did this scene resolve this single loop?

    The judge sees ONE loop's description plus the scene text and answers
    strictly ``{"resolved": true/false, "reason": "<one short sentence>"}``,
    which is the easy discriminative inversion of the extractor's impossible
    scan-everything task. Retries once on a parse failure or call error; a
    double failure returns None, which the caller must treat as NOT resolved.
    Never raises.
    """
    if llm is None:
        return None
    chars = config.get('coherence.loop_closure_scene_chars', 12000)
    prompt = format_loop_closure_prompt(loop_description or "", (scene_text or "")[:chars])
    max_tokens = config.get('coherence.loop_closure_max_tokens', 200)
    for attempt in (1, 2):
        try:
            response = llm.generate(prompt, max_tokens=max_tokens)
            return _parse_loop_judgment(response)
        except Exception as e:
            if attempt == 1:
                logger.warning(f"Loop-closure judge failed, retrying: {e}")
            else:
                logger.error(f"Loop-closure judge failed after retry: {e}")
    return None


def _parse_loop_judgment(response: str) -> Dict[str, Any]:
    """Parse the judge's JSON verdict into ``{resolved, reason}``.

    Accepts a bool or a yes/no/true/false string for the verdict; anything else
    raises (so the caller's retry-once policy applies). Same shape discipline as
    the finale screen parser.
    """
    start = response.find("{")
    end = response.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("no JSON object in loop-closure judgment")
    data = json.loads(response[start:end])
    verdict = data["resolved"]
    if isinstance(verdict, str):
        lowered = verdict.strip().lower()
        if lowered in ("true", "yes"):
            verdict = True
        elif lowered in ("false", "no"):
            verdict = False
    if not isinstance(verdict, bool):
        raise ValueError(f"unusable loop-closure verdict {data['resolved']!r}")
    return {"resolved": verdict, "reason": str(data.get("reason", "")).strip()}


# ---------------------------------------------------------------------------
# The full closure pass for one completed beat
# ---------------------------------------------------------------------------

def close_claimed_loops(llm, memory, beat, scene_id: str, scene_text: str, config) -> Optional[Dict[str, Any]]:
    """Judge and close a completed beat's claimed loops.

    Returns ``{"beat_id", "claimed", "judged", "closed"}``, or None when the
    ``coherence.loop_closure`` gate is off (default False, first-validation-run
    promise) or the beat claims nothing; the caller records None in the rubric
    so "did not run" and "ran and closed nothing" stay distinguishable. On a
    confirmed claim the loop is resolved with an auditable summary
    ("closed via beat <PBxxx>; judge: <reason>"). A judge "no", a parse failure
    after the retry, or any exception closes nothing. Never raises.
    """
    try:
        if not config.get('coherence.loop_closure', False):
            return None
        claims = list(getattr(beat, "resolves_loops", None) or [])
        if not claims:
            return None

        beat_id = getattr(beat, "id", "") or "?"
        result: Dict[str, Any] = {
            "beat_id": beat_id,
            "claimed": claims,
            "judged": 0,
            "closed": [],
        }
        for loop in claimed_open_loops(beat, memory):
            verdict = judge_loop_resolution(llm, loop.description, scene_text, config)
            result["judged"] += 1
            if not (verdict and verdict.get("resolved")):
                logger.info(f"Loop {loop.id} claimed by beat {beat_id} not confirmed "
                            f"resolved; leaving open")
                continue
            summary = f"closed via beat {beat_id}; judge: {verdict.get('reason', '')}"
            try:
                memory.resolve_open_loop(loop_id=loop.id, scene_id=scene_id, summary=summary)
                result["closed"].append(loop.id)
                logger.info(f"Closed loop {loop.id} ({summary})")
            except Exception as e:
                logger.error(f"Failed to close confirmed loop {loop.id}: {e}")
        return result
    except Exception as e:
        logger.warning(f"Judged loop closure failed for beat {getattr(beat, 'id', '?')}: {e}")
        return None


# ---------------------------------------------------------------------------
# Authoring hygiene: sanitize loop claims on freshly authored beats
# ---------------------------------------------------------------------------

def sanitize_beat_loop_claims(beats, memory) -> List[str]:
    """Drop ``resolves_loops`` entries that match no existing loop ID, in place.

    Sanitize-not-trust, the sibling of ``_resolve_beat_references`` and
    ``sanitize_beat_conditions``, shared by both beat-authoring paths
    (plot/manager.py and cli/commands/plot.py) so they cannot drift. Authored
    claims sometimes reference phantom loop IDs (a live run authored
    "OL39_corul_meeting_setup", which exists nowhere); a phantom claim can never
    be confirmed and only pollutes the audit trail. ``creates_loops`` is
    deliberately left alone: its entries are free-text labels for loops the
    beat intends to OPEN, not references to existing IDs, so there is nothing
    to check them against. Returns human-readable warnings; never raises. When
    the loop ledger cannot be read, claims are kept unchanged (graceful
    degradation, matching the sanitizer's None-roster convention).
    """
    warnings: List[str] = []
    try:
        known = {loop.id for loop in memory.load_open_loops()}
    except Exception as e:
        logger.warning(f"Loop-claim sanitization skipped (ledger unreadable): {e}")
        return warnings

    for beat in beats:
        claims = getattr(beat, "resolves_loops", None) or []
        if not claims:
            continue
        kept = [c for c in claims if c in known]
        dropped = [c for c in claims if c not in known]
        if dropped:
            label = getattr(beat, "id", "") or "?"
            warnings.append(
                f"beat {label}: dropped resolves_loops {dropped}: no such loop ID(s)"
            )
            beat.resolves_loops = kept
    return warnings
