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

### Phase 3 — Constraint-as-pressure *(guardrails)*
Shape without scripting, mostly by re-purposing pieces that already exist
(tension scoring, open-loop tracking, novelty tracking, goal promotion,
semantic similarity) as *pressures*, not planning aids.
- **Throughline gate** — scene relevance to the primary goal/theme.
- **Arc-pressure** — a target tension trajectory by story position; the planner
  is pushed toward it (Python owns *where we should be*, LLM owns *how*).
- **Loop-aging pressure** — older open loops surface louder, biasing toward payoff.
- This is also where **block/sub-block contracts** (the DSL) land: per-block
  deterministic checks are the fine-grained instance of this layer.

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
tension-curve adherence, goal-relevance scores. **Open question: decide the
coherence rubric before Phase 3.**

## 6. Tooling caveat (separate from the roadmap)

The `claude-cli` backend runs `claude -p` — a full repo-aware agent, not a
completion API. It returns clean JSON only when the working tree is clean; a
dirty tree derails it into commenting on the repo. Not a StoryDaemon bug, but it
makes unattended `run` fragile. If we keep using it for generation, harden the
wrapper (`--append-system-prompt`, `--disallowedTools`, neutral cwd) or prefer
the `api` backend for multi-tick runs.

## 7. First step

Start Phase 1: design the grounded `name.generate` / entity-minting tool and the
"reference by selection, not free-typing" contract that everything downstream
depends on. Review the approach (against `name_generator_implementation_plan.md`)
before cutting code.
