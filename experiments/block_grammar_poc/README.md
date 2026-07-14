# Block Grammar PoC

Targeted testing of the layered block DSL design
(`docs/MASTERS_BLOCK_GRAMMAR_STUDY.md`) before anything is wired into
`novel_agent`. The strategy is three gates, each testing exactly one thing;
nothing here touches the pipeline.

## Gate A (this directory, DONE): can the architecture reproduce master statistics?

A hierarchical sampler (chapter -> scene -> block) emits block-label
skeletons, zero LLM calls, and `gate_a.py` scores thousands of synthetic
chapters against the statistics measured on the 21-masterwork corpus.

Status: **25/25 checks pass** (seeds 1, 2, 3, 42): base rates, all seven
transition-matrix rows, run lengths, chapter opener/closer distributions,
mean chapter length, and the excursion-and-return rate (generated 0.336 vs
masters 0.355, where a flat first-order chain gives 0.238).

```
python3 gate_a.py --chapters 3000 --seed 1     # the scorecard
python3 sampler.py --chapters 3 --seed 7       # eyeball some skeletons
python3 sampler.py --chapters 500 --stats      # quick mode-share summary
```

`grammar_reference.json` holds every measured statistic the sampler and the
gate consume. Regenerate it (e.g. after the giant books land, or for a
genre-filtered corpus) with:

```
python3 ../../scripts/block_grammar_tables.py --json grammar_reference.json
```

### Finding: carrier memory alone is not enough at block level

The study doc hypothesized that a first-order block matrix plus a persistent
scene carrier would reproduce the masters' excursion-and-return rate. Gate A
falsified the strong version of that: carrier-only memory reached ~0.27-0.32
(vs 0.355 target) because the biggest triple class in the corpus,
ACTION -> DIALOGUE -> ACTION at 0.293, is a *braid* of two persistent modes
(conversation woven through activity), not a carrier plus interruptions.

The fix that passes: within-scene dynamics sample from the **measured
second-order kernel** P(next | prev, current) (exported in
`grammar_reference.json` as `second_order`, contexts with n >= 80,
first-order fallback). The scene layer still owns intent, entry, length, and
boundaries; the kernel owns local texture. Design consequence for the DSL:
block-level guidance should condition on the previous TWO blocks (or
equivalently, track "what mode was interrupted"), not just the current one.

## Gate B (this directory, DONE): does prose round-trip through the skeleton?

`gate_b.py` renders Gate-A skeletons to prose in ONE single-shot writer call
per chapter (the Slice 4 shape from `BLOCKS_CONTRACTS_LANDING_SKETCH.md`),
then re-annotates the prose with the corpus judge protocol, imported from
the analyzer repo so it cannot drift: same rubric prompt, same lenient batch
parser, same model/temperature/system prompt (DeepSeek via OpenRouter,
batches of 20, one re-ask). It scores skeleton-in vs labels-out.

Status: **passing** (4 chapters, writer = deepseek-chat, seed 11):
count compliance 4/4, marker-aligned label agreement **0.834** (per chapter
0.76-0.93), mode-share TV 0.047. Confusions concentrate exactly where the
shading data says modes genuinely blend: DIALOGUE<->ACTION and
DIALOGUE->INTERIORITY.

Finding: the naive prompt ("write exactly N paragraphs") FAILED outright,
0/4 compliance, in two modes: dialogue items exploded into one paragraph per
speech turn (37 -> 50), and long plans got compressed with an invented
ending (40 -> 21). Both vanished with **per-paragraph [n] markers** (each
paragraph opens with its plan number, stripped mechanically before judging)
plus an explicit no-compression rule. Design consequence for Slice 4: scene
skeletons need an explicit per-item accountability structure in the writer
prompt, not just an ordered list.

```
python3 gate_b.py --fake                    # plumbing test, no network
python3 gate_b.py --chapters 4 --seed 11    # real run (OPENROUTER_API_KEY)
python3 gate_b.py --rescore runs/gateb-s11-c4
```

Artifacts (skeleton, prose, judged labels, metrics per chapter) live under
`runs/`; LLM responses are disk-cached under `cache/` (gitignored), so
re-scoring is free and re-runs only pay for changed prompts.

## Gate C (next): does it move the known failure metrics?

Skeleton-guided vs baseline single-shot chapters from the same premise,
scored on block metrics plus the analyzer's st1 (slop, MTLD, cliche).
Success = the skeleton version pulls the known generated-prose failures
(interiority self-transition ~0.40 vs masters ~0.21, under-shading) into the
master bands. Passing Gate C is the evidence bar for wiring skeletons into
`novel_agent` properly.

## Files

- `grammar_reference.json`: measured grammar (regenerable, see above)
- `sampler.py`: L1/L2/L3 skeleton generator (`Grammar`, `Params`, `Sampler`)
- `gate_a.py`: statistical scorecard, exit 0 = pass
- `gate_b.py`: skeleton -> prose -> judge round-trip, exit 0 = pass
- `runs/`: per-run artifacts; `cache/`: LLM response cache (gitignored)
