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

## Addendum: clean re-run after the fixes (same day)

Next-steps item 4 executed immediately: fresh project `descent-pf2`
(`work/novels/descent-pf2_ddd9d9de/`), same foundation, goal, and run-start config as
`descent-pf` (backend `api`, model `openrouter` via `anthropic/claude-haiku-4.5`,
timeout 120, plot-first + contracts on, `target_story_length: 15`, default curve;
`generation.beat_max_tokens` deliberately left unset so the new default 2000 from
b99b67f is what gets exercised). 16 scenes (ticks 0 through 15), ~30.8k words, and
this time **zero manual interventions**: no CLI beat injections, no hand-unwedging.

Headline: **all three b99b67f fixes held, delivery worked unaided, and a new wedge
took delivery's place.** The final scene scored **8 against target 4**: equal to
June's control, worse than both July arms. The cause is entirely new. The peak beat
(PB012, tension_target 8.8, authored postcondition `tension_at_least 8`) failed its
contract at ticks 13 and 14 because the scenes scored 7 (the documented peak
undershoot: the LLM scorer is reluctant to grant 8+), and keep-pending semantics
pinned it through the whole resolution window. The on-time-authored calm beats
(PB013 at 7.3, PB014 at 4, PB015 at 4, `tension_at_most` guards on both 4s) were
never consumed. At tick 15 the scene finally scored 8: the contract passed at the
exact tick the schedule wanted 4.0, and the run ended on its climax ("The
Confrontation Protocol", the Grimel/Wynox executive-office confrontation).

### Four-way comparison

| metric | June (control) | July (reactive + mandate) | plot-first, defect-marred | plot-first, clean re-run |
|---|---|---|---|---|
| overall drift, all scored ticks | **1.20** | 1.55 | 1.60 | 1.65 |
| overall bias (signed) | +0.75 | **+0.55** | +1.15 | +1.21 |
| rising drift (ticks 0-12) | **0.96** | 1.51 | 1.54 | 1.56 |
| peak drift (tick 13) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) |
| resolution drift (ticks 14-15) | 2.35 | **1.65** | 1.85 | 2.15 |
| final scene: target 4.0, actual | 8 | **6** | 7 | 8 |
| final-scene event kind | still the climax | aftermath | the exposure itself | still the climax (stale peak beat) |
| beats steering scenes | n/a | n/a | ticks 2-10 and 15 | every tick 2-15 |
| manual interventions | 0 | 0 | 2 | **0** |

Per-tick trace (`memory/metrics.jsonl`; cc = contract conditions checked/failed):

| tick | target | actual | phase | beat | cc |
|---|---|---|---|---|---|
| 0 | 3.0 | (not scored) | rising | | |
| 1 | 3.5 | 7 | rising | | |
| 2 | 4.1 | 7 | rising | PB001 ✓ | 3/0 |
| 3 | 4.6 | 7 | rising | PB002 ✓ | 2/0 |
| 4 | 5.1 | 7 | rising | PB003 ✓ | 4/0 |
| 5 | 5.3 | 6 (rewrite 8 -> 6) | rising | PB004 ✓ | 2/0 |
| 6 | 5.6 | 7 | rising | PB005 ✓ | 3/0 |
| 7 | 5.9 | 7 | rising | PB006 ✓ | 3/0 |
| 8 | 6.3 | 8 | rising | PB007 ✓ | 2/0 |
| 9 | 6.8 | 8 | rising | PB008 ✓ | 3/0 |
| 10 | 7.3 | 8 | rising | PB009 ✓ | 2/0 |
| 11 | 7.9 | 7 | rising | PB010 ✓ | 3/0 |
| 12 | 8.3 | 8 | rising | PB011 ✓ | 2/0 |
| 13 | 8.8 | 7 | peak | PB012 ✗ (`tension_at_least 8`) | 3/1 |
| 14 | 7.3 | 7 | resolution | PB012 ✗ (again) | 3/1 |
| 15 | 4.0 | 8 | resolution | PB012 ✓ (third attempt) | 3/0 |

The mid-run tracking is the best measured in any arm: mean drift over ticks 5-14 is
**1.01**, with the beat targets and the schedule marching together (7.3 -> 8, 7.9 -> 7,
8.3 -> 8). The overall numbers are dragged by the same hot start as every arm (ticks
1-4 against gentle targets) plus the tick-15 blowout (+4.0), which is the wedge, not
the tracking.

### Fix verification, one by one

- **Token budget (fix 1): held.** Three beat batches, all authored in-run at ticks 2,
  7, and 12, all parsed **first-try** under the 2000-token default: 0 malformed
  responses, 0 retry firings (the defect run: 10 malformed responses across 6
  attempts, 5 starved ticks). The critical tick-12 batch delivered the peak and the
  descent on time and exactly on the slot schedule (targets 8.3 / 8.8 / 7.3 / 4 / 4).
- **Authoring gate (fix 2): held, without even firing.** All 15 beats carried
  postconditions drawn exclusively from the permitted vocabulary (`char_in_prose`,
  `tension_at_least`, `tension_at_most`): zero `char_at_location` or `loop_resolved`
  authored, zero gate warnings, zero sanitizer drops of any kind. The tightened
  prompt was sufficient on its own; the gate is now belt-and-braces.
- **Contract timing at step 11.5 (fix 3): held.** 38 conditions checked, 2 failed,
  and both failures are honest (PB012's `tension_at_least 8` against scenes fairly
  scored 7). All 12 completed beats verified with `verification_method: "contract"`.
  No structurally-unsatisfiable failure occurred anywhere.

### The new wedge: keep-pending vs. the scorer's ceiling

Wedging observed, without intervention: PB012 pending for three ticks (13-15), two
consecutive contract failures, completed on the third attempt only because the final
scene escalated to 8. The mechanism is different from the defect run's
(`char_at_location` was unsatisfiable by construction; `tension_at_least 8` is
unsatisfiable in practice, because the scorer has never granted above 8 in any of the
four arms) but the consequence is identical: one beat eats the descent runway. Tick
14's scene actually landed almost on schedule (7 vs 7.3), yet it "failed" because the
contract it was graded against belonged to the previous slot. The resolution-phase
scenes were therefore both written against a stale peak beat, whose `tension_target`
8.8 also suppresses the writer's resolution-band arc-pressure section: the
de-escalation machinery was overridden precisely when it was needed.

This is next-steps item 2 (the give-up rule), now measured twice in two different
costumes. Two additions to its design brief from this run: (a) an attempt counter
with abandon-or-downgrade semantics remains the core need (N=2 here would have freed
tick 15 for PB013/PB014); (b) authored `tension_at_least` values should be capped at
7, or peak beats' tension floors treated as advisory, because demanding 8+ from a
scorer that almost never grants it manufactures wedges at the worst possible spot.

### Stability

15/15 ticks unaided, `--retries 2` never consumed, `errors/` empty. Per-tick wall
time 71-114s (mean 82.5s); OpenRouter clean across ~150 calls (no 5xx, no 429, no
timeouts). Three absorbed JSON parse warnings during context gathering (ticks 9, 10,
12), all recovered by graceful degradation. Tension rewrite machinery: one downward
rewrite fired and stuck (tick 5, 8 -> 6, the only rewrite that has ever landed in a
plot-first arm), two futile-skips (ticks 1 and 15), two revise-but-keep-original
(ticks 2-3). Loop economy unchanged and still broken: 0 loops closed all run, 64 open
at the end.

### The forward-looking question (forced low-tension scenes)

Unanswerable from this run, and that is itself the finding: **no calm beat has ever
reached the writer in two plot-first attempts** (defect run: starved by truncation;
this run: blocked by the wedge). Scenes 14 and 15 read hot because their assigned
events were hot (a pursuit crawl through cable conduits, then the executive-office
confrontation), and the scorer graded them fairly; there is still zero live evidence
about whether the writer runs hot on a genuinely calm assigned event. The tick-12
batch's calm beats are also worth noting for that future test: authored at story
position 80%, PB014/PB015 are falling-action events (an escape handoff, contacting
federal authorities) rather than the pure aftermath/time-skip denouement the
defect run's position-100% batch produced. Scoping implication: the "forced
low-tension scenes" work is blocked behind the give-up rule, not behind writer
calming; fix the wedge first, then re-ask this question with a consumed
`tension_at_most 4` beat in hand.

### Addendum artifacts

- Clean re-run (gitignored `work/`): `work/novels/descent-pf2_ddd9d9de/` (scenes,
  `memory/metrics.jsonl`, `plot_outline.json` with per-beat `contract_results`,
  planner snapshots in `plans/`).
- Run log: scratchpad copy (`descent-pf2-run.log`), not committed.

## Addendum 2: fork experiment, calm-scene prompt surgery

Single-scene fork experiment (same day) answering the forced-low-tension question the
clean re-run left open: does the writer run hot even on a calm assigned event, and
does pruning the hot momentum context out of the writer prompt fix it?

### Setup

Two fork copies of `descent-pf2_ddd9d9de` (`work/novels/fork-calm-a/`,
`fork-calm-b/`; the original untouched). In each fork, pending PB013 (target 7.3) was
marked `abandoned` (reason recorded in the outline) so the calm denouement beat PB014
became next: target 4, postconditions `char_in_prose C000`, `char_in_prose C007`,
`tension_at_most 5`. One real tick per fork (backend `api`, `openrouter` via
`anthropic/claude-haiku-4.5`). The writer prompt was captured from the fork-b tick by
monkeypatching `SceneWriter._format_writer_prompt` in a scratchpad driver
(`--save-prompts` dumps planner prompts only).

Real-tick baselines: fork-a scored **7**, fork-b **6**, both against target 4, no
rewrite fired in either, and in both PB014 verified `trusted_planner` but failed its
`tension_at_most 5` contract and was kept pending.

A discovery about the hypothesis itself: the captured writer prompt (39.3k chars)
contains **no open-loops board and no tension-history listing**. Those feed the
planner, not the writer. The writer's hot momentum context is entirely the
recent-story region (three climactic scene summaries plus the full text of scenes
14-15: the conduit pursuit, the executive confrontation, a two-hour containment
countdown, and the cliffhanger "What about you?"), 31.6k chars, about 80 percent of
the prompt.

### Variants

Offline, 3 samples each, through the real writer path: `openrouter` at
`writer_max_tokens` 3000, responses parsed with `SceneWriter._parse_scene_response`,
scored by the real `TensionEvaluator` LLM scorer with the fork's config.

- (a) AS-IS: the captured prompt, unedited.
- (b) PRUNED: the whole recent-story body replaced with a neutral aftermath framing
  ("The confrontation has concluded. The exposure is public. Consequences are
  settling... No unresolved threats need attention in this scene."). Everything from
  the plan section onward byte-identical.
- (c) PRUNED+RULES: (b) plus mandatory exclusionary rules beside the tension target
  (no new threats, dangers, mysteries, or complications; no countdowns, no deadlines,
  no cliffhanger ending; let the scene settle, end in stillness), wording aligned
  with `ARC_PHASE_MANDATES["resolution"]`.

### Results (target 4, contract cap 5)

| variant | s1 | s2 | s3 | mean |
|---|---|---|---|---|
| (a) as-is | 6 | 5 | 8 | **6.33** |
| (b) pruned | 7 | 5 | 7 | **6.33** |
| (c) pruned + rules | 7 | 7 | 8 | **7.33** |
| real ticks (fork-a, fork-b) | 7 | 6 | | 6.5 |

### Decision-map verdict: nothing fixed it

No arm landed near 4; per the pre-registered map, the scorer floor for this material
is ~6 and the curve/beat design should absorb it. The sharper reading: "this
material" means the assigned event, not the prompt. Removing 80 percent of the
prompt (all hot momentum context) moved the mean by exactly 0.0, and the
exclusionary rules trended higher, not lower (7.33, likely noise at n=3, certainly
no fix). Every scorer rationale grades the situation: escape in motion, imminent
discovery, trusting a stranger whose motives are uncertain. PB014 ("Nyxiss reaches
the building exit but encounters security officer Raxath... provides a vehicle for
escape") is a falling-action escape event, exactly as the first addendum flagged, and
a mid-escape scene with pursuit implied is a 5-8 in the scorer's rubric no matter how
quiet the prose register is. The writer even synthesizes urgency the prompt does not
contain: sample (b)-1 invented an "approximately eight minutes" sweep and (c)-1
invented a "maybe two hours" deadline, in direct violation of the no-countdown rule
and with no countdown present anywhere in its prompt. One residual hot cue survived
the surgery by design (the untouched plan section's tool results include "Tyrox
security director pursuit threat"), and Tyrox duly appears as off-page menace in most
pruned samples.

Qualitatively, the pruned and rules scenes are competent prose, not calm-but-garbage:
they run tighter (950-1300 words vs 1500-2100 as-is), stay on-beat, and their endings
genuinely settle. The contrast the scores hide, (a) sample 3 (scored 8) versus (c)
sample 1 (scored 7):

> "Two hours, Wynox had said. Two hours before containment protocols activated. ...
> She would trigger alerts. She would be detained. She would be placed in
> institutional containment while Vernmarsh determined what to do with her." (a)

> "It wasn't safety. But it was momentum. It was the moment after the choice, when
> the thing you've set in motion finally becomes real. Nyxiss kept driving." (c)

The (c) ending is in stillness, as instructed; the scene still scores 7 because the
event it depicts is an escape under threat. Verdict for the roadmap: the
forced-low-tension work is not a writer-prompt problem. Prompt pruning and
exclusionary vocabulary are not worth building as tension controls. A target-4 scene
requires a target-4 event: pure aftermath or time-skip denouement beats (the defect
run's PB008 shape, "six months later..."), which is beat authoring and curve/runway
design, plus the give-up rule so those beats are actually reached.

### Addendum 2 artifacts

- Forks (gitignored `work/`): `work/novels/fork-calm-a/`, `work/novels/fork-calm-b/`
  (scene_016, metrics.jsonl, outline with PB014 contract_results).
- Scratchpad (session-local, not committed): captured prompt
  (`writer_prompt_asis.txt`), variants (`writer_prompt_pruned.txt`,
  `writer_prompt_pruned_rules.txt`), edit record (`variant_edits.diff`,
  `build_variants.py`), driver (`gen_and_score.py`, `run_tick_capture.py`), all nine
  scenes with scores (`samples/`, `results.json`), run log (`gen_and_score.log`).

## Addendum 3: descent run 3, the arbiter (cap + staleness live)

The run every prior arm was disqualified from being: nothing broke, nothing was
touched, and the ending got measured. Fresh project `descent-run3`
(`work/novels/descent-run3_8e35c9d2/`), same foundation and user goal verbatim,
run-start config identical to both plot-first arms (backend `api`, model
`openrouter` via `anthropic/claude-haiku-4.5`, timeout 120, plot-first + contracts
on, `target_story_length: 15`, default curve, `beat_max_tokens` unset so the
shipped default 2000 applies), executed at 052e6f0: the first live exercise of the
two new backstops, `TENSION_FLOOR_CAP` (contracts/authoring.py) and
`beat_target_is_stale` (agent/arc_pressure.py). 16 scenes (ticks 0 through 15),
~31.8k words, **zero manual interventions**.

Headline: the final scene ("The Warrant", the arrest watched on monitors) scored
**6 against target 4**, tying July's reactive arm for the best measured ending,
and this time through a fully unbroken plot-first pipeline: three 5-beat batches
authored in-run and parsed first-try (0 malformed responses), 13 of 13 completed
beats verified `contract`, the peak beat cleared at the peak tick, no wedge, no
starvation, every beat consumed exactly on its scheduled slot. Per the
pre-registered decision map, 6 lands in the 6-7 bucket: **the material floor is
real, target-4 same-thread endings are unreachable without a time-skip or
cut-away, and thread interleaving plus the resolution-phase time-skip mandate is
the actual fix, not an enhancement.**

### Predictions, pre-registered

- **P1 (floor cap fires or floors arrive legal): confirmed, first branch, twice.**
  Both in-run peak beats were authored with `tension_at_least 8` and both were
  clamped with the cap warning verbatim: PB010 (tick-7 batch) and PB011 (tick-12
  batch, the actual peak slot). Authoring floors of 8 at the peak is evidently the
  model's habit (2 for 2 across batches); the cap is doing real work.
- **P2 (peak beat completes at the peak tick): confirmed.** PB011 (target 8.8,
  floor clamped 8 to 7) completed at tick 13 on a scene scored 7, exactly the
  wedge the clean re-run died on. The queue advanced into the resolution window
  for the first time in any arm.
- **P3 (calm beats consumed at ticks 14-15 through the unbroken pipeline): half
  confirmed, and the half that failed is the finding.** Beats WERE consumed at
  ticks 14-15 with nothing broken (first time ever), but the beats occupying those
  slots were not the calm ones: tick 14 got PB012 (authored 8.8 against the 7.3
  slot, within the reconciler's deviation band, scored 9) and tick 15 got PB013
  (the FBI raid, authored 7.3 against the 4.0 slot, clamped to 6, scored 6). The
  genuinely calm beats (PB014, PB015) were authored on time and stranded at batch
  slots 4-5, scheduled ticks 16-17 of a 15-tick story.
- **P4 (staleness backstop never needed): confirmed.** Every beat was consumed on
  its scheduled slot; `beat_target_is_stale` never fired. One near-miss worth
  recording: PB013 as authored (7.3) would have read stale at tick 15 (|7.3 - 4.0|
  = 3.3 >= step 3) and yielded the writer to the schedule's target-4 guidance, but
  the schedule reconciler had already clamped its target to 6 (|6 - 4| = 2 < 3),
  so the beat governed and the writer aimed at 6. The two backstops can shadow
  each other: the milder number-clamp pre-empted the stronger yield-to-schedule
  rule at the one tick it might have mattered. The scene then scored exactly 6.

### Five-way comparison

| metric | June (control) | July (reactive + mandate) | plot-first, defect-marred | plot-first, clean re-run | this run (arbiter) |
|---|---|---|---|---|---|
| overall drift, all scored ticks | **1.20** | 1.55 | 1.60 | 1.65 | 1.72 |
| overall bias (signed) | +0.75 | **+0.55** | +1.15 | +1.21 | +1.15 |
| rising drift (ticks 0-12) | **0.96** | 1.51 | 1.54 | 1.56 | 1.69 |
| peak drift (tick 13) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) |
| resolution drift (ticks 14-15) | 2.35 | **1.65** | 1.85 | 2.15 | 1.85 |
| final scene: target 4.0, actual | 8 | **6** | 7 | 8 | **6** |
| final-scene event kind | still the climax | aftermath | the exposure itself | still the climax (stale peak beat) | the arrest (warrant execution, watched on monitors) |
| beats steering scenes | n/a | n/a | ticks 2-10 and 15 | every tick 2-15 | every tick 2-15 |
| manual interventions | 0 | 0 | 2 | 0 | **0** |

The overall drift (1.72, worst of five) is almost entirely the hot start (ticks
1-5 mean drift 2.88 against targets 3.5-5.3, same as every arm) plus tick 14's 9,
the first 9 the scorer has granted in any arm (a small correction to "the scorer
never grants above 8": rarely, not never; the floor cap's premise, that DEMANDING
8+ manufactures wedges, is unchanged and was demonstrated twice by the clamps).
Mid-run tracking (ticks 5-14) is 1.21. The number that matters is the ending: 6,
through a pipeline that finally did everything it was designed to do.

### Beat-authoring quality in the resolution window: the enforcement gap, precisely

The tick-12 batch's slots were scheduled at ticks 13-17: targets 8.8, 7.3, 4.0,
4.0, 4.0. Verbatim, the three beats that landed in or nearest the calm slots:

- **PB013** (slot 3, the tick-15 target-4.0 slot; authored tension_target 7.3,
  clamped to 6): "FBI investigator Taruth arrives at the corporate office with
  federal agents to execute a warrant for Kaelus's devices, emails, and financial
  records, effectively moving the investigation from covert to overt."
  Postconditions: `char_in_prose C008`, `tension_at_most 8`. Creates
  `kaelus_detained`.
- **PB014** (slot 4, scheduled tick 16, never consumed; tension_target 4):
  "Ionaora provides formal testimony to federal investigators about her
  investigation, Aryn's coordination, and the evidence she gathered, officially
  establishing her role as a cooperating witness." Postconditions: `char_in_prose
  C000`, `tension_at_most 5`. Creates none.
- **PB015** (slot 5, scheduled tick 17, never consumed; tension_target 4): "Six
  weeks later, Kaelus is formally charged with securities fraud, wire fraud, and
  conspiracy; Ionaora receives notice of federal witness protection eligibility
  and begins planning her career transition." Postconditions: `tension_at_most 4`.
  Resolves 3 loops, creates none.

Characterization: the batch de-escalates in the right ORDER but at the wrong
OFFSET. PB014 is plausible falling action (procedural aftermath) and PB015 is the
pure time-skip denouement the resolution directive asks for, so the authoring
directives work, again. But the target-4.0 slot itself received a warrant raid, a
hot event, and the only enforcement that exists edited its NUMBER: the reconciler
clamped 7.3 to 6 and nothing anywhere edits the EVENT. A raid with its target
clamped to 6 is still a raid, and it duly scored 6. Meanwhile the author treated
the batch as a serial event sequence (decision, confirmation, raid, testimony,
time-skip) and needed five events to cool down when the story had three slots
left. This is exactly the gap the interleaving design's contracts close:
scene-event integrity plus per-slot assignment honesty ("the target-4 slot may
only receive an event whose natural tension is 4") instead of post-hoc numeric
clamping of whatever event happens to be next in the thread.

One more arithmetic observation, because the pipeline is now deterministic enough
for it to matter: with batches authored at ticks 2, 7, and 12 and one beat
consumed per tick, the finale's identity was decided by a single early stall.
PB001 failed its `tension_at_most 7` once at tick 2 (scene scored 8, the hot
start) and completed at tick 3; without that one-tick slip every beat shifts one
earlier and PB014, the testimony aftermath with `tension_at_most 5`, becomes the
final scene. The ending landed on the raid by one tick of batch arithmetic. The
runway is that tight, which is the same conclusion as the offset problem stated
temporally: same-thread descent needs more slots than a 15-tick story has after
its peak.

### Per-tick trace

Per-tick trace (`memory/metrics.jsonl`; cc = contract conditions checked/failed):

| tick | target | actual | phase | beat | cc |
|---|---|---|---|---|---|
| 0 | 3.0 | (not scored) | rising | | |
| 1 | 3.5 | 7 | rising | | |
| 2 | 4.1 | 8 | rising | PB001 ✗ (`tension_at_most 7`) | 3/1 |
| 3 | 4.6 | 7 | rising | PB001 ✓ (second attempt) | 3/0 |
| 4 | 5.1 | 7 | rising | PB002 ✓ | 3/0 |
| 5 | 5.3 | 8 | rising | PB003 ✓ | 3/0 |
| 6 | 5.6 | 7 | rising | PB004 ✓ | 2/0 |
| 7 | 5.9 | 7 | rising | PB005 ✓ | 3/0 |
| 8 | 6.3 | 7 | rising | PB006 ✓ | 3/0 |
| 9 | 6.8 | 7 | rising | PB007 ✓ | 3/0 |
| 10 | 7.3 | 7 | rising | PB008 ✓ | 3/0 |
| 11 | 7.9 | 7 | rising | PB009 ✓ | 3/0 |
| 12 | 8.3 | 7 | rising | PB010 ✓ | 3/0 |
| 13 | 8.8 | 7 | peak | PB011 ✓ (floor clamped 8 to 7) | 2/0 |
| 14 | 7.3 | 9 | resolution | PB012 ✓ | 3/0 |
| 15 | 4.0 | 6 | resolution | PB013 ✓ (target clamped 7.3 to 6) | 2/0 |

Contract totals: 39 conditions checked, 1 failed (PB001's ceiling at tick 2,
cleared next tick: keep-pending cost one tick, the mildest wedge in any arm, and
it never recurred). All 13 completed beats: `verification_method: "contract"`.

### Fix behavior and stability

- **Cap warnings seen:** 2 (PB010, PB011), both authored `tension_at_least 8`
  clamped to 7. **Staleness fired:** never (P4). **Schedule-reconciler target
  clamps:** 1 (PB013, 7.3 to 6). No gated-check drops, no unresolved-ref drops,
  no condition-count trims.
- **Prior fixes held:** 3 of 3 batches parsed first-try under the 2000-token
  default (0 malformed responses); all 15 beats carried postconditions from the
  permitted vocabulary (zero `char_at_location` / `loop_resolved` authored).
- **Stability:** 15/15 ticks; ONE tick-level retry consumed (tick 6, the scene
  evaluator returned passed=False with an empty issues list, `error_006.json`;
  the retry succeeded), the first `errors/` entry and first retry consumed in any
  descent arm, absorbed exactly as designed. Three graceful fact-extraction
  degradations (ticks 9, 12, 15, malformed extractor JSON, continued without
  updates). Per-tick wall time 66-116s (mean 80.0s); OpenRouter clean otherwise
  (~150 calls, no 5xx, no 429, no timeouts). Tension rewrites: two futile-skips
  (ticks 1-2), two revise-but-keep-original (ticks 3, 5), none in the resolution
  window (tick 15's gap of 2 is not above the threshold 2). Character-detector
  noise persists ("She", "Something", "Special Agent").
- **Loop economy (Slice 0 baseline):** 72 loops opened, **0 closed**, 72 open at
  the end. Beats claim `resolves_loops` (PB013 names OL43) and nothing in the
  pipeline ever sets a loop's status to resolved; third run confirming the
  counter.

### Decision-map verdict

Pre-registered: ~4-5 means the pipeline was sufficient and interleaving is an
enhancement; ~6-7 means the material floor is real and interleaving plus the
resolution-phase time-skip mandate becomes the actual fix. The arbiter says **6**,
with the cleanest possible provenance: no truncation, no unsatisfiable condition,
no wedge, no stale beat, no manual touch. Two independent mechanisms (July's
reactive mandate and this run's beat-steered pipeline) now converge on the same
floor of 6, and this run adds the causal detail the reactive arm could not: the
floor is not in the gauge, the writer, or the delivery, it is in WHICH event the
serial thread offers the final slot. The true target-4 events existed in the
outline (PB015, "Six weeks later..."), authored by the bridge exactly as
directed, two slots out of reach. The elimination chain in
`docs/THREAD_INTERLEAVING_DESIGN.md` section 1 is complete: gauge fixed, writer
acquitted, planner mandated, delivery fixed and now proven end-to-end, and the
ending still cannot reach 4 in the same thread. Scene selection (interleaving,
with the time-skip as the degenerate cut-away and slot-aware assignment honesty
in the contracts) is the fix; the cap and the staleness rule are its backstops,
both now validated live.

### Addendum 3 artifacts

- This run (gitignored `work/`): `work/novels/descent-run3_8e35c9d2/` (scenes,
  `memory/metrics.jsonl` with contract counters, `plot_outline.json` with per-beat
  `contract_results`, planner snapshots in `plans/`, `errors/error_006.json`).
- Run log: scratchpad copy (`descent-run3.log`), not committed.
