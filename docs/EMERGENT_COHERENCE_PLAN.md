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
  postconditions example). Remaining: Slice 2 (precondition pressure), Slice 3 (bounded
  repair + an `event_occurs` LLM-judge checker), Slice 4 (scene skeletons), Slice 5
  (per-sub-block generation, a measured A/B).

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
answer once the cwd changed). **Hardened (`tools/claude_cli_interface.py`):** it
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
contracts Slice 1 (default off), the throughline gate, and its LLM goal-relevance
judge are all in; loop-aging and the remaining contract slices (2-5) are not yet
started.

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
   repair + `event_occurs` judge; Slices 4-5: scene skeletons, per-sub-block A/B), per
   the landing sketch.
4. **Validate the throughline gate** — re-run the on/off A/B now that the gauge is
   an LLM judge. *First pass (2026-05) was inconclusive*: a goal-aligned foundation keeps
   `goal_relevance` high (~7-10) with the pressure on *or* off — a ceiling effect, not a
   gauge artifact. Needs a looser / multi-thread foundation with headroom to drift.

*(Original first step, now done: the grounded `name.generate` / entity-minting
tool and "reference by selection, not free-typing" contract — Phase 1.)*
