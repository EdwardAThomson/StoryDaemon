# Progress Report: 10th July 2026 (Fable 5)

Third arm of the descent validation (June control: `docs/progress_report_20260602.md`;
July reactive+mandate: `docs/progress_report_20260709.md`), and the first live exercise
of the **plot-first descent path**: beats AUTHORED to de-escalate on the falling tail
(the arc-pressure beat-generation bridge, `arc_guidance_for_beats` +
`ARC_PHASE_BEAT_DIRECTIVES`), with beat-embedded contracts on
(`generation.use_contracts`). Everything validated before this ran the rising phase
only; the bridge's entire purpose had never been observed live.

Headline, in two halves: **beat authoring de-escalates exactly as designed, and the
delivery pipeline failed to get those beats to the writer.** When the resolution-phase
batch was finally authored (see section 3), the beats prescribed aftermath events
(consequences, a settlement choice, a six-month time-skip denouement), carried the
scheduled tension_target 4, carried tension_at_most postconditions, resolved loops and
opened none. But in-run beat generation truncated at a hardcoded 1000-token cap for five
consecutive ticks, and before that an unsatisfiable postcondition wedged the queue for
five ticks, so the story consumed only the first (still hot) resolution beat, at the
final tick. The final scene scored **7 against target 4**: worse than July's reactive
run (6), better than June's control (8). The verdict on the bridge is split: authoring
proven, delivery unproven.

## 1. Methodology

Fresh project `descent-pf` (`work/novels/descent-pf_651113b3/`), mirroring the June
(`descent_efa72af8`) and July (`descent2_36ea1526`) runs: same foundation and
user-specified goal copied verbatim from their `state.json` (corporate thriller,
junior-analyst-discovers-heist, "Expose the corporate data heist before the merger
closes and the evidence is buried"), `target_story_length: 15`, default curve, 16
scenes (ticks 0 through 15), ~29.2k words (June ~28.7k, July ~27.6k).

Deliberate differences from July:

- `generation.use_plot_first: true` and `generation.use_contracts: true` (config
  template: the `contracts-smoke_f22e5541` smoke run).
- Backend `api` with model `openrouter` (`OPENROUTER_MODEL=anthropic/claude-haiku-4.5`),
  not `claude-cli`; timeout 120.

Two manual interventions during the run, both documented in place and unavoidable if
the descent was to be observed at all:

1. **Tick 8, unwedge:** beat PB003 was marked `abandoned` by hand after 5 consecutive
   contract failures (ticks 4-8) on a structurally unsatisfiable `char_at_location`
   postcondition (section 5) pinned the queue.
2. **Tick 14, beat injection:** after in-run beat regeneration truncated at ticks
   10-14 (section 4), the resolution batch (PB006-PB008) was generated through the CLI
   path (`novel plot generate --count 3`, 2000-token budget), which parsed on the first
   attempt. Tick 15 consumed PB006 from that batch live.

## 2. Three-way comparison

Mean `|tension - target|` per derived arc phase (same curve and length in all arms):

| metric | June (control) | July (reactive + mandate) | this run (plot-first + contracts) |
|---|---|---|---|
| overall drift, all scored ticks | **1.20** | 1.55 | 1.60 |
| overall bias (signed) | +0.75 | **+0.55** | +1.15 |
| rising drift (ticks 0-12) | **0.96** | 1.51 | 1.54 |
| peak drift (tick 13) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) |
| resolution drift (ticks 14-15) | 2.35 | **1.65** | 1.85 |
| final scene: target 4.0, actual | 8 | **6** | 7 |
| final-scene event kind | still the climax | aftermath of the exposure | the exposure itself (countdown to publication) |
| beats steering scenes | n/a | n/a | ticks 2-10 and 15 only |

Per-tick trace (from `memory/metrics.jsonl`; `cc` = contract conditions
checked/failed, blank where no beat was current):

| tick | target | actual | phase | beat | cc |
|---|---|---|---|---|---|
| 0 | 3.0 | (not scored) | rising | | |
| 1 | 3.5 | 8 | rising | | |
| 2 | 4.1 | 7 | rising | PB001 ✓ | 3/0 |
| 3 | 4.6 | 7 | rising | PB002 ✓ | 2/0 |
| 4 | 5.1 | 7 | rising | PB003 ✗ | 2/1 |
| 5 | 5.3 | 7 | rising | PB003 ✗ | 2/1 |
| 6 | 5.6 | 7 | rising | PB003 ✗ | 2/1 |
| 7 | 5.9 | 7 | rising | PB003 ✗ | 2/1 |
| 8 | 6.3 | 7 | rising | PB003 ✗ (then abandoned) | 2/1 |
| 9 | 6.8 | 7 | rising | PB004 ✓ | 2/0 |
| 10 | 7.3 | 7 | rising | PB005 ✓ | 1/0 |
| 11 | 7.9 | 8 | rising | (regen truncated, reactive) | |
| 12 | 8.3 | 7 | rising | (regen truncated, reactive) | |
| 13 | 8.8 | 7 | peak | (regen truncated, reactive) | |
| 14 | 7.3 | 8 | resolution | (regen truncated, reactive) | |
| 15 | 4.0 | 7 | resolution | PB006 ✗ | 3/3 |

Contract totals: 21 conditions checked, 8 failed (5 of the 8 are PB003's
`char_at_location`, re-checked once per tick while it pinned the queue; 3 are PB006's
at tick 15). No prose tension rewrite fired on any tick.

## 3. The headline: resolution-phase beats DO de-escalate, in authored intent

The resolution batch (authored at story position ~100%, phase RESOLUTION for all three
slots, scheduled target 4.0) is the first live look at what the bridge produces, and it
is exactly what `ARC_PHASE_BEAT_DIRECTIVES["resolution"]` mandates ("denouement only,
show the aftermath and the cost, close the remaining open loops, time-skips encouraged;
do NOT introduce new threats"):

- **PB006** (tension_target 4): "Kelor Bexox publishes the Meridian Initiative exposé,
  forcing Karthorn into crisis management mode and triggering regulatory
  investigations." Postconditions: `loop_resolved OL20`, `loop_resolved OL55`,
  `tension_at_most 6`. Resolves 3 loops, creates none.
- **PB007** (tension_target 4): "Oraex chooses to refuse the settlement offer,
  accepting criminal charges rather than silence, while Ulis faces internal
  investigation but maintains his denial of involvement." Postconditions: two
  `loop_resolved`, `tension_at_most 6`. Resolves 4 loops, creates none.
- **PB008** (tension_target 4): "Six months later, Oraex testifies before a federal
  grand jury while Karthorn dissolves under regulatory sanctions and criminal
  indictments; the Meridian Initiative is dismantled." Postconditions: three
  `loop_resolved`, `tension_at_most 6`. Resolves 7 loops, creates none.

Every marker the bridge is supposed to produce is present: scheduled low
tension_targets (all reconciled to 4, no clamping needed), `tension_at_most`
postconditions on all three, `creates_loops` empty across the batch, aggressive
`resolves_loops`, and an explicit time-skip denouement (PB008). The batch also
de-escalates internally: publication event, then a consequence choice, then
six-months-later closure.

The caveat that decides the final number: the story only reached PB006, the hottest of
the three, at the final tick. Scene 15 ("The Publication") depicts the exposé going
live on a 47-minute countdown; the LLM scorer's 7 is a fair grade of that event. The
genuinely calm beats (PB007, PB008) were authored but never consumed: the run ended,
and PB006's failed contract would have held the queue anyway (section 5). So this run
demonstrates the June thesis at the beat-authoring level too: the *batch* de-escalates,
but the first beat of a resolution batch is still a big event, and target 4 needs the
*later* beats. The descent needs runway in beats, exactly as July concluded it needs
runway in ticks.

Rising-phase contrast, from the tick-2 batch (targets 4.6-5.9, phase RISING): "testing
whether he knows about the export anomaly", "creating immediate suspicion", "risking
digital forensic detection", "surveillance", "forcing her to confront that she is
actively being tracked". Escalation vocabulary throughout, per the rising directive:
the bridge discriminates by phase.

## 4. Delivery failure 1: beat generation truncates at a hardcoded 1000-token cap

The agent path's beat generation (`plot/manager.py:_build_generation_context`) passes a
hardcoded `"planner_max_tokens": 1000` (it does not read `llm.planner_max_tokens`; a
mid-run config bump to 2500 was silently inert). With contracts on, a 5-beat batch plus
postconditions plus the arc schedule does not fit: every truncation was a JSON parse
error at roughly 2400-3100 characters into the payload.

- Tick 2: first response malformed, the one-retry path ("Beat JSON malformed; retrying
  generation once...") fired and the retry parsed. 5 beats, all with postconditions.
- Ticks 10, 11, 12, 13, 14: regeneration attempted every tick (queue below threshold),
  and both the call and its retry truncated every time: 10 malformed responses, 0 beats,
  5 reactive ticks exactly where the schedule wanted the peak and the descent authored
  (targets 7.9, 8.3, 8.8, 7.3, 4.0).
- The CLI path (`cli/commands/plot.py`, `max_tokens=2000`) parsed first-try both times
  it was used this week (the contracts smoke run and this run's injection).

So the descent batch physically could not be authored in-run. This is the single
highest-leverage fix: read the token budget from config in the agent path (or raise the
constant), since contracts+arc-guidance have outgrown 1000 tokens.

## 5. Delivery failure 2: two postcondition types are structurally unsatisfiable and wedge the queue

Beat verification runs at step 8.5, before fact extraction (steps 9-12) mutates any
state. Two checker types depend on state that either updates later or never updates:

- **`char_at_location`** reads `character.current_state.location_id`, which nothing in
  the fact-extraction path ever populates (C000's was still `None` at tick 15). PB003
  carried `char_at_location C000 L001` and failed it **5 consecutive ticks (4-8)**,
  each time as "verified (trusted_planner) but contract failed; not marking complete".
  With `allow_beat_skip: false` and `rolling_horizon: false` the beat just stays
  pending: the queue was pinned for a third of the run until it was manually abandoned.
- **`loop_resolved`** requires the loop's status to be "resolved" at verification time,
  but loop resolution (when it happens at all) lands in fact extraction, after the
  check. Worse, this run's extractor resolved essentially nothing: 70 open loops at the
  end, 0 with status "resolved" (OL20 and OL55 stayed "open" even though scene 15
  on-page publishes the exposé they ask about). PB006 failed 3/3 postconditions at tick
  15 (two `loop_resolved` on timing/extraction, `tension_at_most 6` fairly, scene
  scored 7) and would have pinned the queue exactly like PB003 had the run continued.

Wedging count, for the pending give-up-rule design decision: PB003 five consecutive
failures (manual abandon), PB006 one (run ended). Two implications: (a) beats need an
attempt counter with a give-up rule (abandon, or downgrade to semantic-only
verification, after N contract failures), because keep-pending semantics turn one bad
condition into a stalled outline; (b) contract evaluation should either move after fact
extraction or re-check at the next tick's start, and `char_at_location` /
`loop_resolved` should be treated as unsatisfiable-by-construction until the state they
read is actually written by someone.

The flip side: on satisfiable conditions, contracts behaved exactly as designed. All
four completed beats verified with `verification_method: "contract"` (the
upgraded-confidence path), with `char_in_prose`, `tension_at_least`, and
`tension_at_most` all passing deterministically, e.g. PB001: 3/3 passed, including
`tension_at_most 7` against a scored 7.

## 6. Regression watch on this week's fixes

- **Malformed-JSON retry**: fired on 6 of 6 in-run batches; recovered 1 (tick 2). The
  retry works for stochastic malformation, and cannot work for deterministic truncation
  (section 4): those are different failures and only the first one is the retry's job.
- **Schema-example fix**: held. 8 of 8 persisted beats carried authored postconditions
  (5 in-run, 3 via CLI), against the pre-fix behavior of postconditions omitted every
  time.
- **Sanitizer**: one warning total, on the CLI batch ("beat PB008: 4 postconditions
  authored; keeping the first 3"), which is the cap working. No tension-target clamps
  (all authored targets were within band, including the resolution batch's 4s), no
  unknown-check drops, no unresolved-ref drops on conditions.

## 7. Stability

15/15 ticks completed, zero run-level retries consumed (`--retries 2` never needed),
`errors/` empty. OpenRouter (`anthropic/claude-haiku-4.5` via the `api` backend): no
5xx, no 429, no timeouts observed across ~150 LLM calls; per-tick wall time 59-101s
(mean ~81s), comfortably inside the 60-90s/tick estimate and much faster than the
`claude-cli` arms. The truncations in section 4 are a token-budget artifact, not an
OpenRouter reliability issue. Two cosmetic planner-JSON parse warnings ("Failed to
parse plan JSON", ticks 14-15) were absorbed by the multi-stage planner's fallback.
The character detector's known noise ("And", "That", "There" flagged as characters)
persists but is out of scope here.

## 8. Verdict and next steps

The question this run was built to answer ("do plot-first beats de-escalate the
ending?") splits cleanly: **authoring yes, delivery no.** The bridge writes the right
beats (calm, low-target, `tension_at_most`-guarded, loop-closing, time-skipping), and
the run never got to obey them: a token cap starved the queue through the whole
peak-and-descent window, a dead-on-arrival postcondition pinned it before that, and the
one resolution beat that did reach the writer was the batch's hottest event, at the
last tick, scoring 7 vs 4. July's reactive mandate remains the best measured ending
(6); this run's 7 measures the failure modes, not the bridge's ceiling.

In expected-value order:

1. **Fix the token budget in the agent beat path** (read `llm.planner_max_tokens`
   instead of the hardcoded 1000 in `_build_generation_context`): without this,
   contracts+arc-guidance beat generation fails deterministically and plot-first mode
   silently degrades to reactive.
2. **Give-up rule for failing beats**: attempt counter + abandon/downgrade after N
   contract failures (this run: N=5 and N=1 wedges), plus re-check timing (evaluate
   contracts after fact extraction, or re-verify at next tick start).
3. **Restrict authored condition vocabulary to what the system can satisfy**: drop or
   gate `char_at_location` and `loop_resolved` until `location_id` and loop resolution
   are actually written by the pipeline (or wire the extractor to resolve loops, which
   the loop-aging work already on the Phase 3 list needs anyway).
4. **Re-run this scenario clean** once 1-3 land, with 2-3 ticks of post-peak runway so
   the batch's calmer second and third beats (the PB007/PB008 analogues) are actually
   consumed: that is the real test of whether beat-steered scenes land the 4.

## Artifacts

- This run (gitignored `work/`): `work/novels/descent-pf_651113b3/` (scenes in
  `scenes/`, per-tick rubric in `memory/metrics.jsonl` including contract counters,
  beats with `contract_results` audit trail in `plot_outline.json`, planner snapshots
  in `plans/`).
- Run log: scratchpad copy (`descent-pf-run.log`), not committed.
- Prior arms preserved: `work/novels/descent_efa72af8/` (June),
  `work/novels/descent2_36ea1526/` (July).
