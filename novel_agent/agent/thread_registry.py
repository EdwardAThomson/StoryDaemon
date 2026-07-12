"""Thread registry (Phase 3, interleaving Slice T1): threads as first-class objects.

The interleaving design (docs/THREAD_INTERLEAVING_DESIGN.md, section 6 and
Slice T1) makes story-level tension control a scene-selection policy over a
portfolio of threads. Before any selection policy can exist, threads must exist:
this module seeds them by normalizing the free-text ``plot_threads`` labels
beats already carry (authored today, previously unused downstream) and
instruments each thread's local tension trajectory, membership, and
consecutive-run length.

PURE INSTRUMENTATION: nothing reads the registry for decisions in this slice.
The deliverable is the measurement itself, which answers the design's riskiest
open question with data: do emergent stories develop usable secondary threads,
or does everything collapse into one strand?

Thread identity (design open question 1) is answered here with deterministic
Python normalization: labels are case-folded, separators collapsed, punctuation
stripped, then fuzzy-grouped by difflib ratio at the loop-dedup precedent
threshold of 0.8 ("velyn_agenda" and "Velyn's agenda" are one thread). A thread
is created the first time a label appears; subsequent similar labels map to it.
The future alternative, Python minting thread IDs the LLM selects from (the
Phase 1 name-grounding move), stays open for Slice T2.

Attribution rule: a committed scene belongs to its beat's FIRST plot_threads
label (the primary thread). Scenes with no beat or no labels attribute to an
implicit "main" thread, so the per-tick trace is total.

This module holds the pure logic (the loop_closure.py/finale.py pattern);
agent.py keeps a thin wrapped hook. Persistence is memory/threads.json via
MemoryManager (the open_loops.json ownership pattern), with TH000-style IDs
from the shared counters. Graceful degradation throughout: no function here
may kill a tick.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from ..memory.entities import Thread

logger = logging.getLogger(__name__)

# Name of the implicit fallback thread (scenes with no beat or no labels).
MAIN_THREAD_NAME = "main"

_SEPARATOR_RE = re.compile(r"[_\-./]+")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Label normalization (deterministic; design open question 1)
# ---------------------------------------------------------------------------

def normalize_thread_label(label: Any) -> str:
    """Deterministic normal form of a free-text thread label.

    Case-fold, turn separator runs (``_ - . /``) into spaces, strip remaining
    punctuation (so "Velyn's" becomes "velyns"), collapse whitespace. The
    result is the thread's canonical name material; fuzzy grouping runs on
    these normal forms. An unusable label normalizes to "".
    """
    if not isinstance(label, str):
        return ""
    text = label.casefold()
    text = _SEPARATOR_RE.sub(" ", text)
    text = _NON_WORD_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _thread_keys(thread: Thread) -> List[str]:
    """The normalized forms a label can match this thread on: its name plus
    every raw label variant already seen."""
    keys: List[str] = []
    if thread.name:
        keys.append(normalize_thread_label(thread.name) or thread.name)
    for raw in thread.labels or []:
        normalized = normalize_thread_label(raw)
        if normalized and normalized not in keys:
            keys.append(normalized)
    return keys


def match_thread(label: str, threads: List[Thread], threshold: float = 0.8) -> Optional[Thread]:
    """The existing thread a label maps to, or None when it is genuinely new.

    Exact match on normal forms wins first (deterministic, list order); then
    the best difflib SequenceMatcher ratio at or above ``threshold`` (0.8, the
    loop-dedup precedent: light rewordings of the same strand score well above
    0.85, while distinct strands that share scaffolding sit lower). Ties keep
    the earlier (older) thread.
    """
    normalized = normalize_thread_label(label)
    if not normalized:
        return None

    for thread in threads:
        if normalized in _thread_keys(thread):
            return thread

    best: Optional[Thread] = None
    best_ratio = 0.0
    for thread in threads:
        for key in _thread_keys(thread):
            ratio = SequenceMatcher(None, normalized, key).ratio()
            if ratio > best_ratio:
                best, best_ratio = thread, ratio
    if best is not None and best_ratio >= threshold:
        return best
    return None


def primary_label(beat: Any) -> Optional[str]:
    """The beat's FIRST usable plot_threads label (the primary thread), or None.

    Labels that normalize to "" are skipped; a beat whose labels are all
    unusable attributes like a beat with none (the implicit main thread).
    """
    if beat is None:
        return None
    for label in getattr(beat, "plot_threads", None) or []:
        if normalize_thread_label(label):
            return label
    return None


# ---------------------------------------------------------------------------
# Run accounting
# ---------------------------------------------------------------------------

def compute_current_run(threads: List[Thread]) -> Tuple[Optional[str], int]:
    """The currently active thread id and its consecutive-scene run length.

    Derived from the union of all tension traces (one ``[tick, tension]``
    entry per attributed scene): sort by tick, then count back from the
    latest entry while the thread stays the same. Consecutive means
    consecutive ATTRIBUTED SCENES, not consecutive tick integers (a failed
    tick writes no entry). Returns (None, 0) for an empty registry.
    """
    entries: List[Tuple[int, str]] = []
    for thread in threads:
        for entry in thread.tension_trace or []:
            if entry and entry[0] is not None:
                entries.append((entry[0], thread.id))
    if not entries:
        return None, 0
    entries.sort(key=lambda pair: pair[0])
    active_id = entries[-1][1]
    run = 0
    for _, thread_id in reversed(entries):
        if thread_id != active_id:
            break
        run += 1
    return active_id, run


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

class ThreadRegistry:
    """Seeds and updates the thread registry from committed scenes.

    Thin wrapper over MemoryManager persistence (memory/threads.json, TH000
    IDs from the shared counters). One public entry point per tick:
    ``attribute_scene``. Never raises: instrumentation must not break a tick,
    so any failure returns None and the metrics record its fields as null.
    """

    def __init__(self, memory, config):
        self.memory = memory
        self.config = config

    def attribute_scene(self, *, tick: int, scene_id: Optional[str], beat: Any = None,
                        tension_level: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Attribute one committed scene to its primary thread and update the trace.

        The beat's first plot_threads label picks (or creates) the thread; no
        beat or no usable label attributes to the implicit "main" thread. The
        thread's tension trace gains ``[tick, tension_level]`` (a re-run tick
        replaces its old entry, last-wins, across ALL threads), members union
        the beat's characters_involved, home locations union the beat's
        location, and beats/scenes served are recorded. ``run_count`` on the
        active thread is the current consecutive-scene run. Returns a summary
        for the tick result and the rubric
        (``{thread_id, thread_name, created, thread_count, run_length}``),
        or None on any failure. Never raises.
        """
        try:
            threads = self.memory.load_threads()

            raw_label = primary_label(beat)
            created = False
            if raw_label is None:
                thread = next((t for t in threads if t.implicit), None)
                if thread is None:
                    thread = self._create_thread(threads, MAIN_THREAD_NAME, implicit=True)
                    created = True
            else:
                threshold = float(self.config.get('coherence.thread_match_threshold', 0.8))
                thread = match_thread(raw_label, threads, threshold)
                if thread is None:
                    thread = self._create_thread(threads, normalize_thread_label(raw_label))
                    created = True

            if raw_label is not None and raw_label not in thread.labels:
                thread.labels.append(raw_label)

            if beat is not None:
                for char_id in getattr(beat, "characters_involved", None) or []:
                    if char_id and char_id not in thread.member_characters:
                        thread.member_characters.append(char_id)
                location = getattr(beat, "location", None)
                if location and location not in thread.home_locations:
                    thread.home_locations.append(location)
                beat_id = getattr(beat, "id", None)
                if beat_id and beat_id not in thread.beats_served:
                    thread.beats_served.append(beat_id)

            if scene_id and scene_id not in thread.scene_ids:
                thread.scene_ids.append(scene_id)

            # A retried tick re-attributes: drop any stale entry for this tick
            # everywhere before appending (last-wins, the metrics convention).
            for t in threads:
                t.tension_trace = [e for e in (t.tension_trace or []) if not (e and e[0] == tick)]
            thread.tension_trace.append([tick, tension_level])
            thread.last_active_tick = tick

            active_id, run = compute_current_run(threads)
            if active_id == thread.id:
                thread.run_count = run

            self.memory.save_threads(threads)
            return {
                "thread_id": thread.id,
                "thread_name": thread.name,
                "created": created,
                "thread_count": len(threads),
                "run_length": run,
            }
        except Exception as e:
            logger.warning(f"Thread attribution failed (tick {tick}): {e}")
            return None

    def _create_thread(self, threads: List[Thread], name: str, implicit: bool = False) -> Thread:
        """Mint a thread with a counter-backed TH id and append it to the list."""
        thread = Thread(
            id=self.memory.generate_id("thread"),
            name=name,
            implicit=implicit,
        )
        threads.append(thread)
        logger.info(f"Thread {thread.id} created: {name!r}"
                    f"{' (implicit main)' if implicit else ''}")
        return thread
