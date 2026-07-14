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

## Gate C (this directory, BUILT; verdict pending scale): does skeleton guidance move the failure metrics?

`gate_c.py` is the A/B that justifies (or blocks) wiring skeletons into
`novel_agent`: baseline arm = premise + word budget only (today's
single-shot shape); skeleton arm = identical plus a Gate-A skeleton with
the Gate-B marker protocol. Same writer, temperature, and word budget, so
structure is the only treatment. Both arms are judged with the corpus
protocol and compared, pooled per arm, against the masters' bands on the
pre-registered failure metrics: interiority self-transition (band ceiling
0.30) and shading rate (floor 0.10), with a directional check that the
skeleton arm sits no farther from the masters than the baseline.

The scorecard is tri-state: any metric measured on fewer than 20
interiority transitions reports **INCONCLUSIVE** (exit 2), never PASS or
FAIL. That rule exists because the first short debug run (2 chapters,
24-block cap) produced a spurious FAIL from a 1-vs-5-event comparison,
exactly the bug class the run was meant to catch.

Debug-run observations (2 chapters/arm, too small for a verdict, kept in
`runs/gatec-s23-c2/`): skeleton-arm compliance held (all markers present,
25/29 labels matching plan); unguided DeepSeek does NOT chain interiority
the way StoryDaemon's pilot prose did (band verdicts need more data); and
the baseline over-shades dramatically (0.708 of paragraphs mixed vs
masters 0.204) while the skeleton arm lands near-masters at 0.241, an
unexpected point in favour of structured guidance.

```
python3 gate_c.py --fake                    # plumbing test (rigged baseline
                                            #  chains interiority; scorecard
                                            #  must discriminate)
python3 gate_c.py --chapters 2 --seed 23 --max-blocks 24   # short debug run
python3 gate_c.py --chapters 8 --max-blocks 40             # verdict-scale
python3 gate_c.py --rescore runs/gatec-s23-c2
```

Verdict-scale sizing: interiority is ~9% of blocks, so >= 20 interiority
transitions per arm needs roughly 8 chapters at full skeleton lengths.
Structural metrics only in v1; st1 surface scoring (slop/MTLD/cliche) via
the analyzer venv is a follow-up.

## Write, stop, resume

Real runs are interruptible at two levels, tested without network by
`test_resume.py` (7/7 checks):

- **Implicit:** every billed response is disk-cached by (model,
  temperature, system, prompt) hash, and skeletons are seed-deterministic,
  so re-running the IDENTICAL command after any crash, Ctrl-C, or 402
  fast-forwards through completed calls for free and only pays for what's
  missing. Completed chapters' artifacts are saved as they finish.
- **Explicit:** `--pause-after-calls N` (gate_b and gate_c) stops cleanly
  after N billed calls with exit code 3; cache hits don't count against
  the budget, so a resumed session's budget is spent only on new work.
  Example: run a verdict chunk one billed call at a time:

  ```
  python3 gate_c.py --chapters 2 --seed 31 --pause-after-calls 1   # pay 1 call
  python3 gate_c.py --chapters 2 --seed 31 --pause-after-calls 1   # 1 more
  ...repeat until it exits 0/1/2 instead of 3 (pausing) ...
  ```

## Files

- `grammar_reference.json`: measured grammar (regenerable, see above)
- `sampler.py`: L1/L2/L3 skeleton generator (`Grammar`, `Params`, `Sampler`)
- `gate_a.py`: statistical scorecard, exit 0 = pass
- `gate_b.py`: skeleton -> prose -> judge round-trip, exit 0 = pass
- `gate_c.py`: skeleton-vs-baseline A/B on the failure metrics
  (exit 0 pass / 1 fail / 2 inconclusive)
- `runs/`: per-run artifacts; `cache/`: LLM response cache (gitignored)
