# Loop-aging: the corpus baseline

Status: **the gauge shipped 2026-09-23** (Phase 3, loop-aging Slice L1). No
pressure is applied to planning yet, and this document is the measurement that
the pressure slice has to be designed against.
Code: `novel_agent/agent/loop_aging.py`, script `scripts/loop_age_tables.py`,
command `novel loops`.

Regenerate every number below with:

```bash
venv/bin/python scripts/loop_age_tables.py
venv/bin/python scripts/loop_age_tables.py --sample 60 --seed 7   # the labelling sample
```

The tables here were computed over the 26 novels in `work/novels/` that predate
this slice (1,548 loops with a birth scene). Re-running the script now also
picks up `loopage_a8ae7cc3`, this slice's own live check, so it reports 27 novels
and 1,553 loops.

## What the corpus says

| novel | ticks | loops | closed | unresolved | median age at close | median age unresolved |
|---|---|---|---|---|---|---|
| abtest_off_50c2e918 | 4 | 8 | 2 | 6 | 2.5 | 1.0 |
| abtest_on_ef3513e3 | 3 | 3 | 0 | 3 | | 2 |
| claudetest_e6ae3d40 | 20 | 61 | 1 | 60 | 3 | 9.0 |
| contracts-smoke_f22e5541 | 8 | 41 | 3 | 38 | 2 | 3.0 |
| descent-pf2_ddd9d9de | 16 | 64 | 0 | 64 | | 8.5 |
| descent-pf_651113b3 | 16 | 70 | 0 | 70 | | 10.0 |
| descent-run3_8e35c9d2 | 16 | 72 | 0 | 72 | | 9.0 |
| descent-run4_b724fd32 | 16 | 79 | 1 | 78 | 8 | 7.0 |
| descent-run5_aba39b4f | 16 | 78 | 4 | 74 | 4.0 | 7.5 |
| descent2_36ea1526 | 16 | 60 | 19 | 41 | 2 | 6 |
| descent_efa72af8 | 16 | 76 | 12 | 64 | 1.5 | 5.0 |
| fork-calm-a | 17 | 64 | 0 | 64 | | 9.5 |
| fork-calm-b | 17 | 64 | 0 | 64 | | 9.5 |
| grantrate-run_39a993f0 | 16 | 55 | 9 | 46 | 5 | 7.5 |
| new-scifi-hacker_8a1605f9 | 72 | 108 | 87 | 21 | 2 | 39 |
| new-space-opera_ddfb1438 | 2 | 4 | 1 | 3 | 1 | 1 |
| sci-fi-hacker_6d205100 | 12 | 17 | 12 | 5 | 1.0 | 9 |
| slice0-run2_fe1dd201 | 16 | 50 | 50 | 0 | 8.5 | |
| slice0-run_a9f9b801 | 6 | 24 | 0 | 24 | | 2.5 |
| sunshine-a | 17 | 83 | 1 | 82 | 8 | 8.0 |
| sunshine-b | 17 | 82 | 1 | 81 | 8 | 8 |
| sunshine-c | 17 | 84 | 1 | 83 | 8 | 8 |
| sunshine-d | 17 | 83 | 1 | 82 | 8 | 8.0 |
| sunshine-e | 17 | 84 | 1 | 83 | 8 | 8 |
| sunshine-master | 16 | 79 | 1 | 78 | 8 | 7.0 |
| triple-run_ec75ee96 | 16 | 55 | 13 | 42 | 5 | 6.5 |

**Ever closed: 220 of 1,548 (14%).** Median age at close 3 ticks, max 25.
Closure is near-immediate or never:

| closed within | count | share of all closures |
|---|---|---|
| 1 tick | 66 | 30% |
| 2 ticks | 108 | 49% |
| 3 ticks | 131 | 60% |

**Left unresolved: 1,328.** Median age 7 ticks, max 71, and 131 of them were 15
or more ticks old when the story ended. Five `sunshine` runs each ended with 82
open loops and exactly one closure.

Creation hygiene does not fix this. The three runs with loop dedup and the
creation cap live (`grantrate-run`, `triple-run`, `slice0-run2`) opened 55, 55
and 50 loops against 9, 13 and 50 closures, and their "0 open at end" is the
finale expiry sweep, not payoff.

`scenes_mentioned` is non-zero on **0 of 1,548** loops, because nothing writes
it. See "Known defects this slice did not fix".

## The five kinds of loop

The closure rate alone suggests a payoff pressure. Reading the loops says
something more specific: most of the registry is not story debt, and a pressure
aimed at the whole ledger would be aimed mostly at noise. Five kinds, with the
audit questions answered for each.

### 1. Scene-local suspense (31% by the classifier)

> "Will security personnel intercept Vela before she leaves the building, or has
> she escaped the immediate threat?"

521 of the 1,548 are either/or questions, 209 of those begin "Will", and 219
carry their own deadline in the text ("before she leaves", "within 90 seconds",
"tomorrow", "72 hours").

- **Why is it open?** Nothing ever announces its answer on the page. The story
  simply moves past it, and the closure judge correctly refuses to close a
  question no scene answered.
- **Is it reasonable for it to stay open?** No. It is not debt. It is a sentence
  of suspense that was already spent.
- **Should it ever be closed?** It should never have been registered. Failing
  that it should go stale, not resolve.
- **When ideally?** Within a tick or two, and by expiry rather than by payoff.

### 2. The throughline, restated (4%)

> "What is the full scope of the conspiracy, and how many executives are
> involved?"

55 loops take this shape, and one novel (`sunshine-master`) holds four
near-copies of it: OL8, OL16, OL36, OL63.

- **Why is it open?** Because it is supposed to be. The defect is that it is
  registered as a peer of every other loop instead of as
  `state.story_goals.primary`.
- **Reasonable to stay open?** Yes, to the last page.
- **Should it close?** Exactly once, at the finale.
- **When ideally?** At the finale, and a payoff pressure must exempt it.

### 3. Genuine arc loops (65%)

> "What were the three redacted entries in the March 8th data export, and why
> were they deleted without logging?"
> "Who is the person on the unredacted files list that Vela knows?"

- **Why is it open?** Nothing pressures the planner toward it, and the planner's
  own loop selector hides it: `_filter_relevant_loops` ranks by word overlap
  with the scene intention the planner just wrote, and a loop is old precisely
  because the recent prose stopped mentioning it.
- **Reasonable to stay open?** For a while. That is what a loop is for.
- **Should it close?** Yes. This is the only kind a payoff pressure should ever
  point at.
- **When ideally?** The corpus shows the pipeline can pay these off when it
  engages at all, since 60% of all closures land within three ticks of birth. So
  the window is real: opened in setup, paid by late-rising or resolution phase.
  The shipped threshold is 0.3 of `coherence.target_story_length`, which falls
  between what the pipeline manages (median 3 ticks, 0.19 of a 16-tick run) and
  what it abandons (median 7, 0.44).

### 4. POV-asymmetric questions (not separately counted)

`sunshine-master` S008 is a surveillance and audit POV scene, and it minted six
loops (OL38 to OL43) asking what Vela did at the internet cafe, which the reader
had watched her do three scenes earlier. The fact extractor reads one scene, not
the book, so it registers a question that is open to a character and closed to
the reader.

- **Why is it open?** It was never a reader-facing question.
- **Reasonable? Should it close? When?** No, no, and never. It should not be
  minted. Loops are reader-facing debt by definition.

### 5. Reworded restatements (largely solved)

In one run S009 and S010 minted the same five questions: OL47/OL53 are
byte-identical, OL46/OL51 sit at 0.96, OL48/OL50 at 0.94, OL44/OL49 at 0.92.

That run is dated one day before loop dedup shipped, and every one of those
pairs is above the shipped 0.75 threshold, so they would be caught today.
Corpus-wide the residual restatement rate is 5% at 0.75 and 3% at 0.8, measured
as `max(plain, sorted-token)` difflib ratio (the beat-dedup gauge). This kind
needs no further work.

## Importance is a dead signal

| importance | count |
|---|---|
| critical | 967 |
| high | 554 |
| medium | 27 |
| low | 0 |

62% of every loop ever minted is "critical" and none is "low". Importance cannot
rank anything, which is why the gauge keys on age. It was also sorted wrongly
wherever it was read: see the repairs below.

## Classifier validation

The horizon classifier is deterministic and free, which is exactly why its
accuracy has to be published rather than assumed. This project has twice
replaced a crude gauge (the keyword tension heuristic, the embedding
goal-relevance metric) with an anchored LLM judge, and the rule that came out of
it is to ship the gauge before the pressure and to know how good the gauge is.

Method: 60 loops, stratified 20/20/20 by the classifier's own verdict, sampled
with `--sample 60 --seed 7`, hand-labelled against the reader-facing definitions
above.

**Agreement: 42 of 60 (70%).** Per class:

| classifier said | n | agreed | precision |
|---|---|---|---|
| arc | 20 | 18 | 90% |
| scene | 20 | 12 | 60% |
| throughline | 20 | 12 | 60% |

The 18 disagreements, by cause:

| cause | n | example |
|---|---|---|
| Throughline idiom fires inside a local question | 8 | "What is the **true purpose** of Galen's 72-hour detention?" is one detention, not the story's question |
| Either/or fires on a long-horizon binary or a noun disjunction | 6 | "Will the cooperation agreement protect him, **or** will the company eliminate him despite federal custody?" runs the length of the book; "compromise Tyrux's position **or** objectives?" is not a choice at all |
| Deadline word is a past or framing adverb | 2 | "Why did Zeloth remove a file **immediately after** Aris accessed the partition?" |
| A scene-local choice filed as arc | 2 | "Will Galen attempt to contact Vela despite the restrictions?" is settled by the next scene |

Two things follow, and both matter for the pressure slice.

**The errors are directional.** Sixteen of the eighteen over-claim `scene` or
`throughline`, and both of those horizons are **exempt from overdue
accounting**. So `loop_overdue_total` is a *floor* on the real debt, never an
overstatement. A pressure built on it will under-fire rather than over-fire,
which is the safe direction for a first pressure but means the measured debt
should be read as conservative.

**The throughline horizon cannot be identified reliably yet, for a structural
reason.** The classifier has two throughline tests: similarity to
`state.story_goals.primary`, which is the sound one, and a list of idioms, which
is the guess. Almost no run in the corpus has a primary goal set, because the
only automatic path to one (`_check_goal_promotion`) can never fire. So the
idiom branch is carrying the whole test. Wiring goal promotion would improve
this gauge as a side effect, which is an argument for doing it in L2.

## What Slice L1 records

Per tick in `memory/metrics.jsonl`:

`loop_oldest_age`, `loop_oldest_id`, `loop_median_age`, `loop_overdue_total`,
`loop_overdue_ids`, `loop_stale_threshold`, `loop_horizon_counts`,
`loop_shown_total`, `loop_shown_oldest_age`, `loop_unshown_oldest_age`,
`loop_shown`.

**The decisive pair is `loop_shown_oldest_age` against
`loop_unshown_oldest_age`.** If the loops the planner never sees are
systematically older, the pressure is a selection change in
`_filter_relevant_loops`. If the old loops are already on the page and ignored,
the pressure is a mandate. Until this series exists for a full run, that choice
would be a guess.

Live check (`loopage_a8ae7cc3`, two ticks, 2026-09-23): the block is present on
both ticks including tick 0, `created_tick` and `horizon` are stamped at
creation, and `loop_ids_shown` is populated on tick 1 and empty on tick 0, which
is correct because `_first_tick` never runs the planner.

## Known defects this slice did not fix

- **`scenes_mentioned` and `last_mentioned_tick` are never written.** They are
  read in three places and written in none, so both are 0/None on all 1,548
  loops. The consequence is that `_check_goal_promotion` (`agent/agent.py`,
  ticks 10 to 15, requires 5 or more mentions) **can never fire**, and
  `novel goals` always prints "Mentioned in 0 scenes". Left alone deliberately:
  L1 records loop *exposure* to the planner instead, which is free and exact,
  and the mention signal needs a decision about its source (beat
  `advances_loops` claims, which exist only in plot-first mode, versus a new
  `loops_addressed` field on the tactical plan, which costs planner budget).
- **`_filter_relevant_loops` is untouched**, including its
  `TODO: Use proper embedding similarity`. Embeddings would sharpen its bias
  against old loops rather than fix it, and changing it at all is pressure, not
  instrumentation.

## Repaired here

`context.py:_format_open_loops` sorted `importance` as a raw string with
`reverse=True`, which orders medium, low, high, critical, so **the critical
loops sorted last** in the only place the planner sees the full ledger. It also
chose its status marker by testing `loop.status` against `"urgent"` and
`"active"`, neither of which is a valid `OpenLoop` status, so every loop
rendered identically. Both are fixed: an explicit rank map, age as the
tie-break, the age shown on the line, and the marker now carrying whether an arc
loop is overdue.

## The fork for the pressure slice (L2)

Two candidates, and the instrument above is what should decide between them
rather than taste.

1. **Payoff pressure.** Age-weighted selection into the planner context, an
   explicit overdue-loops section naming one or two, scaled by
   `arc_pressure.compute_arc_phase` so it does not demand payoff during setup
   and fight the shipped arc-phase mandate. `scene`-horizon loops must expire
   rather than generate pressure.
2. **Creation-side hygiene.** Stop minting scene-local suspense and
   POV-asymmetric questions at all, which is a fact-extractor prompt change
   plus a horizon filter at creation. If a third of the ledger is questions the
   prose already walked past, this may buy more than any pressure, and it is
   cheaper.

They are not exclusive, and the numbers to look at first are
`loop_shown_oldest_age` vs `loop_unshown_oldest_age` (does the planner even see
the debt) and the `loop_horizon_counts` series on a full 16-tick run with the
gauge live from tick 0.
