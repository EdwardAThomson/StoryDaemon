# Thread Construction and Parallel Execution (Interleaving Build 2)

**Status:** Design proposal (no implementation)
**Date:** 2026-07-12
**Specs:** Slice T4 of `THREAD_INTERLEAVING_DESIGN.md` (construction pressure), extended by the parallel-execution architecture
**Related:** `THREAD_INTERLEAVING_DESIGN.md` (the portfolio model this builds on), `progress_report_20260712.md` (the T1.5 validation), `BLOCKS_CONTRACTS_LANDING_SKETCH.md` (contracts), `novel_agent/agent/thread_registry.py` (the shipped machinery)

Evidence markers used throughout: **[evidence]** (measured, decided), **[proposed]** (design decision awaiting validation), **[pending: masters study]** (awaits the corpus study running in parallel).

## 1. What this specs and why now

The interleaving design made story-level tension control a scene-selection
policy over a portfolio of threads. Slice T1 built the registry, Slice T1.5
made thread identity a Python-minted, LLM-selected fact. The triple run
(2026-07-12) then answered the design's riskiest open question the hard way:
**[evidence]** 14 of 14 batch-authored beats selected `TH000`, zero sanitizer
clears, zero invented ids, zero `"new:"` mints. Selection works perfectly and
nothing ever exercises it. A single-protagonist premise never pressures the
model to mint a second strand: **all-main-forever is the default outcome**.
The T1 backfill said the same thing retrospectively (34 executed beats across
three finished novels yielded 30 distinct primary labels; casts, not labels,
carry identity).

Conclusion: the portfolio the selection policy needs will not emerge. Python
must construct it. That is this spec's core (section 3).

The spec is extended by a new architectural idea (the user's, designed in
faithfully): threads whose scenes share no entities have no data dependency
until they intermingle, so **threads can run as parallel execution**, with
scenes generated concurrently and interleaving decided at presentation time.
Checks run before a thread's scene executes to guarantee it cannot violate the
other threads' canon, and the model admits "a great number of threads at
once" in principle. Sections 4 and 5 design that honestly, including the
parts of today's tick that would race.

Standing constraints inherited from the interleaving design (design
commitments, not tunables):

1. Thread construction is an early/mid-story move only.
2. No unnecessary de-escalation mid-sequence; hot sequences resolve on the page.
3. Whiplash guard: every thread gets a decent run before a switch.
4. Hooks and cliffhangers are authorial decisions, made deliberately by the
   selection policy, never emergent side effects.
5. Scene-event integrity: a scene delivers its assigned event at that event's
   natural tension. The curve is satisfied by scheduling, never by adulterating
   scenes.

## 2. Construction pressure: detection **[proposed]**

Python decides WHEN a thread is constructed and the constraint envelope it
must satisfy. The LLM authors everything inside the envelope. Two triggers,
both deterministic, both cheap (registry plus curve reads, no LLM call):

### 2.1 The diversity trigger (the one that will actually fire)

Fires once per story when all of:

- `progress >= construction_floor` (default 0.15: the story has established
  its main strand; constructing before the world exists repeats the
  plot-first-start-tick lesson).
- `progress <= construction_cutoff` (default 0.5: **early/mid only**, the
  hard craft line from the interleaving design; past the midpoint, calm must
  come from sequencing and time-skip, never from a new thread).
- Effective thread count is 1 (only the implicit main, or every scene
  attributed to one thread).
- Runway supports a viable B-thread (section 2.3).

**[evidence]** rationale: the default curve rises to a peak then descends, so
a mid-story calm *demand* gap rarely opens on its own; but all-main-forever is
proven, so diversity zero past the floor fraction is the reliable signal. On
the triple run's shape this fires around tick 3-7 of 15.

### 2.2 The demand-gap trigger (the curve foresees calm the portfolio cannot serve)

Evaluated each tick inside the same window, fires when all of:

- Lookahead: `min_target = min(interpolate_curve(t) for t in [tick, tick + W])`
  with `W = generation.plot_beats_ahead` (the horizon the next batch will
  fill), and `min_target <= calm_threshold` (default 4, the calm band's top).
- Supply: no active, unresolved thread can serve that band. A thread can
  serve a band when its recent tension (mean of last 2 trace entries) is
  within `serve_margin` (default 2) of the target. A hot thread mid-sequence
  cannot serve calm: de-escalating it would violate standing constraint 2,
  and the fork experiment proved prose cannot becalm a hot event anyway.
- Same story-fraction window and runway floor as 2.1.

Both triggers record their evaluation to metrics every tick
(`construction_evaluated`, `construction_reason`, fired or not), in the
instrument-first tradition: the detector ships and is measured before the
authoring behavior turns on.

### 2.3 The runway floor (dead-weight guard)

Construction requires the remaining ticks to fit the whole B-thread
lifecycle, not just its opening:

```
remaining >= thread_min_run          (default 3, the whiplash guard's decent run)
           + main_min_run            (default 3, the main thread keeps its floor)
           + convergence_reserve     (default 1, the merge beat, section 5.3)
           + finale_reserve          (default 1, the sacred finale slot)
```

With defaults that is 8 ticks. A 15-tick story firing at tick 6 clears it; at
tick 9 it does not, and the trigger stays silent even inside the fraction
window. This is the direct answer to the T1 backfill's warning: a B-thread
planted without room to live is dead weight, so it is not planted.

## 3. Construction pressure: the B-thread ask **[proposed]**

### 3.1 Who writes what

| Decision | Owner | Mechanism |
|---|---|---|
| When to construct | Python | Triggers (section 2) |
| Constraint envelope: register band, cast disjointness, minimum run, convergence requirement, home location disjointness | Python | Charter validation (3.2) |
| Thread name, premise, cast selection, local arc shape, convergence seed substance | LLM | Charter authoring call (3.2) |
| Beats that serve the thread | LLM | Beat generation with a construction mandate (3.3) |
| Thread identity (TH id), sanitization, attribution | Python | Existing T1.5 machinery, unchanged |

### 3.2 The thread charter (one dedicated authoring call)

Pattern precedent: `author_finale_beat` (finale.py). One focused LLM call
authors the thread's substance inside a Python envelope, Python sanitizes and
mints. This is deliberately NOT left to the beat-generation batch alone: the
T1.5 run proved a batch prompt under no pressure never mints, and a batch
prompt under pressure would mint a strand with no thought-through identity
(the episode-title label failure, prospectively confirmed). The charter is
where the thread earns the right to exist.

Charter context (assembled by Python):

- The main thread's synopsis and cast (from the registry and recent summaries).
- A **secondary-character roster**: existing characters with low
  `scenes_mentioned` that are not main-thread members (the character
  detector's stubs are the natural pool). Drawing from this pool is preferred
  over minting; minting goes through `name.generate` grounding as always.
- The target register band (from the trigger: calm 2-4 for a demand-gap fire,
  or a contrast band chosen against the main thread's recent trace for a
  diversity fire).
- The story foundation and primary goal (the B-thread must belong to this
  story).

Charter output (JSON, sanitized like a plan):

| Field | Constraint enforced by Python |
|---|---|
| `name` | Normalized via `normalize_thread_label`; deduped against the registry via `match_thread` |
| `premise` | Free text (the LLM's substance) |
| `cast` | Resolved to canonical C ids via the entity resolver; **must share zero members with the main thread's core cast**, except at most one designated `bridge_character` (3.4) |
| `home_location` | Resolved L id or a mint request; disjoint from the main thread's current hot location |
| `register_band` | Clamped to the envelope's band |
| `local_arc` | Three-point shape (open, develop, converge), each with a tension note inside the band |
| `convergence_seed` | Required: a described future intersection with the main thread (a person, object, or event both strands touch). Python opens it as a high-importance open loop tagged with both thread ids. A charter without a credible seed is rejected and re-rolled once; two failures abort construction (graceful degradation, the trigger may re-fire later) |

The convergence seed requirement is the second half of the dead-weight guard:
a B-thread that cannot say how it will matter to the main story does not get
constructed. This is a design commitment, not a tunable.

Python then mints the TH id (`mint_thread`, existing), stamps the charter
fields onto the Thread record (new fields: `origin: "constructed"`,
`charter`, `register_band`, `convergence_loop_id`, `status`), and persists.

### 3.3 Seeding through the existing T1.5 machinery

No new prompt path for beats. The next beat-generation batch (or an
immediately triggered horizon revision, `revise_horizon` exists) renders as
today, with two additions to the shared `PLOT_GENERATION_PROMPT_TEMPLATE`
surfaces:

- The roster line for the constructed thread carries its charter premise and
  register band (the roster already renders name, members, tension range).
- A **construction mandate** line in the thread rule block: "this batch must
  include at least N beats serving THxxx (its opening arc: ...)", N default 2.

`sanitize_beat_thread_ids` holds the selections exactly as today. The mandate
is measured, not trusted: if the batch comes back all-main despite the
mandate, the sanitizer's warning stream records it and the construction is
retried on the next batch (never a hard failure; `fallback_to_reactive`
territory).

Beat tension reconciliation (`_reconcile_beat_tension`) needs one change:
beats serving a constructed thread reconcile against the **thread's register
band**, not the global curve slot. The global curve constrains the assembled
reader sequence (section 6.1); forcing a B-thread beat to the curve's hot
slot value would recreate the PB014 category error in mirror image.

### 3.4 The bridge character **[proposed]**

At most one character may be shared between a constructed thread and the main
thread at construction time. A shared character is promoted to **shared
status** (section 5.1): its mutations serialize and its facts are visible to
both threads. Zero bridge characters is legal (the convergence seed can be an
object or event). More than one collapses the disjointness that makes
parallel execution safe, so the sanitizer trims to the first.

## 4. Parallel execution model **[proposed]**

### 4.1 The idea, stated plainly

Two threads with disjoint casts and locations have no data dependency: scene
7 of thread A and scene 3 of thread B read and write different entities, so
nothing about B's scene depends on A's except global world state. They could
be generated concurrently, by multiple writer pipelines in flight, and the
question "which does the reader see first" becomes a decision made at
**presentation time**, over finished scenes, rather than at generation time.

This inverts where the T2 selection policy lives. In the interleaving design
it was a beat-selection policy (choose which thread's beat executes next). In
the assembly model it is a **manuscript-ordering policy**: the story becomes
an assembly of thread streams, and the policy orders committed scenes for the
reader against the tension curve, the run-length guard, and the whiplash
guard. Generation scheduling (which thread's pipeline runs next) is a
separate, boring policy driven by buffer depth (keep every active thread's
stream a scene or two ahead of the assembly point).

The prize is real: the selection policy gets to choose among scenes that
exist, with measured tension levels, instead of predicting what a beat will
score. The curve is fitted against actual values. Cut-aways can be placed
where they land best, in hindsight.

### 4.2 State partition: thread-local vs global

Designed honestly against today's storage:

| Store | Partition verdict | Notes |
|---|---|---|
| Scene prose + Scene entities | **Thread-local** | Each scene belongs to exactly one thread (attribution is already total). File naming must stop being tick-keyed (4.4) |
| Open loops | **Split** | Loops gain a nullable `thread_id`. Thread-local: a loop opened by a thread's scene about its own cast. Global: the convergence seed, story-goal loops, world-level questions. Default for extractor loops: the scene's thread |
| Thread cast (member_characters) | **Thread-local claim** | The claim set the intermingle checks enforce (5.1) |
| Local tension trace | **Thread-local** | Already per-thread in the registry |
| Thread beats (outline entries serving one thread) | **Thread-local logically, global file** | `plot_outline.json` stays one file; beats carry `thread_id`; writes serialize (4.3) |
| Characters, locations, factions | **Global, claim-guarded** | Entity files are world canon. A thread may only MUTATE entities in its claim set or shared-status entities (5.1) |
| World lore | **Global** | Lore is world-level by nature; all lore writes serialize, and lore is visible to every thread's context. Contradiction detection keeps running globally: it is precisely the cross-thread canon guard |
| Vector store | **Global** | One Chroma instance; writes serialize through the commit gate |
| ID counters | **Global** | Single allocator; serialize (4.3) |
| Chronology (story clock) | **Global** | New surface, section 5.2 |
| Metrics, state.json, plans/, errors/ | **Global** | Append/write via the commit gate |

The verdict in one line: **prose and loops partition cleanly; world canon
does not and should not.** The design does not pretend entity state can be
forked per thread and merged later (that is a version-control problem dressed
as a story problem). Instead, disjoint claim sets make concurrent mutation
of the SAME entity impossible by construction, and everything global
serializes through one writer.

### 4.3 Race inventory: every write surface in today's tick

What would actually race if two `_normal_tick` executions ran concurrently
today, and the resolution for each:

| Write surface (tick step) | Race | Resolution |
|---|---|---|
| `counters.json` via `generate_id` (any entity creation) | Read-modify-write, duplicate IDs | All ID allocation moves behind the commit gate (single writer). Duplicate-ID damage is permanent, so this is non-negotiable |
| Entity files via tool execution (step 4: `character.generate` etc.) | Two threads minting/writing entities concurrently | Plan execution is NOT read-only today. Split tools into read (memory.search etc., safe concurrent) and write (entity generation); write-tool execution serializes through the gate. A constructed thread's cast is minted at charter time anyway, so steady-state B-thread ticks rarely create entities |
| `EntityUpdater.apply_updates` (step 10) | Concurrent mutation of one character | Prevented by claim disjointness for thread-local entities; shared-status entities serialize at the gate |
| Open loops file (steps 9.6, 10, 11.6, 11.7) | Concurrent append/close on one JSON list | Serialize at the gate; loop closure judges only loops owned by (or global and claimed by) the committing thread |
| Lore save + contradiction detector (step 12) | Concurrent lore writes; detector reads a moving ledger | Serialize at the gate; the detector runs per commit, in commit order |
| Vector store re-index (steps 11, lore path) | Chroma concurrent writes | Serialize at the gate |
| `plot_outline.json` (beat status, step 11.5; batch authoring) | Concurrent status writes | Serialize at the gate; beat generation itself stays a single global activity (one horizon, thread-labeled beats) |
| `threads.json` (step 11.8) | Concurrent registry updates | Serialize at the gate |
| `metrics.jsonl` (step 14+) | Interleaved appends | Append at the gate, one record per committed scene |
| `state.json` `current_tick` | Lost increments | `current_tick` becomes the global commit counter (incremented at the gate); each thread gains its own scene ordinal |
| `scenes/scene_{tick:03d}.md` naming | Name collisions, and tick no longer equals reader order | New naming: `scene_{Sxxx}.md` keyed by scene ID, with thread and ordinal in front matter; reader order lives in the assembly manifest (4.4) |

The architecture that falls out: **concurrent generation, serial commit.**
The expensive, slow, read-only work (context build, plan, write, evaluate,
tension-score: the LLM calls, which are minutes each) runs concurrently per
thread. Every write funnels through a single commit gate that processes one
scene's full write set (steps 8 through 12 equivalents) atomically, in queue
order. The gate is also where intermingle checks run (section 5), because it
is the one place with a consistent view of everything.

This matches the codebase's grain: `MemoryManager` is already the single
read/write surface, so the gate is a serialization discipline around it, not
a new storage engine.

### 4.4 Generation order vs reader order: the assembly

Decoupled explicitly:

- **Generation order** is whatever the scheduler ran: an implementation
  detail, recorded per scene (`generated_at_commit: 17`) for audit only.
- **Reader order** is the assembly: a persisted manifest
  (`memory/assembly.json` **[proposed]**), an ordered list of scene IDs with
  the policy's reasoning per placement (target band, chosen thread, whether
  this placement is a cut-away, which suspension loop it opened).
- `novel compile` reads the manifest; without one (all existing projects) it
  falls back to scene-number order, so every legacy project compiles
  unchanged.

The T2 selection policy lives here. Its inputs per placement decision: the
curve's target at the READER position (position in the assembly, not the
tick), each thread's next unplaced scene and its measured tension, each
thread's current consecutive-run count in the assembly, and the standing
constraints (run-length minimum, no de-escalation mid-sequence, cut-aways
rare and deliberate, cliffhangers authored not accidental). The curve becomes
a constraint on the assembled sequence, which is what it always claimed to be.

Note what this does NOT change: within one thread, scenes are strictly
ordered (a thread is a serial narrative). Assembly only chooses interleave
points between streams. It never reorders within a stream.

### 4.5 The staged path: complexity tiers **[proposed]**

The full concurrent model is a large lift. It lands incrementally, each tier
useful on its own, each validated before the next:

| Tier | What runs | Concurrency | New machinery | Risk |
|---|---|---|---|---|
| **P0: serial, thread-aware** (Build 2 baseline) | One tick, one thread; the thread whose beat executes is whichever the horizon authored next; construction pressure seeds the B-thread | None | Sections 2-3 only | Low |
| **P1: logical parallelism** | Alternating serial ticks with **isolated thread context**: a tick executing thread B builds writer context from B's own recent scenes (not global recency), stamps the story clock, tags all writes with the thread | None (still one pipeline) | Thread-scoped writer context, story clock, loop `thread_id`, scene naming change, assembly manifest (order still = generation order) | Medium |
| **P2: concurrent generation, serial commit** | Multiple writer pipelines in flight; commit gate serializes all writes; intermingle checks at the gate; assembly policy orders the manuscript | Real (thread pool or async over LLM calls) | Commit gate, generation scheduler, read/write tool split | High |
| **P3: finer-grained locking** | Shared-entity locks instead of a single gate | More | Per-entity locks | Not planned; only if P2 throughput ever matters, and LLM latency dominates so it likely never does |

P1 is the honest workhorse: it delivers everything narratively interesting
(isolated strands, story clock, assembly-time ordering) with zero races,
because there is still exactly one writer. P2 buys wall-clock speed and
hindsight selection over generated-ahead buffers. The design commits to P0
and P1; P2 is specced (the gate, above) but gated behind P1's validation.

Cost honesty: P2 does not multiply cost per scene, it multiplies cost per
wall-clock minute. The real cost multiplier is the B-thread itself: a
2-thread story of the same reader length spends the same scene budget but
gives the main thread fewer scenes, and a 2-thread story with an undiminished
main thread is simply longer. `target_story_length` must be set accordingly
(section 6.4).

## 5. Intermingle checks (checks before a thread's scene executes) **[proposed]**

The user's requirement: threads will intermingle eventually, and we check for
that BEFORE executing a thread's scene. Contracts are the enforcement layer
(the established design); these are precondition-shaped and mostly
deterministic. In P0/P1 they run at beat selection (before the tick executes
the beat); in P2 the deterministic re-check also runs at the commit gate,
because the world may have moved while the scene was in flight (check at
schedule time, verify at commit time, the classic pattern).

### 5.1 Entity claims (no-touch contracts, the cut-away discipline generalized)

Each thread holds a claim set: `member_characters` plus `home_locations`
(both already tracked by the registry). Rules, checked deterministically:

- A beat serving thread X may only involve characters/locations in X's claim
  set, entities with **shared status**, or entities claimed by no thread
  (neutral pool; involving one claims it for X).
- An entity claimed by another thread is untouchable: the beat fails its
  precondition and is not executed (it is re-authored or re-assigned; in
  plot-first terms the horizon revises, the shipped recovery path).
- **Shared status** is the escape hatch, granted only two ways: the bridge
  character at charter time (3.4), and convergence (5.3), which dissolves
  claims wholesale. Shared entities' mutations serialize and their fact
  updates are visible to all claiming threads' contexts.
- Cut-away postconditions from the interleaving design generalize to: a
  scene on thread X must not close or advance loops owned by thread Y, and
  must not mutate entities claimed by Y. Checkable as a deterministic diff of
  the commit's write set, at the gate: this is the strongest form, because it
  inspects what the scene actually did, not what the beat promised.

New condition checkers this needs (registered in `contracts/conditions.py`):
`cast_within_thread`, `entities_unclaimed_or_owned`, `does_not_touch_thread`
(postcondition, write-set diff). All deterministic, no judge needed.

### 5.2 Chronology (does the story clock allow this scene)

Tick number stops meaning "story time" the moment two strands run in
parallel, so the design needs an explicit clock, and it must be coarse to be
checkable (fine-grained timekeeping in emergent prose is a losing game):

- A global **epoch** counter (integer, roughly "chapter-scale story time"),
  advanced deliberately: by a time-skip, by a convergence beat, or by the
  assembly policy when both streams have exhausted an epoch.
- Every scene stamps `(epoch, thread_id, thread_ordinal)`. Within an epoch,
  threads are narratively concurrent (this is exactly the "meanwhile"
  convention of multi-strand fiction).
- Deterministic checks: a shared-status entity may appear in at most one
  thread's scenes per epoch (a person cannot be two places "meanwhile");
  thread ordinals are strictly increasing; a convergence beat requires both
  threads to have reached the convergence epoch (5.3); assembly may not place
  a scene from epoch N+1 before every placed thread has finished epoch N
  unless a time-skip marker is emitted.
- What this deliberately does not attempt: hour-level or day-level
  consistency inside prose. That remains the evaluator's soft territory. The
  clock exists to make the checkable claims checkable and no more.

### 5.3 Merge-point contracts (when threads DO intermingle)

Convergence is a designated beat, not an accident. The convergence seed loop
(3.2) is its anchor. The convergence beat is authored like any beat (the LLM
decides its substance) but carries a Python-stamped contract:

Preconditions (all deterministic):

- Thread B has served at least `thread_min_run` scenes (a thread that
  converges before it has lived was dead weight wearing a disguise).
- The convergence seed loop is still open (if it was resolved early, the
  charter's premise is void and the merge must be re-chartered).
- The main thread is at a legal suspension point (not mid-sequence, standing
  constraint 2) or the convergence IS the main thread's next event.
- Both threads have reached the convergence epoch (5.2).
- Story fraction is before the finale reserve (convergence must precede the
  sacred finale, section 6.2).

Postconditions:

- The convergence seed loop is resolved or explicitly transformed (judged by
  the existing loop-closure judge; the seed is a normal loop).
- Casts have met on the page (`char_in_prose` for the designated members,
  deterministic).

Effects at commit: claim sets union (or thread B's claims transfer), thread B's
registry status becomes `converged` (terminal: subsequent scenes attribute to
the merged/main thread), and the epoch advances. A story may instead END a
B-thread without convergence only by deliberate expiry (`expired` status with
a reason), which the finale accounting surfaces (6.2). Silent abandonment is
not a legal state.

### 5.4 Where the checks live

| Check | When | Mechanism |
|---|---|---|
| Claim-set membership, clock eligibility, convergence preconditions | Before executing a thread's beat (P0/P1: beat selection; P2: schedule time AND commit gate re-check) | Contract preconditions (contracts Slice 2 machinery, currently unbuilt: it is now a hard dependency of this build) |
| No-touch write-set diff, clock stamp validity | At commit | Deterministic gate checks (new, small) |
| Convergence postconditions | At beat verification (step 11.5 equivalent) | Existing contract path plus the loop-closure judge |

A precondition failure is not a tick failure: the beat is skipped for now and
the horizon revises (shipped recovery), or in P2 the scheduler simply picks a
different thread's ready scene. Graceful degradation throughout, per house
rule: no check may kill a run.

## 6. Interaction with everything shipped

### 6.1 Per-thread tension traces vs the global curve

- The global curve (`coherence.target_tension_curve`) becomes a constraint on
  the **assembled reader sequence**. In P0 (reader order = generation order)
  that degenerates to today's behavior exactly.
- Per-thread traces (shipped, T1) are the **supply signal**: what each thread
  can offer next.
- Beat tension reconciliation splits: main-thread beats reconcile against the
  curve as today; constructed-thread beats reconcile against their charter's
  register band (3.3). The curve is served by choosing WHICH stream to place
  next, never by bending a stream's events off their nature.
- Arc-pressure writer guidance follows the beat's thread (the beat's
  tension_target already suppresses the global section; that behavior is
  correct here and needs no change).

### 6.2 Sacred finale

- **Convergence precedes the finale.** The runway floor (2.3) and the
  convergence precondition (5.3) both encode it; slot alignment
  (`cap_beat_count`) additionally reserves the convergence slot when an
  unconverged thread exists, the same move that landed the denouement beat at
  slot 15.
- At the finale tick, every thread must be `converged`, `resolved`, or
  deliberately `expired`. The finale loop expiry (step 11.7) extends to
  thread accounting: an unconverged, unexpired thread at the finale is
  counted in `dangling_threads` alongside dangling loops (the metric exists;
  it gains a per-thread breakdown).
- The known T1.5 gap becomes a prerequisite fix: the sacred finale's authored
  beat bypasses thread selection (finding 8.5, 2026-07-12, minted TH001 at
  the last tick). Cosmetic today, wrong the day anything reads the registry:
  stamp the finale beat with the converged/main thread id. **[evidence]**
  that this must precede Build 2.

### 6.3 Loop ledger

- Loops gain nullable `thread_id` (5.1). Ledger stays one file; ownership is
  a tag, not a partition of storage.
- **Cliffhangers are suspension loops**: when the assembly (or P0/P1 beat
  selection) cuts away from a thread mid-arc, it deliberately opens a
  high-importance suspension loop on that thread (expected-resumption note),
  exactly as the interleaving design specified. Authorial decision, made by
  the policy, never extracted from prose.
- The judged closure path is unchanged; the judge only sees claims about
  loops the committing scene's thread owns or global loops (5.1), which
  SHRINKS the nomination space per scene, helping precision.
- Loop dedup stays global (two threads asking the same world question is real
  duplication worth catching).

### 6.4 Slot alignment and runway math

`cap_beat_count` currently caps a batch to `target_story_length - tick`.
With N active threads sharing the runway it becomes portfolio-aware:

```
remaining_slots = target_story_length - current_tick
reserved        = finale_reserve + convergence_reserve * unconverged_threads
free            = remaining_slots - reserved
```

The batch is capped to `free`, and the construction mandate's N (3.3) counts
against the constructed thread's minimum-run entitlement. When `free` cannot
cover every active thread's minimum remaining entitlement, the horizon is
instructed to converge or expire the weakest thread (the assembly's
run-length accounting says which): the runway crunch is resolved by ENDING
strands, never by starving all of them evenly. `target_story_length` remains
the master knob and multi-thread stories need it raised honestly (a 15-tick
story has no room for 2 full strands plus convergence; ~24 is the plausible
floor for the A/B validation run, to be confirmed by the run itself).

### 6.5 Metrics additions (instrument first, as always)

| Field | Meaning |
|---|---|
| `construction_evaluated` / `construction_reason` | Trigger telemetry every tick (2.1/2.2), fired or not |
| `thread_id`, `thread_origin` | Per committed scene (attribution exists; origin distinguishes constructed threads) |
| `story_clock` | `(epoch, thread_ordinal)` per scene |
| `intermingle_checks_run` / `intermingle_checks_failed` | Gate telemetry, with the failing check name |
| `convergence_status` | Per thread at each tick: pending / eligible / converged / expired |
| `assembly_position` | Reader-order index once the manifest exists; null before |
| `thread_tension_drift` | Per-thread analogue of the drift metric, measured against the thread's band |
| `generation_buffer_depth` | P2 only: unplaced scenes per thread |

## 7. How many threads

- **In principle:** the registry, claims, clock, and gate all scale by thread
  count; nothing in the design hard-codes two. "A great number of threads at
  once" is architecturally admitted: N pipelines, one gate, N claim sets.
- **In practice, recommended limits:** `coherence.max_active_threads`,
  default **2** (main plus one constructed B-thread, the classic A/B plot).
  Every failure mode in section 8 scales superlinearly with thread count
  (claims fragment the cast, the clock fragments time, the assembly
  fragments attention), and the whiplash guard means N threads need roughly
  N x `thread_min_run` reader-scenes per rotation, so thread count is bounded
  by story length long before it is bounded by the machinery. 3+ is a
  config change, not a design change, but it is not part of Build 2's
  validation.
- **[pending: masters study]** The corpus study running in parallel will
  report what published novels actually do: typical concurrent strand
  counts, strand run lengths between cut-aways, convergence timing as a
  story fraction, and how often B-strands out-live convergence. This section
  intentionally cites no numbers for it. When it lands, its findings should
  set: the default `thread_min_run`, the `construction_cutoff` fraction, the
  convergence-timing window, and whether `max_active_threads` above 2 or 3
  ever earns a default.

## 8. Risks, honestly

| Risk | Reality | Mitigation |
|---|---|---|
| Dead-weight B-thread (the T1 backfill's warning) | The single most likely failure: a constructed thread nobody would miss | Charter gate with required convergence seed (3.2); runway floor (2.3); convergence preconditions require a lived arc (5.3); deliberate-expiry path so a failed thread dies visibly; validation includes READING the B-thread, not just scoring it |
| Canon drift between parallel strands | Fact extraction on thread B mutates world understanding thread A's in-flight scene contradicts | Claim disjointness makes entity-level drift structurally impossible; lore stays global and serialized with the contradiction detector as the cross-thread guard; P2's commit-gate re-check catches the in-flight window; P1 has no in-flight window at all |
| Chronology bugs | "Meanwhile" logic is genuinely hard; the coarse clock will miss prose-level anachronisms | Coarse epoch checks catch the structural class (one entity, two places); prose-level time errors remain the evaluator's territory and are accepted as out of scope; validation reads for them |
| Cost multiplication | A second strand is more scenes, and P2 buffers may generate scenes the assembly later regrets | B-thread scenes are budgeted by the runway math (6.4), not open-ended; P2 buffer depth capped at 1-2 scenes per thread; regretted-scene rate is a P2 metric with a kill threshold |
| Single-POV writer context assumption | `_format_recent_context` is global-recency: thread B's scene 2 would see thread A's scene 7 as "the recent scene", poisoning continuity | Thread-scoped writer context is the P1 core deliverable; the fork experiment **[evidence]** showed the writer context is narrower than assumed, so the recent-scenes block is the one hot surface to scope |
| Reader whiplash at assembly | Interleaving badly is worse than not interleaving; a policy can satisfy the curve and still read like channel-surfing | Run-length minimums and cut-away rarity are hard constraints in the policy, not scores; assembly validation is a human read of the interleaved stretch (the interleaving design already committed to this) |
| Complexity for its own sake | P2 is a lot of machinery for a system whose bottleneck is LLM latency, not scheduling | The staged path: P0/P1 deliver the narrative value with zero concurrency; P2 ships only if P1's validation shows generated-ahead selection buys measurable curve fit; P3 is explicitly not planned |
| Contracts Slice 2 dependency | Intermingle preconditions need the precondition machinery, which is unbuilt | Named as a hard dependency (5.4); P0 can ship with checks as plain Python guards at beat selection and migrate onto contracts when Slice 2 lands |

## 9. Slices and validation (instrument first, pressure second)

Each slice ships config-gated, gets a measured run against a pre-registered
bar before the next, in the Phase 3 tradition. Prerequisites from the fix
queue: the finale thread stamp (6.2) and, for slice C onward, contracts
Slice 2 preconditions.

| Slice | Ships | Gate | Validation run and bar |
|---|---|---|---|
| **T4a: construction detector** | Triggers (section 2) as pure instrumentation: every tick logs `construction_evaluated` and would-fire reasons; nothing changes behavior | always-on metrics | Re-run the standard fixture (corporate thriller, 15-16 ticks). Bar: diversity trigger would-fire exactly once, inside the fraction window, respecting the runway floor; demand-gap stays silent on the default rising curve; zero tick failures attributable to the detector |
| **T4b: charter + seeding** (P0) | Charter authoring call, registry stamping, construction mandate in beat generation, register-band reconciliation | `coherence.thread_construction` (default False) | 2-thread A/B run at `target_story_length` ~24. Bar: charter sanitizes clean (cast disjoint, seed loop created); mandate adopted (>= 2 B-beats authored and selected within 2 batches); B-thread reaches `thread_min_run`; qualitative read says the B-thread is alive, not dead weight; main-thread metrics do not regress (drift, ending bar) |
| **T4c: thread-scoped context + story clock** (P1) | Writer context scoped to the scene's thread; epoch/ordinal stamping; loop `thread_id`; scene naming by ID; assembly manifest written (order still = generation order) | same flag family | Re-run the A/B fixture. Bar: deterministic scan shows B-thread scenes reference zero A-exclusive entities; clock stamps monotonic per thread; compile byte-identical to scene order for a single-thread legacy project |
| **T4d: intermingle checks + convergence** | Claim preconditions, no-touch write-set diff, convergence beat contract, deliberate expiry path | `coherence.thread_contracts` | Forced-convergence run. Bar: convergence beat executes only after preconditions pass (at least one deliberate precondition rejection observed and recovered via horizon revision); seed loop judged closed; finale reports zero silently dangling threads |
| **T4e: assembly-time ordering** (T2 lands here) | Selection policy orders the manuscript against the curve; cut-away suspension loops; `novel compile` reads the manifest | `coherence.thread_assembly` | Curve fit measured on the ASSEMBLED order vs generation order on the same scene set; human read of the interleaved stretch; whiplash bar: no thread run below minimum, cut-aways at or under the policy's rarity budget |
| **P2: concurrent generation** | Commit gate, scheduler, read/write tool split | `generation.parallel_threads` (default False) | Only after T4e. Bar: byte-equivalent story state vs serial execution on a fixed seed scenario; zero counter/ID anomalies over a full run; wall-clock and cost accounting published |

## 10. Config surface (all new keys, defaults conservative)

```yaml
coherence:
  thread_construction: false        # T4b master gate
  construction_floor: 0.15          # story fraction: earliest construction
  construction_cutoff: 0.5          # story fraction: latest construction (early/mid only)
  calm_threshold: 4                 # demand-gap trigger band top
  serve_margin: 2                   # thread can serve a target within this distance
  thread_min_run: 3                 # whiplash guard: decent run per thread
  convergence_reserve: 1            # slots held for the merge beat
  max_active_threads: 2             # validated limit; raising it is config, not design
  thread_contracts: false           # T4d gate
  thread_assembly: false            # T4e gate
generation:
  parallel_threads: false           # P2 gate
```

`thread_min_run` and the fraction windows are the knobs the masters study is
expected to re-default **[pending: masters study]**.

## 11. Open questions

1. Does the charter call want the multi-stage planner's stage-2 semantic
   gathering, or is a flat context enough? (Start flat; the finale author is
   flat and works.)
2. When the demand-gap trigger fires but the diversity trigger already
   constructed a thread, is a THIRD strand ever the right answer inside
   `max_active_threads`, or does the existing B-thread absorb the demand by
   re-chartering its band? (Proposed: absorb; construction stays rare.)
3. Should deliberate thread expiry be allowed to leave the convergence seed
   loop open as a story-level dangling question (a strand that never paid
   off, sometimes legitimate in literary fiction), or must expiry always
   resolve or expire the seed? (Proposed: expiry expires the seed with the
   thread, honesty over ambiguity; revisit against the masters study.)
4. POV and threads: T4c scopes context per thread, but whether a single
   thread can rotate POV among its members (the POV-switch machinery allows
   it) is left to the writer-context follow-up flagged in the interleaving
   design's open question 4.
5. Assembly and the reader's chapter boundaries: does a cut-away imply a
   chapter break in compile output? (Cosmetic, decide at T4e.)
