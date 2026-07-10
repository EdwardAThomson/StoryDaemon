# Block Decomposition Study: Master Prose vs Generated Prose at Page Granularity

**Status:** Offline corpus experiment, complete (no pipeline code changes)
**Date:** 2026-07-10
**Serves:** the block/sub-block DSL (`DSL_and_contracts.md`, `BLOCKS_CONTRACTS_LANDING_SKETCH.md` Slice 4) and the thread interleaving design (`THREAD_INTERLEAVING_DESIGN.md`)
**Artifacts:** raw texts, per-paragraph annotations, and driver scripts live in the session scratchpad; only aggregates and short quotes appear here

## Motivation

The block/sub-block idea (`DSL_and_contracts.md`) proposes composing scenes from typed prose blocks (setting, dialogue, action, thoughts, transitions), and the landing sketch (`BLOCKS_CONTRACTS_LANDING_SKETCH.md`) scoped its first slice as a scene skeleton: an ordered, typed sub-block list given to the writer as guidance. Before designing that vocabulary and grammar, we should know what block structure master prose actually exhibits at page granularity, and how far StoryDaemon's generated prose currently is from it. This study annotates every paragraph of two public-domain master corpora and two StoryDaemon runs with a block-type rubric, then compares distributions, run lengths, transition matrices, and per-page texture. A prediction was registered before measurement (section: Prediction verdict) so the result could not be quietly reshaped to fit.

## Block-type rubric

One primary label per paragraph (the dominant mode), plus an optional secondary label when genuinely mixed:

| Label | Meaning |
|---|---|
| SETTING | Description of place, atmosphere, weather, light, objects in the scene |
| CHARACTER_DESC | A character's appearance, dress, manner, bearing |
| LORE | History, backstory, flashback, world facts; includes one-sentence asides about the past dropped into other material |
| DIALOGUE | Paragraph dominated by quoted speech (a line plus its tag counts) |
| ACTION | Events happening now: movement, physical or procedural activity, things done or observed as they occur |
| INTERIORITY | Thoughts, feelings, reasoning, deliberation, judgments |
| TRANSITION | Connective tissue whose main job is a time or place shift |

## Corpora and sample sizes

| Corpus | Source | Sample | Paragraphs | Words | Words/para |
|---|---|---|---|---|---|
| Eddison | *The Worm Ouroboros* (1922), Project Gutenberg #67090 | Chapters IX, X, XII (mid-book: travel, dialogue, action) | 278 | 19.8k | 70.9 |
| Buchan | *The Thirty-Nine Steps* (1915), Project Gutenberg #558 | Chapters III, IV, V (pre-modern thriller, genre-matched to our runs) | 211 | 12.4k | 58.9 |
| descent-run3 | `work/novels/descent-run3_8e35c9d2` (newest full-pipeline thriller) | 9 scenes spread across the run (000, 002, 004, 006, 008, 010, 012, 014, 015) | 490 | 17.9k | 36.5 |
| claudetest | `work/novels/claudetest_e6ae3d40` (second sample, kept separable) | 5 scenes spread across the run (002, 006, 010, 014, 018) | 230 | 7.1k | 31.0 |

Both reference texts are public domain and were fetched as plain text from gutenberg.org. Tolkien was deliberately excluded (in copyright); the pipeline scripts are corpus-agnostic, so a locally owned Tolkien text can be swapped in later for a closer epic-fantasy comparison. Eddison's typographic section breaks (rows of bullets) were treated as scene boundaries, not paragraphs; runs and transitions never cross a scene or section boundary. Generated scene headers (title, scene ID, tick) were stripped.

## Annotation protocol and agreement

Annotator: `anthropic/claude-haiku-4.5` via the OpenRouter path of the `api` backend, temperature 0, batches of 20 numbered paragraphs, strict JSON output, one retry per malformed batch. Roughly 61 batches over 1,209 paragraphs.

Agreement check, run before trusting anything downstream: one 25-paragraph mixed sample (13 Buchan, 12 descent-run3) was annotated twice in independent calls, the second time with the presentation order shuffled. Primary-label agreement: **24/25 = 96 percent** (the one disagreement was CHARACTER_DESC vs SETTING on a paragraph describing a carriage's occupants). This is a single-annotator self-consistency number, not human-validated ground truth; it qualifies everything below.

## Results

### Block-type distribution (percent of paragraphs, primary label)

| Label | Eddison | Buchan | descent-run3 | claudetest |
|---|---|---|---|---|
| SETTING | 10.4 | 4.3 | 5.3 | 5.7 |
| CHARACTER_DESC | 2.2 | 3.8 | 1.8 | 1.7 |
| LORE | 1.1 | 2.8 | 2.2 | 0.0 |
| DIALOGUE | 68.7 | 35.5 | 43.3 | 32.6 |
| ACTION | 17.6 | 39.8 | 23.5 | 29.1 |
| INTERIORITY | 0.0 | 12.3 | **23.1** | **30.0** |
| TRANSITION | 0.0 | 1.4 | 0.8 | 0.9 |
| paragraphs with a secondary label | 35.6 | 35.5 | 24.1 | 23.5 |

Two things stand out. First, INTERIORITY: 23 to 30 percent of generated paragraphs, versus 12.3 percent in the genre-matched master and zero in Eddison (his saga style externalizes everything). Second, masters shade a third of their paragraphs with a secondary mode; generated prose shades a quarter.

### Run lengths (consecutive same-primary paragraphs, within a scene/section)

| Metric | Eddison | Buchan | descent-run3 | claudetest |
|---|---|---|---|---|
| Overall mean run (paragraphs) | 2.65 | 1.61 | 1.81 | 1.62 |
| Longest run | DIALOGUE x22 | DIALOGUE x6 | DIALOGUE x9 | DIALOGUE/INTERIORITY x5 |
| Mean DIALOGUE run | 5.0 | 2.0 | 2.6 | 1.8 |
| Mean INTERIORITY run | n/a | 1.1 | 1.5 | 1.9 |
| Paragraph-to-paragraph switch rate | 34.2% | 61.5% | 54.3% | 60.9% |
| Mean run length in words | 187.8 | 94.9 | 66.2 | 50.3 |

Generated prose does not run longer than the masters; it runs shorter. Eddison sustains 22-paragraph dialogue set-pieces. Because generated paragraphs are also half the length of master paragraphs, the mode-switch cadence in words is starkest: Eddison changes mode every ~188 words, Buchan every ~95, descent-run3 every ~66, claudetest every ~50.

### Per-page texture (350-word sliding page)

| Corpus | Mean distinct primary types per page |
|---|---|
| Eddison | 2.07 |
| Buchan | 2.83 |
| descent-run3 | 3.24 |
| claudetest | 3.33 |

Generated pages contain more distinct modes than master pages, not fewer. Combined with the run-length table, the picture is churn: rapid rotation among DIALOGUE, ACTION, and INTERIORITY, without the masters' willingness to commit to one mode for a stretch.

### SETTING placement and density

Position of SETTING-primary paragraphs within their scene/section (first / middle / last third): Eddison 59/24/17 (n=29), Buchan 56/44/0 (n=9), descent-run3 46/31/23 (n=26), claudetest 69/8/23 (n=13). Everyone front-loads setting; it is not a generated-prose signature. The real difference is density including secondary shading: counting paragraphs where SETTING is primary *or* secondary, masters touch the setting in 16 to 18 percent of paragraphs, generated prose in 8 to 10 percent. Masters keep place alive inside action and dialogue paragraphs; generated prose mostly mentions place when a paragraph is *about* place.

### LORE frequency

| Corpus | LORE primary | LORE secondary | primary /1k words | prim+sec /1k words |
|---|---|---|---|---|
| Eddison | 3 | 20 | 0.15 | 1.17 |
| Buchan | 6 | 3 | 0.48 | 0.72 |
| descent-run3 | 11 | 12 | 0.62 | 1.29 |
| claudetest | 0 | 3 | 0.00 | 0.42 |

Project-dependent, not a systemic near-zero. descent-run3 actually carries more lore per 1,000 words than either master; claudetest carries almost none. Eddison's pattern is distinctive: 20 of his 23 lore touches are secondary labels, history riding inside dialogue and action rather than standing alone.

### Transition matrices (row = current primary, column = next; row-normalized percent; rows with n >= 5)

Selected rows that carry the story:

| From -> To | DIAL | ACT | INT | SET | Corpus |
|---|---|---|---|---|---|
| DIALOGUE -> | 82 | 13 | 0 | 3 | Eddison (n=186) |
| DIALOGUE -> | 49 | 36 | 8 | 3 | Buchan (n=75) |
| DIALOGUE -> | 63 | 16 | 17 | 2 | descent-run3 (n=208) |
| DIALOGUE -> | 44 | 35 | 16 | 1 | claudetest (n=75) |
| INTERIORITY -> | 20 | 60 | **8** | 8 | Buchan (n=25) |
| INTERIORITY -> | 29 | 27 | **35** | 5 | descent-run3 (n=113) |
| INTERIORITY -> | 20 | 28 | **51** | 2 | claudetest (n=65) |
| CHARACTER_DESC -> | 100 | 0 | 0 | 0 | Eddison (n=6) |
| CHARACTER_DESC -> | 75 | 25 | 0 | 0 | Buchan (n=8) |
| SETTING -> | 46 | 23 | 0 | 27 | Eddison (n=26) |

The sharpest divergence in any row: what follows a thought. In Buchan, interiority exits to action 60 percent of the time and chains to more interiority 8 percent of the time. In generated prose, interiority chains to itself 35 percent (descent-run3) and 51 percent (claudetest) of the time. Master pattern worth noting for the grammar: CHARACTER_DESC hands off to DIALOGUE 75 to 100 percent of the time (describe the speaker, then let them speak), and Eddison's SETTING flows into DIALOGUE or ACTION rather than more SETTING.

### Structural distance

Jensen-Shannon divergence (base 2) between block-type distributions, and mean absolute difference between transition matrices (rows with n >= 5 in both corpora):

| Pair | JSD (distribution) | MAD (transition matrix) |
|---|---|---|
| **Buchan vs Eddison (master vs master baseline)** | **0.153** | **0.086** |
| descent-run3 vs Buchan (genre-matched) | 0.034 | 0.068 |
| descent-run3 vs Eddison | 0.151 | 0.074 |
| claudetest vs Buchan | 0.052 | 0.065 |
| claudetest vs Eddison | 0.223 | 0.105 |
| descent-run3 vs claudetest | 0.022 | 0.052 |

The yardstick matters: the two masters are 4.5x further apart from each other (JSD 0.153) than descent-run3 is from its genre-matched master (0.034). At the level of "what fraction of paragraphs is each mode," generated prose sits comfortably inside the master-to-master spread. The structural gap is not in the bulk distribution; it is in the dynamics (self-loop rates, switch cadence, secondary shading) that the distribution does not see.

## Prediction verdict

Pre-registered prediction, judged clause by clause:

1. **"Generated prose shows long monotone runs of one mode (slabs of dialogue-then-action)": refuted.** Generated mean run 1.6 to 1.8 paragraphs (max 9) versus Buchan 1.6 (max 6) and Eddison 2.65 (max 22). The masters are the slab-writers; Eddison's longest dialogue run is 22 paragraphs. In words, generated prose switches mode every 50 to 66 words, faster than either master.
2. **"Setting description front-loaded in a scene then abandoned": not a discriminator.** Generated prose does front-load (claudetest 69 percent of SETTING paragraphs in the first third), but the masters front-load just as hard (Buchan 56, Eddison 59). The real setting deficit is density: masters touch place (primary or secondary) in 16 to 18 percent of paragraphs, generated in 8 to 10 percent.
3. **"Near-zero lore/flashback texture": split by project.** True for claudetest (0 primary LORE paragraphs, 0.42 touches per 1k words). False for descent-run3 (0.62 primary per 1k words, more than either master).
4. **"Master prose interleaves constantly": refuted as stated, one sub-clause held.** Masters interleave *less* per page (2.1 to 2.8 distinct types per 350-word page versus 3.2 to 3.3 generated) and commit to long single-mode set-pieces. The sub-clause that held: lore dropped in single sentences mid-flow is real master technique (Eddison: 20 of 23 lore touches are secondary labels inside dialogue/action paragraphs), and "setting re-touched" is real when measured as secondary shading rather than standalone paragraphs.

Net: the prediction had the direction of the structural gap backwards. Generated prose is not monotone; it is over-fragmented. The master signature is commitment (long runs, fewer modes per page) plus continuous low-level shading of the dominant mode with setting and lore. The generated signature is rapid three-mode churn (dialogue, action, interiority) with thin shading, and interiority that feeds back into itself.

## Illustrative quotes

Master shading and hand-offs (Buchan, ch. V; five consecutive paragraphs labeled ACTION+SETTING, ACTION+INTERIORITY, INTERIORITY+ACTION, SETTING+ACTION, CHARACTER_DESC): "About six in the evening I came out of the moorland to a white ribbon of road which wound up the narrow vale of a lowland stream. ... The road swung over a bridge, and leaning on the parapet was a young man." Then, pivoting to description before the dialogue: "He was smoking a long clay pipe and studying the water with spectacled eyes." Movement, place, thought, and portrait alternate paragraph by paragraph, and most paragraphs carry two modes at once.

Master lore-as-aside (Eddison, ch. VIII, a DIALOGUE+LORE paragraph): "This weather bloweth out of Carcë. ... I do but conjecture it from my studying of certain prophetic writings touching the princes of that blood and line." World history arrives inside a speech, not as an exposition block.

Generated interiority self-loop (claudetest, scene 014; four consecutive INTERIORITY paragraphs): "The access restrictions were a statement made without words. Someone had documentation of what she'd been accessing. ... Her investigation had been detected. ... The timeline assembled itself in her mind with terrible clarity. ... It had all been part of the same response." Four paragraphs of thought chaining into thought, with no exit to action, dialogue, or place.

Generated churn versus master commitment: descent-run3's longest run is a 9-paragraph dialogue exchange of one-line volleys ("What does that mean?" Ionaora asked.), roughly 300 words in total; Eddison's 22-paragraph dialogue set-piece sustains a single interrogation for some 1,500 words while threading lore through the speeches.

## Implications for the block DSL

**Vocabulary the data supports.** The seven-label rubric annotated cleanly (96 percent self-agreement) and every label except TRANSITION pulled real weight. The data suggests two structural classes rather than seven peers: *carrier* modes (DIALOGUE, ACTION, INTERIORITY) that form runs and drive scenes, and *texture* modes (SETTING, CHARACTER_DESC, LORE) that almost never run longer than one paragraph anywhere (mean run 1.0 to 1.3 in all four corpora) and, in master hands, mostly appear as secondary shading inside carrier paragraphs. TRANSITION barely exists inside scenes in any corpus; time and place shifts live at scene boundaries (Eddison uses typographic breaks). The DSL should treat transitions as boundary properties between blocks, exactly as `DSL_and_contracts.md` sketched, not as content blocks.

**What a skeleton grammar should encode.** Not "vary the modes": generated prose already over-varies. The master patterns worth encoding are: (1) carrier set-pieces with word budgets, e.g. a dialogue block that is allowed and expected to run 300 to 1,500 words before the mode changes; (2) hand-off rules mined from the matrices: CHARACTER_DESC introduces a speaker then yields to DIALOGUE, SETTING opens and yields to a carrier, INTERIORITY must exit to ACTION or DIALOGUE within a paragraph or two (Buchan's 60 percent INT to ACT edge versus our 35 to 51 percent self-loop is the single most actionable number in the study); (3) shading directives, instructing the writer to keep place and history alive as clauses inside carrier paragraphs (target roughly one paragraph in three carrying a secondary mode, and setting touched in one in six); (4) an interiority budget per scene, on the order of 12 percent of paragraphs (genre-matched master level), not 23 to 30.

**What the structural-distance gauge could become.** Bulk distribution distance is nearly useless as a quality gauge: ours-vs-Buchan JSD (0.034) is already far inside the master-vs-master baseline (0.153). A useful per-scene gauge should instead track the dynamics where the real gap lives: interiority self-transition rate (target under ~0.15, observed 0.35 to 0.51), mode-switch cadence in words (target 90+, observed 50 to 66), secondary-shading rate (target ~0.33, observed ~0.24), and setting-touch rate including shading (target ~0.16, observed ~0.09). All four are deterministic to compute once paragraphs are labeled, which a single cheap LLM call per scene provides; the master-vs-master spread supplies the tolerance band. This would slot into the coherence rubric (`agent/coherence_metrics.py`) the same way tension and goal relevance did: instrument first, pressure second.

**Caveats.** One annotator model, self-consistency checked once (96 percent), no human gold labels. Paragraph granularity undercounts sub-paragraph mixing except through the single secondary label. Buchan is first-person, which blurs ACTION/INTERIORITY at the margin; Eddison's saga style (zero interiority) is an extreme anchor, useful mainly as the second point of the master baseline. Two generated projects from one genre; the descent-run3 vs claudetest distance (JSD 0.022) suggests the generated signature is stable across runs, but more genres would firm that up.

## Validation

The 96 percent self-agreement above is a RELIABILITY number: it shows the annotator is consistent with itself, not that its labels mean what the rubric says (validity) or that the seven types cover the material (coverage). This section tests validity and coverage directly. All artifacts (sample, second-judge annotations, coverage re-pass, sentence-level annotations, probe batch, driver script `validate.py`) live in the session scratchpad alongside the original study artifacts.

**Method.** A stratified sample of 60 paragraphs was drawn across all four corpora (15 each), oversampling rare labels and including 14 paragraphs the original judge labeled INTERIORITY (the headline finding rests on that boundary). Four tests: (1) cross-model agreement, re-annotating the sample with a maximally independent second judge, `google/gemini-3.5-flash` via OpenRouter (different lab, different family from the `anthropic/claude-haiku-4.5` primary), identical rubric, batching (20), temperature 0, and retry protocol; (2) coverage, re-annotating the same 60 with the original judge under an amended rubric adding an explicit OTHER label plus a free-text `better_label` field; (3) granularity, splitting 6 long paragraphs (three master, from committed-run stretches including an Eddison dialogue set-piece paragraph and two Buchan, at 195 to 399 words; three generated, the longest available at 96 to 101 words) into sentences and annotating each sentence with the original judge; (4) known-answer probes, 8 purpose-written unambiguous paragraphs (one per rubric type plus a second DIALOGUE) and 1 deliberately ambiguous ACTION/INTERIORITY borderline, shuffled among 10 real paragraphs and annotated blind by the original judge.

**Cross-model agreement (validity).** Overall primary-label agreement: 48/60, 80 percent, Cohen's kappa 0.75. Per label: DIALOGUE 17/17, CHARACTER_DESC 4/4, SETTING 5/6, ACTION 12/14, INTERIORITY 8/14, LORE 1/3, TRANSITION 1/2. The disagreements are near-misses, not contradictions: in 10 of 12, one judge's secondary label equals the other's primary. They also concentrate on genuinely ambiguous paragraphs rather than showing a model bias: the coverage re-pass (below) had haiku itself change 12 labels on this stratified sample, 9 of them the same paragraphs Gemini disputed, and on the 48 paragraphs where haiku was self-consistent Gemini agrees 94 percent (INTERIORITY 8/10). The INTERIORITY confusion pattern splits cleanly by corpus: on the 10 generated INTERIORITY paragraphs Gemini confirms 7/10 as primary (9/10 counting its secondary label; the escapes go to ACTION); on the 4 first-person Buchan INTERIORITY paragraphs it confirms only 1/4 (relabeling to SETTING, CHARACTER_DESC, ACTION, with INTERIORITY as secondary in 3 of 4). So the generated interiority mass is real under an independent judge, while the first-person master baseline (Buchan's 12.3 percent) is judge-dependent and, if anything, would be lower under Gemini, which widens rather than closes the generated-versus-master gap.

**Coverage (OTHER-allowed re-pass).** OTHER rate: 2/60, 3.3 percent. Both proposals were EXPOSITION (a Buchan paragraph summarizing the contents of Scudder's notes, and a generated paragraph rendering on-screen profile text). A recurring proposal at this rate is a hairline crack, not a hole: seven types remain defensible, with a noted low-frequency EXPOSITION/SUMMARY residual that currently gets absorbed by LORE, the label with the worst cross-model agreement (1/3). One honest secondary result: haiku's re-pass agreement with its own original labels on this sample was 80 percent, well below the study's 96 percent. The 96 percent was measured on contiguous, in-context passages; this sample is stratified toward rare labels and presented as isolated paragraphs. Read the study's reliability as roughly 96 percent on easy, in-context material and roughly 80 percent on hard, decontextualized material, with the same ceiling for a second model.

**Granularity (sentence-level).** Master long paragraphs are not monotone inside: all three carry 3 distinct sentence-level modes (Eddison's 399-word dialogue speech opens with two CHARACTER_DESC sentences and has one INTERIORITY beat inside 12 DIALOGUE sentences). Generated long paragraphs carry 2 to 3 distinct modes. Counting distinct modes, a finer instrument sees no difference; counting words per within-paragraph mode segment, the gap survives: masters hold a mode for 39 to 100 words per segment (mean about 63), generated for 25 to 48 (mean about 36), matching the paragraph-level cadence numbers (188/95 versus 50/66). Conclusion: the paragraph-count form of the commitment finding (mean run in paragraphs, switch rate per paragraph) is partly a paragraph-length artifact, since generated paragraphs are half the length of master paragraphs; the word-normalized form (mode-switch cadence in words, mean run in words) is the robust form and survives sentence-level re-measurement. The interiority self-chaining also reproduces at sentence level (a generated INTERIORITY paragraph ran ACTION then four consecutive INTERIORITY sentences).

**Known-answer probes.** 8/8 on the unambiguous probes, every rubric type recovered exactly, with the probes shuffled blind among real paragraphs. The deliberately ambiguous ACTION/INTERIORITY borderline was judged ACTION with secondary INTERIORITY, the defensible reading. The 10 real paragraphs in the batch were re-judged consistently with their original labels 9/10.

**Per-finding robustness.**

| Finding | Verdict |
|---|---|
| Distribution similarity (generated JSD inside the master-master baseline) | Robust: bulk distributions are dominated by DIALOGUE/ACTION, the two labels with near-perfect cross-model agreement |
| Switching rates / commitment | Robust in word-normalized form (cadence in words, run length in words); the paragraph-count form is partly a paragraph-length artifact |
| Interiority whirlpool | Confirmed on the generated side (7/10 cross-model primary, 9/10 with secondary; sentence-level chaining reproduces); the master baseline rate is judge-dependent in first-person prose, in the direction that widens the gap |
| Texture density (setting/lore shading) | SETTING-based rates supported (5/6 cross-model, probe exact); LORE-based rates carry the widest label noise (1/3 cross-model, EXPOSITION overlap), treat lore-per-1k-words with wide error bars |

**Human spot-check: pending.** A 30-paragraph stratified spot-check sheet (numbered, unlabeled, instruction header) and its answer key are prepared in the session scratchpad (`spotcheck_sheet.md`, `spotcheck_key.md`) for a human validity pass; no human labels have been collected yet.
