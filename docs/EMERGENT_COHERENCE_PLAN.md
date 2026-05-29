# Emergent Coherence Plan

**Status:** active roadmap · **Supersedes nothing; sequences existing proposals**

This is the spine that ties together the existing design docs and fixes their
ordering. It records the paradigm decision reached in discussion and the
dependency chain that determines what we build first. It does **not** restate
the detailed designs — it points at the docs that already contain them.

Related docs (execute against these for detail):
- `docs/DSL_and_contracts.md` — the scene-composition DSL sketch (blocks/sub-blocks).
- `docs/CONTRACTS_AND_BLOCKS_ARCHITECTURE.md` — full contract/block/entity-registry spec.
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
- **Arc-pressure** — *shipped, but too gentle.* `agent/arc_pressure.py`
  interpolates a target tension over story position and injects a soft nudge into
  the planner's strategic prompt (Python owns *where*, LLM owns *how*). Empirical
  finding from a 7-tick `claude -p` run: on a naturally-tense generator the
  soft, planner-only nudge is **ignored** — early low targets (4–5) did not pull
  the story down from ~7. Tuning leads: also inject the target into the *writer*
  prompt, use firmer language, or have the planner explicitly plan a low-tension
  beat when far below target.
- **Throughline gate** — *not started.* Scene relevance to the primary goal/theme
  (the rubric already records `goal_relevance`).
- **Loop-aging pressure** — *not started.* Older open loops surface louder,
  biasing toward payoff. (Motivation observed: a test run opened 23 loops and
  closed 0 — threads pile up without payoff.)
- **Block/sub-block contracts (the DSL)** — *not started.* Per-block deterministic
  checks are the fine-grained instance of this layer.

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

## 6. Tooling caveat (separate from the roadmap)

The `claude-cli` backend runs `claude -p` — a full repo-aware agent, not a
completion API. **Confirmed empirically:** run from the StoryDaemon repo it loads
`CLAUDE.md` + the codebase and starts *acting* on the repo, derailing/timing out
on open-ended prompts (a planner call went from a 300s timeout to a clean ~5.5s
answer once the cwd changed). **Hardened (`tools/claude_cli_interface.py`):** it
now runs from a neutral temp scratch dir (no `.git`/`CLAUDE.md`), forwards a
Claude `--model` (use `llm.model: haiku` for speed), and has a configurable
`llm.timeout` (default 300s). With those, a multi-tick run completed cleanly.
Remaining advice: still **prefer the `api` backend for unattended multi-tick
runs** — even hardened, `claude -p` is slower and less predictable than a
completion API. (`--append-system-prompt`/`--disallowedTools` remain optional
further hardening; the neutral cwd was the decisive fix.)

## 7. Status & current frontier

Phases 1 and 2 are shipped. Phase 3 is in progress: the coherence rubric,
contradiction enforcement, the LLM tension scorer, and arc-pressure are all in;
the throughline gate, loop-aging, and the block/sub-block DSL are not yet started.

Next, in rough priority:
1. **Strengthen arc-pressure** — the soft planner-only nudge is too gentle (§3,
   measured). Push the target into the writer prompt and/or have the planner plan
   an explicit low-tension beat when far below target.
2. **Loop-aging** — the rubric shows loops accumulating without payoff; surface
   older open loops louder to bias toward resolution.
3. **Throughline gate** — score scene relevance to the primary goal (the rubric
   already records `goal_relevance`).

*(Original first step, now done: the grounded `name.generate` / entity-minting
tool and "reference by selection, not free-typing" contract — Phase 1.)*
