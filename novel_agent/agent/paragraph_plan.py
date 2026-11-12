"""The model plans the paragraphs; Python sets the shares and checks the plan.

Background (2026-11-08). The scene skeleton is a list of paragraph KINDS
sampled by Python from the masters' statistics, with no knowledge of who is
in the scene or what happens. A writer given the whole list in one call fits
events to it (it sent a visitor to the cabin to fill four dialogue slots); a
writer working one paragraph per call cannot, and in the pilot the heroine,
alone in her cabin, read a cipher aloud to herself for four paragraphs.

Handing the model the sampled list and asking it to fill each slot would let
the statistics drive the story. The split here instead:

  - Python owns the targets: how many paragraphs of each kind, taken from the
    sampled skeleton (so tension conditioning and word-budget sizing are kept),
    with a stated tolerance.
  - The model owns the order and the content: one line per paragraph saying
    what happens, and for dialogue the speaker, SELECTED from the cast by id,
    never typed as a name.
  - Python checks the plan before any prose: the kinds, the shares within
    tolerance, every speaker a real id, and no unrecorded person named in the
    plan's text. One retry with the problems listed; otherwise the caller keeps
    the sampled skeleton, exactly as before.

Pure logic: the LLM call and the name check are passed in, so this module does
no I/O and holds no state. Gated by ``generation.paragraph_plan_by_model``.
"""

import json
import re
from collections import Counter
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .scene_skeleton import MODE_GUIDE, _word_range

# Per-kind tolerance: a kind may run this fraction over or under its target
# count, and never less than one paragraph either way.
SHARE_TOLERANCE = 0.25
TOTAL_TOLERANCE = 0.15


def targets(skeleton: Sequence[str]) -> Dict[str, int]:
    """Target paragraph count per kind, from the sampled skeleton."""
    return dict(Counter(skeleton))


def allowed_range(target: int) -> Tuple[int, int]:
    tol = max(1, round(target * SHARE_TOLERANCE))
    return max(0, target - tol), target + tol


def total_range(n: int) -> Tuple[int, int]:
    tol = max(2, round(n * TOTAL_TOLERANCE))
    return max(1, n - tol), n + tol


PLAN_PROMPT = """You are planning the paragraphs of ONE SCENE of a novel before it is written.

{story_context}

## The Cast You May Use

Speakers are chosen from this list BY ID. Nobody outside it may speak or be named.

{roster}

## Paragraph Kinds

{kinds}

## Targets for This Scene

The scene runs to about {n} paragraphs (anything from {total_lo} to {total_hi}). Use roughly these numbers of each kind:

{target_lines}

## Your Task

Plan the scene paragraph by paragraph, in the order the reader will meet them.
- The order follows what happens in the scene. Decide the events first, then
  give each paragraph the kind that fits it. Never bend the events to fit a
  kind: a DIALOGUE paragraph needs a speaker who is present and someone there
  to hear them. When the POV character is alone, write ACTION or INTERIORITY.
- Each DIALOGUE paragraph is ONE speech turn by ONE speaker. Give that
  speaker's id in "speaker". When the speaker changes, the paragraph changes.
- "what" is one plain sentence saying what happens in that paragraph. Refer
  to people only by their names in the cast list, or by role ("a sailor").
  Never name anyone else.
- The scene's key change lands in the final paragraphs, not earlier.

Reply with JSON only:
{{"paragraphs": [{{"kind": "<one of the kinds>", "speaker": "<cast id, for DIALOGUE only>", "what": "<one sentence>"}}, ...]}}"""


RETRY_NOTE = """

## Your Previous Plan Was Refused

Fix these problems and reply with the whole plan again, JSON only:
{problems}"""


def build_prompt(story_context: str, skeleton: Sequence[str],
                 roster: Sequence[Tuple[str, str, str]],
                 problems: Optional[List[str]] = None) -> str:
    """``roster`` is [(id, name, short description)]."""
    t = targets(skeleton)
    n = len(skeleton)
    lo, hi = total_range(n)
    target_lines = []
    for kind in MODE_GUIDE:
        if kind not in t:
            continue
        a, b = allowed_range(t[kind])
        w_lo, w_hi = _word_range(kind)
        target_lines.append(f"- {kind}: {t[kind]} (anything from {a} to {b}), "
                            f"each about {w_lo}-{w_hi} words")
    absent = [k for k in MODE_GUIDE if k not in t]
    if absent:
        target_lines.append(f"- At most one paragraph of any other kind "
                            f"({', '.join(absent)}).")
    prompt = PLAN_PROMPT.format(
        story_context=story_context,
        roster="\n".join(f"- {cid}: {name} ({desc})" if desc else f"- {cid}: {name}"
                         for cid, name, desc in roster) or "(nobody yet)",
        kinds="\n".join(f"- {k}: {g}" for k, g in MODE_GUIDE.items()),
        n=n, total_lo=lo, total_hi=hi,
        target_lines="\n".join(target_lines),
    )
    if problems:
        prompt += RETRY_NOTE.format(problems="\n".join(f"- {p}" for p in problems))
    return prompt


def parse(response: str) -> Optional[List[dict]]:
    """The list of paragraph dicts, or None when the response is unusable."""
    if not response:
        return None
    text = response.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    items = data.get("paragraphs") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return None
    out = []
    for it in items:
        if not isinstance(it, dict):
            return None
        out.append({
            "kind": str(it.get("kind") or it.get("mode") or "").strip().upper(),
            "speaker": str(it.get("speaker") or "").strip(),
            "what": str(it.get("what") or "").strip(),
        })
    return out


def check(items: List[dict], skeleton: Sequence[str], roster_ids: Sequence[str],
          name_check: Optional[Callable[[str], List[str]]] = None) -> List[str]:
    """Every problem with the plan, in plain words; empty means accepted."""
    problems: List[str] = []
    ids = set(roster_ids)
    for i, it in enumerate(items, 1):
        if it["kind"] not in MODE_GUIDE:
            problems.append(f"paragraph {i}: unknown kind {it['kind']!r}")
        if not it["what"]:
            problems.append(f"paragraph {i}: no 'what'")
        if it["kind"] == "DIALOGUE":
            if not it["speaker"]:
                problems.append(f"paragraph {i}: DIALOGUE with no speaker id")
            elif it["speaker"] not in ids:
                problems.append(f"paragraph {i}: speaker {it['speaker']!r} is not "
                                f"an id in the cast list")
        elif it["speaker"] and it["speaker"] not in ids:
            problems.append(f"paragraph {i}: {it['speaker']!r} is not an id in "
                            f"the cast list")
    lo, hi = total_range(len(skeleton))
    if not lo <= len(items) <= hi:
        problems.append(f"{len(items)} paragraphs; the scene needs {lo} to {hi}")
    want, got = targets(skeleton), Counter(it["kind"] for it in items)
    for kind in MODE_GUIDE:
        a, b = allowed_range(want[kind]) if kind in want else (0, 1)
        if not a <= got.get(kind, 0) <= b:
            problems.append(f"{got.get(kind, 0)} {kind} paragraphs; use {a} to {b}")
    if name_check is not None:
        try:
            names = name_check(" ".join(it["what"] for it in items))
        except Exception:  # noqa: BLE001  an instrument must not invent a refusal
            names = []
        for name in names:
            problems.append(f"{name!r} is not in the cast list: refer to that "
                            f"person by role, or leave them out")
    return problems


def notes(items: List[dict], names_by_id: Dict[str, str]) -> List[str]:
    """One line per paragraph for the writer's plan."""
    out = []
    for it in items:
        if it["kind"] == "DIALOGUE" and it["speaker"]:
            who = names_by_id.get(it["speaker"], it["speaker"])
            out.append(f"{who} speaks. {it['what']}")
        else:
            out.append(it["what"])
    return out


def plan_paragraphs(generate: Callable[[str], str], story_context: str,
                    skeleton: Sequence[str],
                    roster: Sequence[Tuple[str, str, str]],
                    name_check: Optional[Callable[[str], List[str]]] = None,
                    ) -> Tuple[Optional[List[str]], Optional[List[str]], dict]:
    """(kinds, notes, report). kinds/notes are None when no plan was accepted,
    and the caller then keeps the sampled skeleton. Never raises on a bad
    response; ``generate`` failing is the caller's to handle."""
    roster_ids = [r[0] for r in roster]
    names_by_id = {r[0]: r[1] for r in roster}
    report = {"attempts": 0, "accepted": False, "problems": []}
    problems: Optional[List[str]] = None
    for _attempt in range(2):
        report["attempts"] += 1
        items = parse(generate(build_prompt(story_context, skeleton, roster, problems)))
        problems = (["the reply was not the JSON asked for"] if items is None
                    else check(items, skeleton, roster_ids, name_check))
        report["problems"].append(problems)
        if not problems:
            report["accepted"] = True
            want, got = targets(skeleton), Counter(it["kind"] for it in items)
            report["targets"] = want
            report["planned"] = dict(got)
            return [it["kind"] for it in items], notes(items, names_by_id), report
    return None, None, report
