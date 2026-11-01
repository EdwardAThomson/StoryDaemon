# DSL Validation, 2026-10-31: Skeletons, Sectioned Writing, Contracts on gpt-5.6-luna

**Status:** complete for the Luna half of the plan; the Terra half was cancelled on purpose (section 7).
**Code:** branch `claude/project-thread-oqxwxt`, from PR #22's branch (the Luna fixes). Harness in `experiments/dsl_validation/`, raw judge outputs in `experiments/dsl_validation/results/`. The novels themselves are under the gitignored `work/dsl/`.
**Cost:** $2.25 of writing, $2.35 on the first judge, $0.75 on the second. About $5.35 in all.
**Plan:** the Claude Doc "StoryDaemon DSL validation plan" (project thread), which also holds the judge v2 rubric.

## 1. The one-paragraph version

The scene skeleton does what it claims. Judged against the register it is meant to produce, skeleton scenes score 3.0 to 3.4 out of 5 where unguided Luna scores 2.0 on every scene and corpus chapters score 4.25. Craft scores barely move between arms. The remaining gap is a single prompt rule, one speaker per DIALOGUE item, holding on one premise (98%) and not the other (77%). Sectioned writing reaches chapter length but loses every blind comparison and leaks seams; leave it off. Contracts ran 58 checks and failed none, so they constrained nothing. And the first judge we used was asked the wrong question: with no target it rated by modern taste and preferred unguided 29 to 3, a number that says nothing about the DSL. The second judge, which knows the target, reverses it.

## 2. Setup

- One writer model for every role: `openrouter:openai/gpt-5.6-luna` (1.5¢ a tick). Every default on, plus the switch under test.
- Two premises: the 1871 survey brig Alcyone (the July premise, so results compare) and the ore hauler thriller from the model comparison.
- Experiment 1, skeletons: `enable_scene_skeleton` off vs on, 8 ticks per cell, 32 scenes.
- Experiment 2, sectioned writing: `scene_length_preset: masters`, skeleton on in both, single-shot vs `subblock_generation`, 6 ticks per cell. Run twice: before and after the fix in section 6.
- Experiment 3, contracts: plot-first on in both, `use_contracts` off vs on, 15 ticks per cell.
- 14 cells, 118 ticks, 118 completed, none failed.
- Cost was logged per call from OpenRouter's `usage.cost` (`run_cell.py`).

## 3. The two judges

**Judge v1** (`judge.py`): Sonnet 5.5 shown two matched scenes and asked which is better on "prose quality, scene craft, dialogue, and how well paragraphing serves the reading", both orders. It preferred unguided over skeleton 29 to 3 (15 of 16 pairs consistent across orders), and single-shot over sectioned 24 to 0. Its reasons named the same faults every time: dialogue packed into dense paragraphs, exposition dumps, against the short modern paragraphs of the unguided arm. With both scenes mechanically re-paragraphed into equal groups of sentences so the judge could not see paragraphing, unguided still won, 20 to 12.

Why that number is not a verdict: the skeleton exists to move the writer from its native modern register to the masters' register (`SLICE4_SCENE_SKELETON_RESULTS.md` section 5 said exactly this in July). A judge with no target scores against its own taste, and its taste is modern. Judging a Victorian page blind by today's standard marks it down for being Victorian.

**Judge v2** (`judge_v2.py`) scores each scene alone, with the target stated first, in three parts. Register fit, 1 to 5 with anchors, plus the worst lapse quoted and classed as fragmented, packed, exposition or none. Five craft scores that ignore paragraph style: movement, voices, subtext, economy, grounding. Plan adherence for skeleton scenes: mode match per paragraph (a Haiku labelling pass), one speaker per DIALOGUE item (quote spans, Python) and words in the mode's measured range (Python). The rubric is in the plan doc.

Calibration: one chapter each from Pride and Prejudice, Jane Eyre, The Moonstone and Lord Jim (all in the 21-book corpus) scored 4, 5, 4, 4 on register fit, and the unguided Luna scenes scored 2, so the judge reads the dial. Two caveats. The judge recognised the authors, so the corpus scores may owe something to recognition; it cannot recognise generated scenes, so the arm comparison is unaffected, but the calibration is weaker than it looks. And its "lapses" on the corpus are things the masters do (Miss Bingley's long speech, a run of one-word exchanges in Collins), so 4 is the realistic ceiling for a scene.

The judge has a spend cap, a call cap, clean Ctrl-C, a per-call cache and resume, exercised with a fake judge before any real call.

## 4. Experiment 1: scene skeletons

### Register fit (judge v2, 1 to 5)

| cell | mean | scores | lapses |
|---|---:|---|---|
| corpus chapters (4) | 4.25 | 4 4 4 5 | packed 2, fragmented 1, none 1 |
| Alcyone, skeleton off | 2.00 | 2 2 2 2 2 2 2 2 | fragmented 8 |
| Alcyone, skeleton on | 3.00 | 2 4 3 4 2 2 3 4 | packed 5, exposition 3 |
| ore hauler, skeleton off | 2.00 | 2 2 2 2 2 2 2 2 | fragmented 8 |
| ore hauler, skeleton on | 3.38 | 4 3 4 4 3 3 3 3 | packed 3, exposition 3, fragmented 2 |

Every unguided scene is a 2 for the same reason, fragmentation: 135 paragraphs of 13 words per scene, dialogue paragraphs of 7 words. The skeleton halves the gap to the corpus. Its lapses are the two things the plan is supposed to prevent, packed dialogue and standalone exposition, which is where the next work is.

### Craft (judge v2, 1 to 5)

| cell | movement | voices | subtext | economy | grounding |
|---|---:|---:|---:|---:|---:|
| corpus chapters | 4.25 | 4.50 | 3.75 | 3.00 | 3.75 |
| Alcyone, off | 4.00 | 2.62 | 3.62 | 2.75 | 4.25 |
| Alcyone, on | 3.75 | 2.12 | 2.50 | 2.50 | 3.88 |
| ore hauler, off | 3.50 | 2.00 | 2.12 | 2.38 | 3.75 |
| ore hauler, on | 3.25 | 2.00 | 2.25 | 2.25 | 3.50 |

Both arms sit in the same band. Skeleton scenes run a little lower on subtext and economy (the skeleton's talk is more on the nose, which v1 also said), and both arms are far below the corpus on voices (2 against 4.5), which is a Luna trait and not a DSL effect. Register moved by 1 to 1.4 points for a craft cost of about 0.3.

### Plan adherence (the mechanism)

| cell | mode match | words in range | one speaker per DIALOGUE item | marker compliance |
|---|---:|---:|---:|---:|
| Alcyone, on | 0.82 | 0.83 | **0.77** | 6 of 8 |
| ore hauler, on | 0.89 | 0.88 | 0.98 | 6 of 8 |

Same prompt, same rules, two premises: the one-turn rule holds on the ore hauler and fails on Alcyone, where 20 dialogue paragraphs hold three or more quoted speeches (a quote-span count: `quote_spans >= 3`). That is the whole of the Alcyone register gap. The September dialogue fix (one turn per item, per-item word ranges) therefore works in principle and is not yet reliable. Word ranges miss mostly on DIALOGUE, in both directions.

### Structure and surface

Paragraph size moved from 13 words (off) to 49 to 57 (on), against the corpus's 59.8 mean, and this time without the July overshoot to 101. Scene length fell from 1,760 to 1,880 words (off, 25 to 35% over the 1,400 target) to 1,220 to 1,510 (on). Skeleton scenes cost 15% less per tick.

### Selective tension revision (read from these runs)

The whole-scene rewrite fired on 4 of 16 unguided scenes and moved the shared-judge tension by 1 to 2 points each time; the selective revision fired on 1 of 16 skeleton scenes and moved it by 1. Too few events to say more than that it fires rarely and does no visible harm to compliance.

## 5. Experiment 2: sectioned writing

| cell | words per scene | sectioned | cost per scene | length cut-offs |
|---|---:|---:|---:|---:|
| Alcyone, single-shot | 2,626 | 0 of 6 | 1.6¢ | 0 |
| Alcyone, sectioned (fixed) | 3,205 | 6 of 6 | 3.1¢ | 8 |
| ore hauler, single-shot | 2,714 | 0 of 6 | 1.8¢ | 3 |
| ore hauler, sectioned (fixed) | 2,971 | 6 of 6 | 3.2¢ | 8 |

It reaches the masters' chapter length (3,165 median) where single-shot lands 15% short, at twice the cost. Judge v1 preferred single-shot 24 to 0, and the seam judge (300 words either side of each join, versus windows with no join from the single-shot arm) detected a join 7 times in 52 against 1 in 50, with continuity 3.37 against 3.75. The sectioned scenes also carried stray `[11]`-style plan markers in the prose until the fix in section 6. Register fit was not re-scored for this experiment. Verdict: leave it off. The chapter-length case it was built for is real, but this is not yet the way to get there.

## 6. Two bugs fixed on the way

Both in `writer.py:_write_in_sections`, both found by the fallback printing to the console as designed:

1. **Empty section on a reasoning model.** Luna spent a section's whole token ceiling on reasoning and returned nothing with `finish_reason == "length"`. The retry reused the same budget, reproduced it, and the fallback threw away every section already written. The retry now doubles the budget when the empty response was cut off (the planner's existing rule). 15 of 67 Luna sections stopped on length.
2. **Markers leaking at the joins.** A section cut off mid-sentence was joined inline to the next, whose opening `[n]` marker then sat mid-paragraph where the line-anchored stripper could not see it. A cut-off section is now trimmed to its last whole sentence and every section starts a new paragraph; `sections_trimmed` is recorded on the scene.

Tests: `tests/unit/test_sectioned_writing.py` (25).

## 7. Experiment 3: contracts

| cell | beats | completed | pending | postconditions checked | failed | premise event staged |
|---|---:|---:|---:|---:|---:|---|
| Alcyone, off | 14 | 13 | 1 | 0 | 0 | no |
| Alcyone, on | 14 | 13 | 1 | 32 | 0 | yes (scene 10: a Meridian signal cloth) |
| ore hauler, off | 18 | 13 | 5 | 0 | 0 | no |
| ore hauler, on | 17 | 13 | 4 | 26 | 0 | no |

Fifty-eight postconditions, zero failures, so the contracts never constrained anything: the authored checks were `char_in_prose` on the beat's characters and `tension_at_most 6`, which a scene passes by existing. No beat wedged (the July failure), and completion was identical with and without. The premise-event gauge (one judge call over the scene summaries: did the premise's key event happen on the page?) fired in 1 of 4 plot-first cells and 0 of 10 reactive cells; the captain's murder in the ore hauler premise never happened in any of 7 ore hauler runs. Verdict: nothing learned about contracts either way; the authored vocabulary is too easy, and the thing worth checking (did the event occur) is the `event_occurs` judge Slice 3 proposes.

## 8. What was stopped, and why

The plan had a Terra arm (about $13). It was cancelled when the v1 results came in, on the rule that a failing result is not rescued by scaling it up. That turned out right for the wrong reason: the result was not failing, the judge was. The Terra question (does the DSL help a strong writer as well as a cheap one) is still open and still worth about $13 when wanted. The judge v2 run was approved in two small steps, a 4-scene test for 8¢ and the calibration for 11¢, before the full 56¢.

## 9. Next steps, in order

1. Make the one-turn rule hold. It is honoured 98% on one premise and 77% on the other with the same prompt, so the fix is likely structural rather than wording: enforce it in code the way marker compliance is enforced (split a DIALOGUE paragraph at a speaker change, or reject and re-ask for that item), since prompt rules proved unreliable here exactly as they did for the markers in Gate B.
2. Standalone exposition is the other named lapse (6 of 16). The plan carries LORE items; check whether the lapses sit on them.
3. Re-run judge v2 on the sectioned scenes before deciding whether their seam problem survives the fixes in section 6 (the fixed cells were written but not register-scored).
4. Adopt judge v2 as the DSL's gauge going forward, and retire pairwise-preference judging without a stated target for any register question.
5. Terra, when the budget allows.
