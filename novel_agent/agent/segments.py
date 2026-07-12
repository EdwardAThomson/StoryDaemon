"""Segment machinery for the write-until-concluded scene loop (Phase 3).

This is the segment plumbing for the block/sub-block writing mode (Slice 5 of
the interleaving/DSL work): sequential prose segments, each request seeing all
prior prose, per-segment token budgets sized from explicit word targets, and
backend-agnostic completion detection.

Evidence base (docs/progress_report_20260711.md, grant-rate addendum): the
writer's flat 3000-token ceiling truncated 8 of 16 scenes mid-sentence, cost a
judged-closure grant (OL37, the judge's refusal reason literally says the scene
cut off), and left a finished novel's finale without an end marker. The root
cause was coordination: nothing connected the instructed length to the allowed
length, and the model cannot see max_tokens. This module owns that
coordination; the invariant it serves is that no scene is ever committed
without a detected ending (natural, concluded on request, or cleanly trimmed
to the last complete sentence and flagged).

Everything here is pure logic: no LLM calls, no I/O, no state.
"""

import re
from typing import Optional, Tuple


# Word targets per planner scene_length label (PLANNER_PROMPT_TEMPLATE metadata:
# brief|short|long|extended). Overridable via generation.scene_word_targets.
DEFAULT_WORD_TARGETS = {
    "brief": 400,
    "short": 800,
    "long": 1400,
    "extended": 2200,
}

# The label used when the plan carries no scene_length. "long" is the choice:
# the old flat ceiling (3000 tokens, roughly 2100 words) was hit mid-sentence
# by half the scenes on the 2026-07-12 run, so the observed "typical output"
# was a truncation artifact, not a preference. A stated 1400-word target with
# a 2x ceiling (3920 tokens at the defaults) gives the model MORE room than
# the old wall while giving it, for the first time, a length it can actually
# aim to conclude inside.
DEFAULT_SCENE_LENGTH = "long"

# The continuation request's own word target: the conclude instruction asks
# for roughly 200-300 words, so the segment budget is sized from the top of
# that range (see continuation_token_budget).
CONTINUATION_WORD_TARGET = 300

# Sentence-terminal characters: period, exclamation, question mark, ellipsis.
_TERMINAL_CHARS = ".!?…"

# Characters that may legitimately close a sentence AFTER its terminal:
# straight and curly quotes, brackets, and markdown emphasis/backtick marks.
_CLOSER_CHARS = "\"'”’)]}*_`"

# A sentence terminal optionally followed by closers (used by the trim helper).
_SENTENCE_END_RE = re.compile(r"[.!?…][\"'”’)\]}*_`]*")


# ---------------------------------------------------------------------------
# Word targets and token budgets
# ---------------------------------------------------------------------------

def word_target_for(scene_length: Optional[str], config=None) -> int:
    """Map a planner scene_length label (brief|short|long|extended) to a word target.

    Unknown, empty, or missing labels fall back to generation.default_scene_length
    (default "long", see DEFAULT_SCENE_LENGTH for the rationale). Targets are
    overridable per label via the generation.scene_word_targets config dict.
    """
    targets = dict(DEFAULT_WORD_TARGETS)
    overrides = config.get('generation.scene_word_targets', None) if config else None
    if isinstance(overrides, dict):
        for label, value in overrides.items():
            try:
                targets[str(label).strip().lower()] = int(value)
            except (TypeError, ValueError):
                continue

    label = scene_length.strip().lower() if isinstance(scene_length, str) else ""
    if label not in targets:
        fallback = config.get('generation.default_scene_length', DEFAULT_SCENE_LENGTH) \
            if config else DEFAULT_SCENE_LENGTH
        label = str(fallback).strip().lower()
        if label not in targets:
            label = DEFAULT_SCENE_LENGTH
    return targets[label]


def token_budget_for(word_target: int, config=None) -> int:
    """Size a request ceiling from a word target.

    ceiling = words * generation.tokens_per_word (default 1.4)
                    * generation.scene_budget_multiplier (default 2.0)

    The 2x headroom means an on-target scene never brushes the ceiling, and a
    "length" finish_reason is a real signal rather than routine. Floored at 256
    so degenerate configs never produce an unusable budget.
    """
    tokens_per_word = 1.4
    multiplier = 2.0
    if config:
        try:
            tokens_per_word = float(config.get('generation.tokens_per_word', 1.4))
        except (TypeError, ValueError):
            tokens_per_word = 1.4
        try:
            multiplier = float(config.get('generation.scene_budget_multiplier', 2.0))
        except (TypeError, ValueError):
            multiplier = 2.0
    try:
        words = int(word_target)
    except (TypeError, ValueError):
        words = word_target_for(None, config)
    return max(256, int(round(words * tokens_per_word * multiplier)))


def continuation_token_budget(config=None) -> int:
    """Token budget for one continuation segment (the conclude-within-300-words ask)."""
    return token_budget_for(CONTINUATION_WORD_TARGET, config)


# ---------------------------------------------------------------------------
# Completion detection (pure, backend-agnostic heuristic)
# ---------------------------------------------------------------------------

def scene_incomplete(text: str) -> bool:
    """True when the prose visibly stops without an ending.

    Conservative signals only:
    - the last non-whitespace character (after unwrapping closing quotes,
      brackets, and markdown emphasis) is not sentence-terminal (. ! ? or an
      ellipsis), which also catches mid-word and trailing-conjunction cuts and
      trailing commas/semicolons/colons/dashes;
    - EXCEPT when the final non-empty line is an explicit end marker
      ("THE END", "*END OF NOVEL*", "FIN"), which counts as complete.

    Empty or whitespace-only text returns False: there is nothing to continue,
    and the caller's empty-response handling governs. The cost model is
    asymmetric by design: wrongly flagging a complete scene wastes one cheap
    continuation call, so the rules stay simple and err toward accepting text
    that ends at a sentence boundary.
    """
    if not text or not text.strip():
        return False

    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if lines and _is_end_marker(lines[-1]):
        return False

    stripped = text.rstrip()
    while stripped and stripped[-1] in _CLOSER_CHARS:
        stripped = stripped[:-1].rstrip()
    if not stripped:
        # Nothing but quotes/brackets: no sentence terminal anywhere near the end.
        return True
    return stripped[-1] not in _TERMINAL_CHARS


def _is_end_marker(line: str) -> bool:
    """True for a short, deliberate end-of-story marker line.

    Matches all-caps marker lines containing the word END or FIN (for example
    "THE END", "END OF NOVEL", "*FIN*"), with markdown decoration tolerated.
    Deliberately narrow: an all-caps shout that happens to end a truncated
    scene will not contain a bare END/FIN word in marker position and length.
    """
    core = line.strip().strip("*_#>- ").strip()
    if not core or len(core) > 40:
        return False
    if core != core.upper():
        return False
    words = re.findall(r"[A-Z]+", core)
    return "END" in words or "FIN" in words


def trim_to_last_sentence(text: str) -> Tuple[str, bool]:
    """Cut trailing partial prose back to the last complete sentence.

    Returns (trimmed_text, changed). The last-resort fallback when the segment
    loop exhausts its cap still incomplete: better a scene that ends one
    sentence early than one that stops mid-word. When no sentence terminal
    exists anywhere (pathological), the text is returned unchanged with
    changed False; the caller still flags the scene.
    """
    if not text:
        return text, False
    matches = list(_SENTENCE_END_RE.finditer(text))
    if not matches:
        return text, False
    trimmed = text[: matches[-1].end()].rstrip()
    if not trimmed:
        return text, False
    return trimmed, trimmed != text.rstrip()
