#!/usr/bin/env python3
"""Write the generated arms of the blind test (Austen vs StoryDaemon vs plain Opus).

For each scene in briefs.json, two fresh projects are made with the same
foundation, the same minted cast (names.json, from the StoryDaemon name
generator), the same story-so-far and the same plan. The writer is the real
StoryDaemon path: WriterContextBuilder -> (StoryAgent._plan_paragraphs) ->
SceneWriter.write_scene. The arms differ only in two flags:

    dsl     generation.enable_scene_skeleton + paragraph_plan_by_model on
    plain   both off

No planner, no extractors, no evaluator: they add cost and nothing to this test.

Guards (2026-11-08 lesson): every request goes through one wrapper that stops
the run before any call once the cap is reached, logs usage per call, and
STOPS THE RUN on the first response cut off by its token limit. --fake swaps
the model for a scripted one at the same point (no network, no spend) so the
whole path can be checked first.

    venv/bin/python experiments/blind_test/write_scenes.py --fake --scenes all
    venv/bin/python experiments/blind_test/write_scenes.py --scenes pp_32 --max-usd 0.40
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
WORK = REPO / "work" / "blind"
MODEL = "openrouter:anthropic/claude-opus-5.5"
ARMS = {
    # The DSL arm's paragraph plan is Austen's own (work/blind/plans, from
    # austen_plans.py, checked by hand), not one the model drafts: the model's
    # own plan recalled her chapter's events (2026-11-10).
    "dsl": {"generation.enable_scene_skeleton": True, "generation.paragraph_plan_by_model": False},
    # The DSL arm plus style targets measured from the author's own novel
    # (work/blind/style/<novel>.json, the passage itself left out).
    "dsl_style": {"generation.enable_scene_skeleton": True, "generation.paragraph_plan_by_model": False},
    "plain": {"generation.enable_scene_skeleton": False, "generation.paragraph_plan_by_model": False},
}
COMMON = {
    "generation.character_personas": False,       # manner comes from the brief
    "coherence.target_tension_curve": None,       # no arc-pressure target for a lone scene
    "generation.writer_canon": False,             # no lore in these projects anyway
    "generation.story_synopsis": True,            # the story-so-far rides the synopsis
    "generation.scene_max_segments": 2,
    # Room for Opus thinking on top of the prose. 3 was enough without style
    # targets (about 900 thinking tokens); with them Opus thought for 2,318
    # and was cut off at 3,209 (2026-11-10). Unused room costs nothing.
    "generation.scene_budget_multiplier": 8,
    "generation.paragraph_plan_max_tokens": 6000,
}
TITLES = {"croft": "Admiral", "brand": "Admiral", "wentworth": "Captain", "benwick": "Captain",
          "harville": "Captain", "brigden": "Captain", "colonel_campbell": "Colonel",
          "lady_russell": "Lady", "lady_dalrymple": "Lady", "lady_catherine": "Lady", "drew": "Sir"}


def full_names():
    """The cast list and the paragraph-plan roster show display_name, which is
    the first name only. In a novel of manners people are known as Mr Devereux
    or Lady Amelia, and the brief uses those forms, so show the full name (with
    title) to both arms."""
    from novel_agent.memory.entities import Character
    Character.display_name = property(lambda self: self.full_name)


class StopRun(BaseException):
    pass


STATE = {"usd": 0.0, "arm": "", "scene": "", "log": None}


# --- one wrapper around every request -------------------------------------------------

def install_requests(max_usd, fake):
    from openai.resources.chat.completions import Completions
    original = Completions.create

    def create(self, *args, **kwargs):
        if STATE["usd"] >= max_usd:
            raise StopRun(f"spend cap reached (${STATE['usd']:.3f} of ${max_usd:.2f})")
        t0 = time.time()
        resp = fake_response(kwargs) if fake else original(self, *args, **kwargs)
        u = resp.usage.model_dump() if getattr(resp, "usage", None) is not None else {}
        cost = float(u.get("cost") or 0.0)
        STATE["usd"] += cost
        finish = resp.choices[0].finish_reason if resp.choices else None
        prompt = (kwargs.get("messages") or [{}])[-1].get("content") or ""
        row = {"t": round(t0), "secs": round(time.time() - t0, 1), "scene": STATE["scene"],
               "arm": STATE["arm"], "kind": "plan" if "planning the paragraphs" in prompt else "write",
               "max_tokens": kwargs.get("max_tokens") or kwargs.get("max_completion_tokens"),
               "finish": finish, "cost": cost, "prompt_tokens": u.get("prompt_tokens"),
               "completion_tokens": u.get("completion_tokens"),
               "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
               "out_chars": len(resp.choices[0].message.content or "") if resp.choices else 0}
        with open(STATE["log"], "a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"    call: {row['kind']} finish={finish} out={row['out_chars']} chars "
              f"thinking={row['reasoning_tokens']} ${cost:.4f} (total ${STATE['usd']:.3f})", flush=True)
        if finish == "length":
            raise StopRun(f"a {row['kind']} call was cut off at {row['max_tokens']} tokens "
                          f"({row['reasoning_tokens']} spent thinking)")
        if not (resp.choices and (resp.choices[0].message.content or "").strip()):
            raise StopRun(f"a {row['kind']} call came back empty")
        return resp

    Completions.create = create


def fake_response(kwargs):
    """A scripted model: a valid paragraph plan, or marked prose of the planned
    shape. Exercises parsing, marker stripping and saving; costs nothing."""
    from openai.types.chat import ChatCompletion
    prompt = (kwargs.get("messages") or [{}])[-1].get("content") or ""
    if "planning the paragraphs" in prompt:
        ids = re.findall(r"^- (C\d{3}): ", prompt, re.M)
        items = []
        for kind, n in re.findall(r"^- ([A-Z]+): (\d+) \(anything", prompt, re.M):
            for i in range(int(n)):
                it = {"kind": kind, "what": f"Something happens ({kind.lower()} {i + 1})."}
                if kind == "DIALOGUE":
                    it["speaker"] = ids[i % min(2, len(ids))]
                items.append(it)
        text = json.dumps({"paragraphs": items})
    else:
        n = len(re.findall(r"^\s*(\d+)\. [A-Z]+", prompt, re.M)) or 8
        m = re.search(r"(\d[\d,]*) words", prompt)
        words = int(m.group(1).replace(",", "")) if m else 900
        per = max(10, words // n)
        marked = "plan number in square brackets" in prompt
        paras = [("[%d] " % (i + 1) if marked else "") + " ".join(["The morning was quiet."] * (per // 4))
                 for i in range(n)]
        text = "\n\n".join(paras)
    return ChatCompletion.model_validate({
        "id": "fake", "object": "chat.completion", "created": 0, "model": "fake",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(text) // 4,
                  "total_tokens": 0, "cost": 0.0}})


# --- one project per scene and arm ----------------------------------------------------

def make_project(scene_id, arm, brief, names, foundation):
    from novel_agent.cli.foundation import StoryFoundation
    from novel_agent.cli.project import create_novel_project
    from novel_agent.memory.entities import Character, Location
    from novel_agent.memory.manager import MemoryManager

    novel = names[brief["novel"]]
    people = novel["people"]
    pov = people[brief["pov"]]
    pov_name = f"{pov['first']} {pov['last']}"
    f = StoryFoundation(
        genre=foundation["genre"], setting=foundation["setting"], tone=foundation["tone"],
        premise=foundation["premises"][brief["novel"]],
        protagonist_archetype=brief["cast"][brief["pov"]],
        protagonist_name=pov_name, protagonist_gender=pov["gender"], protagonist_age=pov["age"])
    base = WORK / "projects"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(create_novel_project(
        "untitled", base_dir=str(base), foundation=f, llm_backend="api", llm_model=MODEL,
        name_banks={"person_bank": "victorian", "place_bank": "victorian", "register": "gentry"}))
    memory = MemoryManager(path)

    ids = {}
    pov_id = None
    for cid in memory.list_characters():          # the protagonist minted at creation
        c = memory.load_character(cid)
        if f"{c.first_name} {c.family_name}" == pov_name:
            pov_id = cid
            c.role, c.description = brief["cast"][brief["pov"]], brief["cast"][brief["pov"]]
            memory.save_character(c)
    if pov_id is None:
        raise StopRun(f"{scene_id}: the protagonist was not minted as {pov_name}")
    ids[brief["pov"]] = pov_id
    for key, role in brief["cast"].items():
        if key == brief["pov"]:
            continue
        p = people[key]
        cid = memory.generate_id("character")
        memory.save_character(Character(
            id=cid, first_name=p["first"], family_name=p["last"], title=TITLES.get(key, ""),
            gender=p["gender"], age_group=p["age"], role=role, description=role,
            metadata={"source": "blind_test", "minted": "generated (names.json)"}))
        ids[key] = cid

    loc = brief["location"]
    name = novel["places"][loc["key"]] if loc.get("key") else loc["name"]
    lid = memory.generate_id("location")
    memory.save_location(Location(id=lid, name=name, description=loc["description"]))
    memory.save_synopsis({"version": 1, "arcs": [], "synopsis": brief["story_so_far"]})
    return path, memory, pov_id, lid, ids


def scaled(words):
    """A paragraph's target from Austen's length. Opus writes over each
    target, more so on short ones (step 2: about 1.0-1.4x, 3.4x on a
    13-word item), so aim under by size."""
    f = 0.88 if words >= 60 else 0.8 if words >= 25 else 0.7
    return max(3, round(words * f))


def austen_plan(scene_id, brief, names):
    """Austen's paragraph plan: kinds, one line per paragraph (with the
    speaker for dialogue) and a scaled word target per paragraph."""
    items = json.loads((WORK / "plans" / f"{scene_id}.json").read_text())
    people = names[brief["novel"]]["people"]

    def who(k):
        p = people[k]
        return f"{TITLES.get(k, '')} {p['first']} {p['last']}".strip()
    kinds = [it["kind"] for it in items]
    notes = [(f"{who(it['speaker'])} speaks. " if it["kind"] == "DIALOGUE" and it.get("speaker") else "")
             + it["what"] for it in items]
    targets = [scaled(it["words"]) for it in items]
    return kinds, notes, targets, [it["words"] for it in items]


def style_section(novel, words):
    """Style targets from the author's measured profile, turned into counts
    for a scene of this length. Plain English, one line per measure."""
    p = json.loads((WORK / "style" / f"{novel}.json").read_text())
    per = lambda rate: max(1, round(rate * words / 1000))
    return f"""

**Style targets (measured from the period's own novels; hit these numbers):**
- Sentences average about {round(p['sentence_mean_words'])} words, and their lengths vary a great deal: about {p['short_sentence_pct']}% are 6 words or fewer and about {p['long_sentence_pct']}% run to 30 words or more. Build the long ones from balanced clauses joined by commas and semicolons.
- Semicolons: about {per(p['semicolons_per_1k'])} in this scene ({p['semicolons_per_1k']} per 1,000 words), in narration and in speech.
- Dashes: about {per(p['dashes_per_1k'])} in this scene, written as an em dash (—), where speech breaks off or turns.
- No contractions anywhere, in speech or narration: "do not", "cannot", "I am", "it is".
- Speech: about {p['speech_word_pct']}% of the scene's words inside quotation marks.
- "said" for about {round(p['said_share'] * 100)}% of speech tags; otherwise "replied", "cried", "answered" and the like.
- Avoid "seemed", "felt", "as if", "as though", "suddenly", "somehow": at most {per(p['seemed_felt_per_1k'])} in the whole scene."""


def write_arm(scene_id, arm, brief, names, foundation, llm_factory):
    from novel_agent.agent.agent import StoryAgent
    from novel_agent.agent.writer import SceneWriter
    from novel_agent.agent.writer_context import WriterContextBuilder
    from novel_agent.cli.project import get_project_config

    STATE["arm"], STATE["scene"] = arm, scene_id
    from novel_agent.agent import scene_skeleton as S
    kinds, notes, targets, _austen = austen_plan(scene_id, brief, names)
    total = sum(targets)
    original = getattr(S, "_blind_original_targets", S.block_word_targets)
    S._blind_original_targets = original
    S.block_word_targets = (lambda sk, seed=None: list(targets) if list(sk) == kinds
                            else original(sk, seed))
    path, memory, pov_id, lid, ids = make_project(scene_id, arm, brief, names, foundation)
    config = get_project_config(str(path))
    for k, v in {**COMMON, **ARMS[arm],
                 "generation.default_scene_length": "long",
                 "generation.scene_word_targets": {"brief": 300, "short": total,
                                                   "long": total, "extended": total}}.items():
        config.set(k, v)
    state = json.loads((path / "state.json").read_text())
    state["current_tick"] = 12
    state["novel_name"] = "(untitled)"
    intention = brief["intention"]
    if brief.get("secret"):
        intention += f" (Known to the author, never to be stated in this scene: {brief['secret']})"
    if arm == "plain":
        # The same events as the DSL arm, with no kinds, lengths or paragraphing.
        intention += "\n\nWhat happens, in order:\n" + "\n".join(f"- {n}" for n in notes)
    plan = {"scene_intention": intention, "key_change": brief["key_change"],
            "pov_character": pov_id, "target_location": lid, "metadata": {}}
    if ARMS[arm]["generation.enable_scene_skeleton"]:
        plan["scene_skeleton"] = list(kinds)

    llm = llm_factory()
    writer = SceneWriter(llm, config)
    ctx = WriterContextBuilder(memory, None, config).build_writer_context(plan, {}, state)
    # These scenes come from the middle of a novel with no earlier scenes on
    # disk; the library's empty-history line would tell the writer otherwise.
    ctx["recent_context"] = ctx["recent_context"].replace(
        "This is the first scene of the novel.", "This scene comes from the middle of the novel.")
    if ARMS[arm]["generation.enable_scene_skeleton"]:
        old = S.skeleton_prompt_section(kinds)
        if old not in ctx["scene_length_guidance"] or ctx.get("scene_skeleton") != kinds:
            raise StopRun(f"{scene_id}/{arm}: Austen's plan did not reach the writer")
        ctx["scene_length_guidance"] = ctx["scene_length_guidance"].replace(
            old, S.skeleton_prompt_section(kinds, notes))
        ctx["paragraph_notes"] = notes
        if arm == "dsl_style":
            ctx["scene_length_guidance"] += style_section(brief["novel"], total)
    if ARMS[arm]["generation.paragraph_plan_by_model"]:
        stub = SimpleNamespace(config=config, memory=memory, writer=writer, state=state)
        stub._known_names = lambda: StoryAgent._known_names(stub)
        ctx = StoryAgent._plan_paragraphs(stub, ctx)
        if not (ctx.get("paragraph_plan_report") or {}).get("accepted"):
            raise StopRun(f"{scene_id}/{arm}: the paragraph plan was not accepted: "
                          f"{(ctx.get('paragraph_plan_report') or {}).get('problems')}")
    prompt = writer._format_writer_prompt(ctx)
    out = WORK / "out" / scene_id
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{arm}_prompt.txt").write_text(prompt)
    result = writer.write_scene(ctx)
    text = result.get("text", "")
    (out / f"{arm}.md").write_text(text)
    meta = {k: v for k, v in result.items() if k != "text"}
    meta.update(project=str(path), word_target=total, austen_words=brief["words"],
                skeleton=ctx.get("scene_skeleton"), plan_report=ctx.get("paragraph_plan_report"))
    (out / f"{arm}.json").write_text(json.dumps(meta, indent=1, default=str))
    return text, meta, memory, state


def check(scene_id, arm, text, meta, memory, state, brief):
    """Hard faults only (the rule for re-writes): unfinished, far off length,
    a name the generator never minted. Taste is never a reason."""
    from novel_agent.agent.name_hygiene import prose_gauge
    faults = []
    words = len(text.split())
    if meta.get("trimmed") or not meta.get("concluded_naturally", True):
        faults.append("did not end on its own")
    if not 0.6 * brief["words"] <= words <= 1.5 * brief["words"]:
        faults.append(f"{words} words for a target of {brief['words']}")
    if arm.startswith("dsl") and not meta.get("skeleton_compliance"):
        faults.append("no skeleton compliance recorded (plan not used?)")
    if re.search(r"^\s*\[\d+\]", text, re.M):
        faults.append("paragraph markers left in the prose")
    roster = []
    for cid in memory.list_characters():
        c = memory.load_character(cid)
        roster += [c.first_name, c.family_name, c.full_name]
    roster += [l.name for l in (memory.load_location(i) for i in memory.list_locations()) if l]
    novel = json.loads((WORK / "names.json").read_text())[brief["novel"]]
    roster += [v for p in novel["people"].values() for v in (p["first"], p["last"])]
    roster += list(novel["places"].values())          # places the story mentions
    gauge = prose_gauge(text, roster, state.get("story_foundation") or {})
    names = gauge.get("unregistered_names") or gauge.get("other") or []
    names = sorted({re.sub(r"['\u2019]s$", "", n) for n in names} - set(roster))
    if names:
        faults.append(f"names not in the cast (check by hand, the gauge has false alarms): {names}")
    shared = verbatim_overlap(text, scene_id)
    if shared:
        faults.append(f"{len(shared)} eight-word runs shared with Austen, e.g. {shared[0]!r}")
    paras = [len(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    _k, _n, _t, austen = austen_plan(scene_id, brief, json.loads((WORK / "names.json").read_text()))
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0
    print(f"  {scene_id}/{arm}: {len(paras)} paragraphs (Austen {len(austen)}), median "
          f"{med(paras)} words (Austen {med(austen)})", flush=True)
    print(f"  {scene_id}/{arm}: {words} words, segments {meta.get('segments_used')}, "
          f"{'OK' if not faults else 'CHECK: ' + '; '.join(faults)}", flush=True)
    return faults


def verbatim_overlap(text, scene_id, n=8):
    """Eight-word runs the scene shares with the renamed Austen excerpt: Opus
    knows these books, and a copied line would spoil the test."""
    src = WORK / "austen" / f"{scene_id}.md"
    if not src.exists():
        return []
    norm = lambda t: re.findall(r"[a-z']+", t.lower().replace("\u2019", "'"))
    a, b = norm(src.read_text()), norm(text)
    grams = {tuple(a[i:i + n]) for i in range(len(a) - n + 1)}
    return [" ".join(b[i:i + n]) for i in range(len(b) - n + 1) if tuple(b[i:i + n]) in grams]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", required=True, help="comma list of scene ids, or 'all'")
    ap.add_argument("--arms", default="dsl,plain")
    ap.add_argument("--max-usd", type=float, default=0.0)
    ap.add_argument("--fake", action="store_true", help="scripted model, no network, no spend")
    args = ap.parse_args()
    if not args.fake and args.max_usd <= 0:
        raise SystemExit("a real run needs --max-usd")

    briefs = json.loads((WORK / "briefs.json").read_text())
    names = json.loads((WORK / "names.json").read_text())
    scenes = list(briefs["scenes"]) if args.scenes == "all" else args.scenes.split(",")
    STATE["log"] = WORK / ("usage_fake.jsonl" if args.fake else "usage.jsonl")
    install_requests(args.max_usd if not args.fake else 1.0, args.fake)
    full_names()

    def llm_factory():
        from novel_agent.tools.llm_setup import initialize_llm_with_persona
        return initialize_llm_with_persona(backend="api", model=MODEL, timeout=300)

    report = {}
    try:
        for sid in scenes:
            for arm in args.arms.split(","):
                print(f"[blind] {sid} / {arm}", flush=True)
                text, meta, memory, state = write_arm(sid, arm, briefs["scenes"][sid], names,
                                                      briefs["foundation"], llm_factory)
                report[f"{sid}/{arm}"] = check(sid, arm, text, meta, memory, state, briefs["scenes"][sid])
    except StopRun as e:
        print(f"[blind] STOPPED: {e}", flush=True)
    print(f"[blind] spent ${STATE['usd']:.3f}; {sum(1 for v in report.values() if not v)} of "
          f"{len(report)} clean", flush=True)
    (WORK / ("report_fake.json" if args.fake else "report.json")).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
