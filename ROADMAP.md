# Roadmap — StoryDaemon

_Status: active · updated 2026-09-01_

An agentic long-form fiction generator: an autonomous LLM agent runs iterative
"story tick" cycles (plan → tools → write → evaluate) that grow characters, lore,
and plot emergently rather than from a pre-plan. Python, multi-backend. The active
strategic plan is `docs/EMERGENT_COHERENCE_PLAN.md`.

## Shipped

- [x] Agentic story-tick loop (plan → tool use → write → evaluate)
- [x] Multi-backend LLM support (Codex / Gemini / Claude Code CLIs + OpenAI / Claude / Gemini APIs / Self-hosted OpenAI compatible)
- [x] Deep-POV writing with POV validation + character-continuity checks
- [x] Dynamic memory — characters, locations, factions, relationships, scenes persist and evolve
- [x] ChromaDB vector search for semantic context retrieval
- [x] Story Foundation system (immutable constraints + interactive setup)
- [x] Emergent plot-first mode — rolling-horizon beats, beat-constrained writing + verification (Phase 2)
- [x] Multi-stage planner (strategic → semantic → tactical, with token reduction)
- [x] Tension tracking (LLM 0–10 scoring, dynamic pacing, arc-pressure control)
- [x] Arc-phase planner mandate (rising/peak/falling/resolution derived from the tension curve; per-phase event mandates into the planner, futile-rewrite skip, `arc_phase` in metrics) (Phase 3). Validated on a descent re-run (`docs/progress_report_20260709.md`): de-escalation largely fixed (final scene 8 to 6 against a target of 4; resolution drift 2.35 to 1.65)
- [x] Beat-generation bridge: arc tension targets + phase feed plot beat generation (per-beat schedule, per-phase authoring directives, sanitize-not-trust reconciliation of authored targets; both generation paths) (Phase 3)
- [x] Contracts Slice 1: beat-embedded pre/postconditions authored at beat-generation time from a closed checker vocabulary, evaluated at beat verification (`generation.use_contracts`, default off) (Phase 3)
- [x] OpenRouter support in the `api` backend (model `openrouter`, `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`), live-validated
- [x] Venice support in the `api` backend (model `venice`, `VENICE_API_KEY`/`VENICE_MODEL`; Venice's injected system prompt disabled per request)
- [x] Shared `llm-backends` package: the six `novel_agent/tools/` backend modules are now compatibility shims over it; the fiction persona is passed explicitly on the `api` backend (`tools/llm_setup.py`) and `DEFAULT_API_MODEL` is read from the package instead of hardcoded
- [x] Write-until-concluded scene loop: scenes are sized from `generation.scene_word_targets` and continued in bounded segments instead of truncating at a flat token ceiling (Phase 3)
- [x] Honest loop accounting (interleaving Slice 0): judged loop closure (`coherence.loop_closure`), creation-time dedup and a per-tick creation cap, judged extractor resolutions (Phase 3)
- [x] Sacred finale (`coherence.sacred_finale`): on plot-first runs Python owns the final tick — guaranteed beat ask, fresh re-rolls against a finale tension cap, and quarantine of the finale's freshly minted loops (Phase 3)
- [x] Story-thread registry (interleaving Slices T1/T1.5): threads minted in Python and selected by the beat author via `thread_id`, per-tick attribution, `novel threads` (Phase 3)
- [x] Tension-curve presets (`coherence.curve_preset`) grounded in the masters decile tables, plus the construction-pressure detector (instrumentation only, Slice T4a) (Phase 3)
- [x] Hardening batch: beat-level dedup at authoring time (`generation.beat_dedup`), a per-call `llm.timeout` honored on the api backend, loop-dedup threshold recalibration (Phase 3)
- [x] Contradiction detection (lore contradictions, dispute quarantine)
- [x] Per-tick coherence rubric (loop churn, contradictions, tension vs. target, goal relevance) via `novel metrics`
- [x] Goal hierarchy (immediate / arc / story goals, auto-promotion, throughline gate + LLM goal-relevance judge)
- [x] Lore system (rules, constraints, facts, capabilities per tick, dedup)
- [x] Checkpointing (project snapshots + restore)
- [x] Manuscript compilation (Markdown / HTML / prose / EPUB / PDF export, scene filtering)
- [x] Grounded name generator (syllable-based, culture/era banks) (Phase 1)
- [x] Full CLI (`novel new`, `tick`, `run`, `resume`, `status`, `goals`, `lore`, `compile`, `plot`, …)
- [x] Neutral-CWD isolation for CLI backends (avoid repo-awareness derailment)
- [x] **Scene layer (L2) induction, negative result**: the excursion-return excess that Section 7 of the masters study read as evidence for a level above the block is second-order memory, not hierarchy. A plain second-order chain reproduces it (0.353 vs the masters' 0.355, cross-validated across four book-level folds) where first-order gives 0.234, and no fitted HMM matches it at any state count tried. Three recognisable scene types do emerge and sit close to the constants already shipping. Tooling: `scripts/scene_layer_hmm.py` (LLM-free). Closes gap 1 of the study's next steps: it retires inducing L2 *from block labels*, not the idea of a scene. Scenes are real and scene-sized here (the induced conversation state runs 1,000 to 1,500 words), and the scene question that matters is about *intent* (same place, cast, purpose), which block labels cannot see at all and which needs a different annotation pass to measure. Note the scope: all of this concerns the plan *generator*, not the proportion control the DSL exists for, which lives in the writer prompt and is unaffected. Details in `docs/MASTERS_BLOCK_GRAMMAR_STUDY.md` section 12
- [x] **Chapter-length calibration** (`generation.scene_length_preset`, default `house` and byte-identical): Gate A run against the *production* sampler for the first time (`experiments/block_grammar_poc/gate_a_production.py`) passes 25/25 at chapter scale but fails DIALOGUE share at the 1400-word default (0.510 vs 0.565). It is a length effect: scene maps to chapter 1:1, the grammar's opening orientation is measured per chapter, and the house targets sit below the corpus p10 with the house *maximum* below the per-chapter average of every book in it (masters median 3,165 words; shortest book 1,989). The opt-in `masters` preset (1,600/2,150/3,150/4,450) scores 24/24. Default unchanged: adopting it roughly doubles prose per tick, a cost and pacing decision. Details in `docs/MASTERS_BLOCK_GRAMMAR_STUDY.md` section 13
- [x] **Masters block grammar + evaluation harness**: block-transition grammar, chapter boundary rules, run lengths, and the excursion-return kernel measured on the 21-masterwork nd1 corpus (`docs/MASTERS_BLOCK_GRAMMAR_STUDY.md`, data in `novel_agent/data/block_grammar_v1.json`, 26-book refresh pre-validated); reusable gates methodology in `experiments/block_grammar_poc/` (statistical Gate A, compliance Gate B, outcome-A/B Gate C, corpus-judge scene scoring)
- [x] **Scene skeletons (contracts Slice 4)**, `generation.enable_scene_skeleton` (default off): typed paragraph plan sampled from the masters grammar (planner-authored `scene_skeleton` wins when present), sized by the scene word target, tension-conditioned, carried in the writer prompt with per-item [n] markers, stripped with compliance recording. Production A/B vs unguided (gpt-5.5): every solidly measured block statistic moved toward the masters; 16/16 marker compliance on all production scenes; no surface regression (`docs/SLICE4_SCENE_SKELETON_RESULTS.md`)
- [x] Pipeline hardening from the skeleton trials: character/location IDs can no longer leak into prose as names ("C0"); a failing scene evaluation with an empty issues list is non-fatal; fact extraction survives explicit JSON nulls
- [x] 800+ tests (unit, integration, manual scenarios)

## Next

- [ ] **Loop-aging pressure** (older open loops surface louder for payoff): now twice-evidenced (the descent re-run's resolution ticks opened 8 loops and closed 0; contracts can check `loop_resolved` but nothing pressures the planner to close loops)
- [ ] **Thread interleaving (tension by scene selection)** — *partly landed:* the registry, thread identity by selection, and the construction-pressure detector are in (see Shipped); construction itself (Slice T4b) and selection are not. The tension curve becomes a scene-selection policy over a portfolio of story threads; a calm page comes from cutting away to a calmer thread (leaving a cliffhanger), never from becalming a hot event. Design: `docs/THREAD_INTERLEAVING_DESIGN.md`. Replaces the "forced low-tension scenes" idea, which the fork experiment falsified (`progress_report_20260710.md` Addendum 2: pruning 80 percent of the writer prompt moved mean tension by 0.0; the overshoot lives in the assigned event, not the prompt). Empirical grounding now available: the masters corpus thread-architecture data (thread counts, run lengths, convergence shapes) and the nd1 26-book reference bands
- [ ] Contracts Slice 2: precondition pressure (unmet preconditions become planner setup pressure at beat selection, never a hard raise)
- [ ] Contracts Slice 3: bounded contract repair (mirror the tension-rewrite pattern) plus an `event_occurs` LLM-judge checker
- [ ] Gate A re-run against a sampler with `_SCENE_TYPES` removed (second-order kernel plus measured openers/closers only). Section 12 finds the scene layer earns none of the return rate and costs a little accuracy on shares and run lengths, but Gate A's 25/25 was scored against the hybrid, so the comparison has to be made on the same instrument first. The run must add a *commitment* measure (set-piece length) at matched sequence lengths: commitment is the gap the decomposition study named, Gate A's current checks would not notice a sampler that stopped sustaining set-pieces, and the one measurement taken so far is confounded by skeleton length
- [ ] Per-sub-block generation experiment (contracts Slice 5, own flag): explicitly a measured A/B per `docs/BLOCKS_CONTRACTS_LANDING_SKETCH.md`. De-risked by Slice 4: the [n] marker protocol gives every block an address, and the designed entry point is a selective per-block repair pass (expand deficient paragraphs only), documented in `docs/SLICE4_SCENE_SKELETON_RESULTS.md`. Production evidence says it is NOT currently needed for gpt-5.5 (single-shot honors paragraph fullness); build only if a chosen writer model does not
- [ ] Skeleton refinements from the Slice 4 reading notes. **Dialogue-run paragraphing is built, not yet validated:** paragraph length is now measured per mode on the masters corpus (`paragraph_words` in the grammar, study section 5b), every plan item carries its own word range, consecutive DIALOGUE items are one speech turn each, and the sampler fills a word budget instead of dividing by a flat 90. The predicted lift in excursion-return rate needs a re-run to confirm, and the PoC harness's writer prompt has to be synced to the production one first. Still open: genre-conditioned grammars; MTLD over-diversity as a candidate metric
- [ ] Add support for guided generation per tick (largely superseded by Slice 4 scene skeletons for structure; reword or retire once remaining intent is defined)
- [ ] Validate the throughline gate with a headroom scenario (goal-aligned foundations hit a ceiling — the LLM gauge is sound, but the pressure shows no lift when the story is already on-goal)
- [ ] Resolve embedding-similarity placeholders in `multi_stage_planner.py`
- [ ] Scene-summarization callback stub in `cli/main.py` (Phase 2)

## Backlog

- [ ] Phase 4 — setup/payoff foresight (planted-element ledger for Chekhov's guns)
- [ ] Plan explicit low-tension beats if arc-pressure proves insufficient (note: Slice 4 skeleton sampling already tension-conditions the prose-level block mix; this item concerns beat selection, which it does not touch)
- [ ] Wedged-beat problem (noted, deliberately not auto-fixed): a beat whose contract keeps failing retries forever when `allow_beat_skip` and `rolling_horizon` are both off (observed live: 4 consecutive failures on one beat, 2026-07-10 smoke run). A bounded give-up rule was considered and rejected as dangerous (silently drifting off-outline); the preferred fix is making scenes comply with their tension targets (see forced low-tension scenes) so contracts stop failing in the first place
