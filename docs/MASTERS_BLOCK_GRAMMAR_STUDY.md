# Masters Block Grammar Study: Ordering Rules and a Layered Design for the Block DSL

**Status:** Offline corpus analysis, complete (no pipeline code changes)
**Date:** 2026-07-14
**Serves:** the block/sub-block DSL (`DSL_and_contracts.md`, `BLOCKS_CONTRACTS_LANDING_SKETCH.md` Slice 4 scene skeletons) and the thread interleaving design (`THREAD_INTERLEAVING_DESIGN.md`)
**Extends:** `BLOCK_DECOMPOSITION_STUDY.md` (the 2-master pilot) from ~1k sampled paragraphs to 38,495 paragraphs across 21 complete masterworks
**Data:** nd1 block-rhythm sidecars under `work/corpus/scores/nd1_ab/deepseek/` (DeepSeek judge, produced by the analyzer repo's `narrative_dynamics` benchmark)
**Regeneration:** every table below is printed by `python scripts/block_grammar_tables.py` (no LLM calls; add `--include-giants` once the giant runs are folded in)

---

## 1. Motivation

The DSL composes stories from typed blocks, and the ordering of blocks is the
open design question. Rather than invent ordering rules, this study measures
them: across 21 canonical novels (the masters corpus), what block follows what
block, what opens and closes a chapter, how long blocks run, how the mix shifts
with position and tension, and, critically, what evidence exists for structure
*above* the block level. The headline result is a concrete argument for a
hierarchical (block within scene within chapter within book) design, plus the
measured matrices to seed it.

Scope and caveats up front:

- 21 books, 38,495 judged paragraphs, 37,836 within-chapter adjacent pairs.
  The five giants are excluded here to match the masters corpus report scope
  (two of them are judged and can be folded in via `--include-giants`).
- One paragraph = one block, labeled with the 7-type rubric from
  `BLOCK_DECOMPOSITION_STUDY.md` (primary mode + optional secondary shading).
- Single LLM judge (DeepSeek, validated against Haiku on tension only);
  paragraph classification carries noise.
- The corpus is dialogue-heavy Victorian/Edwardian fiction (dialogue share
  26-68% by book). Genre-conditioned variants of every table are desirable
  once the corpus grows; for now treat these as the pooled register.
- Transitions never cross chapter boundaries (by construction of the data),
  which is why chapter boundary behaviour is measured separately (Section 4).

## 2. Vocabulary recap

Seven primary modes (full rubric in `BLOCK_DECOMPOSITION_STUDY.md` and
`benchmarks/narrative_dynamics/rubrics/block_types.py` in the analyzer repo):
SETTING, CHARACTER_DESC, LORE, DIALOGUE, ACTION, INTERIORITY, TRANSITION.

The pilot's carrier/texture split holds at full-corpus scale and matters for
the DSL design below:

- **Carrier modes** (DIALOGUE, ACTION, INTERIORITY): form runs, drive scenes,
  close chapters.
- **Texture modes** (SETTING, CHARACTER_DESC, LORE): median run length 1,
  frequently appear as secondary shading, open chapters.

## 3. The block transition matrix (the ordering grammar)

P(next block | current block), pooled over all within-chapter adjacent
paragraph pairs. Rows are the current block, columns the next.

| from \ to | SET | CHR | LOR | DLG | ACT | INT | TRN | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SETTING | 0.190 | 0.064 | 0.053 | 0.238 | 0.324 | 0.121 | 0.009 | 1,523 |
| CHARACTER_DESC | 0.027 | 0.098 | 0.045 | 0.537 | 0.188 | 0.089 | 0.015 | 1,102 |
| LORE | 0.063 | 0.042 | 0.382 | 0.160 | 0.219 | 0.118 | 0.017 | 1,258 |
| DIALOGUE | 0.013 | 0.021 | 0.008 | 0.704 | 0.185 | 0.066 | 0.003 | 21,584 |
| ACTION | 0.062 | 0.031 | 0.025 | 0.477 | 0.305 | 0.083 | 0.018 | 8,694 |
| INTERIORITY | 0.046 | 0.029 | 0.038 | 0.359 | 0.300 | 0.205 | 0.024 | 3,243 |
| TRANSITION | 0.130 | 0.012 | 0.093 | 0.123 | 0.428 | 0.148 | 0.067 | 432 |

Read a row as a weighted grammar production: after a CHARACTER_DESC block,
emit DIALOGUE with probability 0.54. The idioms worth encoding:

- **CHARACTER_DESC -> DIALOGUE (0.54):** introduce a character, then let them
  speak. The strongest single idiom in the matrix.
- **SETTING -> ACTION (0.32) / DIALOGUE (0.24):** setting is a springboard,
  not a destination.
- **INTERIORITY -> DIALOGUE (0.36) / ACTION (0.30):** thought resolves outward
  into speech or event; interiority self-chains only 0.205.
- **ACTION -> DIALOGUE (0.48):** action beats alternate with talk rather than
  compounding.
- **DIALOGUE is the only sticky mode** (self-transition 0.70). **LORE is the
  licensed clumper** (self-transition 0.38, max run 76): exposition may run
  long, but per Section 6 it does so mostly at the book's ends.

## 4. Chapter boundary grammar

Chapter openings and closings differ sharply from the running mix. Base rate
is each mode's overall share of paragraphs.

| mode | base rate | opens chapter | closes chapter |
|---|---:|---:|---:|
| SETTING | 0.041 | 0.238 | 0.073 |
| CHARACTER_DESC | 0.029 | 0.052 | 0.020 |
| LORE | 0.034 | 0.187 | 0.052 |
| DIALOGUE | 0.565 | 0.052 | 0.238 |
| ACTION | 0.232 | 0.234 | 0.367 |
| INTERIORITY | 0.088 | 0.131 | 0.209 |
| TRANSITION | 0.012 | 0.108 | 0.041 |

Two rules the data supports directly:

- **Open by orienting.** SETTING, ACTION, LORE, and INTERIORITY open chapters;
  DIALOGUE opens only 5.2% of them, a 10x suppression against its base rate.
  Masters almost never open a chapter in mid-conversation.
- **Close on event or reflection.** ACTION (1.6x base) and INTERIORITY (2.4x
  base) are over-represented at chapter ends; SETTING and LORE nearly vanish.

These are exactly the entry/exit vectors the Slice 4 scene skeleton can use
today, independent of everything else in this doc.

## 5. Run lengths are memoryless at block level

Observed run lengths match the geometric distribution implied by each mode's
self-transition probability almost exactly:

| mode | mean | geometric-implied mean | median | p90 | max | runs |
|---|---:|---:|---:|---:|---:|---:|
| SETTING | 1.23 | 1.23 | 1 | 2 | 8 | 1,282 |
| CHARACTER_DESC | 1.11 | 1.11 | 1 | 1 | 6 | 1,007 |
| LORE | 1.59 | 1.62 | 1 | 2 | 76 | 812 |
| DIALOGUE | 3.32 | 3.37 | 2 | 7 | 57 | 6,554 |
| ACTION | 1.42 | 1.44 | 1 | 2 | 16 | 6,282 |
| INTERIORITY | 1.24 | 1.26 | 1 | 2 | 13 | 2,717 |
| TRANSITION | 1.07 | 1.07 | 1 | 1 | 6 | 430 |

Design consequence: **no explicit duration model is needed at block level.**
Sampling from the matrix reproduces the masters' run lengths. Persistence and
long-range structure must therefore come from levels above the block, which
Section 7 shows is also what the data demands.

## 5b. Paragraph length is a property of the mode, not of the book

Added 2026-09-10. Block *counts* say nothing about how long a scene will run,
because a paragraph's length depends almost entirely on which mode it is. The
labels carry no word counts, so these are measured by aligning each book's
per-paragraph labels back to the extracted markdown; alignment is accepted
only where a unit offset reproduces every unit's paragraph count exactly, and
all 21 books align.

| mode | n | mean | p25 | median | p75 | p90 |
|---|---:|---:|---:|---:|---:|---:|
| SETTING | 1,571 | 104.7 | 47 | 85 | 137 | 209 |
| CHARACTER_DESC | 1,115 | 91.3 | 32 | 69 | 123 | 197 |
| LORE | 1,292 | 115.0 | 34 | 85 | 149 | 243 |
| DIALOGUE | 21,741 | 41.5 | 11 | 22 | 48 | 94 |
| ACTION | 8,936 | 74.3 | 25 | 53 | 97 | 158 |
| INTERIORITY | 3,381 | 93.6 | 38 | 72 | 122 | 191 |
| TRANSITION | 459 | 10.2 | 4 | 5 | 7 | 25 |

Pooled over all 38,495 paragraphs the mean is **59.8 words, median 35**.

Two consequences, both load-bearing for Slice 4:

1. **A dialogue paragraph is a speech turn.** At a 22-word median it holds one
   character's words plus a tag, which is why DIALOGUE is 56.5% of all
   paragraphs while being far short of 56.5% of the words. Any instruction
   that asks for a uniformly "full" paragraph is asking the writer to pack
   several turns together, and that is exactly what it does.
2. **Scene length must be budgeted by mode mix, not by block count.** At these
   lengths 1,400 words is roughly 34 dialogue paragraphs or roughly 12
   exposition paragraphs. A flat words-per-paragraph divisor gives both the
   same count and silently distorts whichever mode it is wrong about.

Note on the earlier figure: the "90 words per paragraph" that appeared in the
Slice 4 masters column was `WORDS_PER_BLOCK`, the shared word budget the Gate C
harness set for both arms. It was a convention, never a measurement, and it was
hardcoded next to values that were genuinely read from this corpus. The
measured figure is 59.8.

## 6. Position and tension condition the mix only mildly

**By book position** (paragraph deciles, pooled): the mix is nearly
stationary. Dialogue holds 52-60% and action 21-25% in every decile. The only
real positional signals: LORE is U-shaped (5.4% in decile 0, ~2.5% mid-book,
5.9% in decile 9), TRANSITION concentrates at both ends, INTERIORITY ticks up
in decile 8 (pre-climax reflection).

| decile | SET | CHR | LOR | DLG | ACT | INT | TRN |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.047 | 0.047 | 0.054 | 0.550 | 0.208 | 0.081 | 0.013 |
| 1 | 0.044 | 0.032 | 0.034 | 0.562 | 0.225 | 0.084 | 0.019 |
| 2 | 0.048 | 0.034 | 0.026 | 0.570 | 0.228 | 0.083 | 0.012 |
| 3 | 0.041 | 0.030 | 0.022 | 0.562 | 0.251 | 0.083 | 0.011 |
| 4 | 0.040 | 0.026 | 0.024 | 0.602 | 0.216 | 0.085 | 0.008 |
| 5 | 0.040 | 0.030 | 0.033 | 0.565 | 0.236 | 0.086 | 0.009 |
| 6 | 0.036 | 0.017 | 0.027 | 0.568 | 0.243 | 0.098 | 0.010 |
| 7 | 0.034 | 0.026 | 0.026 | 0.600 | 0.221 | 0.088 | 0.006 |
| 8 | 0.036 | 0.022 | 0.031 | 0.549 | 0.243 | 0.107 | 0.012 |
| 9 | 0.043 | 0.026 | 0.059 | 0.520 | 0.250 | 0.083 | 0.018 |

**By chapter tension band** (nd1 judge's 0-10 unit tension): high-tension
chapters shift weight toward ACTION and away from LORE and INTERIORITY, but
the grammar's shape is unchanged.

| band | n paragraphs | SET | CHR | LOR | DLG | ACT | INT | TRN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| calm (<=3) | 10,199 | 0.039 | 0.036 | 0.047 | 0.574 | 0.200 | 0.095 | 0.010 |
| mid (4-6) | 10,597 | 0.035 | 0.024 | 0.033 | 0.593 | 0.209 | 0.095 | 0.010 |
| high (>=7) | 17,699 | 0.045 | 0.028 | 0.026 | 0.543 | 0.265 | 0.079 | 0.014 |

Design consequence: a tension parameter should **reweight** block
probabilities, not switch grammars. And act-level structure should NOT be
expressed as block quotas ("description-heavy act one"): masters do not do
that. Long-range structure lives in tension curves and thread scheduling
(`MASTERS_THREADS_TENSION_STUDY.md`), not in the block mix.

## 7. The excursion-and-return finding (why hierarchy is mandatory)

Test: after every genuine switch A -> B (B != A), how often does the next
block return straight to A? A first-order model predicts the return rate from
the matrix row of B. Observed, pooled over 17,983 switches:

- **observed return rate 0.355 vs first-order prediction 0.238**

The masters return to the interrupted mode about 50% more often than a flat
Markov chain would. The excess is concentrated in dialogue interruptions:

| pattern | n | observed return | predicted | excess |
|---|---:|---:|---:|---:|
| DIALOGUE -> INTERIORITY -> back | 1,365 | 0.609 | 0.359 | +0.250 |
| DIALOGUE -> CHARACTER_DESC -> back | 452 | 0.768 | 0.537 | +0.230 |
| DIALOGUE -> SETTING -> back | 267 | 0.446 | 0.238 | +0.207 |
| DIALOGUE -> ACTION -> back | 3,894 | 0.628 | 0.477 | +0.151 |
| ACTION -> LORE -> back | 203 | 0.360 | 0.219 | +0.141 |
| ACTION -> INTERIORITY -> back | 682 | 0.412 | 0.300 | +0.112 |
| ACTION -> DIALOGUE -> back | 4,108 | 0.293 | 0.185 | +0.108 |

(Full table, including the small-excess pairs, from
`scripts/block_grammar_tables.py`.)

This is the beat idiom: a conversation interrupted by one paragraph of
gesture, thought, or scene-touch, then resumed. Two readings, both load
bearing for the DSL:

1. **Rapid A-B-A alternation is master behaviour, not a defect.** Any
   "no immediate return" penalty at block level would push generated prose
   away from the masters.
2. **A flat block-level matrix cannot represent "we are still in the
   conversation."** The excess return rate is the statistical signature of a
   hidden persistent state above the block: a *scene* whose carrier mode
   endures across texture excursions. The failure mode to prevent is not
   block-level flip-flop but aimless drift between scene intents, one level
   up.

   > **Superseded, 2026-09-10 (see Section 12).** Reading 2 compares against
   > the wrong null. The excess over a *first-order* prediction is fully
   > accounted for by a **second-order** chain (0.353 against the observed
   > 0.355), so it is evidence for one block of memory, not for a level above
   > the block. Reading 1 stands unchanged, and the closing sentence here about
   > drift of *intent* is still the real argument for L2, but intent is not
   > visible in block labels, so this statistic cannot support it.

## 8. Secondary shading (the sub-block seed data)

7,851 of 38,495 paragraphs (20.4%) carry a secondary label; blocks are not
pure. ACTION is the most-shaded mode. Top pairs:

| primary + secondary | count |
|---|---:|
| ACTION + INTERIORITY | 971 |
| ACTION + SETTING | 907 |
| ACTION + DIALOGUE | 876 |
| DIALOGUE + ACTION | 823 |
| DIALOGUE + LORE | 541 |
| SETTING + ACTION | 475 |
| INTERIORITY + ACTION | 459 |
| DIALOGUE + INTERIORITY | 391 |
| ACTION + CHARACTER_DESC | 386 |
| ACTION + LORE | 230 |

Design consequence: a pure-blocks-only grammar generates prose measurably
flatter than the corpus. The DSL should allow a primary+shading annotation on
blocks (or equivalently, mixed-mode sub-blocks), weighted toward these pairs,
especially on ACTION. Caution: secondary labels are unordered within a
paragraph, so within-block sub-block *sequencing* is not recoverable from
this dataset.

## 9. The layered design

The measurements decompose cleanly into levels, each with its own alphabet,
its own transition structure, and its own boundary behaviour:

- **L0, book.** Not a matrix: an authored curve. Tension trajectory shape
  (sustained-high / spike-and-settle / slow burn), the peak-position
  regularity (hotter books peak earlier, r = -0.70), thread schedule and
  convergence shape, register/genre. This layer carries ALL long-range
  structure. Evidence it should not dictate block mix: Section 6
  stationarity. Source data: masters corpus report Sections 6-9 and
  `MASTERS_THREADS_TENSION_STUDY.md`.
- **L1, chapter.** Entry and exit vectors measured in Section 4 (open by
  orienting, close on event or reflection). Body = a sequence of scenes.
  Receives a tension band and thread membership from L0.
- **L2, scene.** The hidden layer revealed by Section 7. Small alphabet
  (candidate types: DIALOGUE_SCENE, ACTION_SEQUENCE, REFLECTIVE_PASSAGE,
  EXPOSITION), each owning a block-level emission matrix, entry/exit vectors,
  and a length distribution. The scene-to-scene matrix is the knob that
  prevents wandering: scenes persist across many blocks by construction.
  **Not yet measured** (Section 10).
- **L3, block (paragraph).** Per-scene-type block dynamics, reweighted by
  the L0/L1 tension band (ACTION up, LORE and INTERIORITY down as tension
  rises). *Revised by the Gate A PoC (`experiments/block_grammar_poc/`):*
  the original hypothesis, first-order rows plus a persistent carrier, gets
  close but undershoots the return rate, because patterns like
  ACTION -> DIALOGUE -> ACTION (0.293) are a braid of two persistent modes,
  not carrier plus interruption. What passes all checks is sampling from the
  measured second-order kernel P(next | prev, current) within scenes, with
  the scene layer owning intent, entry, length, and boundaries. Block-level
  guidance should therefore condition on the previous two blocks, or
  equivalently track which mode was interrupted.
- **L4, sub-block.** Shading/composition inside a block, seeded from the
  Section 8 pair statistics.

### Rules for handling matrices across levels

1. **One matrix per level, over that level's alphabet.** Never let a lower
   level transition across an upper-level boundary; a level transitions only
   when its child process has terminated (the hierarchical-HMM discipline).
2. **Parent selects or reweights the child matrix.** Conditioning variables
   the data already supports: tension band (Section 6), chapter position
   (Section 4), register (pooled here; split when the corpus grows).
3. **Every level needs entry and exit vectors, not just the square matrix.**
   Section 4 is L1's pair; measure the same for scenes when L2 is induced.
4. **Put duration control only where persistence lives.** Block runs are
   geometric (Section 5): sample them from the matrix. Scene and chapter
   lengths are where explicit length models belong.
5. **No anti-repetition hacks at block level.** Masters return to the
   interrupted mode more than a flat model predicts (Section 7), so an
   immediate-return penalty is anti-master. Repetition control belongs at
   scene level (do not emit two REFLECTIVE_PASSAGE scenes back to back) and
   above.

### Immediate DSL implications (usable before L2 exists)

For the Slice 4 scene skeleton (`BLOCKS_CONTRACTS_LANDING_SKETCH.md`), three
guidance rules are directly measurable and cheap to enforce in the writer
prompt or QA today:

- skeleton openers drawn from {SETTING, ACTION, LORE, INTERIORITY}, closers
  from {ACTION, DIALOGUE, INTERIORITY}; dialogue-opening chapters rare;
- carrier/texture discipline: texture sub-blocks appear singly (run length
  1-2) between carrier stretches; only DIALOGUE may run long;
- shading expectation: roughly one block in five carries a secondary
  function, most often on ACTION.

## 10. Revisions to the pilot's calibration bands

The pilot (`BLOCK_DECOMPOSITION_STUDY.md`, 2 masters, sampled chapters) fed
calibration numbers into the analyzer's `block_types.py` rubric. The
full-corpus values revise two of them:

| quantity | pilot band | full corpus (21 books) |
|---|---|---|
| secondary shading rate | ~0.26-0.54 | pooled 0.204; 11 of 21 books fall below 0.26 |
| INTERIORITY self-transition | pooled 0.143 | pooled 0.205 (masters band ceiling ~0.28-0.29 holds) |

The masters corpus report (analyzer repo, Section 8) reached the same
conclusion from the per-book angle: the pilot's shading band fails to contain
the corpus (Austen's tight free-indirect novels sit as low as 0.106). The
pilot's *qualitative* findings (carrier/texture split, dialogue stickiness,
generated prose's interiority self-transition ~0.40 being far outside master
range) all survive at scale. Treat the pilot bands as superseded by this
doc's tables; the direction "generated prose chains interiority far more than
masters do" is unchanged and if anything sharper.

## 11. Gaps and next steps

0. **Gate A of the PoC is done and passing** (25/25 statistical checks,
   multiple seeds): `experiments/block_grammar_poc/` contains the skeleton
   sampler, the scorecard, and the machine-readable grammar
   (`grammar_reference.json`, regenerated via
   `scripts/block_grammar_tables.py --json`). Gates B (skeleton-to-prose
   round-trip) and C (does skeleton guidance move the known failure metrics)
   are specified in its README.
1. ~~**Induce the scene layer (L2).**~~ **Done 2026-09-10, negative: see
   Section 12.** Both proposed routes were run
   (`scripts/scene_layer_hmm.py`). The statistic that motivated the search
   turns out to be second-order memory rather than hierarchy, and no fitted
   HMM generates block sequences as well as a plain second-order table. Three
   recognisable scene types do emerge (a long conversation, an exposition
   passage, a mixed narration opening) and they sit close to the hand-tuned
   constants already shipping; the additional states are dwell-1 oscillators
   encoding alternation, not scene identity. The heuristic route's answer is
   set by its own threshold. What remains open is not "induce L2 from block
   labels" (block labels cannot settle it) but whether scene *intent* needs
   explicit control, which needs a different annotation.
2. **Register/genre-conditioned matrices.** The corpus supports a two-way
   split now (dialogue-led vs narration-led books); proper per-genre matrices
   need corpus growth. Rerun `scripts/block_grammar_tables.py` over subsets.
3. **Fold in the giants** (`--include-giants`) once their runs are aggregated,
   and re-check stability of the matrix and the return test.
4. **Order within blocks.** If sub-block sequencing matters to the DSL, the
   secondary labels are insufficient (unordered); a finer-grained annotation
   pass (sentence-level, sampled chapters only) would be the follow-up study.

## 12. Inducing the scene layer: the excursion-return excess is memory, not hierarchy

Added 2026-09-10, closing gap 1 of Section 11 ("induce the scene layer").
Tooling: `scripts/scene_layer_hmm.py` (Baum-Welch over the label sequences,
numpy only, no LLM calls). Both routes Section 11 proposed were run.

**The result is negative, and it lands on Section 7's argument.** Section 7
infers a hidden persistent state from the excursion-return excess: the masters
return to an interrupted mode 0.355 of the time against a first-order
prediction of 0.238, and "a flat block-level matrix cannot represent 'we are
still in the conversation'." That inference compares against the wrong null. A
plain **second-order** chain, `P(next | prev, current)` with backoff on thin
cells, reproduces the rate almost exactly:

| generator | return rate | vs masters 0.355 |
|---|---:|---:|
| first-order Markov | 0.234 | -0.121 |
| **second-order Markov** | **0.353** | **-0.002** |
| shipped hybrid sampler (scene layer + second-order kernel) | 0.335 | -0.020 |
| best fitted HMM (K=5, K=8) | 0.321 to 0.326 | -0.034 to -0.029 |

Cross-validated by book, so this is not the 343-cell table memorising its own
corpus. Trained on three quarters of the books, simulating the held-out
quarter's unit-length profile:

| fold | held-out books | observed | first-order | second-order |
|---|---:|---:|---:|---:|
| 0 | 6 | 0.356 | 0.237 | 0.355 |
| 1 | 5 | 0.326 | 0.238 | 0.356 |
| 2 | 5 | 0.366 | 0.234 | 0.344 |
| 3 | 5 | 0.365 | 0.229 | 0.356 |

One extra block of context, not a scene, accounts for the entire excess. The
beat idiom Section 7 describes is real and still master behaviour; what is not
supported is treating it as *evidence for a level above the block*.

Half of this correction was already in the document. Section 9's L3 entry
records that the Gate A PoC revised the first-order hypothesis precisely
because it "undershoots the return rate," and the shipped sampler has used the
second-order kernel ever since. Section 7's hierarchy argument was simply never
revisited against that finding.

### The HMM route: some real scene types, and states spent on memory

Fitting hidden states directly (`scripts/scene_layer_hmm.py`, Baum-Welch,
held-out by book) gives a more interesting answer than a flat negative.

A caveat first, because it bit this analysis. Baum-Welch collapses to a
degenerate fit from roughly half of random starts on this data (two states
dominated by one mode, a non-sticky transition matrix, no convergence inside
the iteration cap). The highest-likelihood restart is reliably the correct one,
so restart count is what buys reliability, and a first pass at four restarts
produced a spurious pattern: return rate apparently flat near 0.30 through K=7
then jumping at K=8. At six restarts that jump disappears. **It was
under-optimisation, not signal.** The numbers below are the ones to trust; a
full K sweep at a trustworthy restart count has not been run, because the
second-order result above already settles the question it was asked to answer.

| K | train ll/blk | held-out ll/blk | return rate |
|---|---:|---:|---:|
| 5 | -1.1208 | -1.1949 | 0.326 |
| 8 | -1.1063 | -1.1858 | 0.321 |

No fitted HMM reached the masters' 0.355, and none came near plain
second-order's 0.353. As a generator of block sequences the hidden layer is
simply worse than one extra block of context.

The induced states are worth reading anyway. At K=5:

| state | share | dwell | dominant emission | self-transition |
|---|---:|---:|---|---:|
| DIALOGUE_1 | 0.573 | 24.3 | DIALOGUE 0.860 | 0.938 |
| ACTION_1 | 0.222 | 5.6 | ACTION 0.407, INTERIORITY 0.241, SETTING 0.159 | 0.743 |
| ACTION_2 | 0.110 | 1.4 | ACTION 0.472, DIALOGUE 0.334 | 0.341 |
| DIALOGUE_2 | 0.070 | 1.0 | DIALOGUE 0.896 | 0.053 |
| LORE | 0.026 | 4.8 | LORE 0.734 | 0.725 |

Three of these read as scene types, and match the hand-defined layer more
closely than expected. `DIALOGUE_1` is a long sticky conversation with a dwell
of 24.3 blocks, against the hand-tuned `DIALOGUE_SCENE` mean of 21.0. `LORE` is
an exposition passage at 4.8 blocks against a hand-tuned 3.8. `ACTION_1` is a
mixed narration state carrying action, interiority and setting together, and it
takes 0.728 of the chapter entries: chapters open by orienting, exactly as
Section 4 measured.

The other two are not scene types at all. `DIALOGUE_2` and `ACTION_2` both have
a dwell of 1.0 to 1.4 and transition into each other at 0.842 and 0.559: a
two-state oscillator whose entire job is to alternate. That is the A-B-A beat
idiom of Section 7, encoded in hidden state because the emission model has no
other way to remember what the previous block was. At K=8 the pattern is
sharper still: one dominant conversation state (share 0.672, dwell 35.2,
self-transition 0.930) plus a second dwell-1.0 oscillator pair transitioning
into each other at 0.762 in both directions.

So the extra states past the recognisable few are memory in disguise, which is
why held-out likelihood keeps improving with K while the return rate does not,
and why a second-order table beats all of them. The scene layer that *is*
present in the data is small, and the shipped hand-tuned constants already
approximate it.

The heuristic route is inconclusive by construction, since its answer is set by
its purity threshold:

| carrier-share threshold | DIALOGUE | ACTION | INTERIORITY | LORE |
|---|---:|---:|---:|---:|
| 0.5 | 49.6 | 8.8 | 4.6 | 4.8 |
| 0.7 | 24.8 | 5.5 | 3.8 | 5.4 |
| 0.9 | 6.8 | 2.7 | 2.6 | 3.6 |
| *hand-tuned `_SCENE_TYPES` today* | *21.0* | *9.0* | *3.8* | *3.8* |

It can bracket the hand-tuned constants (they sit near a 0.7 threshold) but it
cannot determine them.

### What this means for the design

1. **Section 7 no longer carries the hierarchy argument.** L2 may still be
   worth building, but on its own merits: control over scene entry, exit,
   length and *intent*, which is what the section's closing sentence actually
   worries about ("aimless drift between scene intents"). Drift of intent is
   not visible in block labels at all, so no amount of block-sequence
   statistics will settle it. That is a different study, and it needs a
   different annotation pass.
2. **A scene layer exists, but it is small and already approximated.** The
   induced states recover three recognisable types whose dwell lengths sit
   close to the hand-tuned constants (conversation 24.3 against 21.0,
   exposition 4.8 against 3.8), plus a narration state that takes most chapter
   entries. That is a modest vindication of the shipped scene layer as a
   description, and simultaneously a reason not to invest in fitting it more
   precisely: the payoff over what is already in the code is small, and the
   generator does not improve.
3. **The scene layer is not what makes the shipped sampler work.** Comparing
   the shipped hybrid against a pure second-order sampler over the statistics
   Gate A checks, second-order matches the masters better on every base rate,
   every run length, and the return rate. The hybrid's one decisive advantage
   is the chapter boundary, where it applies the measured closer distribution:
   closing on DIALOGUE is 0.238 in the masters and 0.226 under the hybrid, but
   0.589 under pure second-order, which simply runs off the end of the unit.

   | statistic | masters | hybrid (shipped) | second-order only |
   |---|---:|---:|---:|
   | return rate | 0.355 | 0.335 | 0.359 |
   | close on DIALOGUE | 0.238 | 0.226 | 0.589 |
   | DIALOGUE share | 0.565 | 0.536 | 0.561 |
   | DIALOGUE run mean | 3.317 | 3.004 | 3.176 |
   | LORE run mean | 1.591 | 1.511 | 1.635 |

   So the load-bearing parts of the sampler are the second-order kernel and
   the explicit opener/closer treatment. The hand-defined scene layer costs a
   little accuracy on shares and run lengths and earns none of the return rate.
4. **Concrete next step, not taken here:** re-run Gate A's 25 checks against a
   sampler that keeps the second-order kernel and the measured openers and
   closers but drops `_SCENE_TYPES`. Gate A's 25/25 was scored against the
   hybrid, so the comparison has to be made on the same instrument before
   anything is removed from a shipping path.
