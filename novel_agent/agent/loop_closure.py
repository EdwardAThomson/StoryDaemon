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
True since the 2026-07-11 validation run passed,
docs/progress_report_20260711.md: 13 claims judged, 3 honest closures, 10
correct refusals, 0 parse failures). Graceful degradation throughout: no
function here may kill a tick.

Phase 3, Slice 0 follow-ups (same validation run): the extractor's
``open_loops_resolved`` path mass-swept 47 loops closed at the finale with no
per-loop audit, so its claims now face the SAME judge before anything closes
(``judge_extractor_resolutions``, bounded per tick), and on the finale tick the
still-open remainder is marked "expired" instead of silently swept
(``expire_open_loops_at_finale``): a story that ends with unanswered loops
LEAVES them, it does not resolve them. Both are gated by the same
``coherence.loop_closure`` flag so A/B against the old behavior stays possible.

Interplay notes: the finale loop quarantine (finale.py, suppress_finale_loops)
is a separate, ending-only discipline and is untouched. The
``loop_resolved`` contract check stays gated in authoring
(contracts/authoring.py, GATED_AUTHORING_CHECKS); with the resolves-vs-advances
claim reframe shipped, re-measuring the judge's grant rate is the remaining
prerequisite for un-gating it.
"""

import json
import logging
import re
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

    Returns ``{"beat_id", "claimed", "judged", "closed", "refused"}``, or None
    when the ``coherence.loop_closure`` gate is off (default True since the
    2026-07-11 validation run) or the beat claims nothing; the caller records
    None in the rubric so "did not run" and "ran and closed nothing" stay
    distinguishable. On a confirmed claim the loop is resolved with an
    auditable summary ("closed via beat <PBxxx>; judge: <reason>"). A judge
    "no", a parse failure after the retry, or any exception closes nothing;
    refusals are recorded as ``{"loop", "reason"}`` entries so the "no" reasons
    survive in run artifacts (the validation flagged info-level-only refusal
    logging as an observability gap). Never raises.
    """
    try:
        if not config.get('coherence.loop_closure', True):
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
            "refused": [],
        }
        for loop in claimed_open_loops(beat, memory):
            verdict = judge_loop_resolution(llm, loop.description, scene_text, config)
            result["judged"] += 1
            if not (verdict and verdict.get("resolved")):
                reason = (verdict or {}).get("reason") or "judge unavailable"
                result["refused"].append({"loop": loop.id, "reason": reason})
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
# Extractor-claimed resolutions: the same judge, before anything closes
# (Phase 3, Slice 0 follow-ups)
# ---------------------------------------------------------------------------

def judge_extractor_resolutions(llm, memory, claims, scene_id: str, scene_text: str,
                                config) -> Optional[Dict[str, Any]]:
    """Judge the fact extractor's ``open_loops_resolved`` claims before any close.

    The 2026-07-11 validation run (docs/progress_report_20260711.md section 4)
    caught this path mass-sweeping 47 loops closed at the finale with the
    audit-free summary "Resolved in scene S015", so extractor claims now face
    the SAME one-loop, one-scene judge as beat claims. Claim IDs normalize like
    beat claims (colon-suffixed lines accepted, phantoms dropped with a
    warning); at most ``coherence.extractor_resolutions_judged_cap`` claims are
    judged per tick (default 5; None or 0 disables), the rest ignored with a
    warning naming them. A confirmed claim closes with the auditable summary
    "closed via extractor claim; judge: <reason>"; a judge "no" or failure
    leaves the loop open and records the refusal. Returns
    ``{"claimed", "judged", "closed", "refused", "capped"}``, or None when
    there are no claims. Never raises. The caller owns the
    ``coherence.loop_closure`` gate: off means not calling this at all, so the
    old unjudged behavior is restored exactly (A/B stays possible).
    """
    try:
        raw_claims = [c for c in (claims or []) if c]
        if not raw_claims:
            return None
        result: Dict[str, Any] = {
            "claimed": list(raw_claims),
            "judged": 0,
            "closed": [],
            "refused": [],
            "capped": [],
        }

        try:
            loops_by_id = {loop.id: loop for loop in memory.load_open_loops()}
        except Exception as e:
            logger.warning(f"Extractor-resolution judging could not read the loop ledger: {e}")
            return result

        known = set(loops_by_id)
        nominated: List[Any] = []
        for claim in raw_claims:
            normalized = _normalize_loop_claim(claim, known)
            if normalized is None:
                logger.warning(f"Extractor claims unknown loop {claim!r}; skipping")
                continue
            loop = loops_by_id[normalized]
            if getattr(loop, "status", "open") != "open":
                logger.info(f"Extractor claims loop {normalized} "
                            f"(status {getattr(loop, 'status', '?')}); skipping")
                continue
            if all(l.id != normalized for l in nominated):
                nominated.append(loop)

        cap = int(config.get('coherence.extractor_resolutions_judged_cap', 5) or 0)
        if cap > 0 and len(nominated) > cap:
            over = [l.id for l in nominated[cap:]]
            result["capped"] = over
            logger.warning(f"Extractor claimed {len(nominated)} loop resolutions; judging "
                           f"the first {cap}, ignoring: {', '.join(over)}")
            nominated = nominated[:cap]

        for loop in nominated:
            verdict = judge_loop_resolution(llm, loop.description, scene_text, config)
            result["judged"] += 1
            if not (verdict and verdict.get("resolved")):
                reason = (verdict or {}).get("reason") or "judge unavailable"
                result["refused"].append({"loop": loop.id, "reason": reason})
                logger.info(f"Extractor claim on loop {loop.id} not confirmed resolved; "
                            f"leaving open")
                continue
            summary = f"closed via extractor claim; judge: {verdict.get('reason', '')}"
            try:
                memory.resolve_open_loop(loop_id=loop.id, scene_id=scene_id, summary=summary)
                result["closed"].append(loop.id)
                logger.info(f"Closed loop {loop.id} ({summary})")
            except Exception as e:
                logger.error(f"Failed to close confirmed loop {loop.id}: {e}")
        return result
    except Exception as e:
        logger.warning(f"Judged extractor resolutions failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Finale expiry: honest end-of-story accounting (Phase 3, Slice 0 follow-ups)
# ---------------------------------------------------------------------------

def expire_open_loops_at_finale(memory, scene_id: str) -> Optional[Dict[str, Any]]:
    """Mark every still-open loop "expired" at the story's end.

    A story that ends with unanswered loops LEAVES them, it does not resolve
    them: "resolved" is reserved for questions answered on the page. Runs
    AFTER the finale's own judged closures, so anything the judge confirmed is
    already resolved; the remainder becomes terminal-but-distinct
    (status "expired", resolution_summary "left open at story end",
    resolved_in_scene the finale scene). Returns
    ``{"expired": [ids], "dangling_threads": n}`` where dangling_threads counts
    expired loops of high or critical importance (the story's honest
    unanswered-questions number), or None on failure. Never raises.
    """
    try:
        loops = memory.load_open_loops()
        expired: List[str] = []
        dangling = 0
        for loop in loops:
            if getattr(loop, "status", "open") != "open":
                continue
            loop.status = "expired"
            loop.resolution_summary = "left open at story end"
            loop.resolved_in_scene = scene_id
            expired.append(loop.id)
            if getattr(loop, "importance", "medium") in ("high", "critical"):
                dangling += 1
        if expired:
            memory.save_open_loops(loops)
        return {"expired": expired, "dangling_threads": dangling}
    except Exception as e:
        logger.warning(f"Finale loop expiry failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Authoring hygiene: sanitize loop claims on freshly authored beats
# ---------------------------------------------------------------------------

# Both loop-claim fields are sanitized identically (Phase 3, Slice 0
# follow-ups: the resolves-vs-advances reframe added advances_loops).
LOOP_CLAIM_FIELDS = ("resolves_loops", "advances_loops")


def sanitize_beat_loop_claims(beats, memory) -> List[str]:
    """Drop ``resolves_loops``/``advances_loops`` entries that match no existing
    loop ID, in place.

    Sanitize-not-trust, the sibling of ``_resolve_beat_references`` and
    ``sanitize_beat_conditions``, shared by both beat-authoring paths
    (plot/manager.py and cli/commands/plot.py) so they cannot drift. Authored
    claims sometimes reference phantom loop IDs (a live run authored
    "OL39_corul_meeting_setup", which exists nowhere); a phantom claim can never
    be confirmed and only pollutes the audit trail. Both claim fields get the
    same treatment (colon-suffixed lines normalize to the bare ID, phantoms are
    dropped with a warning naming the field). ``creates_loops`` is
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
        for field_name in LOOP_CLAIM_FIELDS:
            claims = getattr(beat, field_name, None) or []
            if not claims:
                continue
            kept: List[str] = []
            dropped: List[str] = []
            for claim in claims:
                normalized = _normalize_loop_claim(claim, known)
                if normalized is not None:
                    if normalized not in kept:
                        kept.append(normalized)
                else:
                    dropped.append(claim)
            if dropped or kept != claims:
                label = getattr(beat, "id", "") or "?"
                if dropped:
                    warnings.append(
                        f"beat {label}: dropped {field_name} {dropped}: no such loop ID(s)"
                    )
                setattr(beat, field_name, kept)
    return warnings


def _normalize_loop_claim(claim, known) -> Optional[str]:
    """The known loop ID a claim refers to, or None for a true phantom.

    Models copy the prompt's rendered loop line ("OL4: What is Kessler-Vex...")
    instead of the bare ID, which the 2026-07-11 Slice 0 validation run showed
    silently disarms judged closure (two valid claims stripped as phantoms).
    Accept the exact ID, or a leading ID token followed by a non-word boundary
    (so "OL4: description" normalizes to "OL4" while an invented label like
    "OL39_corul_meeting_setup" stays a phantom and is dropped).
    """
    if not isinstance(claim, str):
        return None
    text = claim.strip()
    if text in known:
        return text
    match = re.match(r"(OL\d+)\b", text)
    if match and match.group(1) in known:
        return match.group(1)
    return None
