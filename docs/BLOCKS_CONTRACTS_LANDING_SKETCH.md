# Blocks and Contracts: Landing Sketch

**Status:** Design (reconciliation, no implementation)
**Date:** 2026-07-09
**Reconciles:** `CONTRACTS_AND_BLOCKS_ARCHITECTURE.md` (2025-11-25) and `DSL_and_contracts.md` against the current codebase
**Roadmap home:** Phase 3 of `EMERGENT_COHERENCE_PLAN.md` ("Block/sub-block contracts (the DSL)")

The 2025-11-25 proposal predates all of the shipped Phase 1-3 work, so a naive
reading over-scopes it badly. Roughly half of the proposal has since shipped
under other names, a quarter is superseded by better mechanisms, and the rest
needs deliberate re-scoping to fit the "LLM decides what happens, Python holds
it to canon" direction. This document maps every proposal component onto the
current code, names the exact hook points in the tick loop, answers the
proposal's five open questions, and cuts the work into shippable slices.

The single most important fact for anyone reading the old proposal today: **a
prototype contract layer already exists** (`novel_agent/contracts/`), wired
into the tick at step 8.7 (`StoryAgent._check_beat_contract`), opt-in via
`generation.use_contracts` (default False), record-only. It already made the
key language decision (declarative JSON conditions checked by named Python
functions, not lambdas). What it lacks is an authoring path (nothing ever
writes `contracts.json`), durability across beat regeneration (the bug recorded
in `EMERGENT_COHERENCE_PLAN.md` §4), a precondition hook, and any consequence
for failure. That is the gap this sketch closes.

---

## 1. Component-by-component mapping

| Proposal concept | What exists today | Gap | Verdict |
|---|---|---|---|
| **StoryContract** (global constraints object) | Global pressures shipped as separate mechanisms: contradiction enforcement (`lore.enforce_contradictions` + `MultiStagePlanner._active_lore`), arc-pressure (`agent/arc_pressure.py`), throughline gate (`agent/throughline.py`), dedup at entity creation (Phase 1) | No single `StoryContract` class, and none is needed; a bag of independently-gated pressures is easier to A/B and dial than one monolith | **Drop** the class. Config (`coherence.*`, `lore.*`) is the story-level contract surface |
| **BeatContract** (pre/postconditions per beat) | `contracts/beat_contract.py`: declarative `BeatContract` with pre/postcondition lists, `to_dict`/`from_dict`, `from_beat` seeding. Checked record-only at step 8.7 | Not authored by anyone; stored in `contracts.json` keyed by `beat_id` (goes stale when the rolling horizon regenerates beats); preconditions never evaluated; failures have no consequence | **Extend**: move conditions onto `PlotBeat` itself so they serialize into `plot_outline.json` and live/die with the beat; author them at beat-generation time; wire into beat verification (see §2) |
| **Preconditions** (checked before generation) | `BeatContract.validate_preconditions` exists but is never called from the tick | No hook; also no policy for what a failure means | **Extend** (Slice 2): evaluate when the beat is selected; unmet preconditions become planner *pressure* (set this up first) or defer the beat, never a hard raise |
| **Postconditions** (checked after generation) | Evaluated at step 8.7 against prose + memory + tension; 7 built-in checkers in `contracts/conditions.py` (`entity_exists`, `char_at_location`, `char_in_prose`, `prose_contains`, `tension_at_least`, `tension_at_most`, `loop_resolved`) | Runs after the beat-verification decision (step 8.5) instead of informing it; result is printed and returned but influences nothing | **Extend** (Slice 1): fold into step 8.5 as a deterministic verification signal alongside the semantic score |
| **Pre/postconditions as Python callables (lambdas)** | Deliberately replaced by the flat JSON `Condition` (`{"check": name, ...params}`) + checker registry | None; the prototype already corrected the proposal | **Reuse** as-is. This is the settled contract language (see §3 Q5) |
| **EntityRegistry** (centralized creation + fuzzy dedup) | Phase 1 grounded identity: `NameGenerator` (dedup against used names, shared instance threaded through character/location/faction generate tools), `MemoryManager` ID counters (reconciled against disk, no ID reuse), `EntityResolver` (planner/beat refs resolved by selection, phantoms dropped), `CharacterDetector` grounding writer-introduced names | The proposal's `EntityRegistry` class does not exist as such, but everything it was for does | **Reuse**. Do not build the class; `MemoryManager` + `NameGenerator` + `EntityResolver` are the registry |
| **Item / inventory system** | Nothing. No `Item` entity, no counter, no inventory field on `Character` | Full build: entity type, persistence, extraction (who picked up what), checkers, prompt surface | **Defer**. Inventory consistency without a story that needs it is bookkeeping without payoff; the real use case is the Phase 4 planted-element ledger (Chekhov's gun). Build a minimal `Item` only when a contract first needs `char_has_item`, likely as part of Phase 4 |
| **ProseBlock / SubBlock** (typed narrative units) | Scene generation is single-shot (`SceneWriter.write_scene`, one prompt). The plan schema already carries soft structure hints: `scene_mode`, `transition_path`, `dialogue_targets`, `palette_shift`, `scene_length` | No block objects, no block-level generation | **Build later, scaled down** (Slice 4): a *scene skeleton* (ordered, typed sub-block list) as writer guidance inside the existing single prompt, not per-block LLM calls. Per-sub-block generation stays out until single-shot demonstrably fails (see §5) |
| **Transition** (dataclass with journey/time-skip flags) | `plan.transition_path` (planner-authored, feeds the writer prompt and QA's `transition_clarity`); arc-pressure already stages transitions for big tension drops (`arc_pressure_guidance_for_planner`, `revise_for_tension` continuity line) | No structured Transition object | **Drop** the dataclass for now; the prose-level need is served. Revisit as a skeleton sub-block type in Slice 4 |
| **BlockPlanner** (fixed setup/action/climax template per beat) | Nothing, by design | The proposal's static template scripts *how* the story is told, which is the Craft layer the LLM owns | **Drop** the fixed-template version. If skeletons land (Slice 4), the *planner LLM* authors the skeleton and Python validates it (closed type vocabulary, linear, bounded count) |
| **Per-sub-block generation + incremental state update** | Nothing. State updates happen once per scene (fact/lore extraction, steps 9-12) | 5-10x LLM calls per tick, plus a new mid-scene state model | **Build as a measured experiment** (Slice 5): single-shot scenes read as superficially coherent, and granularity is the standing hypothesis for richer text. Gated, instrumented, judged by A/B (see §5) |
| **NoCharacterDuplication / NoLocationDuplication constraints** | Prevented at creation time by Phase 1 grounding (strictly better than detecting duplicates after the fact) | None | **Reuse** (already satisfied) |
| **InventoryConsistency constraint** | Nothing (no items) | Depends on Item entity | **Defer** with items |
| **TensionPacing constraint** (min/max bounds, stagnation check) | Superseded by a better mechanism: arc-pressure target curve + LLM tension scorer + `tension_delta` in the coherence rubric (`memory/metrics.jsonl`); stagnation is visible in `novel metrics` | None worth closing; static min/max bounds are cruder than the curve | **Drop**. Per-beat tension conditions should *derive from* `PlotBeat.tension_target`, not add a third tension authority (see §6) |
| **Retry-with-feedback on contract failure** | The pattern exists for tension: `_maybe_rewrite_for_tension` (step 7.6), one bounded revision, kept only if closer, never raises | Not applied to contract failures | **Build** (Slice 3) by mirroring the proven pattern |

Summary: the proposal's *contract* half lands as a modest extension of shipped
code; the *entity* half already shipped under Phase 1; the *block* half lands
as prompt-level structure guidance first, then per-sub-block generation as a
measured experiment (Slice 5); items and global constraint objects are dropped
or deferred.

## 2. Hook points in the tick pipeline

All references are to `StoryAgent._normal_tick` in `novel_agent/agent/agent.py`
(step numbers as printed by the tick) unless noted.

| Pipeline point | Today | Change |
|---|---|---|
| **Beat generation** (`PlotOutlineManager.generate_next_beats` / `_parse_beats_response`, prompt `PLOT_GENERATION_PROMPT_TEMPLATE` in `agent/prompts.py`) | Emits beats with `tension_target`, `characters_involved`, `resolves_loops`, etc.; `_resolve_beat_references` forces refs to real IDs | Slice 1: the same prompt optionally emits 1-3 `postconditions` per beat from the closed checker vocabulary. `_resolve_beat_references` grows a sibling, `_resolve_beat_conditions`: unknown `check` names and unresolvable entity/loop refs are dropped with a warning, exactly like phantom character refs today. Authoring the contract *atomically with its beat* is what fixes the durability bug: when `revise_horizon` abandons a beat, its conditions go with it |
| **Beat selection** (top of `_normal_tick`, `self.plot_manager.get_next_beat()`) | Returns first pending beat | Slice 2: evaluate the beat's preconditions here (deterministic checks only, against `CheckContext(memory, state)`). Unmet preconditions do not raise; they are threaded into the planner context (step 1, `ContextBuilder.build_planner_context` / `MultiStagePlanner.plan_for_beat`) as explicit setup pressure, and optionally defer the beat |
| **Plan validation** (step 3, `schemas.py:validate_plan`) | JSON-schema check of planner output | Slice 4 only: add an optional `scene_skeleton` property (array of `{type, purpose}` objects) validated against the sub-block type vocabulary. No change in Slices 1-3 |
| **Writer context** (step 6, `WriterContextBuilder.build_writer_context`) | Injects `plot_beat_section` (with `tension_target`), `arc_pressure_section`, cast + name pool | Slice 1 (optional, cheap): render the beat's postconditions into `plot_beat_section` as plain-language "this scene must leave the story in a state where..." lines, so the writer aims at what the checker grades (the same lesson as unifying `tension_scale.py`). Slice 4: render the skeleton as structure guidance |
| **Scene evaluation** (step 7, `SceneEvaluator.evaluate_scene`) | Heuristic pass/fail + QA metrics | No change. Contracts do not join the hard pass/fail gate; a contract failure is a beat-verification concern, not a scene-rejection concern |
| **Tension rewrite** (step 7.6, `_maybe_rewrite_for_tension`) | One bounded revision toward the arc target | Slice 3 mirrors this as `_maybe_rewrite_for_contract`: one revision pass with the failed postconditions as feedback, kept only if strictly more conditions pass, never raises. Runs before commit so the committed scene is the best attempt |
| **Beat verification** (step 8.5, trusted-planner vs semantic-threshold paths, `_mark_beat_complete`) | Semantic similarity + planner trust decide completion | Slice 1, the heart of the change: when the current beat carries postconditions, evaluate them here (deterministic, after tension is known) and record the result on the beat (`contract_passed`, per-condition detail in `execution_notes` or a new field). Policy: conditions passing upgrades confidence (`verification_method="contract"`); conditions failing on an otherwise-verified beat downgrades to the existing failure paths (keep pending, or `_revise_horizon` when `generation.rolling_horizon` is on). This retires step 8.7's separate `contracts.json` lookup; `_check_beat_contract` and `ContractManager` remain only as a manual-override path, or are removed once the beat-embedded path lands |
| **Coherence metrics** (`_record_coherence_metrics` → `CoherenceMetrics.record_tick`) | Loop churn, contradictions, tension + target + delta, goal relevance | Slice 1: add `contract_conditions_checked` / `contract_conditions_failed` per tick, so contract adherence is measurable before it is enforceable (the same instrumentation-first discipline as the rest of Phase 3) |
| **First tick** (`_first_tick`) | No beats, no contracts | No change; contracts require plot-first mode and a current beat, same as beat verification today |

Failure handling follows the house convention throughout: contract evaluation
is wrapped, degrades gracefully, and never kills a tick or a multi-tick `run`.

## 3. The five open questions, answered

**Q1: Contract granularity (sub-block micro-contracts vs beat-level)?**
Beat-level only. The scene is the atomic unit that gets committed, evaluated,
scored for tension, and fact-extracted; there is no reliable gauge below it (a
sub-block boundary in generated prose is not even well-defined once the writer
produces a continuous scene). Sub-blocks, if they land, carry a `purpose`
string as guidance, not conditions. Micro-contracts would multiply the
validation surface exactly where the checkers are weakest.

**Q2: Fixed vs LLM-planned block structure?**
LLM-planned, Python-validated. A fixed setup/action/climax template per beat
type is NovelWriter's quadrant (high constraint on *content shape*), and it
directly contradicts the layering table in `EMERGENT_COHERENCE_PLAN.md` §2:
"how do we tell this story" is Craft, owned by the LLM. Python's job is the
closed vocabulary (the `SubBlockType` enum survives from the proposal), the
linearity rule (no nesting, append-only), and a bounded count. Concretely:
Stage 3 of `MultiStagePlanner` may emit an optional `scene_skeleton`; Python
validates and renders it, never invents it.

**Q3: Constraint recovery (retry / rollback / relax)?**
Retry-with-feedback, once, bounded, keep-only-if-better; then record and move
on. This is already the proven pattern (`_maybe_rewrite_for_tension`: revise,
re-score, keep only if closer). Rollback is ruled out by the pipeline shape:
by the time postconditions are checkable the scene is written and tension-scored,
and fact/lore extraction mutates entities right after; unwinding that is
expensive and error-prone. Silent relaxation is ruled out on principle, but
"record the failure, leave the beat pending, let the rolling horizon re-derive
the lookahead" is the honest version of relaxation: the story is never stuck,
and `metrics.jsonl` keeps the audit trail. A *consistently* failing contract is
a signal the beat is wrong, and the rolling horizon is the mechanism that
already exists to fix wrong beats.

**Q4: How much validation overhead is acceptable?**
Deterministic checks are effectively free (they read memory JSON and the prose
string); run as many as the beat declares. LLM-judged checks are the real
cost, so the budget is: preconditions are deterministic-only (they run every
tick a beat is pending); postconditions get at most one LLM call per beat, and
only via a future `event_occurs` judge checker (see §5), reusing the prompt
shape of `_verify_beat_execution`. Tension conditions reuse the score already
computed at step 7.5 (zero extra calls, via `CheckContext.scene_tension`).
No caching machinery: contract state is a few KB inside `plot_outline.json`,
which is already loaded multiple times per tick.

**Q5: Contract language (Python callables vs YAML/JSON vs custom DSL)?**
Declarative JSON conditions validated by a small set of named, registered
Python check functions. This is already decided and implemented in
`contracts/conditions.py`, and it is the right call for three compounding
reasons. First, serialization: contracts must ride inside `plot_outline.json`
next to their beat (the durability fix), and nothing that touches that file
can serialize a callable. Second, authorship: the beat-generation LLM already
emits structured JSON reliably under `PLOT_GENERATION_PROMPT_TEMPLATE`; asking
it to pick from a documented checker vocabulary is the same "select, don't
invent" move as Phase 1 naming. Third, safety and testability: named checkers
are a closed, unit-tested surface (`tests/unit/test_contracts.py` exists);
arbitrary lambdas are neither. A custom DSL adds a parser and a new failure
mode for zero expressive gain over `{"check": "loop_resolved", "loop": "OL3"}`.
The "DSL" in the roadmap's "block/sub-block DSL" should be read as this JSON
vocabulary plus the skeleton schema, not a new syntax.

Grow the checker vocabulary conservatively, in this order of preference:
memory-state checks (`entity_exists`, `loop_resolved`, future
`char_at_location` once fact extraction reliably updates locations), gauge
checks (`tension_at_most`/`at_least` against the existing scorer), grounded
prose checks (`char_in_prose` via known names), and only then raw
`prose_contains` (see §5 for why it is last).

## 4. Slices

### Slice 1 (MVP, one PR): contracts ride the beats

Shippable alone, valuable alone: deterministic postconditions, authored with
the beat, feeding beat verification, measured in the rubric.

- Add `preconditions: List[dict]` and `postconditions: List[dict]` to
  `PlotBeat` (`plot/entities.py`), default empty. Legacy outlines load
  unchanged (dataclass defaults); the fields serialize into
  `plot_outline.json` via the existing `asdict` round-trip.
- Extend `PLOT_GENERATION_PROMPT_TEMPLATE` to optionally emit 1-3
  postconditions per beat, documented as the closed checker vocabulary with
  one example each. Parse in `_parse_beats_response`; sanitize in a new
  `PlotOutlineManager._resolve_beat_conditions` (drop unknown checks and
  phantom refs, warn, never fail beat generation).
- In `_normal_tick` step 8.5: when the current beat has postconditions, build
  the existing `CheckContext` (memory, state, prose, tension) and evaluate via
  the existing `evaluate_conditions`. Record per-condition results on the
  beat; use the aggregate to set `verification_method="contract"` on pass and
  to route to the existing keep-pending / `_revise_horizon` paths on fail.
- Record `contract_conditions_checked` / `_failed` in `CoherenceMetrics`.
- Render the postconditions into the writer's `plot_beat_section` so the
  writer sees what will be checked.
- Reuse `generation.use_contracts` (stays default False); retire the
  `contracts.json` lookup at step 8.7 in favor of the beat-embedded path (keep
  `ContractManager` briefly as a manual-override shim, or delete it and its
  step, whichever the PR review prefers; the test file moves with it).

Explicitly out of scope for Slice 1: preconditions, any LLM-judged checker,
any rewrite-on-failure, blocks, items.

### Slice 2: precondition pressure

Evaluate the selected beat's preconditions before planning. Unmet conditions
are injected into `plan_for_beat` context as setup instructions ("before this
beat can land, X must be true; plan this scene to establish it or the beat
will be deferred"). A config knob decides whether a beat with unmet
preconditions is deferred (skipped for the next pending beat) or attempted
anyway with pressure. Never a raise: a hard precondition gate can deadlock
the loop (nothing forces the planner to ever satisfy it).

### Slice 3: bounded contract repair

`_maybe_rewrite_for_contract`, mirroring `_maybe_rewrite_for_tension`: when
postconditions fail and the failures are prose-addressable (not state checks),
one revision pass with the failed conditions as explicit feedback, kept only
if strictly more conditions pass. Add an `event_occurs` LLM-judge checker
(semantic "did this event happen in the scene", the `_verify_beat_execution`
prompt generalized) so beats can check events without keyword matching.

### Slice 4 (experimental, behind its own flag): scene skeletons

The block layer, scaled to fit: optional `scene_skeleton` in the plan schema
(ordered `{type, purpose}` list from the `SubBlockType` vocabulary), authored
by Stage 3 of the multi-stage planner, validated in `validate_plan`, rendered
into the writer prompt as structure guidance for the *single* scene call.
`SceneEvaluator` gains a soft skeleton-adherence warning (never a failure).
Per-sub-block generation is deliberately not in this slice; it is Slice 5,
and skeletons are its prerequisite (the skeleton defines the sub-block
boundaries Slice 5 generates against).

### Slice 5 (experiment, behind its own flag): per-sub-block generation

The granularity hypothesis, tested rather than assumed: single-shot scenes
read as superficially coherent, and generating each skeleton sub-block with
its own focused call may produce richer, denser text than one prompt can.
Behind `generation.subblock_generation` (default False), orthogonal to the
Slice 4 flag: when on, the writer generates the scene sub-block by sub-block
(each call sees the skeleton, the beat, and the prose so far), then one
stitch pass smooths seams. Measured as an A/B against skeleton-guided
single-shot on the same foundation and seed beats: the existing gauges
(tension adherence, QA metrics, goal relevance), a prose-richness LLM judge
(specificity, sensory density, interiority, subtext, scored against anchored
examples the way the tension rubric is), a voice-continuity judge across
sub-block seams, cost per scene, and a human read. Promote the mode only if
richness wins and voice continuity holds; otherwise it stays an experiment
flag with its findings recorded.

## 5. Risks and tensions with the emergent philosophy

- **Keyword postconditions are the keyword tension heuristic again.** The
  proposal's example (`"blackout" in prose.lower()`) checks surface vocabulary,
  and this codebase has now twice proven that surface-vocabulary gauges cannot
  see the property they name (keyword tension collapsed to a flat ~6; embedding
  goal-relevance measured topic overlap, not progress). A scene can depict a
  blackout without the word, and contain the word without the event. Keep
  `prose_contains` in the vocabulary (it is occasionally right, e.g. a required
  proper noun) but steer the authoring prompt away from it; prefer state checks
  (`loop_resolved`, `entity_exists`), the tension gauge, `char_in_prose` (which
  matches any known name or nickname), and the Slice 3 `event_occurs` judge.
- **Contracts must check the beat's job, not the prose's wording.** Cap
  conditions per beat (1-3) in the authoring prompt and sanitizer. A beat with
  ten conditions is an outline pretending to be a guardrail.
- **Hard gates stall the loop.** Precondition failure as a raise, or
  postcondition failure as a tick failure, would end multi-tick runs on the
  first stubborn beat (the run loop retries a failed tick only `--retries`
  times). Everything here is pressure, deferral, or horizon revision;
  graceful degradation is the house rule and contracts are no exception.
- **Fixed block templates script the Craft layer.** The proposal's
  `BlockPlanner` hardcodes setup/action/climax; that is pre-baked structure on
  the content axis, the exact move §1 of the roadmap rejects. Skeletons must
  stay LLM-authored, Python-validated.
- **Per-sub-block generation is expensive and risks Frankenstein prose.**
  5-10 LLM calls per scene instead of one, each with rebuilt context, plus a
  mid-scene state-update model that does not exist. Voice continuity across
  independently generated 300-token chunks is unproven. The counter-risk is
  real too: single-shot scenes are only superficially coherent, and
  granularity is a plausible route to richer text than one prompt produces.
  So these are the variables the Slice 5 experiment measures, not reasons to
  skip it: run it gated, A/B against single-shot on the same foundation, and
  let the gauges plus a human read decide.
- **Inventory tracking without payoff is dead weight.** Items only matter when
  a later scene must remember them, which is precisely the Phase 4
  setup/payoff ledger. Building `Item` now would add an entity type, an
  extractor burden, and checkers that no beat asks for. Deferred is not
  dropped: the contract vocabulary is designed to grow a `char_has_item`
  checker without any schema change.
- **Two contract stores would be worse than one.** Slice 1 must actually
  retire the `contracts.json` path (or demote it to an explicit manual
  override), not run both. A beat-embedded contract and a file contract
  disagreeing about the same `beat_id` is the durability bug reborn.

## 6. Composition with the arc-phase planner mandate

The arc-phase mandate (roadmap frontier item 1) is landing in parallel and, as
of this writing, sits uncommitted in the working tree: `derive_arc_phase` /
`compute_arc_phase` in `agent/arc_pressure.py` derive rising / peak / falling /
resolution from the target curve; `ARC_PHASE_MANDATES` injects firm,
event-level instructions into `arc_pressure_guidance_for_planner` (gated by
`coherence.arc_phase_mandate`, default True); `rewrite_futile` skips the step
7.6 prose rewrite when the drop needs different events; and the phase is
recorded per tick in the coherence rubric.

It overlaps contracts at exactly one point: tension. Three mechanisms could
plausibly claim a scene's tension target: the arc-pressure curve plus phase
mandate, the beat's `tension_target` (authored at beat-generation time), and a
contract `tension_at_least`/`tension_at_most` condition. The composition rule
is a strict chain of custody, so they cannot fight:

1. **Arc-pressure (target plus phase) must inform beat generation.** This is
   the gap the mandate does not yet cover, and it matters doubly under
   contracts: the mandate is injected via Stage 1 of the multi-stage planner
   (`_build_strategic_prompt`), but `plan_for_beat` (the plot-first path)
   *bypasses Stage 1 entirely*, so in exactly the mode where contracts run,
   the mandate never reaches the planner and the beat governs. Fix at the
   source: pass `compute_target_tension` and `compute_arc_phase` into
   `PlotOutlineManager._build_generation_context`, so newly generated beats
   carry `tension_target` values (and event kinds: escalate / confront /
   resolve) already shaped by the curve. This also attacks the validated
   de-escalation failure (`progress_report_20260602.md`) where tension lives:
   in the events the beats prescribe.
2. **The beat's `tension_target` governs its scene.** This precedence already
   exists: `WriterContextBuilder._build_arc_pressure_section` suppresses the
   arc-pressure writer section when the plan's beat carries a
   `tension_target`. Keep it.
3. **Contracts may author tension conditions, because their author is the
   beat's author.** The same LLM call that writes the beat writes its
   conditions, grounded in the prose so far, so a `tension_at_least` or
   `tension_at_most` condition is emergent (derived from previous outputs),
   not hand-inserted. The guard is consistency, not prohibition: the sanitizer
   checks an authored tension condition against the beat's own
   `tension_target` (within the `coherence.tension_rewrite_threshold` band)
   and reconciles or warns on contradiction, so beat and contract cannot
   disagree about the same scene. Where the LLM authors no tension condition
   and the beat has a target, the sanitizer may still derive one (target 8
   yields `tension_at_least: 6`). The proposal's global `TensionPacing`
   constraint stays dropped: a static min/max band is a fourth voice saying a
   cruder version of what the curve already says.

The `rewrite_futile` lesson carries over to Slice 3: contract repair should
only attempt a prose rewrite for prose-addressable failures. A failed
state-level condition (`loop_resolved`, `char_at_location`) or a tension
condition a full transition step off means the *events* are wrong, which is
the planner's and rolling horizon's job, not the rewriter's.

One interaction to preserve from the arc-phase design: in the falling and
resolution phases, arc-pressure wins over the throughline gate (be calm beats
advance-the-goal). Contracts inherit that automatically under rule 1, because
a resolution-phase beat will carry a low `tension_target` and therefore, if
anything, a `tension_at_most` condition. The gauges stay consistent end to
end: one `TENSION_ANCHORS` scale, one scorer, one target per scene, and the
contract checks the same number everything else steered toward.

## References

- `docs/CONTRACTS_AND_BLOCKS_ARCHITECTURE.md`, `docs/DSL_and_contracts.md`: the original proposal
- `docs/EMERGENT_COHERENCE_PLAN.md` §2 (layering), §4 (why Phase 1/2 precede the DSL)
- `novel_agent/contracts/`: the shipped prototype (conditions, BeatContract, ContractManager)
- `novel_agent/agent/agent.py`: `_normal_tick` steps 8.5 and 8.7, `_maybe_rewrite_for_tension`, `_revise_horizon`
- `novel_agent/plot/manager.py`: beat generation, `_resolve_beat_references`, `revise_horizon`
- `docs/progress_report_20260602.md`: the de-escalation finding motivating arc phases
