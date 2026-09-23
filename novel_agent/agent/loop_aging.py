"""Loop-aging gauge (Phase 3, loop-aging Slice L1).

Loop-aging is the pressure that makes older open loops surface louder so they
get paid off. This module is its GAUGE, shipped instrument-only in the house
tradition (measure before pressure): every tick it computes how old the open
loops are, what kind of question each one is, and which of them the planner was
actually shown. Nothing here changes planning, selection or authoring.

Why a gauge first, and why this one. A corpus read of the 26 novels under
work/novels/ (tables in docs/LOOP_AGING_BASELINE.md) found 1,548 loops with a
birth scene, 220 of which ever closed, and closure that is near-immediate or
never (108 of the 220 closed within two ticks). It also found that the registry
is not all story debt:

- 34 percent are either/or suspense questions and 14 percent carry their own
  deadline ("before she leaves the building", "within 90 seconds"). These are
  answered by the story simply continuing, so the closure judge rightly never
  closes them. Pressuring the planner to "pay off" one of these would buy
  nothing.
- A handful restate the story's central question ("what is the full scope of
  the conspiracy"), which is SUPPOSED to stay open until the finale.
- The rest are genuine arc loops, and they are the only ones a payoff pressure
  should ever point at.

So the gauge reports a ``horizon`` per loop, not just an age. Classification is
deterministic and cheap, which also lets it backfill every loop already on disk
and give the pressure slice a pre-change baseline. Its agreement with a
hand-labelled sample is published in docs/LOOP_AGING_BASELINE.md; a poor
agreement rate is the evidence for replacing it with an anchored judge, the way
the keyword tension heuristic and the embedding goal-relevance metric were
replaced.

Age is deliberately measured as a FRACTION of story length rather than in
ticks: 8 ticks is half a 16-tick book and a fifth of a 40-tick one. Importance
cannot do this job, because 62 percent of the corpus's loops are marked
"critical" and none are marked "low".

Pure logic (the loop_closure.py / thread_construction.py pattern): stdlib only,
no LLM calls, no I/O, no state. Every entry point degrades to a None/empty
answer rather than raising, so a gauge failure can never cost a tick.
"""

import logging
import re
from difflib import SequenceMatcher
from statistics import median
from typing import Any, Dict, List, Optional, Sequence

from .arc_pressure import remaining_story_ticks

logger = logging.getLogger(__name__)

# The three horizons. "scene" is suspense with a one-scene lifespan, "arc" is a
# reader-facing question with a payable answer, "throughline" is the story's own
# central question restated as a loop.
HORIZON_SCENE = "scene"
HORIZON_ARC = "arc"
HORIZON_THROUGHLINE = "throughline"
HORIZONS = (HORIZON_SCENE, HORIZON_ARC, HORIZON_THROUGHLINE)

# Loop statuses that still represent debt. "resolved" is answered and "expired"
# is terminal-but-distinct (left open at story end), the same split _open_loops
# and _active_lore already make for the planner.
OPEN_STATUS = "open"

# A binary opener: the question can be answered "yes" or "no", which the prose
# does by continuing rather than by announcing anything.
_BINARY_OPENER = re.compile(
    r"^(will|would|does|do|did|is|are|was|were|has|have|had|can|could|should|if)\b",
    re.IGNORECASE,
)

# An either/or question ("Will she sign, or will she refuse?"): a choice point,
# which the next scene settles by staging one branch.
_EITHER_OR = re.compile(r"\bor\b[^?]*\?\s*$", re.IGNORECASE)

# Deadline markers: the loop dates itself. Any one of these means the question
# is about the next few minutes or hours of story time, so it is stale as debt
# within a tick or two whatever the ledger says.
_DEADLINE_WORDS = (
    "before",
    "within",
    "tonight",
    "tomorrow",
    "immediately",
    "in time",
    "right now",
    "by morning",
    "next scene",
)
_DEADLINE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _DEADLINE_WORDS) + r")\b"
    r"|\b\d+\s*(?:second|minute|hour|day|week)s?\b",
    re.IGNORECASE,
)

# Throughline idioms: the shapes the extractor uses when it re-registers the
# story's central question as though it were one loop among many.
_THROUGHLINE_WORDS = (
    "full scope",
    "true scope",
    "true agenda",
    "true objective",
    "true purpose",
    "true motive",
    "how high",
    "how deep",
    "how far up",
    "extent of",
    "entire conspiracy",
    "whole conspiracy",
    "ultimate",
)
_THROUGHLINE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _THROUGHLINE_WORDS) + r")\b",
    re.IGNORECASE,
)

# A loop description this close to the story's primary goal IS the primary goal.
# The loop-dedup precedent (0.75 after two documented ~0.78 near-misses) is the
# reference; this sits higher because a false throughline call exempts a real
# loop from every future pressure.
GOAL_MATCH_THRESHOLD = 0.8

# Importance is a near-dead signal (corpus: 967 critical, 554 high, 27 medium, 0
# low out of 1,548), but where it is read it must at least be ordered correctly.
# A string sort put "critical" LAST for a year; this map is the fix.
IMPORTANCE_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}

_SCENE_ID_RE = re.compile(r"^S(\d+)$")

# Only arc loops can be overdue. A scene loop was never debt and a throughline
# is meant to stay open to the last page, so counting either as overdue would
# aim the pressure slice at noise.
OVERDUE_HORIZONS = (HORIZON_ARC,)

# Ids listed in a metrics record; the count is always exact, the list is capped
# so one tick's record cannot grow unbounded on a 70-loop ledger.
MAX_LISTED_IDS = 10


def _text(value: Any) -> str:
    return (value or "").strip() if isinstance(value, str) else ""


def is_open(loop: Any) -> bool:
    """True for a loop that still represents debt (status "open")."""
    return getattr(loop, "status", OPEN_STATUS) == OPEN_STATUS


def birth_tick(loop: Any) -> Optional[int]:
    """The tick a loop was created on.

    ``created_tick`` when the loop carries it (everything minted from Slice L1
    on), else parsed from ``created_in_scene`` ("S007" -> 7), which is exact for
    every project on disk because scene ids are allocated one per tick. None
    when neither is available, and callers must treat None as "unknown age"
    rather than as zero.
    """
    try:
        recorded = getattr(loop, "created_tick", None)
        if isinstance(recorded, bool):
            return None
        if isinstance(recorded, int) and recorded >= 0:
            return recorded
        match = _SCENE_ID_RE.match(_text(getattr(loop, "created_in_scene", "")))
        if match:
            return int(match.group(1))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"birth_tick failed: {e}")
    return None


def loop_age(loop: Any, current_tick: Any) -> Optional[int]:
    """Age of a loop in ticks, or None when the birth tick is unknown."""
    born = birth_tick(loop)
    if born is None or not isinstance(current_tick, int) or isinstance(current_tick, bool):
        return None
    return max(current_tick - born, 0)


def classify_horizon(description: Any,
                     primary_goal_description: Any = None) -> str:
    """The kind of question a loop asks: scene, throughline or arc.

    Order matters. Throughline is tested first, because the story's central
    question often also reads as a binary ("Is the conspiracy ongoing, or has
    the data already moved?") and must never be filed as scene-local suspense.
    Scene is then a deadline in the text, or a binary opener that is also an
    either/or choice; a binary opener alone is too broad, since "Will the
    cooperation agreement protect him?" runs the length of a book. Everything
    else is an arc loop, which is the default on purpose: the pressure slice
    will point at arc loops, and a misfiled arc loop is a missed payoff while a
    misfiled scene loop is a wasted demand.
    """
    text = _text(description)
    if not text:
        return HORIZON_ARC
    try:
        if _THROUGHLINE_RE.search(text):
            return HORIZON_THROUGHLINE
        goal = _text(primary_goal_description)
        if goal:
            ratio = SequenceMatcher(None, text.lower(), goal.lower()).ratio()
            if ratio >= GOAL_MATCH_THRESHOLD:
                return HORIZON_THROUGHLINE
        if _DEADLINE_RE.search(text):
            return HORIZON_SCENE
        if _BINARY_OPENER.match(text) and _EITHER_OR.search(text):
            return HORIZON_SCENE
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"classify_horizon failed: {e}")
    return HORIZON_ARC


def horizon_of(loop: Any, primary_goal_description: Any = None) -> str:
    """A loop's stored horizon, classified on the fly when it has none.

    Stored values win, so a hand-corrected horizon survives; legacy loops (and
    anything minted before this slice) are classified from the description.
    """
    stored = _text(getattr(loop, "horizon", None))
    if stored in HORIZONS:
        return stored
    return classify_horizon(getattr(loop, "description", ""), primary_goal_description)


def stale_threshold(config: Any) -> Optional[int]:
    """Ticks of age past which an arc loop is overdue, or None if unknowable.

    ``loop_stale_fraction`` of ``coherence.target_story_length``, floored at
    ``loop_stale_floor_ticks`` so a short run does not flag every loop at tick
    2. The corpus is what sets the working point: closures land at a median 3
    ticks (0.19 of a 16-tick run) while loops left unresolved at the end sit at
    a median 7 (0.44), so 0.3 falls between what the system does manage and what
    it abandons.
    """
    try:
        length = config.get('coherence.target_story_length', None)
        fraction = config.get('coherence.loop_stale_fraction', 0.3)
        floor = config.get('coherence.loop_stale_floor_ticks', 3)
        floor = int(floor) if floor is not None else 0
        if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
            return None
        return max(floor, int(round(float(fraction) * length)))
    except Exception as e:
        logger.debug(f"stale_threshold failed: {e}")
        return None


def staleness(loop: Any, current_tick: Any, config: Any,
              primary_goal_description: Any = None) -> Dict[str, Any]:
    """Age, story fraction, remaining runway and the overdue verdict for a loop.

    ``overdue`` is True only for an OPEN ARC loop whose age is at or past the
    threshold. Unknown age, unknown story length, a scene loop, a throughline
    and a closed loop all yield False rather than an error, so a caller can use
    the flag directly.
    """
    report = {
        "id": _text(getattr(loop, "id", "")),
        "horizon": horizon_of(loop, primary_goal_description),
        "age": loop_age(loop, current_tick),
        "fraction": None,
        "remaining": remaining_story_ticks(current_tick, config) if isinstance(current_tick, int) else None,
        "threshold": stale_threshold(config),
        "overdue": False,
    }
    try:
        length = config.get('coherence.target_story_length', None)
        if report["age"] is not None and isinstance(length, int) and length > 0:
            report["fraction"] = round(report["age"] / length, 3)
        if (is_open(loop)
                and report["horizon"] in OVERDUE_HORIZONS
                and report["age"] is not None
                and report["threshold"] is not None):
            report["overdue"] = report["age"] >= report["threshold"]
    except Exception as e:
        logger.debug(f"staleness failed: {e}")
    return report


def age_report(loops: Sequence[Any],
               current_tick: Any,
               config: Any,
               shown_ids: Optional[Sequence[str]] = None,
               primary_goal_description: Any = None) -> Dict[str, Any]:
    """The per-tick loop-age payload recorded in metrics.jsonl.

    ``shown_ids`` is what the planner was actually shown this tick (the
    multi-stage planner's ``relevant_loops``). The decisive pair in this record
    is ``shown_oldest_age`` against ``unshown_oldest_age``: if the loops the
    planner never sees are systematically older, the pressure slice is a
    selection change; if the old loops are on the page and ignored, it is a
    mandate. Returns ``{"enabled": False}`` when loop-aging is off, and never
    raises.
    """
    try:
        if not config.get('coherence.loop_aging', True):
            return {"enabled": False}
    except Exception:
        pass

    payload: Dict[str, Any] = {
        "enabled": True,
        "open_total": 0,
        "oldest_age": None,
        "oldest_id": None,
        "median_age": None,
        "by_horizon": {h: 0 for h in HORIZONS},
        "overdue_total": 0,
        "overdue_ids": [],
        "stale_threshold": stale_threshold(config),
        "shown_total": 0,
        "shown_oldest_age": None,
        "unshown_oldest_age": None,
        "shown": [],
    }
    try:
        shown = {s for s in (shown_ids or []) if isinstance(s, str)}
        open_loops = [l for l in (loops or []) if is_open(l)]
        payload["open_total"] = len(open_loops)

        ages: List[int] = []
        shown_ages: List[int] = []
        unshown_ages: List[int] = []
        for loop in open_loops:
            report = staleness(loop, current_tick, config, primary_goal_description)
            horizon = report["horizon"]
            if horizon in payload["by_horizon"]:
                payload["by_horizon"][horizon] += 1
            if report["overdue"]:
                payload["overdue_total"] += 1
                if len(payload["overdue_ids"]) < MAX_LISTED_IDS:
                    payload["overdue_ids"].append(report["id"])
            age = report["age"]
            if age is None:
                continue
            ages.append(age)
            if payload["oldest_age"] is None or age > payload["oldest_age"]:
                payload["oldest_age"] = age
                payload["oldest_id"] = report["id"]
            if report["id"] in shown:
                shown_ages.append(age)
                if len(payload["shown"]) < MAX_LISTED_IDS:
                    payload["shown"].append({"id": report["id"], "age": age,
                                             "horizon": horizon})
            else:
                unshown_ages.append(age)

        payload["shown_total"] = len(shown_ages)
        if ages:
            payload["median_age"] = round(float(median(ages)), 1)
        if shown_ages:
            payload["shown_oldest_age"] = max(shown_ages)
        if unshown_ages:
            payload["unshown_oldest_age"] = max(unshown_ages)
    except Exception as e:
        logger.warning(f"Loop-age report failed; recording partial payload: {e}")
    return payload


def scene_local_confident(description: Any) -> bool:
    """True only for the loops it is SAFE to refuse at creation.

    Creation-side hygiene (Phase 3, loop-aging Slice L2a). The horizon
    classifier is 60 percent precise on ``scene`` against a hand-labelled sample
    (docs/LOOP_AGING_BASELINE.md), so refusing every loop it calls scene-local
    would discard real arc debt: six of its eighteen recorded errors were arc
    loops misfiled as scene. This is the high-precision subset instead, and it
    requires BOTH signals at once:

    - a binary opener, so the question is answerable by the story simply
      continuing ("Will she", "Can he", "Is it"), and
    - a deadline in the loop's own text, so it dates itself to the next few
      minutes or hours of story time.

    Each signal alone is too loose. A deadline alone also fires on framing and
    past-tense clauses ("Why did Zeloth remove a file *immediately after* Aris
    logged in?" is a real mystery); a binary opener alone runs the length of a
    book ("Will the cooperation agreement protect him?"). Together they reach 8
    percent of the 1,553 loops on disk, and on the labelled sample the
    conjunction made no false call.

    The prompt rules do the bulk of the work; this is the deterministic backstop
    for the blatant cases, in the spirit of the loop-dedup gate beside it.
    """
    text = _text(description)
    if not text:
        return False
    try:
        return bool(_BINARY_OPENER.match(text)) and bool(_DEADLINE_RE.search(text))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"scene_local_confident failed: {e}")
        return False


def importance_rank(loop: Any) -> int:
    """Sort key for importance, highest first when used with reverse=True.

    Exists because the only place importance was read sorted the raw strings,
    which orders medium, low, high, critical and put the critical loops last.
    An unrecognised importance ranks lowest rather than raising.
    """
    return IMPORTANCE_RANK.get(_text(getattr(loop, "importance", "")).lower(), -1)
