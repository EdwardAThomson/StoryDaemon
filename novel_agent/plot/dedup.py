"""Beat-level dedup at authoring time (Phase 3 hardening).

Evidence base (docs/progress_report_20260712.md section 8.2): the triple run's
tick-6 batch authored PB006 as a near-duplicate of the still-pending PB005
(same confrontation, same cast), and the duplicate beat became a page defect,
not a cosmetic note: scene 7 shared ~9,200 characters of verbatim text with
scene 6 (SequenceMatcher ratio 0.668 against a 0.017-0.051 adjacent-pair
baseline), and the duplicated prose then minted duplicated loops (OL23/OL27).
Loop dedup cannot see beats, so this is the beat-side sibling: freshly authored
beats are fuzzy-matched against the live horizon (pending / in-progress beats),
the most recently completed beats, and earlier beats in the same batch, and a
match is dropped with a warning before it ever reaches the outline.

Gauge calibration (measured over the gitignored ``work/`` corpus at the 0712
report): plain difflib ratio alone cannot separate the species, because the
real offending pair measures 0.521 while a legitimately distinct same-batch
pair in grantrate-run measures 0.513, a 0.008 gap. Taking
``max(plain ratio, sorted-token ratio)`` fixes the separation: word-order
shuffles of the same event rise (the offending pair goes 0.521 -> 0.697, and
all confirmed duplicates measure 0.697-0.770) while genuinely distinct beats
stay low (max observed 0.574). The default threshold 0.65
(``generation.beat_dedup_threshold``) splits that gap, deliberately keeping
the one ambiguous escalation-retread specimen at 0.644: dropping a legitimate
beat costs the story more than letting a near-duplicate through.

Deterministic, no LLM. Shared by BOTH beat-authoring paths (the house
convention, like loop_closure.sanitize_beat_loop_claims): the agent path calls
it inside ``PlotOutlineManager.add_beats`` (plot/manager.py) and the CLI path
calls it next to the other sanitizers (cli/commands/plot.py), so the two
cannot drift. Never raises; any problem (unreadable outline, broken config)
keeps all beats (graceful degradation).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, List, Sequence, Tuple

# How many of the most recently completed beats stay in the comparison window.
# Pending / in-progress beats are always candidates (the offending species was
# authored against a still-pending twin); a beat completed a tick or two ago
# can still spawn a duplicate, but old completed beats are legitimate history
# the story may deliberately echo.
RECENTLY_COMPLETED_WINDOW = 3

# Statuses that mean "this beat already executed" (legacy outlines use
# "executed"), matching the treatment in cli/commands/plot.py.
_COMPLETED_STATUSES = ("completed", "executed")

# Descriptions shorter than this many words are exempt from dedup: difflib is
# noise on very short strings ("beat 1" vs "beat 2" measures 0.833 while being
# obviously distinct), and a real beat description is a 10-20 word sentence
# (the line-fallback parser already rejects under-3-word fragments outright).
MIN_DEDUP_WORDS = 4

_WORD_RE = re.compile(r"[a-z0-9']+")


def beat_similarity(a: str, b: str) -> float:
    """Similarity of two beat descriptions in [0, 1] (the calibrated gauge).

    ``max(plain difflib ratio, sorted-token difflib ratio)`` on case-insensitive
    text: the plain ratio catches shared phrasing in order, the sorted-token
    variant catches the word-order-shuffled duplicate species that plain difflib
    under-scores (see the module docstring for the measured separation).
    """
    left = (a or "").strip().lower()
    right = (b or "").strip().lower()
    if not left or not right:
        return 0.0
    plain = SequenceMatcher(None, left, right).ratio()
    left_sorted = " ".join(sorted(_WORD_RE.findall(left)))
    right_sorted = " ".join(sorted(_WORD_RE.findall(right)))
    token_sorted = SequenceMatcher(None, left_sorted, right_sorted).ratio()
    return max(plain, token_sorted)


def _candidate_beats(existing_beats: Sequence[Any]) -> List[Any]:
    """The comparison window: all pending/in-progress beats plus the last
    ``RECENTLY_COMPLETED_WINDOW`` completed ones, in outline order."""
    live: List[Any] = []
    completed: List[Any] = []
    for beat in existing_beats or []:
        status = getattr(beat, "status", "pending") or "pending"
        if status in ("pending", "in_progress"):
            live.append(beat)
        elif status in _COMPLETED_STATUSES:
            completed.append(beat)
    return completed[-RECENTLY_COMPLETED_WINDOW:] + live


def _beat_label(beat, position: int) -> str:
    """A beat's id when assigned, else its 1-based batch position."""
    beat_id = getattr(beat, "id", "") or ""
    return beat_id if beat_id else f"batch position {position}"


def dedup_new_beats(
    new_beats: Sequence[Any],
    existing_beats: Sequence[Any],
    config,
) -> Tuple[List[Any], List[str]]:
    """Drop freshly authored beats that duplicate the live horizon or the batch.

    Each new beat's description is compared (``beat_similarity``) against the
    window from ``existing_beats`` (pending / in-progress beats plus the
    ``RECENTLY_COMPLETED_WINDOW`` most recently completed) and against the
    earlier KEPT beats of the same batch; a similarity at or above
    ``generation.beat_dedup_threshold`` drops the beat with a warning naming
    the match and the measured ratio. Returns ``(kept_beats, warnings)``.

    Gated by ``generation.beat_dedup`` (default True). Never raises: any
    internal problem returns all beats unchanged, the same
    ledger-unreadable-keeps-all rule the loop dedup follows.
    """
    beats = list(new_beats or [])
    try:
        if not config.get('generation.beat_dedup', True):
            return beats, []
        threshold = float(config.get('generation.beat_dedup_threshold', 0.65))

        candidates: List[Tuple[str, str]] = []  # (label, description)
        for beat in _candidate_beats(existing_beats):
            description = (getattr(beat, "description", "") or "").strip()
            if description and len(_WORD_RE.findall(description.lower())) >= MIN_DEDUP_WORDS:
                candidates.append((getattr(beat, "id", "") or "?", description))

        kept: List[Any] = []
        warnings: List[str] = []
        for position, beat in enumerate(beats, start=1):
            description = (getattr(beat, "description", "") or "").strip()
            if len(_WORD_RE.findall(description.lower())) < MIN_DEDUP_WORDS:
                kept.append(beat)  # empty or too short for the gauge; other sanitizers govern
                continue
            match = None  # (label, ratio), best at or above the threshold
            for label, existing_desc in candidates:
                ratio = beat_similarity(description, existing_desc)
                if ratio >= threshold and (match is None or ratio > match[1]):
                    match = (label, ratio)
            if match is not None:
                warnings.append(
                    f"dropped duplicate beat ({_beat_label(beat, position)}): "
                    f"\"{description[:90]}\" matches beat {match[0]} at "
                    f"similarity {match[1]:.3f} (threshold {threshold:g})"
                )
                continue
            kept.append(beat)
            # Earlier kept beats of this batch join the window (within-batch dedup).
            candidates.append((_beat_label(beat, position), description))
        return kept, warnings
    except Exception:
        return beats, []
