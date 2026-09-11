# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

StoryDaemon is an agentic novel-generation system. An LLM-driven `StoryAgent` runs a "story tick" loop (plan → execute tools → write scene → evaluate → extract facts/lore → commit), evolving characters/locations/lore from emergent prose rather than from a pre-baked outline. Python 3.11+, installed as the `novel` CLI via `setup.py`.

## Install & Run

```bash
pip install -e .                    # install package + `novel` entry point
pip install -e ".[dev]"             # add pytest, pytest-cov
pip install -e ".[export]"          # add WeasyPrint for PDF (needs Pango/Cairo system libs)
pip install -e ../llm-backends      # the shared backend layer, a sibling checkout
```

**Run everything from `venv/`.** The repo carries a `venv/` with `chromadb` and the editable `llm-backends` install; the system interpreter has neither, and `python -m pytest` outside the venv fails with ~53 collection errors on `ModuleNotFoundError: chromadb` rather than anything real.

Common dev commands:

```bash
pytest                                                  # full suite
pytest tests/unit/test_file_ops.py                      # single file
pytest tests/unit/test_tension_evaluator.py -v          # single file, verbose
pytest --cov=novel_agent                                # with coverage
python tests/manual_tension_test.py                     # manual integration check

novel new my-story --dir work/novels                    # interactive foundation + LLM wizard
novel new my-story --no-interactive                     # bare project
novel tick                                              # single tick in CWD project
novel run --n 5 --checkpoint-interval 10                # multi-tick + auto-checkpoint
novel resume                                            # most-recently-touched project
novel tick --save-prompts                               # dumps prompts/ for debugging
novel tick --llm-backend api --llm-model claude-sonnet-4-5  # one-off backend override
novel metrics                                           # per-tick coherence rubric
novel threads                                           # story-thread registry
novel plot revise                                       # regenerate pending beats from canon
novel compile --format epub                             # -> manuscript.epub
```

There is no lint/format/typecheck configured in the repo.

Test layout: `tests/unit/` and `tests/integration/` are discovered by `pytest.ini`; loose `tests/test_*.py` files (`test_entities.py`, `test_memory_manager.py`, `test_phase3_basic.py`, `test_phase6_commands.py`, `test_full_text_context.py`) also run. `tests/manual_tension_test.py` is intentionally not auto-discovered (no `test_*` prefix on its functions) — run it directly with `python`.

## Architecture

### The tick loop (`novel_agent/agent/agent.py`)

`StoryAgent.tick()` is the heart of the system. Tick 0 uses a two-phase "first tick" path (`_first_tick`) that splits entity generation from scene writing so the writer sees real IDs; tick 1+ uses `_normal_tick`. The step numbers below match the `# Step N` markers in the source. The normal pipeline:

0.5. `_detect_construction_pressure()` (Phase 3, interleaving Slice T4a): would thread construction fire at this tick? Evaluated before planning, where T4b's real construction would run, so the verdict sees the state construction would see. Instrument-only, recorded in metrics, never read for decisions. Gated by `coherence.thread_construction_detector`.
1. (Plot-first mode only, tick ≥ `plot_first_start_tick`) beat selection. On the **finale tick** `_sacred_finale_applies()` diverts to `_sacred_finale_beat()` (`agent/finale.py`), which owns the ask via a three-step chain: screen the pending beat as a genuine denouement, else author a dedicated finale beat, else a deterministic template; a total failure falls through to the normal path, so the worst case is exactly pre-finale behavior. Otherwise: regenerate beats if pending < threshold, then fetch the next pending `PlotBeat`.
2. `ContextBuilder.build_planner_context(state, current_beat=...)` → planner context.
3. Plan via `MultiStagePlanner` (default) or legacy single-stage `_generate_plan`. If a beat is current, `plan_for_beat()` is used.
4. `validate_plan()` (schema in `agent/schemas.py`) → `PlanExecutor.execute_plan()` (runs tool calls).
5. If `active_character` is still None, promote a newly-generated character to active and rewrite the plan's `pov_character`. `PlanManager.save_plan()` snapshots plan + execution results + context to `plans/`.
6. In plot-first mode, inject `plot_beat` into the plan before building writer context (including the beat's `postconditions` when `generation.use_contracts` is on, so the writer sees what will be checked) and, on the finale tick, `finale_mode` (`settled`, or `hook` when `coherence.ending_hook` is set). Then `WriterContextBuilder.build_writer_context()` → `SceneWriter.write_scene()`. The writer context carries a typed `scene_skeleton` when `generation.enable_scene_skeleton` is on, and `write_scene` runs the write-until-concluded segment loop rather than truncating at a flat token ceiling (see the two sections below).
7. `SceneEvaluator.evaluate_scene()` → `_gate_on_evaluation()`: a failing verdict raises **only when it carries concrete issues**; a failure with an empty issues list is logged and treated as warnings (a scene must not be lost to an unparseable evaluator response).
7.5. `TensionEvaluator.evaluate_tension()` (0–10; LLM-rated against an anchored rubric when an LLM is wired in, keyword heuristic as fallback — `tension.use_llm_scorer`).
7.6. `_control_scene_tension()` dispatches one bounded correction, never both: on a normal tick `_maybe_rewrite_for_tension()` (if the scored scene is > `coherence.tension_rewrite_threshold` off the target, one context-rich prose revision toward it, kept only if closer; skipped as futile when the gap exceeds what prose can close (`rewrite_futile`, gated with `coherence.arc_phase_mandate`)); on the finale tick `_finale_reroll_for_tension()` instead, up to `coherence.finale_retries` *fresh* renders against the finale tension cap (the hot-finale flips are staging choices a rewrite cannot unstage). Never raises.
8. `SceneCommitter.commit_scene()` writes the scene and updates summaries/vector index. **8.1** guarantees an explicit end-marker line on a finale scene. **8.5** writes the tension level/category back onto the scene. **8.6** `CharacterDetector` flags new named entities in prose (`auto_create_minor_characters` controls whether stubs are created).
9. `FactExtractor` → facts. **9.5** on the finale tick, `_quarantine_finale_loops()` drops the finale's freshly minted open loops before they are applied. **9.6** `_judge_extractor_resolutions()` puts the extractor's `open_loops_resolved` claims through the same one-loop/one-scene judge as beat claims (gated by `coherence.loop_closure`; when off the facts pass through untouched).
10–11. `EntityUpdater.apply_updates()` mutates characters/locations and `_reindex_updated_entities()` re-embeds them.
11.5. Beat verification (`_verify_and_complete_beat`, deliberately after the fact/entity steps so state-reading contract checks see the post-scene world): trust planner if `beat_target.beat_id` matches the current beat (record semantic score as reference); otherwise compute semantic similarity and mark complete if ≥ `beat_verification_threshold`. When `generation.use_contracts` is on and the beat carries postconditions, they are evaluated here against the written scene (deterministic checkers, result persisted onto the beat as `contract_results`, never a raise): all passing upgrades `verification_method` to `"contract"`; any failing keeps an otherwise-verified beat from completing and routes to the shared failure path (`_revise_horizon` when `generation.rolling_horizon` is on, else keep pending). `_mark_beat_complete()` persists status/score/method to the outline.
11.6. `_close_claimed_loops()` (`agent/loop_closure.py`): a verified beat claiming `resolves_loops` has each claim confirmed by a focused one-loop, one-scene judge before any loop closes. Gated by `coherence.loop_closure`; never breaks the tick.
11.7. On the finale tick, `_expire_finale_loops()` marks every still-open loop expired ("left open at story end") *after* the scene's own judged closures, so end-of-run accounting stays honest instead of mass-swept.
11.8. `_update_thread_registry()` (Phase 3, interleaving Slice T1): the committed scene joins its beat's primary thread's trace (implicit `main` when there is no beat or no labels, so the trace stays total). Instrumentation only.
12. `LoreExtractor` → `_save_lore_items()` persists Lore items, indexes them, and runs `LoreContradictionDetector.update_contradictions()`.
13. `_check_goal_promotion()` (tick 10–15 only) auto-promotes the most-mentioned protagonist loop into `state.story_goals.primary` if it has ≥5 mentions and the user didn't set a primary goal.
14. `state.current_tick += 1` and save, then `_record_coherence_metrics()` appends one per-tick record to `memory/metrics.jsonl` via `CoherenceMetrics` (Phase 3 instrumentation: loop churn, contradictions detected, tension, `arc_phase`, goal relevance, contract-condition counts, loop-closure/thread/finale/construction payloads). Fully wrapped — a metrics failure never breaks the tick. Also runs in `_first_tick` (with no tension signal).

Failures route through `PlanManager.save_error()` (writes to `errors/`) and re-raise.

### Memory & storage (`novel_agent/memory/`)

Each novel lives in its own directory (`<base>/<name>_<8charUUID>/`) with `state.json`, `config.yaml`, `memory/` (entities, counters, qa, vector index, plus `open_loops.json`, `lore.json`, `relationships.json`, `threads.json` and the append-only `metrics.jsonl`), `scenes/`, `plans/`, `errors/`, `checkpoints/`, optional `plot_outline.json`, optional `prompts/`. `MemoryManager` is the single read/write surface for entities (characters, locations, scenes, factions, lore, open loops, relationships) and owns ID counters in `memory/counters.json` — its constructor backfills any missing counter and reconciles the character counter against files on disk to prevent ID reuse on legacy projects.

`VectorStore` (ChromaDB, `memory/index/`) keeps parallel collections for characters/locations/scenes/lore/factions. Anything mutated in `MemoryManager` should also be re-indexed (the agent does this via `_reindex_updated_entities` and the lore save path). `VectorStore.compute_semantic_similarity()` is what beat verification uses — keep that contract.

### LLM backends (`llm-backends` package; `novel_agent/tools/` shims)

The backend layer lives in the shared `llm-backends` package (sibling checkout, `pip install -e ../llm-backends`; pinned git tag once published, see `requirements.txt`). The six modules `novel_agent/tools/{multi_provider_llm,llm_interface,codex_interface,claude_cli_interface,gemini_cli_interface,agent_cwd}.py` are compatibility shims that alias themselves to the package modules, so old import paths (and test monkeypatch targets) keep working; new code should import from `llm_backends` directly.

**Initialize through `tools/llm_setup.py:initialize_llm_with_persona()`, not `initialize_llm` directly.** llm-backends 0.2.0 stopped sending a system prompt unless one is asked for, so the fiction persona StoryDaemon used to get implicitly on the `api` backend is now an explicit opt-in (`FICTION_ROLE` passed as `role_description`). That wrapper is the single place the policy lives, and it passes the role only on `api`/`openai`: the CLI backends have no system-prompt concept and the package *raises* if you pass one. Requires llm-backends >= 0.2.0.

`initialize_llm(backend, codex_bin, model, timeout)` in `llm_interface.py` dispatches to one of four interfaces — `codex` (CodexInterface), `api` (`MultiProviderInterface` routes by model name across OpenAI/Anthropic/Gemini), `gemini-cli`, `claude-cli`. The aliases `openai` → `api`, `gemini` → `gemini-cli`, `claude` → `claude-cli` are supported for back-compat. There is a module-level singleton `_llm_client` used by `send_prompt*`, but the agent receives an explicit instance — don't rely on the singleton inside the agent path.

API env vars: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (canonical in the package; the old `CLAUDE_API_KEY` spelling still works as a deprecated fallback and loses if both are set), `GEMINI_API_KEY`.

The `api` backend's supported models live in `_model_config` (`llm_backends/multi_provider_llm.py`), a key-to-callable registry surfaced by `get_supported_models()`. **The `llm-backends` package registry is the source of truth for model naming** (inventory assumption A1; `LLM-Remote-Runner` reconciliation is now an optional alignment step, not a sync requirement). Primary keys use the hyphenated convention (`claude-sonnet-4-5`); StoryDaemon's legacy spellings (`claude-sonnet-4.5`, `claude-haiku-4.5`, `claude-4.5` alias to Sonnet) still resolve through `MODEL_ALIASES`. Providers: OpenAI `gpt-5.5`/`gpt-5.4`/`gpt-5.4-mini`/`gpt-5.2`; Anthropic Claude (incl. `claude-fable-5`/`claude-opus-4-8`, which omit sampling params); Gemini 3.x/2.5 families; `hosted-llm`, a self-hosted OpenAI-compatible endpoint configured via the `HOSTED_LLM_URL`/`HOSTED_LLM_PORT`/`HOSTED_LLM_API_KEY`/`HOSTED_LLM_MODEL` env vars (its own client singleton, distinct from `OPENAI_API_KEY`); `openrouter`, which routes to OpenRouter (https://openrouter.ai), a hosted OpenAI-compatible router over many upstream models, configured via `OPENROUTER_API_KEY`/`OPENROUTER_MODEL` (also its own client singleton; the package also accepts the open-ended `openrouter:<upstream-id>` passthrough form); and `venice`, which routes to Venice (https://venice.ai), an OpenAI-compatible host of open-weight/uncensored models, configured via `VENICE_API_KEY`/`VENICE_MODEL` (Venice's injected system prompt is disabled on every request). The canonical default (`config.llm.model`) is `gpt-5.5`; the CLI fallback sites in `cli/main.py`/`commands/*.py` read `llm_backends.DEFAULT_API_MODEL` instead of hardcoding it, so refreshing models is a package-side change only.

`claude-cli` (`ClaudeCliInterface`, `llm_backends/claude_cli_interface.py`) shells out to `claude -p <prompt> --output-format json`. It forwards `llm.model` as `--model` when it looks like a Claude model (`haiku`/`sonnet`/`opus`/`fable`/`claude…`; other names are ignored so the CLI's own default applies), and uses `llm.timeout` (default 300s) as the per-call timeout. Caveat (see `docs/EMERGENT_COHERENCE_PLAN.md` §6): `claude -p` is a full repo-aware *agent*, not a completion API — it's slow and can derail/time out on large prompts (e.g. the planner). Use a fast model (`llm.model: haiku`) for multi-call workloads, and **prefer the `api` backend for unattended multi-tick `run`s.**

**CLI-agent isolation (shared):** all three CLI backends (`codex`, `claude-cli`, `gemini-cli`) are repo-aware agents, so they all run their subprocess from a single neutral scratch dir, `llm_backends/agent_cwd.py:neutral_cwd()`, instead of the repo, or they load `CLAUDE.md`/`AGENTS.md` + the codebase and act on the repo instead of answering the prompt. `CodexInterface` additionally runs `codex exec` **read-only and non-interactive** (`--sandbox read-only --ask-for-approval never`, *not* the old `--dangerously-bypass-approvals-and-sandbox`) and reads only the final message via `--output-last-message` (codex flag names pinned for codex-cli ~0.118 in module constants); on hardened Linux hosts that block unprivileged user namespaces it falls back to running codex inside an identity-mapped userns. **Billing (key-stripping, default ON):** each CLI backend strips its provider's API key(s) from the subprocess env (`OPENAI_API_KEY` for codex; `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY` for claude; `GEMINI_API_KEY`/`GOOGLE_API_KEY` for gemini) so the CLI authenticates via its own subscription login instead of silently billing a metered key inherited from the environment; pass `strip_provider_keys=False` to opt out. This is a behavior change from the old in-repo backends, which inherited the full env.

### Tools (`novel_agent/tools/`)

Subclasses of `tools/base.py:Tool` register into a `ToolRegistry` in `cli/main.py` (`tick`/`run`). Tool names use dotted form (`character.generate`, `memory.search`, …). The planner sees these tools via `ToolRegistry.get_tools_description()`. `CharacterGenerateTool` takes a `beat_mode` argument that tightens name-generation behavior when plot-first runs in `guided` mode. New tools must be registered in **both** `tick()` and `run()` in `cli/main.py` — these blocks are duplicated; updating only one will silently break the multi-tick flow.

`NameGeneratorTool` (`name.generate`, `tools/name_generator.py`) is the Phase 1 "grounded identity" tool: names are minted in Python (`NameGenerator` — syllable/name banks by culture/era, dedup against existing entities), and the LLM *selects and justifies* rather than inventing. Its shared `NameGenerator` instance (`name_gen_tool.generator`) is threaded into `CharacterGenerateTool`/`LocationGenerateTool`/`FactionGenerateTool` so all entity creation grounds names the same way. See `docs/EMERGENT_COHERENCE_PLAN.md` Phase 1.

### Multi-stage planner (`agent/multi_stage_planner.py`)

Default planner. Three stages: (1) strategic intention from foundation+goals, (2) semantic context gathering via `VectorStore`, (3) tactical plan with tools. `stage_stats` is surfaced in the CLI output. `plan_for_beat(state, beat)` is the beat-aware entry point used by plot-first mode and by the legacy `plot.beat_mode == "guided"` path. Falls back to `plan()` on exception.

Set `generation.use_multi_stage_planner: false` to use the single-stage planner in `_generate_plan` (raw JSON extraction via regex from the LLM response).

### Plot-first mode (`novel_agent/plot/`)

Off by default. When `generation.use_plot_first: true`:
- Beats live in `plot_outline.json`, managed by `PlotOutlineManager`.
- `plot_first_start_tick` (default 2) delays beats until characters/world exist.
- Beats regenerate when pending count drops below `plot_regeneration_threshold`.
- Two verification paths in `_normal_tick`: trusted-planner (planner set `beat_target.beat_id`) vs. semantic threshold (`beat_verification_threshold`, default 0.5). `allow_beat_skip` controls whether failing verification advances or leaves the beat pending.
- `fallback_to_reactive: true` is what keeps a beat-generation failure from killing the tick.

Beat-generation is arc-aware (Phase 3 bridge, sharing the `coherence.arc_phase_mandate` gate): `beat_tension_schedule`/`arc_guidance_for_beats` (`agent/arc_pressure.py`) render a per-beat tension target + phase directive into the beat prompt, and `reconcile_beat_tension_targets` sanitizes the authored targets back toward the schedule after parsing. Both generation paths (`plot/manager.py` and `cli/commands/plot.py`) run the same helpers.

Contracts (Phase 3, contracts Slice 1, `novel_agent/contracts/`; gated by `generation.use_contracts`, default False): `PlotBeat` carries `preconditions`/`postconditions`/`contract_results`. Conditions are beat-embedded, authored at beat-generation time from the closed checker vocabulary in `contracts/conditions.py` (registry: `entity_exists`, `char_at_location`, `char_in_prose`, `prose_contains`, `tension_at_least`, `tension_at_most`, `loop_resolved`) and sanitized in both generation paths (`contracts/authoring.py:sanitize_beat_conditions`, same sanitize-not-trust pattern as entity refs). Postconditions are evaluated during beat verification (tick step 11.5). There is no separate contract store: the old `ContractManager`/`contracts.json` path was removed.

Two further authoring-time guards run in **both** generation paths. `plot/dedup.py:dedup_new_beats()` kills near-verbatim beats (a live run produced 9.2k verbatim characters of repeat): the gauge is `max(plain, sorted-token)` difflib ratio, because a plain ratio cannot separate duplicates from legitimate neighbors; gated by `generation.beat_dedup` (default True), threshold `generation.beat_dedup_threshold`. And `thread_registry.sanitize_beat_thread_ids()` holds authored `thread_id`s to the minted roster (see Story threads). Beat generation also has its own token budget, `generation.beat_max_tokens` (default 2000); the old hardcoded 1000 truncated every contracts-plus-arc-guidance batch.

The **sacred finale** (`coherence.sacred_finale`, default True) is plot-first only: on the final tick Python owns the beat ask outright (`agent/finale.py`, tick step 1), re-rolls the scene against a finale tension cap rather than rewriting it, guarantees an end marker, quarantines the finale's freshly minted loops, and expires the rest. See the tick loop above.

`config.plot.beat_mode` is an older switch (`off | soft_hint | guided | strict`) that predates the full plot-first toggle. `guided` triggers `_update_beats_from_evaluation` to mark beats complete based on `eval_result["beat_hint_alignment"]`. New work should prefer `generation.use_plot_first`.

### Story threads (`agent/thread_registry.py`, `agent/thread_construction.py`)

Groundwork for thread interleaving (`docs/THREAD_INTERLEAVING_DESIGN.md`), where story-level tension control becomes a *scene-selection* policy over a portfolio of threads rather than a property of any one scene. Slice T1 seeded `Thread` objects by normalizing the free-text `plot_threads` labels beats already carried; Slice T1.5 replaced that with the Phase 1 grounded-identity pattern after a backfill over three finished novels showed authored labels are per-beat episode titles, not persistent threads (34 executed beats, 30 distinct labels). So **Python mints thread identity and the LLM selects it**: `thread_roster_section()` puts a roster of exact `TH000`-style ids in the beat-generation prompt, each beat names the ONE thread it serves via `thread_id` (`"new: <name>"` mints a strand), and `sanitize_beat_thread_ids()` holds the authored ids to the roster. Attribution falls back in order: the beat's sanitized `thread_id`, else its first `plot_threads` label, else an implicit `main` thread, so the per-tick trace is total. Persistence is `memory/threads.json` via `MemoryManager` (the `open_loops.json` ownership pattern), ids from the shared counters. `agent/thread_construction.py` is the Slice T4a construction-pressure detector: it computes when construction *would* fire and records the verdict, with no effect on planning. Both are **pure instrumentation**: nothing reads the registry for decisions yet, and the module pattern is `loop_closure.py`/`finale.py` (pure logic here, a thin wrapped hook in `agent.py`, no function may kill a tick). Surfaced by `novel threads`. Knobs: `coherence.thread_identity` (default True; off restores exact T1 behavior), `thread_match_threshold`, `thread_construction_detector`, `construction_floor`/`construction_cutoff`, `thread_min_run`, `convergence_reserve`.

### Scene skeletons and the write-until-concluded loop (`agent/scene_skeleton.py`, `agent/segments.py`)

Two independent pieces of the writer path, both landed after the masters block-grammar study.

`scene_skeleton.py` (contracts Slice 4, **default off**, `generation.enable_scene_skeleton`) samples an ordered, typed paragraph plan for one scene from the block grammar measured on the 21-masterwork corpus (`novel_agent/data/block_grammar_v1.json`, exported by `scripts/block_grammar_tables.py`; every table and caveat in `docs/MASTERS_BLOCK_GRAMMAR_STUDY.md`). The mix is tension-conditioned and the plan rides the writer prompt under the `[n]` marker protocol; `strip_skeleton_markers()` removes the markers from the returned prose and records compliance onto `scene_data["skeleton_compliance"]`. **Sizing is by word budget, not block count:** paragraph length is a property of the mode (measured medians run from 22 words for DIALOGUE to 85 for LORE, in the grammar's `paragraph_words` section), so `generate_skeleton` fills the scene's word target using `mode_word_stats()` and each plan item is rendered with its own measured word range. A flat divisor gave a dialogue scene and an exposition scene the same paragraph count, which a dialogue scene could only reach by packing several speech turns into each paragraph; consecutive DIALOGUE items are now declared one turn each. Regenerate the grammar with `scripts/block_grammar_tables.py --json` (it needs the extracted corpus under the gitignored `work/corpus/`; without it the word section is omitted and everything else still builds). A planner-authored `scene_skeleton` in the plan wins over a sampled one (`writer_context.py:_build_scene_skeleton`). Stdlib-only, side-effect free, and guarded at every call site: a skeleton failure must never cost a scene. Gates A/B/C for the design live in `experiments/block_grammar_poc/`; production results in `docs/SLICE4_SCENE_SKELETON_RESULTS.md`.

`segments.py` owns the write-until-concluded loop, which replaced the writer's flat 3000-token ceiling after it was found truncating 8 of 16 scenes mid-sentence. The invariant it holds: **no scene commits without a detected ending**, whether natural, concluded on request, or trimmed to the last complete sentence and flagged. It coordinates the instructed length with the allowed length (`word_target_for` → `token_budget_for`, from `generation.scene_word_targets` / `default_scene_length` / `tokens_per_word` / `scene_budget_multiplier`), carries all prior prose into each continuation (`continuation_token_budget`, capped at `generation.scene_max_segments`), and detects completion from the backend's `finish_reason` where exposed, falling back to the pure `scene_incomplete()` heuristic for the CLI backends. `write_scene` returns `segments_used` / `concluded_naturally` / `trimmed` alongside the prose. Pure logic: no LLM calls, no I/O, no state. This plumbing was deliberately built so the DSL's per-block writing mode (Slice 5) can reuse it.

### Export (`novel_agent/export/`)

`novel compile --format {markdown,html,prose,epub,pdf}`. The Markdown/HTML/prose paths stay in `cli/commands/compile.py`; the binary formats go through `novel_agent/export/`: `chapters.py` owns the chapter seam (scene = chapter in v1), `metadata.py` the book-level metadata mapping, and `epub.py`/`pdf.py` the two writers. `compile.py` is only the dispatcher, and nothing in `export/` talks to the CLI. Config: `export.author`, `export.language`, `export.page_size`, `export.pdf_engine` (`auto` tries WeasyPrint then pandoc, or name one explicitly). EPUB needs `ebooklib`, a core dependency; **PDF is the optional `storydaemon[export]` extra** because WeasyPrint needs the Pango/Cairo system libraries, with an installed `pandoc` as a silent fallback. PDF is therefore best-effort: `write_pdf` degrades with an instructive message rather than raising.

### Configuration

Defaults live in `novel_agent/configs/config.py:DEFAULT_CONFIG`. `Config.get('llm.model')` uses dot notation; everything in the agent reads through this. Project-level `config.yaml` (created by `create_novel_project`) overrides global. `Config.get()` returns `None` for missing keys unless a default is passed — code in this repo frequently passes a fallback (e.g. `config.get('generation.plot_beats_ahead', 5)`); preserve that pattern, don't assume keys exist.

`llm.model` is the canonical model key; `llm.openai_model` is legacy and still read as a fallback in CLI resolution — keep both paths working. `llm.timeout` (default 300) is honored per call on the `api` backend across every provider; it used to be inert there, letting a hung server hang for 22 minutes.

Knob groups worth knowing before touching config, all in `DEFAULT_CONFIG`:

- **Scene sizing / skeletons**: `generation.scene_length_preset` (`house`, the byte-identical default, or `masters`, calibrated to the corpus per-chapter distribution; an explicit `scene_word_targets` dict that differs from the shipped defaults wins over it, same precedence rule as `coherence.curve_preset`), `scene_word_targets` (`brief|short|long|extended`), `default_scene_length`, `tokens_per_word`, `scene_budget_multiplier`, `scene_max_segments`, `enable_scene_skeleton`.
- **Beat authoring**: `generation.beat_max_tokens`, `beat_dedup`, `beat_dedup_threshold`, `use_contracts`, `rolling_horizon`, `allow_beat_skip`, `fallback_to_reactive`.
- **Arc pressure**: `coherence.target_story_length`, `target_tension_curve`, `curve_preset` (`house` is byte-identical to the shipped curve; the other presets trace to the masters decile tables, and every curve reader including the finale goes through one resolver), `arc_phase_mandate`, `tension_rewrite`, `tension_rewrite_threshold`, `tension_step_for_transition`.
- **Finale**: `coherence.sacred_finale`, `finale_retries`, `ending_hook`.
- **Loop accounting**: `coherence.loop_closure` (judged closure, both the beat and extractor paths), `loop_closure_max_tokens`, `loop_closure_scene_chars`, `extractor_resolutions_judged_cap`, `loop_dedup`, `loop_dedup_threshold` (0.75, recalibrated against two documented near-misses), `loop_creation_cap`.
- **Threads**: `coherence.thread_identity`, `thread_match_threshold`, `thread_construction_detector`, `construction_floor`, `construction_cutoff`, `thread_min_run`, `convergence_reserve`, `demand_gap_trigger`, `calm_threshold`, `serve_margin`.
- **Export**: `export.author`, `export.language`, `export.page_size`, `export.pdf_engine`.

### CLI (`novel_agent/cli/`)

`main.py` is the Typer app exposing `new`, `tick`, `run`, `resume`, `recent`, `status`, `goals`, `metrics`, `threads`, `lore`, `list`, `inspect`, `plan`, `compile`, `checkpoint`, `titles`, `summarize` (registered but still the Phase 2 `TODO` stub at `cli/main.py:759`, which prints and does nothing), plus the `plot` sub-app (`plot status|next|generate|revise|clear`). `find_project_dir()` walks up to 3 parents looking for `state.json`, so most commands work from any subdirectory of a project.

`main.py` remains the Typer app (it owns the command decorators and wires everything up), but the per-command implementation logic now lives in the `cli/commands/` package (`status.py`, `goals.py`, `lore.py`, `metrics.py`, `threads.py`, `list.py`, `inspect.py`, `plan.py`, `compile.py`, `checkpoint.py`, `titles.py`, `plot.py`). `plot revise` (Phase 2) is the manual rolling-horizon trigger — it abandons the pending beats and regenerates them from current canon (`revise_and_regenerate_beats_cli` in `commands/plot.py`). Both the CLI path (`commands/plot.py`) and the agent path (`plot/manager.py`) render the single shared `PLOT_GENERATION_PROMPT_TEMPLATE` in `agent/prompts.py` via `format_plot_generation_prompt`; they differ only in how they assemble the context dict.

Typer quirk worked around in `tick()`: when `tick()` is called programmatically from `resume()`, Typer passes `OptionInfo` objects for unset options. The function defensively coerces them to `None`. Apply the same pattern if you add new programmatically-called commands.

### State machine constraints

- `state["current_tick"]` is the single source of truth for tick number; `_first_tick` runs iff `current_tick == 0`.
- `state["active_character"]` is set lazily on the first tick that produces a character; downstream code (writer context, goal promotion) assumes it can be `None` for tick 0.
- `state["story_goals"]["primary"]` with `source: "user_specified"` blocks the tick-10–15 auto-promotion; `source: "auto_promoted"` records a promotion that happened.

## Conventions specific to this codebase

- IDs are short prefixed strings, zero-padded to 3 digits: `C000`, `L000`, `S000`, `F000`, etc. (`generate_id` uses `f"C{n:03d}"`). Counters are persisted in `memory/counters.json`; allocate via `MemoryManager.generate_*_id()` rather than computing them manually.
- Graceful degradation is the rule for LLM-dependent extractors (`_extract_facts_with_retry`, `_extract_lore_with_retry`, `_verify_beat_execution`): retry once, log, return empty/`True`/`None` on second failure. Don't change these into hard failures without considering the multi-tick `run` loop: it retries a failed tick `--retries` times (default 1, `cli/main.py:run`) before stopping, so a transient backend timeout no longer ends the run — but a *consistent* hard failure still halts it after the retries are exhausted.
- `work/` is the gitignored scratch area where test novels are created (`work/novels/`); never commit anything inside `work/` (the `.gitignore` whitelists only `work/README.md` and `work/.gitkeep`).
- Keep **this file** in the doc sweep by hand. The automated sweeps mostly target `README.md`, `ROADMAP.md` and `docs/`, so `CLAUDE.md` silently rots: it went ~6 weeks and two feature waves out of date before the 2026-09-10 pass. When you land a feature, check whether the tick loop, the config knob groups, or the roadmap shape above needs a line.
- Phase numbers in comments (`# Phase 5`, `# Phase 7A.4`) refer to the *legacy* roadmap in `docs/plan.md` and `docs/archive/`. They tag features, not gated code paths. The newer `Phase 1`–`Phase 4` numbering (e.g. recent `feat: … (Phase 1/2)` commits) refers instead to the **active** roadmap in `docs/EMERGENT_COHERENCE_PLAN.md` — don't conflate the two numbering schemes.

## Roadmap (active: `docs/EMERGENT_COHERENCE_PLAN.md`)

The current direction is **emergent content + high structural constraint**: the LLM decides *what happens*; Python holds it to canon, arc shape, and a short revisable "rolling horizon" of beats regenerated from the prose just written. The layering principle is the thing to internalize: **Python owns where the story should be, the LLM owns how it gets there.**

**`ROADMAP.md` and `docs/EMERGENT_COHERENCE_PLAN.md` §7 are the live status; don't re-derive it from this file.** What follows is the shape, current as of 2026-07-28 (the last feature commit).

- **Phase 1, grounded identity** (the LLM selects names/IDs, never authors them): shipped. Python-grounded `name.generate`, entity references resolved by selection, planner POV/location refs resolved to canonical IDs, and contradiction detection upgraded to a similarity pre-filter + LLM judge. The pattern generalized: it is now also how thread identity works (Slice T1.5).
- **Phase 2, rolling horizon** (lookahead emerges *from* the prose, beats are revisable): shipped, including the `novel plot revise` manual trigger.
- **Phase 3, constraint-as-pressure** (throughline gate, arc-pressure, loop-aging, where the block/sub-block DSL lands): **in progress, and where nearly all recent work sits.** Shipped: the coherence rubric (`novel metrics`), contradiction enforcement (disputed lore filtered out of the planner), the LLM tension scorer, arc-pressure and the arc-phase planner mandate, the arc-into-beats bridge, the throughline gate with its LLM goal-relevance judge, contracts Slice 1 (default off) and Slice 4 scene skeletons (default off), honest loop accounting, the sacred finale, the write-until-concluded scene loop, curve presets, beat dedup, and the thread-interleaving groundwork (registry, thread identity by selection, construction-pressure detector).
- **Phase 4, setup/payoff foresight** (planted-element ledger for clues/reveals): explicitly deferred until 1–3 prove out.

Genuinely open, in rough priority:

1. **Loop-aging**: the top item, and *no code exists for it* (grep finds nothing). Older open loops should surface louder so they get paid off. Twice-evidenced: the descent re-run's resolution ticks opened 8 loops and closed 0, and while contracts can now *check* `loop_resolved`, nothing *pressures* the planner to close loops.
2. **Thread construction and selection** (interleaving Slice T4b): the registry and the detector are in; construction and the selection policy are not. The endgame is that a calm page comes from cutting away to a calmer thread on a cliffhanger, never from becalming a hot event. This matters because the fork experiment falsified prompt surgery: pruning 80% of the writer prompt moved mean tension by 0.0, so the overshoot lives in the *assigned event*. Design: `docs/THREAD_INTERLEAVING_DESIGN.md`.
3. **Contract Slices 2, 3, 5**: precondition pressure; bounded repair plus an `event_occurs` judge; the per-sub-block generation A/B. Scoped in `docs/BLOCKS_CONTRACTS_LANDING_SKETCH.md`. Slice 4's production evidence says Slice 5 is *not* currently needed for `gpt-5.5`; build it only if a chosen writer model does not honor paragraph fullness single-shot.

Two methodological habits this project holds to, worth respecting in new work:

- **Ship the gauge before the pressure.** Both the keyword tension heuristic and the embedding goal-relevance metric were crude gauges that made their pressures unmeasurable, and both were replaced with anchored LLM judges before the pressure was trusted. If a new pressure has no working gauge, build the gauge first.
- **Instrument-only first.** The construction-pressure detector and the thread registry both shipped computing their verdict and recording it with no effect on decisions, so the decision can be made against data. Follow that for the next pressure.
