"""Per-section jobs for sectioned scene writing (DSL Slice 5).

The 2026-10-31 validation (docs/DSL_VALIDATION_2026-10-31.md section 5) found
the sectioned scenes losing every blind comparison for one reason: each
section restarted the scene. A character re-announced the findings the
previous section had just made, a request was asked twice in near-identical
words, a middle section re-described the room as if newly introduced. The
cause was the brief: every call carried the whole scene's intention and its
key change, plus all the prose so far, and nothing that said what *its own*
slice was for or what had already been achieved. So each middle section tried
to deliver the whole scene again in its ten paragraphs.

This module gives each section a job of its own. One cheap planning call
splits the scene intention into one beat per section, in order, with the key
change landing in the last; the writer then shows each section its job, the
jobs already done above it, and a rule against re-establishing anything the
text above has covered. If the planning call fails or returns something
unusable, position-based jobs stand in (open, carry, close), so the feature
can never cost a scene.

Pure logic: no LLM calls, no I/O, no state.
"""

import json
import re
from typing import Any, Dict, List, Optional

SECTION_JOBS_PROMPT_TEMPLATE = """You are planning how ONE SCENE of a novel will be written in {n} consecutive sections.

## The scene

**Intention:** {scene_intention}
**Key change this scene must accomplish:** {key_change}
{beat_line}
## The sections

{section_lines}

## Your task

Give each section ONE job: a single sentence saying what happens in it and nothing else. Together the {n} jobs must deliver the intention above exactly once, in order, with no overlap:
- Section 1 establishes the situation and starts the movement. It does not resolve anything.
- Each middle section advances the movement by one step that the sections before it have not taken.
- Only the last section lands the key change and ends the scene.
- Something asked, found, said or decided in one job is settled and must not be asked, found, said or decided again in a later one.

Reply with JSON only: {{"jobs": ["<job of section 1>", "<job of section 2>", ...]}} with exactly {n} entries."""


def section_lines(bounds: List[Any], skeleton: List[str]) -> str:
    """One line per section: its plan range and its mode mix."""
    out = []
    for i, (first, last) in enumerate(bounds):
        modes = skeleton[first - 1:last]
        counts: Dict[str, int] = {}
        for m in modes:
            counts[m] = counts.get(m, 0) + 1
        mix = ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
        out.append(f"{i + 1}. paragraphs {first} to {last} ({last - first + 1} items: {mix})")
    return "\n".join(out)


def section_jobs_prompt(writer_context: Dict[str, Any], bounds: List[Any],
                        skeleton: List[str]) -> str:
    ctx = writer_context or {}
    beat = (ctx.get("plot_beat_section") or "").strip()
    beat_line = f"**Plot beat:** {beat}\n" if beat else ""
    return SECTION_JOBS_PROMPT_TEMPLATE.format(
        n=len(bounds),
        scene_intention=ctx.get("scene_intention") or "(none given)",
        key_change=ctx.get("key_change") or "(none given)",
        beat_line=beat_line,
        section_lines=section_lines(bounds, skeleton),
    )


def fallback_jobs(n: int) -> List[str]:
    """Position-based jobs when the planning call gives nothing usable."""
    if n <= 0:
        return []
    if n == 1:
        return ["Write the whole scene."]
    jobs = ["Establish the situation and start the scene's movement; "
            "resolve nothing."]
    for k in range(2, n):
        jobs.append(f"Advance the scene by one step the sections before it "
                    f"have not taken (step {k - 1} of {n - 2}); resolve nothing.")
    jobs.append("Land the key change and end the scene.")
    return jobs


def parse_section_jobs(response: Optional[str], n: int) -> Optional[List[str]]:
    """The planner's jobs, or None when the response is unusable.

    Lenient on wrapping (prose or fences around the JSON) and on count: one
    missing or extra job is trimmed or padded from the fallback, since a
    model that writes n-1 good jobs has still done the work. More than one
    off is treated as a failure.
    """
    if not response:
        return None
    m = re.search(r"\{.*\}", response, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    jobs = [str(j).strip() for j in jobs if str(j).strip()]
    if not jobs or abs(len(jobs) - n) > 1:
        return None
    if len(jobs) > n:
        jobs = jobs[:n]
    elif len(jobs) < n:
        jobs = jobs + fallback_jobs(n)[len(jobs):]
    return jobs
