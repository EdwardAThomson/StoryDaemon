# Progress Report: 9th July 2026 (Fable 5)

Re-run of the June "descent" validation scenario (`docs/progress_report_20260602.md`,
section 2) to test the **arc-phase planner mandate** shipped since then
(`agent/arc_pressure.py`: `derive_arc_phase`, `ARC_PHASE_MANDATES`, `rewrite_futile`;
gated by `coherence.arc_phase_mandate`, default True). The June run is the control arm;
this run is the treatment arm. The question: with the planner told the arc *phase*
(rising / peak / falling / resolution) and mandated event kinds (escalate / confront /
resolve), do the resolution-phase scenes finally land calm?

Headline: **the mandate demonstrably changed planner event selection, and the ending is
no longer a climax.** The final scene dropped from 8/10 (June) to 6/10 against a target
of 4; resolution-phase drift fell from 2.35 to 1.65. But 6 is not calm: the fix is
directionally right and quantitatively half-landed.

## 1. Methodology: a faithful replication

Fresh project `descent2` (`work/novels/descent2_36ea1526/`), configured to mirror the
June `descent` run (`work/novels/descent_efa72af8/`, still on disk) exactly:

- Same foundation and goal, copied verbatim from the June project's `state.json`:
  corporate thriller, junior-data-analyst-discovers-heist premise, and the same
  user-specified primary goal ("Expose the corporate data heist before the merger
  closes and the evidence is buried").
- Same config: `claude-cli` backend, `haiku`, timeout 300, `target_story_length: 15`,
  default tension curve (`[[0,3],[0.25,5],[0.5,6],[0.75,8],[0.9,9],[1.0,4]]`),
  throughline pressure and LLM goal relevance on.
- Same length: 16 scenes (ticks 0 through 15), ~27.6k words (June: ~28.7k).
- Only deliberate difference: the arc-phase mandate code now exists and is on by
  default. With length 15 and the default curve the derived phases are: rising for
  ticks 0-12, peak at tick 13 (target 8.8), resolution at ticks 14 (target 7.3) and
  15 (target 4.0).

Reliability: 16/16 ticks completed. One transient `claude-cli` failure on tick 5's
writer call ("Unknown error"); the in-run retry (`--retries 2`) recovered it on the
first attempt. The harness also killed the `novel run` process once between ticks 12
and 13 (an environment lifetime limit, not a StoryDaemon failure); resuming with
`novel run --n 3` picked up cleanly from disk, re-confirming the stateless-tick
architecture noted in June.

## 2. Side-by-side: June control vs. mandate-on

Mean `|tension - target|` per derived arc phase (June's metrics predate the
`arc_phase` field, so its phases are derived from the same curve/length):

| metric | June (control) | July (mandate on) |
|---|---|---|
| overall drift, all scored ticks | **1.20** | 1.55 |
| overall bias (signed) | +0.75 | +0.55 |
| rising drift (ticks 0-12) | **0.96** | 1.51 |
| peak drift (tick 13) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8) |
| resolution drift (ticks 14-15) | 2.35 | **1.65** |
| final scene: target 4.0, actual | **8** | **6** |
| final-scene event kind | still the climax ("90 minutes to a critical statement") | aftermath (fallout of an exposure that already happened) |
| futile-rewrite skip | n/a (feature didn't exist); tick 15 wasted a failed rewrite | fired once (tick 1: 7 vs 3.5, both revision calls saved) |

Per-tick trace (July run, from `memory/metrics.jsonl`):

| tick | target | actual | phase | rewrite |
|---|---|---|---|---|
| 0 | 3.0 | (not scored) | rising | |
| 1 | 3.5 | 7 | rising | skipped as futile (drop >= 3) |
| 2 | 4.1 | 7 | rising | tried, not closer, kept original |
| 3 | 4.6 | 6 | rising | |
| 4 | 5.1 | 7 | rising | |
| 5 | 5.3 | 7 | rising | 8 -> 7 |
| 6 | 5.6 | 7 | rising | |
| 7 | 5.9 | 5 | rising | 8 -> 5 |
| 8 | 6.3 | 7 | rising | |
| 9 | 6.8 | 7 | rising | |
| 10 | 7.3 | 7 | rising | |
| 11 | 7.9 | 6 | rising | |
| 12 | 8.3 | 7 | rising | |
| 13 | 8.8 | 7 | peak | 6 -> 7 (upward) |
| 14 | 7.3 | 6 | resolution | |
| 15 | 4.0 | 6 | resolution | |

## 3. What the mandate fixed: the planner now chooses aftermath events

The June diagnosis was that the floor is the *planner*: it kept scheduling tense events
(a discovery, a confrontation) at a low target because it read the number as "how tense
should the prose feel," not as an arc position. The mandate attacks exactly that, and
the planner's own scene intentions show it worked:

- Tick 13 (peak, mandated "confront"): "discovered by corporate security... forcing an
  immediate, irreversible choice between public exposure and consequences." A genuine
  climax event, on schedule.
- Tick 14 (resolution): "faces the final fallout of the exposure... accept the
  irreversible consequences of being right."
- Tick 15 (resolution): "the heist's exposure forces the merger to collapse, but
  Elaraene must confront the personal and professional fallout of being the
  whistleblower everyone now knows about."

The prose matches the intentions. Scene 14 is a quiet patrol-car transfer to a safe
house (stillness, protective custody, a briefing). Scene 15 ("The Exposure") is pure
aftermath: the protagonist wakes *after* the exposure has landed, her name leaks in a
court filing, the stock collapses, colleagues turn on her, and the scene closes on cost
and reflection ("she had exposed the truth. The truth was now destroying everything,
including her"). No violence, no ticking clock, no new antagonist move. Contrast June's
final scene, which was still mid-climax (guarded underground, formal statement in 90
minutes). The founding thesis holds in both directions: tension lives in the events,
and changing the mandated *event kind* moved it where four weeks of prose-level
pressure could not.

The `rewrite_futile` skip also behaved as designed: at tick 1 (scored 7 against target
3.5) it recognized a drop too big for a prose rewrite and skipped the revision pass,
saving two LLM calls that June's equivalent tick spent on a rewrite that failed anyway.

## 4. What is still off

- **The ending is subdued, not calm (6 vs 4).** The scorer is being fair: scene 15's
  *events* are consequence events, but they are big ones (identity exposed nationally,
  an FBI interview pending, a company collapsing). "Aftermath of a corporate scandal"
  has an intrinsic tension floor around 6 when it happens on-page the morning after the
  peak. The residual gap looks like *runway*, not defiance: the curve gives exactly one
  tick at 7.3 and one at 4.0 to descend from a 8.8 peak. A denouement at 4 probably
  needs either a longer resolution tail on the curve or a time-skip big enough to make
  the fallout old news, which the mandate permits but does not force.
- **The resolution mandate's "close open loops" clause did not bite.** Ticks 14-15
  opened 3 and 5 new loops respectively and closed none (36 -> 41 open). The planner
  de-escalated events but kept planting threads. This is the loop-aging gap already on
  the Phase 3 list; the mandate text alone does not close loops.
- **Rising drift regressed (0.96 -> 1.51), driven by a very hot start.** Ticks 1-2
  scored 7 against targets of 3.5/4.1. Plausibly the "RISING: escalate, sharpen a
  complication" mandate amplifies the thriller generator's existing hot bias exactly
  where the targets are gentle; also this is n=1 per arm, so single-run variance is in
  play. Worth watching, and possibly worth softening the rising mandate at low targets
  (the phase mandate could defer to the band directive when the target is below 5).
- **The peak undershot (7 vs 8.8) in both runs.** The LLM scorer appears reluctant to
  grant 8+; the upward rewrite (6 -> 7) helped but could not reach the band. Less
  important than the descent, but it means the measured arc is flatter than the target
  arc at both ends.

## 5. Verdict and next step

The June failure mode ("at the final scene the planner was still writing the climax")
is gone: phase-mandated event selection works, and it, not a stronger rewrite, was the
right lever. Remaining work to actually land a calm ending, in order of expected value:

1. **Give the descent more runway**: default curve or docs guidance putting 2-3 ticks
   of tail after the peak (e.g. a control point near `[0.85, 9]` then `[1.0, 3]` with a
   longer `target_story_length`), and/or have the resolution mandate explicitly demand
   a substantial time-skip when the previous scene scored >= 6.
2. **Loop-aging** (already planned): resolution scenes that open five new loops are not
   winding down, whatever their tension score.
3. Re-examine the rising mandate at low targets, after another run or two establishes
   whether the hot start was variance or a real interaction.

## Artifacts

- Treatment run (gitignored `work/`): `work/novels/descent2_36ea1526/` (manuscript
  scenes in `scenes/`, per-tick rubric in `memory/metrics.jsonl` including the new
  `arc_phase` field, planner snapshots in `plans/`).
- Control run preserved from June: `work/novels/descent_efa72af8/`.
- June baseline numbers recomputed from its `metrics.jsonl` with phases derived from
  the same curve, so both columns in section 2 are measured identically.
