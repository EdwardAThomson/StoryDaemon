#!/usr/bin/env python3
"""Same-plan A/B: one call for the whole scene vs one call per plan item.

Each tick plans once. The writer is then called twice from the identical
writer context (same brief, same paragraph plan):

  A  single  generation.subblock_generation off: the whole scene in one call.
             This version is the one committed, so the story carries on from it.
  B  peritem subblock_generation on, subblock_section_blocks=1: one call per
             plan item. Section jobs and hide_ending are off, so every call
             sees the whole brief (intention, key change, beat), the whole
             paragraph plan with its own item marked, and all the prose
             written so far. Saved beside the project, never committed.

Run 1 (ab1, 2026-11-08) was spoiled by token limits: each per-item call's
ceiling was sized from one paragraph's words (often the 256-token floor), Opus
spent much of it thinking, and 34 of 73 calls were cut off. This version:

  - gives every per-item call PERITEM_MAX_TOKENS (measured need: up to 857
    thinking tokens plus about 400 of prose; output is billed as used);
  - reorders the per-item prompt so what never changes comes first (brief,
    rules, the whole plan), then the prose so far, then this item's own
    instruction, and marks Anthropic cache points in the request so each call
    re-reads the earlier part from cache (Opus 5.5: 5% of the input price);
  - stops the whole run at the first per-item cut-off, and before any call
    once the spend cap is reached, rather than charging on.

Both raw writer outputs (markers stripped, before any tension pass) are saved
to <project>/ab/scene_NNN_{single,peritem}.md plus a JSON record and the
writer context, and every LLM call's cost and cache use is logged to
<project>/usage.jsonl, tagged with its arm.

    venv/bin/python experiments/dsl_validation/ab_sectioned.py \
        --name ab2-opus55-alcyone --foundation alcyone \
        --model anthropic/claude-opus-5.5 --ticks 1 --max-usd 1.20
"""

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import run_cell  # noqa: E402

ARM = {"name": "plan"}          # which arm the next LLM call belongs to
SPENT = {"usd": 0.0}

PERITEM_MAX_TOKENS = 3000

PERITEM = {
    "generation.subblock_generation": True,
    "generation.subblock_section_blocks": 1,
    "generation.subblock_section_jobs": False,
    "generation.subblock_hide_ending": False,
}

# Sentinels the reordered prompt carries; the request wrapper turns them into
# separate content blocks with cache points and removes them. Private-use
# characters, so they can never occur in real prose.
CACHE_END = "CACHE"     # end of a cached region
PARA = "PARA"           # boundary between two prose paragraphs


class StopRun(BaseException):
    """Stops the whole run. BaseException, so the writer's own
    `except Exception` fallback (which would re-write the scene single-shot,
    at full cost) cannot swallow it."""


# --- requests: cost log, cache points, guard rails ------------------------------------

def to_blocks(text):
    """Split a sentinel-marked prompt into content blocks with cache points.

    Shape: [fixed part][para 1][para 2]...[para k][this item's instruction].
    Cache points go on the fixed part and on the last paragraph. Each call
    adds one paragraph block, well inside Anthropic's 20-block lookback, so
    every call reads the previous call's cache entry.
    """
    regions = text.split(CACHE_END)
    blocks = []
    for r_i, region in enumerate(regions):
        paras = region.split(PARA)
        for p_i, para in enumerate(paras):
            if not para:
                continue
            blocks.append({"type": "text", "text": para})
        if r_i < len(regions) - 1 and blocks:
            blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def install_requests(log_path, max_usd):
    from openai.resources.chat.completions import Completions
    original = Completions.create

    def create(self, *args, **kwargs):
        if max_usd is not None and SPENT["usd"] >= max_usd:
            raise StopRun(f"spend cap reached (${SPENT['usd']:.3f} of ${max_usd:.2f})")
        msgs = kwargs.get("messages") or []
        cached = False
        if msgs and isinstance(msgs[-1].get("content"), str) and CACHE_END in msgs[-1]["content"]:
            msgs = [dict(m) for m in msgs]
            msgs[-1]["content"] = to_blocks(msgs[-1]["content"])
            kwargs["messages"] = msgs
            cached = True
        t0 = time.time()
        resp = original(self, *args, **kwargs)
        u = resp.usage.model_dump() if getattr(resp, "usage", None) is not None else {}
        cost = u.get("cost") or 0.0
        SPENT["usd"] += cost
        finish = resp.choices[0].finish_reason if resp.choices else None
        details = u.get("prompt_tokens_details") or {}
        row = {
            "t": t0, "secs": round(time.time() - t0, 2), "arm": ARM["name"],
            "model": kwargs.get("model"), "max_tokens": kwargs.get("max_tokens"),
            "finish": finish, "cache_marked": cached,
            "out_chars": len(resp.choices[0].message.content or "") if resp.choices else 0,
            "cost": cost, "prompt_tokens": u.get("prompt_tokens"),
            "cached_tokens": details.get("cached_tokens"),
            "cache_write_tokens": details.get("cache_write_tokens"),
            "completion_tokens": u.get("completion_tokens"),
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        if ARM["name"] == "peritem" and finish == "length":
            raise StopRun(f"a per-item call was cut off at {kwargs.get('max_tokens')} tokens "
                          f"({row['reasoning_tokens']} spent thinking)")
        return resp

    Completions.create = create


# --- the reordered per-item prompt ----------------------------------------------------

PERITEM_TEMPLATE = """You are a creative fiction writer writing ONE PARAGRAPH of a scene, against a paragraph plan. Other calls write the other paragraphs.

{story_context}

{craft_rules}

{plan_rules}

## The Whole Paragraph Plan

{whole_plan}
{cache_end}{scene_so_far}
## Your Paragraph: number {n}

{item_line}

## Your Task

{position_instruction}

{continuity_rules}

**OUTPUT FORMAT:** Output ONLY paragraph {n}, opening with its marker "[{n}] ". No title, no notes, no commentary.

Write paragraph {n} now:"""


def install_peritem_prompt():
    """Replace the section prompt for the per-item arm with a cache-friendly
    order. The content is the library's own (brief, craft rules, plan rules,
    position and continuity rules); only the order changes, plus the whole
    plan, which the library's section prompt does not show."""
    from novel_agent.agent import prompts as P
    from novel_agent.agent.scene_skeleton import skeleton_lines
    library = P.format_scene_section_prompt

    def fmt(writer_context, plan_lines, plan_rules, first, last, item_count=0,
            section_words=0, scene_so_far="", is_first=False, is_last=False,
            section_job="", jobs_done=None, hide_ending=False, event_rules=False):
        if first != last or section_job:
            return library(writer_context, plan_lines, plan_rules, first, last,
                           item_count, section_words, scene_so_far, is_first,
                           is_last, section_job, jobs_done, hide_ending, event_rules)
        ctx = dict(writer_context or {})
        skeleton = ctx.get("scene_skeleton") or []
        n = first
        # Reuse the library's own position and continuity wording verbatim by
        # rendering its prompt and cutting those two pieces out of it.
        ref = library(writer_context, plan_lines, plan_rules, first, last, 1,
                      section_words, "", is_first, is_last)
        task = ref.split("## Your Task", 1)[1].split("**OUTPUT FORMAT:**", 1)[0].strip()
        position, _, continuity = task.partition("\n\n")
        if not is_first:
            # The library's continuity rules for a later section; the reference
            # render above had no prose, so it gave the opening rules instead.
            ref2 = library(writer_context, plan_lines, plan_rules, first, last, 1,
                           section_words, "x", False, is_last)
            task2 = ref2.split("## Your Task", 1)[1].split("**OUTPUT FORMAT:**", 1)[0].strip()
            position, _, continuity = task2.partition("\n\n")
        so_far = ""
        if scene_so_far:
            paras = [p for p in scene_so_far.split("\n\n") if p.strip()]
            # The header must not change between calls, or it breaks the
            # cached prefix: no paragraph range in it.
            so_far = ("\n## The Scene So Far\n\n"
                      + "".join(p + "\n\n" + PARA for p in paras)
                      + CACHE_END)
        return PERITEM_TEMPLATE.format(
            story_context=P.story_context_section(ctx, task="write"),
            craft_rules=P.craft_rules(ctx),
            plan_rules=plan_rules,
            whole_plan=(skeleton_lines(skeleton, 1, len(skeleton),
                                       notes=ctx.get("paragraph_notes"))
                        if skeleton else plan_lines),
            cache_end=CACHE_END,
            scene_so_far=so_far,
            n=n,
            item_line=plan_lines,
            position_instruction=position.strip(),
            continuity_rules=continuity.strip(),
        )

    P.format_scene_section_prompt = fmt


# --- the A/B around the writer --------------------------------------------------------

def install_ab(project):
    from novel_agent.agent import segments as seg
    from novel_agent.agent.writer import SceneWriter
    original = SceneWriter.write_scene
    budget_for = seg.token_budget_for
    out = project / "ab"
    out.mkdir(exist_ok=True)

    def ab_write(self, writer_context):
        cfg = self.config
        saved = {k: cfg.get(k) for k in PERITEM}
        n = len(list(out.glob("scene_*_single.md")))
        (out / f"scene_{n:03d}_context.json").write_text(
            json.dumps(writer_context, indent=1, default=str))
        try:
            ARM["name"] = "single"
            cfg.set("generation.subblock_generation", False)
            a = original(self, copy.deepcopy(writer_context))
            (out / f"scene_{n:03d}_single.md").write_text(a.get("text", ""))
            (out / f"scene_{n:03d}_single.json").write_text(json.dumps(
                {k: v for k, v in a.items() if k != "text"}, indent=2, default=str))
            ARM["name"] = "peritem"
            for k, v in PERITEM.items():
                cfg.set(k, v)
            seg.token_budget_for = lambda w, c=None: PERITEM_MAX_TOKENS
            b = original(self, copy.deepcopy(writer_context))
        finally:
            seg.token_budget_for = budget_for
            for k, v in saved.items():
                cfg.set(k, v)
            ARM["name"] = "plan"
        (out / f"scene_{n:03d}_peritem.md").write_text(b.get("text", ""))
        (out / f"scene_{n:03d}_peritem.json").write_text(json.dumps(
            {k: v for k, v in b.items() if k != "text"}, indent=2, default=str))
        print(f"[ab] scene {n}: single {a.get('word_count')} words, "
              f"per-item {b.get('word_count')} words, sectioned={b.get('sectioned')}, "
              f"spent so far ${SPENT['usd']:.3f}")
        if not b.get("sectioned"):
            raise StopRun("the per-item arm fell back to single-shot")
        return a

    SceneWriter.write_scene = ab_write


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--foundation", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--ticks", type=int, required=True)
    ap.add_argument("--max-usd", type=float, required=True,
                    help="spend cap for this invocation; no call starts past it")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = ap.parse_args()

    sets = ["generation.enable_scene_skeleton=true",
            "generation.character_personas=true",
            "generation.paragraph_plan_by_model=true"] + args.set
    argv = sys.argv
    sys.argv = [argv[0], "--name", args.name, "--foundation", args.foundation,
                "--model", args.model, "--ticks", "0"]
    for s in sets:
        sys.argv += ["--set", s]
    run_cell.main()               # creates the project (or finds it); runs nothing
    sys.argv = argv
    project = run_cell.find_project(args.name)
    state = json.loads((project / "state.json").read_text())
    remaining = args.ticks - state.get("current_tick", 0)
    print(f"[ab] {project.name}: tick {state.get('current_tick')} -> {args.ticks}, "
          f"cap ${args.max_usd:.2f}")
    if remaining <= 0:
        return

    install_requests(project / "usage.jsonl", args.max_usd)
    install_peritem_prompt()
    install_ab(project)
    os.chdir(project)
    from novel_agent.cli.main import run
    try:
        run(n=remaining, project=str(project), checkpoint_interval=0, retries=0)
    except StopRun as e:
        print(f"[ab] STOPPED: {e}. Spent ${SPENT['usd']:.3f} this invocation.")
        sys.exit(3)
    print(f"[ab] done. Spent ${SPENT['usd']:.3f} this invocation.")


if __name__ == "__main__":
    main()
