# Slice 4 Scene Skeletons: Production Results and Reading Notes

**Status:** Evaluation complete; flag remains default-off pending adoption decision
**Date:** 2026-07-15
**Feature:** `generation.enable_scene_skeleton` (agent/scene_skeleton.py), Slice 4 of the block DSL
**Method provenance:** grammar and gates in `MASTERS_BLOCK_GRAMMAR_STUDY.md` and `experiments/block_grammar_poc/README.md`; raw run artifacts under gitignored `work/skeltest/`; judged metrics in `experiments/block_grammar_poc/runs/judge_scenes_last.json`
**Cost of the entire evaluation:** ~$5 in API calls (DeepSeek judging + gpt-5.5 writing), zero pipeline risk (flag off = byte-identical)

---

## 1. What was tested

The Slice 4 question: does a typed paragraph plan ("scene skeleton"),
sampled from the block grammar measured on 21 masterworks and carried in
the writer prompt with per-item [n] markers, make production scenes
measurably more master-like than unguided single-shot writing?

Four cells, all on the same premise (the 1871 survey-brig Alcyone
foundation), judged with the same DeepSeek block-rhythm protocol that
annotated the masters corpus:

- gpt-5.5 + skeleton and gpt-5.5 unguided (4 scenes each, the primary A/B)
- deepseek-chat + skeleton and unguided (3 scenes each, secondary)

## 2. Structural results (block metrics vs the masters)

| metric | masters | gpt-5.5 + skeleton | gpt-5.5 unguided |
|---|---:|---:|---:|
| words per paragraph | 90 | **101.4** | 16.9 |
| dialogue share | 0.565 | **0.500** | 0.351 |
| dialogue run mean | 3.32 | **2.91** | 1.98 |
| shading rate | 0.204 | **0.266** | 0.099 |
| interiority self-trans | 0.205 | 0.000 (n=4, indicative) | 0.261 (n=111) |
| return rate | 0.355 | 0.154 (small n, see 6.1) | 0.247 |

**The skeleton moved every solidly measured statistic toward the
masters.** The headline is paragraph shape: unguided gpt-5.5 fragments a
scene into 112-177 paragraphs of ~17 words while overshooting the word
budget by 80%; the same model with a skeleton wrote 16 master-sized
paragraphs per scene, on target (1541-1675 words vs the 1400 request),
with 16/16 plan markers on all 13 production skeleton scenes run to date
and zero markers leaking into saved prose.

Model comparison: instruction-following on structure is equal (both
writers hit perfect marker compliance), but gpt-5.5 is far more
*steerable* on prose density: told 60-130 words per paragraph it
delivered 96-105, while deepseek-chat delivered ~33 regardless of
instruction. Unguided, gpt-5.5 fragments harder than DeepSeek (17 vs ~26
words per paragraph), so the production writer is better under guidance,
not better by default.

## 3. The founding assumption, revised

This project began from the pilot observation that generated prose
chains interiority (self-transition ~0.40 vs masters 0.205). That
disease **did not replicate** in raw-API gpt-5.5: the unguided arm
measured 0.261 on a solid n=111 events, inside the 26-book masters band
(max 0.339). The pilot's number was likely specific to the codex
harness, older prompts, or an older model. The real unguided failure
modes, well measured here, are **fragmentation** (17-word paragraphs)
and **under-shading** (0.099 vs masters 0.204: fragmented paragraphs do
only one job each). The skeleton fixes both.

## 4. Surface quality (st1 pass: analyzer lexicons, LLM-free)

| cell | MTLD | cliché/1k | slop/1k | em-dash/1k |
|---|---:|---:|---:|---:|
| masters band (median) | 70-106 (91) | 0-0.15 (0.05) | 0-0.41 (0.05) | 0.1-18.3 (5.6) |
| gpt-5.5 + skeleton | **132** | 0.15 | ~0 | 1.97 |
| gpt-5.5 unguided | 141 | 0.00 | ~0 | 0.86 |
| deepseek + skeleton | 161 | 0.00 | ~0 | 5.64 |
| deepseek unguided | 148 | 0.00 | ~0 | 8.05 |

No surface rot anywhere: cliché and slop are essentially zero in all
cells, so the structural gains cost nothing at the surface level. One
new finding: **every cell exceeds the masters' MTLD ceiling** (132-161
vs max 106). Modern LLM prose over-diversifies vocabulary (the
thesaurus-never-repeats tell), the opposite failure from the slop era.
The skeleton arm is closest to band, but lexis is a writer trait
skeletons do not control. Candidate future metric; unknown whether
readers perceive it as a defect. (DeepSeek cells carry a short-text
caveat; spaCy-dependent st1 metrics, cast census and duplication, were
skipped: no environment on this machine currently has the heavy deps.)

## 5. Reading notes (the side-by-side)

Both arms independently opened with a depth-sounding scene, giving a
near-controlled comparison of the same dramatic material.

**The unguided scene is genuinely good prose**, and the statistics alone
would caricature it: modern literary register, short paragraphs,
isolated one-line beats ("Seventeen."), white space as rhythm,
procedural tension with interiority threaded through. Its fragmentation
is substantially deliberate style, not incompetence.

**The guided scene reads like the masters corpus**: dense ~100-word
paragraphs, setting-into-action opening, distinct character voices, and
it advances the premise harder (the Meridian canvas surfaces on the
sounding lead: a real plot event in scene one).

The honest framing of the result: **the skeleton does not make the
writer "better"; it makes the writer produce the masters' register
instead of its native modern register, controllably.** Which register a
given novel should want is an authorial choice; the skeleton makes it a
*choice* rather than an accident of the model's defaults.

## 6. Weak points and backlog (ranked)

1. **Dialogue paragraphing (top craft item, found by reading, not by
   metrics).** The one-item-one-paragraph rule makes the writer pack
   5-6 speaker exchanges into single paragraphs. The masters mostly give
   each speaker turn its own paragraph within a run of DIALOGUE blocks;
   our skeletons have such runs, but the rule forces compression anyway.
   It reads nonstandard, and it plausibly explains the skeleton arm's
   low excursion-return rate (0.154 vs 0.355): packing exchanges
   flattens exactly the texture that metric measures. Precise fix to
   test: for consecutive DIALOGUE blocks, instruct one exchange per
   paragraph. Small prompt change, PoC-testable before production.
2. **Statistics are not quality.** The st1 pass and the reading close
   part of this gap, but human judgment on longer stretches (does a
   whole skeleton-guided novel *read* better?) remains untested.
3. **One premise, one genre, pooled-Victorian grammar.** All runs used
   the Alcyone foundation. Genre-conditioned grammars are future work.
4. **Interiority in skeleton cells is under-measured by construction**
   (plans carry 1-2 INTERIORITY blocks per scene); many more scenes are
   needed before that cell's number means anything.
5. **Pipeline bugs observed during runs (not skeleton-related): FIXED**
   the same day. Character/location IDs leaking into prose as names
   ("C0"/"L0": the context builder surfaced raw IDs when entities were
   missing; it now falls back to the foundation protagonist or a neutral
   descriptor), the first-tick hard failure on a failing evaluation with
   an EMPTY issues list (heuristic warnings flipped the passed flag
   without producing issues; empty-issues failures are now non-fatal),
   and the fact-extraction NoneType error (explicit JSON nulls from the
   LLM hit len()). 13 regression tests added; suite at 804.
6. **MTLD over-diversity** (Section 4): measure first, judge later.
7. **Long-range structure untouched**: skeletons shape single scenes;
   thread architecture, convergence, and book-level block placement (the
   L0/L2 layers of the study doc) remain design-only. Parked with them:
   the per-block repair pass (targeted per-[n] expansion calls),
   unnecessary for gpt-5.5 but the designed escalation valve and the
   natural first step toward Slice 5 per-block generation; promotion of
   the 26-book grammar (Gate A already passes 25/25 against it); and
   z-scoring against the analyzer's nd1_reference.json.

## 7. Recommendation

Adopt behind the flag for real projects where the masters' register is
the goal, with the dialogue-paragraphing refinement tested first (it is
the one known craft defect and the likely fix for the one wrong-way
metric). The evidence chain is complete and cheap to extend: grammar
(Gate A) -> compliance (Gate B) -> outcome A/B (Gate C) -> production
A/B (this doc), every step judged by the same instrument that measured
the masters.
