# Thread Interleaving: Tension by Scene Selection

**Status:** Design proposal (no implementation)
**Date:** 2026-07-10
**Motivated by:** the calm-scene prompt-surgery experiment (`progress_report_20260710.md`, Addendum 2) and the four descent validation arms before it
**Related:** `EMERGENT_COHERENCE_PLAN.md` (Phase 3), `BLOCKS_CONTRACTS_LANDING_SKETCH.md` (contracts), `DEV_NOTES_POV_SWITCH.md` (POV mobility)

## 1. The finding this answers

Five experiments over two months chased the same failure: the story cannot land
a calm ending on a descending tension curve. The chain of eliminated suspects:

1. The gauge (June): the keyword scorer was blind; replaced with the LLM scorer. Real.
2. The writer's calibration (June): writer and scorer unified on one scale. Held.
3. The planner's events (July): the arc-phase mandate made the planner choose
   aftermath events. Largely worked in reactive mode (final scene 8 to 6).
4. Beat delivery (July, plot-first): token truncation and wedged beats starved the
   descent window. Fixed (beat_max_tokens, authoring gates, step 11.5 timing).
5. The writer's prompt (the fork experiment): pruning 80 percent of the hot
   momentum context moved the mean tension by 0.0, and explicit no-countdown rules
   trended hotter. The writer was acquitted.

What remained: the assigned EVENT. The target-4 beat under test was a mid-escape
handoff with pursuit implied. Nobody can or should write a calm scene about an
escape. The scorer was right, the writer was right, and the request was wrong.

Conclusion: at the scene level, tension is a property of the event; you cannot
becalm a hot event with prompt engineering. Story-level tension control must
therefore operate one level up, on WHICH event the reader sees next.

## 2. The core model

A human author whose story must calm down while the main thread is mid-chase does
not becalm the chase. They cut away: leave the hot thread on a cliffhanger, pick
up a different, calmer thread. Page-to-page tension drops; long-term tension
RISES, because the suspended cliffhanger pulls the reader forward.

So the tension curve stops being a constraint on the next event of a single
serial thread and becomes a **scene-selection policy over a portfolio of
threads**:

- Each thread has its own natural, local tension trajectory. An escape thread
  stays hot until it resolves. A B-story domestic thread runs cool. Neither is
  forced against its nature.
- Python owns the interleave: at beat-selection time, prefer the pending beat
  from the thread whose current state best matches the curve's target band.
- The writer is always asked for exactly what the scene is: an escape scene is
  written as an escape, a calm scene as calm. Ask for rainbows and butterflies,
  get rainbows and butterflies. Scene-event integrity is non-negotiable; the
  curve is satisfied by scheduling, not by adulterating scenes.

## 3. Authoring principles (constraints on the mechanism)

These are design commitments, not tunables:

1. **Scene-event integrity.** A scene delivers the event it was assigned, at that
   event's natural tension. Contracts verify what was actually asked for. The
   PB014 failure (a tension_at_most 5 contract on an escape event) was a category
   error in assignment, not a contract defect.
2. **Thread construction is an early/mid-story move.** If no calm thread exists,
   one may be constructed, but only at the start or middle of a story. Late in a
   full-length work, introducing a new thread is a craft violation; late calm
   must come from SEQUENCING instead: resolve the hot thread, then the
   denouement, with a time-skip as the standard device (the time-skip is the
   degenerate cut-away: same thread, later).
3. **No unnecessary de-escalation mid-sequence.** A hot sequence in progress is
   not interrupted just because the curve dips; switching is a deliberate escape
   valve used when the story-level curve demands relief, and the hot sequence
   must still RESOLVE on the page eventually. The denouement is only reachable
   after the main thread's resolution, never instead of it.
4. **Whiplash guard.** Cut-aways are rare and deliberate. Every thread gets a
   decent run (a minimum consecutive-scene count) before a switch is considered.
   Interleaving badly is worse than not interleaving.

## 4. Contracts as the enforcement layer

The contract system (Slice 1, shipped) is the natural home for thread
discipline; this design extends what contracts are FOR rather than adding a
parallel mechanism:

- **Thread assignment rides the beat.** Beats already carry `plot_threads`
  labels; under this design a beat gets a primary thread, and its contract
  verifies the scene served THAT thread (deterministic where possible via the
  thread's characters/locations, judge-based otherwise).
- **Cut-away discipline as postconditions.** A B-thread scene written while
  thread A hangs on a cliffhanger carries conditions of the form: does not
  resolve thread A's suspended loop, does not advance thread A offscreen, does
  not introduce a new thread (late-story). These are checkable, and mostly
  deterministic against loop/entity state.
- **Scheduling rules as preconditions.** Minimum thread run-length and
  switch-eligibility are precondition-shaped: "thread B may be scheduled only
  if the current thread has run >= N consecutive scenes or sits at a legal
  suspension point." Slice 2 (precondition pressure) is the delivery vehicle.
- **Tension conditions become per-thread honest.** tension_at_most on a calm
  B-thread scene is natural and satisfiable; the same condition on an escape
  scene was the wedge. Assignment integrity dissolves the wedge class that
  cap-at-7 and the staleness rule currently backstop.

## 5. What already exists (footholds)

| Need | Existing machinery |
|---|---|
| Thread labels | `PlotBeat.plot_threads` (authored today, max 3 names, unused downstream) |
| POV mobility | POV-switch detection (`DEV_NOTES_POV_SWITCH.md`, entity_updater) already survives viewpoint changes |
| Cliffhangers | Open loops ARE suspended threads; a cut-away is a deliberately opened, high-salience loop with a planned payoff (unifies with loop-aging) |
| Scheduling surface | Beat selection (`get_next_beat`) plus the rolling horizon; the interleave policy is a beat-selection policy |
| Enforcement | Beat-embedded contracts (Slice 1), preconditions (Slice 2, unbuilt), judge checkers (Slice 3, unbuilt) |
| Curve and phases | arc_pressure target and arc phase, reinterpreted as the selection policy's demand signal |

## 6. Mechanism sketch

- **Thread registry:** a small first-class store (id, name, member characters,
  home locations, local tension state, suspended-at flag with the cliffhanger
  loop id, consecutive-run count). Seeded by normalizing the `plot_threads`
  labels the beats already carry.
- **Selection policy:** each tick, among pending beats, prefer the beat whose
  thread state best matches the curve's target band, subject to the run-length
  guard and the no-unnecessary-de-escalation rule. A hot thread mid-sequence
  with runway remaining keeps the floor.
- **Cut-away mechanics:** suspending a thread writes the cliffhanger loop
  (high importance, expected-resumption note); the next scenes' contracts carry
  the do-not-touch conditions; resumption closes the suspension loop.
- **Thread construction pressure:** when the curve foresees a calm demand the
  portfolio cannot meet (early/mid story only), beat generation is instructed to
  plant a B-thread; late-story, the planner must instead schedule resolution
  first and satisfy the calm tail by sequencing and time-skip.
- **Ending sequencing:** the finale is the special case with nothing to cut to.
  The descent tail of the curve is satisfied as: resolve (hot, honest), then
  aftermath (calmer), then denouement (calm, usually time-skipped). Beat
  authoring for the resolution phase must produce exactly that shape.

## 7. Hard parts, named honestly

1. **A calm thread must exist to cut to.** Construction pressure (section 6) is
   a real authoring behavior change; a B-thread planted badly is dead weight.
   This is the riskiest piece and should be validated in isolation.
2. **Context scoping.** The writer context should weight the scheduled thread's
   material. (The fork experiment showed the writer prompt is already narrower
   than assumed: no loop board, no tension history, so the lift is small.)
3. **Whiplash.** Guarded by run-length minimums and switch rarity, but the
   failure is qualitative; validation must include reading the interleaved
   stretch, not just scoring it.
4. **Short single-thread stories.** The portfolio may be one thread. The design
   must degrade to today's behavior plus time-skip sequencing, gracefully.

## 8. Slices

- **Slice 0 (prerequisites, independent value):** loop closure that actually
  works (beat completion nominates its `resolves_loops`, a focused judge
  confirms, importance-gated); the tension-floor cap and stale-target
  precedence rule. Without a working loop eraser, cliffhanger bookkeeping
  would drown like everything else.
- **Slice T1: thread registry.** Normalize `plot_threads` labels into the
  registry; instrument per-thread tension in metrics. No behavior change.
- **Slice T2: thread-aware beat selection.** The interleave policy with the
  run-length guard, gated by config. Validate on a mid-story calm-demand
  scenario (the fork projects are reusable fixtures).
- **Slice T3: cut-away contracts.** Suspension loops, do-not-touch
  postconditions, resumption. Requires Slice 2/3 contract machinery for
  preconditions and judge checks.
- **Slice T4: thread construction pressure** (early/mid only) and the
  resolution-phase sequencing mandate for endings.

Each slice ships config-gated and gets a measured run before the next, in the
Phase 3 tradition (instrument first, pressure second).

## 9. Open questions

1. Thread identity: normalize the LLM's free-text `plot_threads` names by
   similarity (the Phase 1 name-grounding move), or have Python mint thread ids
   the LLM selects from?
2. Where does the run-length minimum live: config constant, or derived from
   story length and thread count?
3. Does the selection policy ever OVERRIDE beat order authored by the rolling
   horizon, or does interleaving happen at authoring time (the horizon is told
   which thread to author next)? Authoring-time selection preserves the
   existing consume-in-order pipeline and is probably the smaller change.
4. How does POV interact with threads: is a thread bound to a POV character, or
   can a thread be viewed from multiple POVs? (The POV-switch machinery supports
   either; the writer context does not yet.)
