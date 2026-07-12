"""Construction-pressure detector (Phase 3, interleaving Slice T4a).

The thread-construction design (docs/THREAD_CONSTRUCTION_DESIGN.md, section 2)
makes Python decide WHEN a B-thread is constructed. This module is the
detector for that decision, shipped instrument-only in the house tradition
(measure before pressure): every tick it computes whether construction WOULD
fire, and the verdict is recorded to metrics and surfaced in the tick result.
Nothing here changes planning or authoring; the authoring behavior is Slice
T4b, gated separately.

Two triggers, evaluated in order:

- **Diversity** (primary): the effective thread count is 1 (all-main-forever,
  the proven default outcome) while the story fraction sits inside the
  construction window (``construction_floor`` .. ``construction_cutoff``) and
  the runway floor holds. The masters study confirmed diversity as the real
  deficit: corpus books run 2-3 concurrent threads, our runs produce 1.
- **Demand-gap** (EXPERIMENTAL, demoted per the masters study, opt-in via
  ``coherence.demand_gap_trigger``, default False): the curve foresees calm
  the portfolio cannot serve. No corpus book keeps a calm B-thread, so the
  trigger's construct-calm-supply premise is unsupported; it is kept as an
  instrumented experiment because the pipeline's measured inability to
  de-escalate (2026-06) is a real problem the masters do not have. Evaluated
  only when diversity did not fire.

The runway floor derives ``thread_min_run`` from story length (masters run
committed blocks of roughly 15-30 percent of book length; the 20 percent
working point gives runs of 3 at length 15, 5 at 24, 8 at 40) unless
``coherence.thread_min_run`` is set explicitly.

This module holds the pure logic (the loop_closure.py/finale.py pattern);
agent.py keeps a thin wrapped hook. Graceful degradation throughout: no
function here may kill a tick.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .arc_pressure import _progress, interpolate_curve, resolve_tension_curve

logger = logging.getLogger(__name__)

# The sacred finale slot (docs/THREAD_CONSTRUCTION_DESIGN.md section 2.3): the
# runway must always keep the story's final scene out of B-thread accounting.
FINALE_RESERVE = 1

# thread_min_run derivation constants (section 2.3 arithmetic): masters' block
# hand-offs run roughly 15-30 percent of book length; 0.2 is the working point,
# and 2 is the absolute whiplash floor (a 1-scene "thread" is a cut, not a run).
MIN_RUN_FRACTION = 0.2
MIN_RUN_FLOOR = 2


def derive_thread_min_run(target_story_length: Any) -> int:
    """The whiplash-guard minimum run derived from story length.

    ``max(2, round(0.2 * length))``: the masters' 8-14+ chapter blocks at
    roughly 15-30 percent of book length, scaled to our tick counts (length 15
    gives 3, length 24 gives 5, length 40 gives 8). Returns the floor for an
    unusable length (the caller gates on length validity anyway).
    """
    try:
        length = int(target_story_length)
    except (TypeError, ValueError):
        return MIN_RUN_FLOOR
    if length <= 0:
        return MIN_RUN_FLOOR
    return max(MIN_RUN_FLOOR, round(MIN_RUN_FRACTION * length))


def _resolved_min_run(config, length: int) -> int:
    """``coherence.thread_min_run`` when set to a positive integer, else derived."""
    explicit = config.get('coherence.thread_min_run', None)
    try:
        explicit = int(explicit)
    except (TypeError, ValueError):
        explicit = None
    if explicit is not None and explicit > 0:
        return explicit
    return derive_thread_min_run(length)


def runway_floor(config, length: int) -> int:
    """Ticks the whole B-thread lifecycle needs (section 2.3 dead-weight guard).

    ``thread_min_run`` for the B-thread's decent run, the same again for the
    main thread's floor, plus the convergence reserve and the sacred finale
    slot.
    """
    min_run = _resolved_min_run(config, length)
    try:
        convergence = int(config.get('coherence.convergence_reserve', 1))
    except (TypeError, ValueError):
        convergence = 1
    return 2 * min_run + convergence + FINALE_RESERVE


def effective_thread_count(threads: List[Any]) -> int:
    """Threads with at least one attributed scene (section 2.1's effective count).

    A minted-but-never-served thread is not a strand the story is running, so
    it does not count toward diversity.
    """
    count = 0
    for thread in threads or []:
        if (getattr(thread, "scene_ids", None) or []) \
                or (getattr(thread, "tension_trace", None) or []):
            count += 1
    return count


def _recent_thread_tension(thread: Any) -> Optional[float]:
    """Mean of the thread's last 2 scored trace entries, or None when unscored."""
    levels = [entry[1] for entry in (getattr(thread, "tension_trace", None) or [])
              if entry and len(entry) > 1 and entry[1] is not None]
    if not levels:
        return None
    recent = levels[-2:]
    return sum(recent) / len(recent)


def _demand_gap(threads: List[Any], config, current_tick: int,
                length: int) -> Tuple[bool, str]:
    """The experimental demand-gap evaluation (section 2.2). Returns (fires, reason).

    Fires when the curve's lookahead window demands the calm band and no
    active thread's recent tension sits within ``serve_margin`` of it.
    """
    curve = resolve_tension_curve(config)
    if not curve:
        return False, "demand-gap: arc-pressure disabled (no curve to foresee demand)"

    try:
        window = int(config.get('generation.plot_beats_ahead', 5))
    except (TypeError, ValueError):
        window = 5
    targets = [interpolate_curve(_progress(t, length), curve)
               for t in range(current_tick, current_tick + max(0, window) + 1)]
    targets = [t for t in targets if t is not None]
    if not targets:
        return False, "demand-gap: no interpolable targets in the horizon"
    min_target = min(targets)

    try:
        calm_threshold = float(config.get('coherence.calm_threshold', 4))
    except (TypeError, ValueError):
        calm_threshold = 4.0
    if min_target > calm_threshold:
        return False, (f"demand-gap: no calm demand in the next {window} ticks "
                       f"(min target {min_target:g} > {calm_threshold:g})")

    try:
        serve_margin = float(config.get('coherence.serve_margin', 2))
    except (TypeError, ValueError):
        serve_margin = 2.0
    for thread in threads or []:
        recent = _recent_thread_tension(thread)
        if recent is not None and abs(recent - min_target) <= serve_margin:
            return False, (f"demand-gap: thread {getattr(thread, 'id', '?')} can "
                           f"serve the calm band (recent tension {recent:g})")

    return True, (f"demand_gap (experimental): the curve demands {min_target:g} "
                  f"within {window} ticks and no thread can serve it")


def evaluate_construction_pressure(memory, config, current_tick: int) -> Optional[Dict[str, Any]]:
    """Would thread construction fire at this tick? Instrument-only verdict.

    Returns None when ``coherence.thread_construction_detector`` is off, else a
    dict: ``{would_fire, trigger, reason, story_fraction, thread_count,
    runway}``. ``trigger`` is ``"diversity"`` or ``"demand_gap"`` on a fire and
    None otherwise; ``story_fraction``/``thread_count``/``runway`` are None
    when unavailable (no configured length, unreadable registry), the
    None-when-unavailable convention. Never raises.
    """
    if not config.get('coherence.thread_construction_detector', True):
        return None

    result: Dict[str, Any] = {
        "would_fire": False,
        "trigger": None,
        "reason": "",
        "story_fraction": None,
        "thread_count": None,
        "runway": None,
    }
    try:
        try:
            length = int(config.get('coherence.target_story_length', None))
        except (TypeError, ValueError):
            length = None
        if not length or length <= 0:
            result["reason"] = ("no intended story length configured; no story "
                                "fraction to window construction against")
            return result

        fraction = _progress(current_tick, length)
        runway = max(0, length - current_tick)
        result["story_fraction"] = round(fraction, 3)
        result["runway"] = runway
        pct = int(round(fraction * 100))

        try:
            threads = memory.load_threads()
        except Exception as e:
            result["reason"] = f"thread ledger unreadable ({e})"
            return result
        count = effective_thread_count(threads)
        result["thread_count"] = count

        try:
            floor = float(config.get('coherence.construction_floor', 0.15))
        except (TypeError, ValueError):
            floor = 0.15
        try:
            cutoff = float(config.get('coherence.construction_cutoff', 0.5))
        except (TypeError, ValueError):
            cutoff = 0.5

        if fraction < floor:
            result["reason"] = (f"before the construction floor ({pct} percent "
                                f"< {floor:g}); the main strand is still establishing")
            return result
        if fraction > cutoff:
            result["reason"] = (f"past the construction cutoff ({pct} percent "
                                f"> {cutoff:g}); late calm comes from sequencing, "
                                f"never a new thread")
            return result

        needed = runway_floor(config, length)
        if runway < needed:
            result["reason"] = (f"runway too short ({runway} ticks left, floor "
                                f"{needed}); a B-thread without room to live is "
                                f"dead weight")
            return result

        if count == 0:
            result["reason"] = "no attributed scenes yet; nothing established to diversify"
            return result
        if count == 1:
            result["would_fire"] = True
            result["trigger"] = "diversity"
            result["reason"] = f"diversity ({count} thread at {pct} percent)"
            return result

        # Diversity satisfied: the demoted, experimental demand-gap trigger
        # (docs/THREAD_CONSTRUCTION_DESIGN.md section 2.2) runs only when
        # explicitly opted in.
        if config.get('coherence.demand_gap_trigger', False):
            fires, reason = _demand_gap(threads, config, current_tick, length)
            if fires:
                result["would_fire"] = True
                result["trigger"] = "demand_gap"
            result["reason"] = reason
            return result

        result["reason"] = (f"{count} threads active; diversity satisfied "
                            f"(demand-gap trigger off)")
        return result
    except Exception as e:
        logger.warning(f"Construction-pressure detector failed (tick {current_tick}): {e}")
        result["reason"] = f"detector error ({e})"
        return result
