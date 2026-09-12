# Emergent Coherence Plan

**Status:** active roadmap · **Supersedes nothing; sequences existing proposals**

This is the spine that ties together the existing design docs and fixes their
ordering. It records the paradigm decision reached in discussion and the
dependency chain that determines what we build first. It does **not** restate
the detailed designs — it points at the docs that already contain them.

Related docs (execute against these for detail):
- `docs/DSL_and_contracts.md` — the scene-composition DSL sketch (blocks/sub-blocks).
- `docs/CONTRACTS_AND_BLOCKS_ARCHITECTURE.md` — full contract/block/entity-registry spec.
- `docs/BLOCKS_CONTRACTS_LANDING_SKETCH.md`: reconciles the two docs above with shipped
  code; the slice plan (Slice 1 shipped) that governs the contracts work.
- `docs/ARCHITECTURE_PROPOSAL_EMERGENT_PLOTTING.md` — emergent "middle-out" vs. NovelWriter.
- `docs/archive/name_generator_implementation_plan.md` — Python-backed `name.generate`.

---

## 1. The decision

Pure emergence produced incoherent stories. The instinct was to fix that with
pre-planning (plot-first mode). But **incoherence was not caused by the lack of a
plan** — it was caused by zero structural constraint. Pre-planning treats
emergence itself as the disease and removes the agency we actually want to study.

We are **not** replicating NovelWriter's full top-down approach. We commit to the
unexplored quadrant:

> **Emergent content + high structural constraint.**
> The LLM decides *what happens*; Python holds it to canon, arc shape,
> throughline, and payoff. Real foresight is reserved only for setup/payoff
> structures (mysteries, foreshadowing), via a short **rolling horizon** —
> a revisable lookahead of a few beats, regenerated *from* the prose just
> written, not a fixed outline.

### The spectrum is two axes, not one
- **Content axis** — who decides what happens (LLM emergent ↔ pre-baked plan).
- **Constraint axis** — how much structural pressure is applied (none ↔ rigid).

NovelWriter is high/high. Original StoryDaemon was low/low (drifted). Plot-first
slid the *content* axis up when the real deficit was the *constraint* axis at
zero. Our target: **content low (emergent + rolling horizon), constraint high.**

## 2. The layering principle (who owns what)

Every tick mixes three kinds of work. The current design blurs them; coherence
comes from separating them cleanly.

| Layer | Owns | Mechanism |
|-------|------|-----------|
| **Craft** | prose, dialogue, pacing, what happens next, character voice | full LLM autonomy |
| **Canon** | identity (IDs, names), dedup, what is already true | deterministic Python; LLM *references by selection*, never authors |
| **Guardrails** | did the scene keep continuity / hit its job / advance the arc | deterministic checks on autonomous output |

The contract layer (already shipped) is the *right* shape: write freely, then
check invariants in Python. The ID mismatch we fixed was the *wrong* shape:
the LLM was asked to do canon bookkeeping (type IDs) inside a creative task.

## 3. Phased roadmap

Ordering is a dependency chain — each phase is the substrate for the next.

### Phase 1 — Grounded identity *(foundation)*
**Rule:** the LLM never authors an identifier or a name; it selects from what
Python hands it. Entities are deduped and canon-safe, mintable on demand.
- Python-grounded `name.generate` (name banks by culture/era, dedup against
  existing) — see `docs/archive/name_generator_implementation_plan.md`. LLM
  *chooses and justifies*; it does not invent.
- Entity references become *selection from a provided set* (or a name resolved
  via lookup tool), never free-typed IDs. This supersedes the roster band-aid
  shipped in `fix: anchor plot-beat generation to real entity IDs`.
- Unify the two divergent beat-generation prompts (`novel_agent/agent/prompts.py`
  and the inline one in `novel_agent/cli/commands/plot.py`) while we're in there.
- Contradiction detection becomes a real gate where it matters.
- Corresponds to "Strict Entity Management" + "Entity Registry" in
  `CONTRACTS_AND_BLOCKS_ARCHITECTURE.md`.

*Why first:* prerequisite for safe on-demand entity creation; kills the worst
incoherence (contradiction, name/ID chaos); most deterministic and least
ambiguous. Grounded entities are what make emergence *safe* — the story can
introduce who it needs without breaking continuity.

### Phase 2 — Rolling horizon *(paradigm core)*
Make lookahead emerge *from* the prose instead of running parallel to it.
- Regenerate the short horizon (a few beats) from the just-written scene +
  current canon, so the next intention reacts to what actually happened.
- Beats become explicitly revisable; the agent can revise/abandon them.
- Beat-verification feeds back into horizon revision, not just a done/skip flag.

*Why second:* needs grounded entities to reference; this is the actual
"emergent + light lookahead" mechanism.

### Phase 3 — Constraint-as-pressure *(guardrails)* — *in progress*
Shape without scripting, mostly by re-purposing pieces that already exist
(tension scoring, open-loop tracking, novelty tracking, goal promotion,
semantic similarity) as *pressures*, not planning aids.

**Prerequisite shipped — the coherence rubric** (`agent/coherence_metrics.py`,
`memory/metrics.jsonl`, `novel metrics`): per-tick loop churn, contradictions,
disputed-lore count, tension + target + delta, goal relevance. Pure
instrumentation so every pressure below is measurable (see §5).

- **Contradiction enforcement** — *shipped.* Confirmed contradictions mark the
  non-canon (newer) lore `disputed`; the planner filters disputed lore out of
  the only place lore feeds generation (`MultiStagePlanner._active_lore`). Gated
  by `lore.enforce_contradictions`.
- **LLM tension scorer** — *shipped* (prerequisite for arc-pressure to mean
  anything). The keyword heuristic measured pulp surface vocabulary and collapsed
  real literary prose to a flat ~6 (proven on a 71-scene run: 4–8, never calm/
  climactic). `TensionEvaluator` now LLM-rates *dramatic* tension on an anchored
  0–10 rubric; validated on real `claude -p` at 0/4/8/9 for calm→climactic prose.
- **Arc-pressure** — *shipped; strengthened.* `agent/arc_pressure.py`
  interpolates a target tension over story position (Python owns *where*, LLM owns
  *how*). A 7-tick `claude -p` run showed the original soft, **planner-only** nudge
  was ignored — early low targets (4–5) did not pull a naturally-tense story down
  from ~7. Fix: the target is now also injected into the **writer** prompt with
  firm, band-specific language and an actionable directive
  (`arc_pressure_guidance_for_writer` → `WriterContextBuilder._build_arc_pressure_section`
  → `{arc_pressure_section}`), suppressed when a plot beat already sets a
  `tension_target`. **Iterated after live runs** (claude-cli + gemini-cli) showed the
  planner/writer nudge alone didn't control tension (it stayed pinned at 8-9 while
  targets sat at 4-6): (1) **calibration** — the writer's scale was unified with the
  scorer's (`agent/tension_scale.py`) so "4/10" means one thing on both sides;
  (2) the key finding — **tension lives in the *events*, not the prose**, so a
  prose-only rewrite that keeps the events can't lower a hot scene; (3) **option (c)** —
  the **planner** now sets event-level tension and stages a *transition* (new location /
  aftermath / time skip) for a big drop (continuity-aware via the previous scene's
  tension), the writer gets concrete situational *ingredients* per band up front, and a
  bounded **rewrite** (`SceneWriter.revise_for_tension`, kept only if closer) polishes
  prose toward the target within that transition. Full live validation is still pending
  a backend that survives a multi-tick run here (gemini-cli reliably completes only ~2
  ticks before timing out). *Update, validated 2026-06* (`progress_report_20260602.md`,
  claude-cli survived ~16-20 tick runs): tracks rising targets (drift ~1.2) but could
  not de-escalate for a resolution; the floor was the planner's event selection, fixed
  by the arc-phase mandate below.
- **Arc-phase planner mandate**: *shipped, validated 2026-07.* The de-escalation fix
  at the event level: `derive_arc_phase` reads the phase (rising / peak / falling /
  resolution) off the target curve's shape, `ARC_PHASE_MANDATES` puts a firm per-phase
  event mandate (escalate / confront / resolve) into the planner's arc-pressure
  guidance, `rewrite_futile` skips the prose rewrite when the gap is too big for prose
  to close, and `arc_phase` is recorded per tick. Gated by `coherence.arc_phase_mandate`
  (default True). Descent re-run vs the June control (`progress_report_20260709.md`):
  the planner now chooses aftermath events in the resolution phase; final scene 8 to 6
  against target 4, resolution drift 2.35 to 1.65. Residuals: the ending is subdued,
  not calm (the default curve gives little descent runway); the rising phase ran hotter
  than control at n=1; the "close open loops" clause did not bite (resolution ticks
  opened 8 loops, closed 0), direct evidence for loop-aging.
- **Arc-into-beats bridge**: *shipped.* In plot-first mode the same curve/phase now
  governs beat *authoring*, not just scene planning: `beat_tension_schedule` assigns
  each future beat a target from the curve, `arc_guidance_for_beats` renders per-phase
  authoring directives into the beat prompt, and `reconcile_beat_tension_targets`
  sanitizes LLM-authored targets back toward the schedule after parsing (fill / clamp /
  replace, the same sanitize-not-trust pattern as entity refs). Shares the mandate's
  gate (no new knob); wired through both generation paths (`plot/manager.py` and
  `cli/commands/plot.py`).
- **Throughline gate** — *shipped.* The planner's strategic prompt now carries the
  primary goal (`agent/throughline.py`, `coherence.throughline_pressure`) so scenes
  serve the throughline; dormant until a goal exists. Its gauge, the rubric's
  `goal_relevance`, was upgraded from embedding similarity to an **LLM judge** (0-10,
  "serves-the-goal" rubric, `coherence.use_llm_goal_relevance`, embedding fallback) —
  the embedding gauge measured topical overlap, not "advances the goal," so an A/B
  couldn't see the pressure. (Same crude-gauge lesson as the keyword tension heuristic.)
- **Loop-aging pressure** — *not started.* Older open loops surface louder,
  biasing toward payoff. (Motivation observed: a test run opened 23 loops and
  closed 0 — threads pile up without payoff. Second evidence, 2026-07: the descent
  re-run's resolution ticks opened 8 loops and closed 0 despite a mandate clause to
  close them, and contracts can now *check* `loop_resolved` but nothing pressures the
  planner to close loops.)
- **Block/sub-block contracts (the DSL)**: *Slice 1 shipped 2026-07*, per the landing
  sketch (`docs/BLOCKS_CONTRACTS_LANDING_SKETCH.md`, "contracts ride the beats"):
  `PlotBeat` carries `preconditions`/`postconditions`/`contract_results`; postconditions
  are authored atomically with their beat from the closed checker vocabulary
  (`contracts/authoring.py`, checkers in `contracts/conditions.py`), sanitized in both
  generation paths, evaluated during beat verification (pass upgrades
  `verification_method` to `contract`; failure routes to keep-pending or horizon
  revision), and counted in the rubric (`contract_conditions_checked`/`_failed`).
  Gated by `generation.use_contracts`, default off. The separate
  `ContractManager`/`contracts.json` store is retired (two contract stores would be
  worse than one). Live smoke run confirmed LLM-authored conditions on all beats after
  two fixes (beat-JSON parse retry; the prompt's shape block now carries a
  postconditions example). **Slice 4 (scene skeletons) also shipped** 2026-07, default
  off (`generation.enable_scene_skeleton`): a typed paragraph plan sampled from the
  masters block grammar (`agent/scene_skeleton.py`, data in
  `novel_agent/data/block_grammar_v1.json`) rides the writer prompt with the `[n]`
  marker protocol, markers are stripped and compliance recorded; the production A/B
  moved every solidly measured block statistic toward the masters with no surface
  regression (`docs/SLICE4_SCENE_SKELETON_RESULTS.md`). **Slice 5 (sectioned
  writing) shipped** 2026-09 at *section* granularity, default off
  (`generation.subblock_generation`, `subblock_section_blocks`): the scene is
  written across several plan-addressed calls, each owning a contiguous range of
  the skeleton's `[n]` blocks, seeing all prose so far and sized from its own mode
  mix (`agent/segments.py:partition_skeleton`/`section_word_target`,
  `SceneWriter._write_in_sections`). It requires `enable_scene_skeleton` and
  returns to single-shot on any failure. The motivation changed from the original
  richness hypothesis (which Slice 4's production runs answered "not needed for
  gpt-5.5") to *length*: one request does not reliably produce a masters-length
  chapter. Seam quality, voice continuity and cost per scene are **unvalidated**;
  the landing sketch's A/B is still owed. Remaining: Slice 2 (precondition
  pressure), Slice 3 (bounded repair + an `event_occurs` LLM-judge checker).
- **Honest loop accounting** (interleaving Slice 0) — *shipped.* Loop closure is now
  judged rather than claimed: a beat's `resolves_loops` claims each get one focused
  LLM check against the scene and close only on a confirmed yes with an auditable
  summary (`agent/loop_closure.py`, `coherence.loop_closure`), the same gate covering
  the judged extractor-resolution path and finale loop expiry. Creation hygiene came
  with it: deterministic dedup of new loops against open ones
  (`coherence.loop_dedup_threshold`) and a per-tick creation cap. `PlotBeat` also
  carries `advances_loops` (moved forward without answering on the page), stored and
  sanitized as future loop-aging fuel.
- **Sacred finale** — *shipped* (`coherence.sacred_finale`, default True). On the
  finale tick of a plot-first run (`current_tick == coherence.target_story_length`)
  Python owns the ending: the beat ask is guaranteed (pending-beat screen, then an
  authored finale beat, then a deterministic template), the scene gets bounded fresh
  re-rolls against the finale tension cap (`coherence.finale_retries`) in place of the
  prose rewrite, and a settled ending (`coherence.ending_hook: false`) quarantines the
  finale's freshly minted open loops.
- **Write-until-concluded scene loop** — *shipped.* The flat writer token ceiling
  truncated 8 of 16 scenes mid-sentence (`progress_report_20260711.md`); the writer now
  sizes each request from `generation.scene_word_targets` x `tokens_per_word` x
  `scene_budget_multiplier` and runs bounded continuation segments
  (`agent/segments.py`) until the scene concludes, trimming and flagging only after
  `scene_max_segments`. Chapter-length calibration rides the same module:
  `generation.scene_length_preset` picks the target set (`house`, the shipped
  default, or `masters` at 1,600/2,150/3,150/4,450 from the corpus per-chapter
  distribution), with an explicit `scene_word_targets` dict winning over either,
  exactly as `coherence.curve_preset` resolves.
- **Thread interleaving groundwork** — *Slices T1 / T1.5 / T4a shipped.* A thread
  registry (`agent/thread_registry.py`, `memory/threads.json`, viewable via
  `novel threads`) mints thread identity in Python; the beat prompt carries a roster of
  exact `TH` ids and each beat names the ONE thread it serves via `thread_id`
  ("select, don't invent" applied to threads, `coherence.thread_identity`). A
  construction-pressure detector records per tick whether thread construction *would*
  fire (`coherence.thread_construction_detector`, `construction_would_fire` in the
  rubric) and named tension-curve presets (`coherence.curve_preset`) come from the
  masters decile tables. All instrumentation so far: nothing constructs or selects
  threads yet (Slice T4b), see `docs/THREAD_INTERLEAVING_DESIGN.md` and
  `docs/THREAD_CONSTRUCTION_DESIGN.md`.

*Why third:* tunable pressures layered on a *working* emergent loop; easy to
add/remove/dial in.

### Phase 4 — Setup/payoff foresight *(optional, later)*
The one case that genuinely needs lookahead: clues planted before a reveal,
Chekhov's guns. Needs a planted-element ledger. Skip until 1–3 earn their keep.

## 4. How contracts and the DSL fit

Contracts/DSL are **not a separate track** — they are the per-beat/per-block
instance of the Phase 3 guardrail layer. But the DSL has hard dependencies we
validated empirically this session:

- **Phase 1 makes contracts *trustworthy*.** A contract can only check what it
  can reliably refer to. We had to hand-write `C000` because the beat said `C0`.
  An expressive DSL over an ungrounded identity space is precise language about
  unreliable referents.
- **Phase 2 makes contracts *durable*.** Contracts keyed purely by `beat_id`
  silently validate the wrong beat when beats regenerate (observed: a `PB001`
  contract validated a *different* `PB001`). Fix: author the contract
  atomically *with* its beat and regenerate/invalidate them together — that
  authoring step *is* the rolling horizon.

So: **Phase 1 → contracts trustworthy; Phase 2 → contracts durable; DSL → the
expression upgrade**, once 1 and 2 give it solid ground. The basic contract
layer already shipped is the prototype whose findings feed the DSL design;
designing the DSL in the abstract first risks designing it twice.

## 5. Measurement & iteration

Phases 2–3 are empirical — build the mechanism, run a batch of ticks, read the
story, tune. We need a way to *tell if coherence improved*, beyond reading
output by hand. Candidate signals: loops closed vs. opened, contradiction count,
tension-curve adherence, goal-relevance scores. ~~Open question: decide the
coherence rubric before Phase 3.~~ **Resolved — shipped** as `CoherenceMetrics`
(`agent/coherence_metrics.py`): one record per tick to `memory/metrics.jsonl`
(loops opened/closed/open, contradictions, disputed lore, tension + target +
delta, goal relevance), viewable via `novel metrics`. It already surfaced two
findings — arc-pressure being too gentle, and loops accumulating without payoff.
Two of these gauges (tension, goal-relevance) started as crude proxies — keyword
density and embedding similarity — that couldn't see the property they named, and
were each upgraded to an anchored LLM judge so the matching pressure is measurable.

## 6. Tooling caveat (separate from the roadmap)

The `claude-cli` backend runs `claude -p` — a full repo-aware agent, not a
completion API. **Confirmed empirically:** run from the StoryDaemon repo it loads
`CLAUDE.md` + the codebase and starts *acting* on the repo, derailing/timing out
on open-ended prompts (a planner call went from a 300s timeout to a clean ~5.5s
answer once the cwd changed). **Hardened (`llm_backends/claude_cli_interface.py`;
the `novel_agent/tools/` modules named below are now compatibility shims over the
shared `llm-backends` package):** it
now runs from a neutral temp scratch dir (no `.git`/`CLAUDE.md`), forwards a
Claude `--model` (use `llm.model: haiku` for speed), and has a configurable
`llm.timeout` (default 300s). With those, a multi-tick run completed cleanly.
The neutral-cwd isolation is now **shared across all three CLI backends**
(`tools/agent_cwd.py:neutral_cwd()`), and the `codex` backend was de-fanged from
`--dangerously-bypass-approvals-and-sandbox` to a read-only, non-interactive run
(`--sandbox read-only --ask-for-approval never`) that reads only the final
message — text generation needs no write/exec.
Remaining advice: still **prefer the `api` backend for unattended multi-tick
runs** — even hardened, `claude -p` is slower and less predictable than a
completion API. (`--append-system-prompt`/`--disallowedTools` remain optional
further hardening; the neutral cwd was the decisive fix.)

## 7. Status & current frontier

Phases 1 and 2 are shipped. Phase 3 is in progress: the coherence rubric,
contradiction enforcement, the LLM tension scorer, arc-pressure, the arc-phase
planner mandate (validated on the descent re-run), the arc-into-beats bridge,
contracts Slice 1 (default off) and Slice 4 (scene skeletons, default off), the
throughline gate and its LLM goal-relevance judge, honest loop accounting, the
sacred finale, the write-until-concluded scene loop (with chapter-length
calibration behind `generation.scene_length_preset`), contracts Slice 5
(sectioned writing, default off and its A/B still owed), and the
thread-interleaving groundwork (registry, thread identity by selection,
construction-pressure detector) are all in; loop-aging, thread
construction/selection itself, and contract Slices 2 and 3 are not yet started.

Next, in rough priority:
1. ~~**Arc-_phase_ planner mandate** — *validated 2026-06* (`progress_report_20260602.md`):
   over ~16-20 tick `claude-cli` runs arc-pressure *tracks rising targets* (drift ~1.2)
   but **cannot de-escalate for a resolution** — at a sharp downward target the planner
   keeps choosing tense *events* and the prose rewrite can't lower them. Diagnostic
   confirmed the scorer is fine (a calm denouement control scores 1/10) and the generator
   *can* write calm; the floor is the *planner*. Fix: give the planner the arc *phase*
   (rising/peak/falling) → escalate/confront/**resolve** (aftermath, close a loop,
   time-skip), and skip the rewrite for big drops. Note the throughline↔arc-pressure
   conflict at low targets (advance-the-goal vs. be-calm) — arc-pressure must win in the
   resolution phase.~~ **Resolved: shipped and validated 2026-07**
   (`progress_report_20260709.md`); see the Phase 3 bullet. Residual descent-runway and
   rising-heat findings tracked there.
2. **Loop-aging** — the rubric shows loops accumulating without payoff; surface
   older open loops louder to bias toward resolution. Now the top open item: the descent
   re-run's resolution ticks opened 8 loops and closed 0, and contracts can check
   `loop_resolved` but nothing pressures the planner to close loops.
3. **Remaining contract slices** (Slice 2: precondition pressure; Slice 3: bounded
   repair + `event_occurs` judge), per the landing sketch. Slice 4 (scene skeletons)
   is done, and Slice 5 is built as sectioned writing (default off); what is left of
   Slice 5 is its measured A/B: prose richness, voice continuity across section
   seams, and cost per scene against skeleton-guided single-shot.
4. **Validate the throughline gate** — re-run the on/off A/B now that the gauge is
   an LLM judge. *First pass (2026-05) was inconclusive*: a goal-aligned foundation keeps
   `goal_relevance` high (~7-10) with the pressure on *or* off — a ceiling effect, not a
   gauge artifact. Needs a looser / multi-thread foundation with headroom to drift.

*(Original first step, now done: the grounded `name.generate` / entity-minting
tool and "reference by selection, not free-typing" contract — Phase 1.)*
