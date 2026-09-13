# Prompt Architecture: one context spine, two tasks

**Status:** Plan, not yet built
**Date:** 2026-09-13
**Cause:** Sectioned writing and selective revision were built quickly on top of a
context assembly that took months, and they silently dropped most of it.
**Serves:** `agent/prompts.py`, `agent/writer.py`, `agent/writer_context.py`

---

## 1. The defect

The writer prompt carries 19 context fields. Audited against it:

| prompt | fields carried | dropped |
|---|---:|---:|
| `WRITER_PROMPT_TEMPLATE` | 19 | 0 |
| `SCENE_SECTION_PROMPT_TEMPLATE` | 12 | 14 |
| `PARTIAL_REVISION_PROMPT_TEMPLATE` | 10 | 19 |

(The section prompt adds fields of its own, hence 12 carried against 14 dropped.)

Four of the dropped fields are contracts, not decoration:

| field | what its absence disables |
|---|---|
| `approved_new_names` | **Phase 1 grounded identity.** The writer may invent names again |
| `plot_beat_section` | plot-first beats never reach the writer |
| `arc_pressure_section` | the tension target the arc system exists to deliver |
| `recent_context` | continuity with prior scenes |

So `generation.subblock_generation: true` quietly switches off four features.
This is not theoretical: the first live sectioned scene invented three
characters (Tarex, Renex, Vexul) instead of using the foundation's protagonist,
and that was filed at the time as first-tick noise. It was the naming contract
being bypassed.

Every judged number in section 5 was produced by that pipeline. They are a
floor for the architecture, not a measurement of it.

## 2. What we are building

Three layers, replacing three hand-picked field subsets.

**A context spine, shared by every call.** One renderer over the context
`WriterContextBuilder` already assembles: story, recent story, the scene's
plan, POV, location, cast and naming, beat, arc pressure. No call picks its
own subset; a call may only omit a field that genuinely does not apply, and
must say why in code.

**Plan rules, shared by every plan-driven call.** Already factored out as
`scene_skeleton.plan_rules()`: markers, one item one paragraph, the
one-speech-turn dialogue rule, per-item lengths.

**A task block per call type.** Originally specified as two templates rather
than three, on the argument that single-shot and sectioned writing are the same
task at different scope.

**Revised while building (2026-09-13).** The merge was the wrong move and the
templates stay separate. The single-shot task block carries SCENE-shape
requirements ("execute the key change", "build to a turning point: opening,
rising action, turning point, resolution", "use the planned transition",
"honour dialogue targets") that describe the arc of a whole scene. Handing
those to a call writing paragraphs 21 to 30 would ask a middle section to open,
turn and resolve on its own. What was actually shared and missing was the
per-call *craft* discipline, now extracted as `craft_rules()`: POV, naming,
show-don't-tell, sensory grounding, no head-hopping. Sections had none of it.

The deeper correction: **the contract test is what prevents drift, not the
template count.** Merging templates would have been a readability choice
wearing a safety argument. Craft markers are now in the contract test too, so
either template losing them fails.

```
story_context_section(ctx)      shared by all calls
plan_rules(...)                 shared by all plan-driven calls
  write task   (scope: whole | blocks a..b; position: open | middle | land)
  revise task  (targets, invariants)
```

### Why revision keeps its own task block

Sharing the *context* is right. Sharing the *task* is not, and one case shows
why. The writer's naming block carries `approved_new_names` under an
instruction to use them for new characters. A revision needs the same data
with the opposite directive: the cast is fixed, introduce no new named
entities, because a revision inventing a character is a continuity break
rather than a creative choice. Same field, inverted instruction. A shared task
block would either lose that distinction or accumulate conditionals until it
is unreadable.

Revision invariants, stated in its task block: events unchanged, cast
unchanged, paragraph count fixed, length close to what is replaced, only the
pressure changes.

## 3. Ordering: static first, volatile last

Required for prompt caching and free to do now.

```
craft rules and role            identical for every call, whole project
story foundation, POV, location, cast, naming
beat, arc pressure              identical across one scene's sections
plan rules
---- cache breakpoint ----
this call's plan slice          volatile
the prose so far                volatile, grows per section
task, position, output format   last, for instruction recency
```

The current section prompt interleaves: it puts the growing `scene_so_far`
*before* the static plan rules, so the prose poisons the prefix. Static-first
also suits instruction-following, since the task stays last.

**Caching is not enabled by this change.** `send_prompt_openrouter_meta` sends
plain messages, and Anthropic caches only at explicit `cache_control`
breakpoints (unlike OpenAI, where it is automatic). Adding breakpoint support
to `llm-backends` is a separate follow-up, deliberately not done here: there is
no sense marking breakpoints in prompts that are about to be rewritten. Sizing
for when it happens: the scaffolding alone is ~242 tokens, under Anthropic's
1024-token minimum, but a spine carrying `recent_context` runs to several
thousand and clears it comfortably. On a five-section scene with a ~4,000-token
spine that is roughly 20,000 input tokens uncached against ~6,600 cached.

## 4. Examples in the prompt

Every writing prompt today is zero-shot. Grepping the repo for few-shot,
zero-shot, exemplar or worked-example returns nothing; the tension and
goal-relevance judges use anchored rubrics, which is about grading rather than
generating.

The corpus is the obvious source and it is already here: 38,495 masters
paragraphs annotated by block mode, alignable to their source text by the
machinery in `scripts/block_grammar_tables.py`. For a plan item reading
`ACTION, ~90 words` we can show a real masters ACTION paragraph of about 90
words.

**Decision required before building this part.** Those are pre-1930 works, so
examples carry Victorian register. The project already frames the skeleton as
making the masters' register "a choice rather than an accident of the model's
defaults" (`SLICE4_SCENE_SKELETON_RESULTS.md` section 5), so this may be
exactly what is wanted. It should be decided rather than discovered. If the
answer is no, the fallback is hand-written modern examples matching the same
measured lengths and block types, which costs authoring effort and loses the
empirical grounding.

Scope when built: examples selected per mode and length band, at most two per
call, inserted in the static region so they stay cacheable.

## 5. Where we are starting from

Judged 2026-09-13 by the corpus DeepSeek protocol, 216 paragraphs across four
sectioned scenes, and 56 in a single-call control. `gpt-5.5` July figures for
reference; this run is `claude-sonnet-5` via OpenRouter, so writer model is a
confound between the columns.

| metric | masters | sectioned | single call | July |
|---|---:|---:|---:|---:|
| dialogue share | 0.565 | **0.565** | 0.607 | 0.500 |
| dialogue run mean | 3.32 | 3.13 | 2.83 | 2.91 |
| words per paragraph | 59.8 | 46.6 | 35.0 | 101.4 |
| return rate | 0.355 | 0.246 | 0.345 | 0.154 |
| shading rate | 0.204 | 0.102 | 0.107 | 0.266 |
| interiority self-transition | 0.205 | 0.053 | 0.143 | 0.000 |

Won: dialogue share is exact, dialogue run is close, paragraph length moved
from 70% over to 22% under, return rate rose from 0.154 to 0.246.
Lost: shading is now as far under as July was over, and interiority
self-transition is a quarter of the masters'.

One hypothesis already falsified, recorded so it is not re-proposed: section
seams do **not** break the excursion-return pattern. Measured against the
persisted section boundaries, return rate within a section is 0.219 (n=64)
against 0.381 across a seam (n=21). The deficit is distributed inside
sections, so sectioning is not its cause.

## 6. Not in scope

- `cache_control` support in `llm-backends` (follow-up, section 3).
- Changing how sectioning works. It costs marker discipline (2 of 4 scenes
  fully compliant against 1 of 1 single-call), its length benefit is real but
  modest (80% of target against 62%), and its supposed harm to the return rate
  failed its test. It is not what is limiting us.
- Chasing the shading and interiority deficits. Measure again after the spine
  lands; they may be downstream of the missing context.

## 7. Build order

1. `story_context_section()` plus the contract test, before any template moves.
   The test builds a context of sentinel values and asserts every contract
   field appears in every rendered prompt. This is the piece that would have
   caught the original defect, so it goes first.
2. Collapse the two writing templates into one task with a scope parameter.
3. Rewrite the revision task block over the shared spine, with its invariants.
4. Reorder static-before-volatile.
5. Re-measure: four scenes and a control on the same foundation, judged by the
   same protocol. Section 5 is the "before".
6. Examples, once the register question in section 4 is decided.

## 8. How we will know it worked

The contract test passing is necessary, not sufficient. The claim is that
restoring the four dropped contracts improves the page, so the measurable
predictions are:

- **Naming**: zero invented character names not drawn from the approved pool.
  Currently unmeasured; `CharacterDetector` already finds new names in prose,
  so the count is available.
- **Continuity**: scenes reference prior events. Judgeable, not yet judged.
- **Arc adherence**: `tension_delta` in the per-tick rubric should fall, since
  the writer will see the target for the first time on the sectioned path.
- **Structural metrics**: section 5's table, re-run. No prediction is made for
  shading or interiority; they are being observed rather than targeted.

If the structural metrics do not move, the honest conclusion is that the
dropped context was not what limited them, and section 5's floor was closer to
a ceiling than expected.
