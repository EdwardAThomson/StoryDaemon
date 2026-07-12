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

Thread identity (design open question 1) was first answered with deterministic
Python normalization: labels are case-folded, separators collapsed, punctuation
stripped, then fuzzy-grouped by difflib ratio at the loop-dedup precedent
threshold of 0.8 ("velyn_agenda" and "Velyn's agenda" are one thread). A thread
is created the first time a label appears; subsequent similar labels map to it.

Slice T1.5 (thread identity grounding) closes the question the other way: the
T1 backfill over three finished novels showed authored plot_threads labels are
per-beat episode titles, not persistent threads (34 executed beats yielded 30
distinct primary labels; the reliable identity signal was the cast), so Python
now mints thread identity and the LLM SELECTS it, exactly like Phase 1
character naming. The beat-generation prompt carries a roster of exact TH ids
(``thread_roster_section``), each beat names the ONE thread it serves via
``thread_id`` ("new: <name>" mints a strand), and
``sanitize_beat_thread_ids`` holds the authored ids to the roster. All gated
by ``coherence.thread_identity`` (default True); off restores exact T1
behavior.

Attribution rule: a committed scene belongs to its beat's sanitized
``thread_id`` when present and resolvable (Slice T1.5 selection), else its
beat's FIRST plot_threads label (the T1 primary thread), else an implicit
"main" thread, so the per-tick trace is total.

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

from ..contracts.authoring import entity_label
from ..memory.entities import Thread

logger = logging.getLogger(__name__)

# Name of the implicit fallback thread (scenes with no beat or no labels).
MAIN_THREAD_NAME = "main"

_SEPARATOR_RE = re.compile(r"[_\-./]+")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

# "new: <short thread name>": the one sanctioned way for the LLM to open a
# genuinely new strand; Python mints the TH id (Slice T1.5).
_NEW_THREAD_RE = re.compile(r"^new\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)


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
# Minting (Python assigns thread identity; Slice T1.5)
# ---------------------------------------------------------------------------

def mint_thread(threads: List[Thread], memory, name: str, implicit: bool = False,
                raw_label: Optional[str] = None) -> Thread:
    """Mint a thread with a counter-backed TH id and append it to the list.

    The caller persists via ``memory.save_threads``; only the id allocation
    touches disk here (the shared counters). ``raw_label`` records the
    pre-normalization spelling as match material, the T1 labels convention.
    """
    thread = Thread(
        id=memory.generate_id("thread"),
        name=name,
        implicit=implicit,
    )
    if raw_label and raw_label not in thread.labels:
        thread.labels.append(raw_label)
    threads.append(thread)
    logger.info(f"Thread {thread.id} created: {name!r}"
                f"{' (implicit main)' if implicit else ''}")
    return thread


# ---------------------------------------------------------------------------
# Beat-generation prompt surface (Slice T1.5: select, don't invent)
# ---------------------------------------------------------------------------

THREAD_ROSTER_HEADER = "## Story threads (use these exact IDs)"

# One line saying the portfolio is still the single implicit strand; rendered
# under the roster header when the registry is empty so the selection rule
# still has a section to point at.
EMPTY_ROSTER_LINE = ("No named threads yet: the story has one implicit main "
                     "thread so far.")

# Injected into PLOT_GENERATION_PROMPT_TEMPLATE's authoritative JSON shape
# block right after "plot_threads" when the gate is on (the
# contract_schema_example precedent: a field absent from the shape block is a
# field a schema-obedient model omits every time).
_THREAD_SCHEMA_EXAMPLE = '\n      "thread_id": "TH000",'

# The selection rule, rendered with the other exact-ID rules in the beat style
# block (leading newline so the off state leaves the bullet list untouched).
_THREAD_PROMPT_RULE = (
    '\n- For "thread_id", name the ONE thread this beat serves, using the '
    'exact TH id from the Story threads section (for example "TH000"). To '
    'open a genuinely new strand, write "new: <short thread name>" and the '
    'system will mint it. Never invent TH ids.'
)


def _member_roster(thread: Thread, memory) -> str:
    """The thread's member characters as "Name (Cxxx)" entries, resolved via
    memory (grounded identity on the selection surface, the contract-surface
    names lesson: the LLM can only select among names it has seen). Falls back
    to the bare id per member when a lookup fails."""
    labels = []
    for char_id in thread.member_characters or []:
        if not char_id:
            continue
        labels.append(entity_label(char_id, memory) or char_id)
    return ", ".join(labels) if labels else "none yet"


def _tension_range(thread: Thread) -> str:
    """Compact min-max of the thread's scored tension entries ("n/a" when none)."""
    levels = [e[1] for e in (thread.tension_trace or [])
              if e and len(e) > 1 and e[1] is not None]
    if not levels:
        return "n/a"
    low, high = min(levels), max(levels)
    return f"{low:g}" if low == high else f"{low:g}-{high:g}"


def _roster_line(thread: Thread, memory) -> str:
    """One roster line: TH id, name, members, scenes served, recency, tension."""
    name = thread.name or "?"
    if thread.implicit:
        name += " (implicit main)"
    last = (f"tick {thread.last_active_tick}"
            if thread.last_active_tick is not None else "never")
    return (f"{thread.id}: {name} | members: {_member_roster(thread, memory)} | "
            f"scenes: {len(thread.scene_ids or [])} | last active: {last} | "
            f"tension: {_tension_range(thread)}")


def thread_roster_section(memory, config) -> str:
    """The beat-generation prompt's thread roster, or "" when the gate is off.

    Rendered into ``PLOT_GENERATION_PROMPT_TEMPLATE``'s ``{thread_section}`` by
    BOTH beat-generation paths (``plot/manager.py`` and ``cli/commands/plot.py``,
    the drift-prevention convention, like ``contract_authoring_section``).
    Gated by ``coherence.thread_identity`` (default True). An empty registry
    renders the one-implicit-main-thread line; an unreadable ledger omits the
    section entirely. Never raises.
    """
    if not config.get('coherence.thread_identity', True):
        return ""
    try:
        threads = memory.load_threads()
        lines = [THREAD_ROSTER_HEADER]
        if not threads:
            lines.append(EMPTY_ROSTER_LINE)
        else:
            lines.extend(_roster_line(thread, memory) for thread in threads)
        return "\n".join(lines) + "\n"
    except Exception as e:
        logger.warning(f"Thread roster unavailable: {e}")
        return ""


def thread_schema_example(config) -> str:
    """The shape-example fragment for thread_id, or "" when the gate is off.

    Rendered into ``PLOT_GENERATION_PROMPT_TEMPLATE``'s
    ``{thread_schema_example}`` placeholder (inside the authoritative JSON
    shape block) by both beat-generation paths, alongside
    ``thread_roster_section``.
    """
    if not config.get('coherence.thread_identity', True):
        return ""
    return _THREAD_SCHEMA_EXAMPLE


def thread_prompt_rule(config) -> str:
    """The thread_id selection rule bullet, or "" when the gate is off.

    Rendered into ``PLOT_GENERATION_PROMPT_TEMPLATE``'s ``{thread_rule}``
    placeholder (with the other exact-ID rules) by both beat-generation paths.
    """
    if not config.get('coherence.thread_identity', True):
        return ""
    return _THREAD_PROMPT_RULE


# ---------------------------------------------------------------------------
# Resolution/minting sanitizer (Slice T1.5; runs with the other beat sanitizers)
# ---------------------------------------------------------------------------

def sanitize_beat_thread_ids(beats: List[Any], memory, config) -> List[str]:
    """Hold freshly authored beats' ``thread_id`` to the registry, in place.

    The "select, don't invent" move applied to threads (Phase 3, interleaving
    Slice T1.5), sibling of ``_resolve_beat_references`` and the other beat
    sanitizers. Per authored thread_id:

    - an exact known TH id is kept (rewritten to canonical casing);
    - ``"new: <name>"`` mints a registry thread (Python assigns the TH id, the
      name is normalized) and the beat's thread_id is rewritten to the minted
      id, unless the name already matches an existing thread (the T1 matcher),
      which is reused instead of duplicated;
    - anything else (label junk, unknown id) is normalization-matched against
      existing thread names (the T1 matcher), else set to None with a warning.

    Cast validation is a soft signal: a beat whose characters_involved shares
    zero members with the resolved thread's membership warns but keeps the
    assignment (conservative: warn, never reassign in this slice). Returns
    human-readable warnings; never raises. An unreadable ledger leaves every
    thread_id untouched. No-op (returns []) when ``coherence.thread_identity``
    is off: the prompt never asked for a selection.
    """
    if not config.get('coherence.thread_identity', True):
        return []
    try:
        threads = memory.load_threads()
    except Exception as e:
        return [f"thread ledger unreadable ({e}); beat thread_ids left untouched"]

    warnings: List[str] = []
    try:
        threshold = float(config.get('coherence.thread_match_threshold', 0.8))
        minted = False
        for beat in beats:
            raw = getattr(beat, "thread_id", None)
            if raw is None:
                continue
            if not isinstance(raw, str) or not raw.strip():
                beat.thread_id = None
                continue
            raw = raw.strip()

            thread: Optional[Thread] = None
            exact = next((t for t in threads
                          if t.id.casefold() == raw.casefold()), None)
            new_match = _NEW_THREAD_RE.match(raw)
            if exact is not None:
                thread = exact
            elif new_match:
                raw_name = new_match.group(1).strip()
                name = normalize_thread_label(raw_name)
                if not name:
                    warnings.append(f"beat {beat.id}: unusable thread name in "
                                    f"{raw!r}; thread_id cleared")
                    beat.thread_id = None
                    continue
                thread = match_thread(raw_name, threads, threshold)
                if thread is not None:
                    warnings.append(f"beat {beat.id}: 'new: {raw_name}' matches "
                                    f"existing thread {thread.id} ({thread.name}); "
                                    f"reusing it")
                else:
                    thread = mint_thread(threads, memory, name, raw_label=raw_name)
                    minted = True
            else:
                thread = match_thread(raw, threads, threshold)
                if thread is None:
                    warnings.append(f"beat {beat.id}: thread_id {raw!r} matches "
                                    f"no known thread; cleared")
                    beat.thread_id = None
                    continue
                warnings.append(f"beat {beat.id}: thread_id {raw!r} resolved to "
                                f"{thread.id} ({thread.name})")
            beat.thread_id = thread.id

            # Cast validation (soft signal): casts, not labels, are the reliable
            # identity signal (the T1 backfill evidence), so a disjoint cast is
            # worth flagging, but this slice only warns.
            cast = [c for c in (getattr(beat, "characters_involved", None) or []) if c]
            if cast and thread.member_characters \
                    and not set(cast) & set(thread.member_characters):
                warnings.append(f"beat {beat.id}: cast disjoint from thread "
                                f"{thread.id} ({thread.name})")
        if minted:
            memory.save_threads(threads)
    except Exception as e:
        warnings.append(f"thread_id sanitization aborted ({e}); remaining beats "
                        f"left untouched")
    return warnings


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
        """Attribute one committed scene to its thread and update the trace.

        Preference order (Slice T1.5, gated by ``coherence.thread_identity``):
        the beat's sanitized ``thread_id`` wins when present and resolvable
        (source "selected"); else the T1 first-label behavior (the beat's first
        plot_threads label picks or creates the thread, source
        "label_fallback"); else the implicit "main" thread (source "main").
        The thread's tension trace gains ``[tick, tension_level]`` (a re-run
        tick replaces its old entry, last-wins, across ALL threads), members
        union the beat's characters_involved, home locations union the beat's
        location, and beats/scenes served are recorded. ``run_count`` on the
        active thread is the current consecutive-scene run. Returns a summary
        for the tick result and the rubric
        (``{thread_id, thread_name, created, thread_count, run_length,
        source}``; ``source`` is None with the gate off), or None on any
        failure. Never raises.
        """
        try:
            threads = self.memory.load_threads()

            identity_on = bool(self.config.get('coherence.thread_identity', True))
            raw_label = primary_label(beat)
            created = False
            thread: Optional[Thread] = None
            source: Optional[str] = None

            # Slice T1.5: an explicit, resolvable selection wins over labels.
            if identity_on and beat is not None:
                selected = getattr(beat, "thread_id", None)
                if isinstance(selected, str) and selected.strip():
                    thread = next((t for t in threads
                                   if t.id == selected.strip()), None)
                    if thread is not None:
                        source = "selected"

            if thread is None:
                if raw_label is None:
                    thread = next((t for t in threads if t.implicit), None)
                    if thread is None:
                        thread = mint_thread(threads, self.memory,
                                             MAIN_THREAD_NAME, implicit=True)
                        created = True
                    source = "main"
                else:
                    threshold = float(self.config.get('coherence.thread_match_threshold', 0.8))
                    thread = match_thread(raw_label, threads, threshold)
                    if thread is None:
                        thread = mint_thread(threads, self.memory,
                                             normalize_thread_label(raw_label))
                        created = True
                    source = "label_fallback"

            # Under selection the label is per-beat color (the T1 backfill
            # showed labels are episode titles); recording it as match material
            # on the selected thread would pollute the T1 matcher.
            if source != "selected" and raw_label is not None \
                    and raw_label not in thread.labels:
                thread.labels.append(raw_label)

            # Selection-adoption counter (Slice T1.5): persisted only with the
            # gate on, so gate-off registries stay byte-identical to T1.
            if identity_on and source:
                thread.attribution_sources[source] = (
                    thread.attribution_sources.get(source, 0) + 1
                )

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
                # Slice T1.5 selection-adoption signal; None with the gate off
                # (exact T1 behavior restored, so the field stays unavailable).
                "source": source if identity_on else None,
            }
        except Exception as e:
            logger.warning(f"Thread attribution failed (tick {tick}): {e}")
            return None
