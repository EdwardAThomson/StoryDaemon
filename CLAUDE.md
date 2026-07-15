# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

StoryDaemon is an agentic novel-generation system. An LLM-driven `StoryAgent` runs a "story tick" loop (plan → execute tools → write scene → evaluate → extract facts/lore → commit), evolving characters/locations/lore from emergent prose rather than from a pre-baked outline. Python 3.11+, installed as the `novel` CLI via `setup.py`.

## Install & Run

```bash
pip install -e .                    # install package + `novel` entry point
pip install -e ".[dev]"             # add pytest, pytest-cov
```

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
novel tick --llm-backend api --llm-model claude-4.5     # one-off backend override
```

There is no lint/format/typecheck configured in the repo.

Test layout: `tests/unit/` and `tests/integration/` are discovered by `pytest.ini`; loose `tests/test_*.py` files (`test_entities.py`, `test_memory_manager.py`, `test_phase3_basic.py`, `test_phase6_commands.py`, `test_full_text_context.py`) also run. `tests/manual_tension_test.py` is intentionally not auto-discovered (no `test_*` prefix on its functions) — run it directly with `python`.

## Architecture

### The tick loop (`novel_agent/agent/agent.py`)

`StoryAgent.tick()` is the heart of the system. Tick 0 uses a two-phase "first tick" path (`_first_tick`) that splits entity generation from scene writing so the writer sees real IDs; tick 1+ uses `_normal_tick`. The normal pipeline:

1. (Plot-first mode only, tick ≥ `plot_first_start_tick`) regenerate beats if pending < threshold; fetch next pending `PlotBeat`.
2. `ContextBuilder.build_planner_context(state, current_beat=...)` → planner context.
3. Plan via `MultiStagePlanner` (default) or legacy single-stage `_generate_plan`. If a beat is current, `plan_for_beat()` is used.
4. `validate_plan()` (schema in `agent/schemas.py`) → `PlanExecutor.execute_plan()` (runs tool calls).
5. If `active_character` is still None, promote a newly-generated character to active and rewrite the plan's `pov_character`.
6. `PlanManager.save_plan()` snapshots plan + execution results + context to `plans/`.
7. In plot-first mode, inject `plot_beat` into the plan before building writer context (including the beat's `postconditions` when `generation.use_contracts` is on, so the writer sees what will be checked).
8. `WriterContextBuilder.build_writer_context()` → `SceneWriter.write_scene()` → `SceneEvaluator.evaluate_scene()` (raises if `eval_result["passed"]` is False).
9. `TensionEvaluator.evaluate_tension()` (0–10; LLM-rated against an anchored rubric when an LLM is wired in, keyword heuristic as fallback — `tension.use_llm_scorer`) + `SceneCommitter.commit_scene()` writes the scene and updates summaries/vector index.
10. `CharacterDetector` flags new named entities in prose (`auto_create_minor_characters` controls whether stubs are created).
11. `FactExtractor` → `EntityUpdater.apply_updates()` mutates characters/locations and `_reindex_updated_entities()` re-embeds them.
12. Beat verification (`_verify_and_complete_beat`, after the fact/entity steps so state-reading contract checks see the post-scene world): trust planner if `beat_target.beat_id` matches the current beat (record semantic score as reference); otherwise compute semantic similarity and mark complete if ≥ `beat_verification_threshold`. When `generation.use_contracts` is on and the beat carries postconditions, they are evaluated here against the written scene (deterministic checkers, result persisted onto the beat as `contract_results`, never a raise): all passing upgrades `verification_method` to `"contract"`; any failing keeps an otherwise-verified beat from completing and routes to the shared failure path (`_revise_horizon` when `generation.rolling_horizon` is on, else keep pending). `_mark_beat_complete()` persists status/score/method to the outline.
13. `LoreExtractor` → `_save_lore_items()` persists Lore items, indexes them, and runs `LoreContradictionDetector.update_contradictions()`.
14. `_check_goal_promotion()` (tick 10–15 only) auto-promotes the most-mentioned protagonist loop into `state.story_goals.primary` if it has ≥5 mentions and the user didn't set a primary goal.
15. `state.current_tick += 1` and save.
- (Step 7.6, between tension eval and commit) `_maybe_rewrite_for_tension()` — Phase 3 arc-pressure (c): if the scored scene is > `coherence.tension_rewrite_threshold` off the target, one bounded, context-rich revision pass toward it (kept only if closer). Skipped as futile when the gap exceeds what a prose rewrite can close (`rewrite_futile`, gated with `coherence.arc_phase_mandate`). Never raises.
16. `_record_coherence_metrics()` appends one per-tick record to `memory/metrics.jsonl` via `CoherenceMetrics` (Phase 3 instrumentation: loop churn, contradictions detected, tension, `arc_phase`, goal relevance, contract-condition counts). Fully wrapped — a metrics failure never breaks the tick. Also runs in `_first_tick` (with no tension signal).

Failures route through `PlanManager.save_error()` (writes to `errors/`) and re-raise.

### Memory & storage (`novel_agent/memory/`)

Each novel lives in its own directory (`<base>/<name>_<8charUUID>/`) with `state.json`, `config.yaml`, `memory/` (entities, counters, qa, vector index), `scenes/`, `plans/`, `errors/`, `checkpoints/`, optional `plot_outline.json`, optional `prompts/`. `MemoryManager` is the single read/write surface for entities (characters, locations, scenes, factions, lore, open loops, relationships) and owns ID counters in `memory/counters.json` — its constructor backfills any missing counter and reconciles the character counter against files on disk to prevent ID reuse on legacy projects.

`VectorStore` (ChromaDB, `memory/index/`) keeps parallel collections for characters/locations/scenes/lore/factions. Anything mutated in `MemoryManager` should also be re-indexed (the agent does this via `_reindex_updated_entities` and the lore save path). `VectorStore.compute_semantic_similarity()` is what beat verification uses — keep that contract.

### LLM backends (`llm-backends` package; `novel_agent/tools/` shims)

The backend layer lives in the shared `llm-backends` package (sibling checkout, `pip install -e ../llm-backends`; pinned git tag once published, see `requirements.txt`). The six modules `novel_agent/tools/{multi_provider_llm,llm_interface,codex_interface,claude_cli_interface,gemini_cli_interface,agent_cwd}.py` are compatibility shims that alias themselves to the package modules, so old import paths (and test monkeypatch targets) keep working; new code should import from `llm_backends` directly.

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

Contracts (Phase 3, contracts Slice 1, `novel_agent/contracts/`; gated by `generation.use_contracts`, default False): `PlotBeat` carries `preconditions`/`postconditions`/`contract_results`. Conditions are beat-embedded, authored at beat-generation time from the closed checker vocabulary in `contracts/conditions.py` (registry: `entity_exists`, `char_at_location`, `char_in_prose`, `prose_contains`, `tension_at_least`, `tension_at_most`, `loop_resolved`) and sanitized in both generation paths (`contracts/authoring.py:sanitize_beat_conditions`, same sanitize-not-trust pattern as entity refs). Postconditions are evaluated during beat verification (tick step 10). There is no separate contract store: the old `ContractManager`/`contracts.json` path was removed.

`config.plot.beat_mode` is an older switch (`off | soft_hint | guided | strict`) that predates the full plot-first toggle. `guided` triggers `_update_beats_from_evaluation` to mark beats complete based on `eval_result["beat_hint_alignment"]`. New work should prefer `generation.use_plot_first`.

### Configuration

Defaults live in `novel_agent/configs/config.py:DEFAULT_CONFIG`. `Config.get('llm.model')` uses dot notation; everything in the agent reads through this. Project-level `config.yaml` (created by `create_novel_project`) overrides global. `Config.get()` returns `None` for missing keys unless a default is passed — code in this repo frequently passes a fallback (e.g. `config.get('generation.plot_beats_ahead', 5)`); preserve that pattern, don't assume keys exist.

`llm.model` is the canonical model key; `llm.openai_model` is legacy and still read as a fallback in CLI resolution — keep both paths working.

### CLI (`novel_agent/cli/`)

`main.py` is the Typer app exposing `new`, `tick`, `run`, `resume`, `recent`, `status`, `goals`, `metrics`, `threads`, `lore`, `list`, `inspect`, `plan`, `compile`, `checkpoint`, `titles`, plus the `plot` sub-app (`plot status|next|generate|revise|clear`). `find_project_dir()` walks up to 3 parents looking for `state.json`, so most commands work from any subdirectory of a project.

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
- Phase numbers in comments (`# Phase 5`, `# Phase 7A.4`) refer to the *legacy* roadmap in `docs/plan.md` and `docs/archive/`. They tag features, not gated code paths. The newer `Phase 1`–`Phase 4` numbering (e.g. recent `feat: … (Phase 1/2)` commits) refers instead to the **active** roadmap in `docs/EMERGENT_COHERENCE_PLAN.md` — don't conflate the two numbering schemes.

## Roadmap (active: `docs/EMERGENT_COHERENCE_PLAN.md`)

The current direction is **emergent content + high structural constraint**: the LLM decides *what happens*; Python holds it to canon, arc shape, and a short revisable "rolling horizon" of beats regenerated from the prose just written. Status as of 2026-07-10:

- **Phase 1 — Grounded identity** (the LLM selects names/IDs, never authors them): shipped — Python-grounded `name.generate`, entity references resolved by selection, writer-introduced names grounded, planner POV/location refs resolved to canonical IDs, the two beat-generation prompts unified onto `PLOT_GENERATION_PROMPT_TEMPLATE` (both `plot/manager.py` and `cli/commands/plot.py` render it), and contradiction detection upgraded from a coarse type heuristic to a similarity pre-filter + LLM judge (`LoreContradictionDetector`, tick step 13). Detection now *records* a verdict per pair (`Lore.contradiction_details`: confirmed partner, canon = older item, reason); it does **not** yet enforce — quarantining the non-canon item is deliberately deferred to Phase 3.
- **Phase 2 — Rolling horizon** (lookahead emerges *from* the prose, beats are revisable): core shipped — rolling-horizon beat revision plus the `novel plot revise` CLI trigger.
- **Phase 3 — Constraint-as-pressure** (throughline gate, arc-pressure, loop-aging, where the block/sub-block DSL lands): in progress.
  - The **coherence rubric** prerequisite is built — `CoherenceMetrics` (`agent/coherence_metrics.py`) records per-tick signals (loop churn, contradictions detected, disputed-lore count, tension, target tension + delta, goal relevance) to `memory/metrics.jsonl`, viewable via `novel metrics`; pure instrumentation (no behavior change) so the pressures can be measured.
  - **Contradiction enforcement** (pressure) shipped — when a contradiction is confirmed, `update_contradictions` marks the non-canon (newer) item `Lore.status = "disputed"` (gated by `lore.enforce_contradictions`, default True); the planner's `MultiStagePlanner._active_lore()` filters disputed lore out of the only place lore feeds generation. Disputed lore stays on disk (shown as `⊘ disputed` in `novel lore`). Older = canon; no auto-revert if later resolved (future work).
  - **Tension control (arc-pressure, iterated)** — the 0-10 tension scale is unified in `agent/tension_scale.py` (single `TENSION_ANCHORS` source of truth: grading definition + situational writing ingredients per band), so the writer aims at exactly what the scorer grades. Live runs showed tension lives in the *events*, not the prose, so control is layered: the **planner** sets event-level tension and stages transitions for big drops (`arc_pressure_guidance_for_planner`, continuity-aware via `last_scene_tension`); the **writer** gets the target band's ingredients up front (`arc_pressure_guidance_for_writer`); and a bounded **rewrite** polishes prose toward the target *within* that transition (`SceneWriter.revise_for_tension`, gated by `coherence.tension_rewrite`, kept only if closer). `coherence.tension_step_for_transition` (default 3) defines a "drop that needs a transition."
  - **LLM tension scorer** shipped — `TensionEvaluator` (`agent/tension_evaluator.py`) now LLM-rates *dramatic* tension across the full 0–10 range (anchored rubric, `tension.use_llm_scorer`, heuristic fallback). The old keyword heuristic measured pulp surface vocabulary and collapsed real prose to a flat ~6 (proven on a 71-scene run: range 4–8, never calm/climactic), which made arc-pressure's `tension_delta` meaningless. This is the working *gauge* arc-pressure steers against.
  - **Arc-pressure** (pressure) shipped — `agent/arc_pressure.py` interpolates a target tension over story position (`progress = current_tick / coherence.target_story_length`, against the `coherence.target_tension_curve` control points) and injects it into **both** the planner's strategic prompt (`_build_strategic_prompt`, soft one-liner `arc_pressure_guidance`) and the **writer** prompt (`WriterContextBuilder._build_arc_pressure_section` → `{arc_pressure_section}`, the firmer band-specific `arc_pressure_guidance_for_writer` — added because the planner-only nudge was empirically too gentle). The writer section is suppressed when a plot beat already carries a `tension_target` (the beat governs). Python owns *where* tension should be; the LLM owns *how*. Set the curve to `None` to disable. The rubric records `target_tension`/`tension_delta` so adherence is measurable. `target_story_length` is the main knob — set it to the intended length (short story vs. novel). **Validated 2026-06 (`docs/progress_report_20260602.md`):** over two ~16-20 tick `claude-cli` runs it *tracks rising targets* (mean drift ~1.2, slight upward bias) but **cannot de-escalate for a resolution** — at a sharp downward target the planner keeps choosing tense *events* and the prose rewrite can't lower them (the LLM scorer correctly rates a real confrontation 7-8; a calm denouement control scores 1, so the floor is the *planner*, not the gauge or the writer). The fix, an **arc-*phase* planner mandate** rather than a stronger rewrite, shipped (next bullet).
  - **Arc-phase planner mandate** (pressure) shipped and validated: `derive_arc_phase` (`agent/arc_pressure.py`) reads the phase (rising/peak/falling/resolution) off the tension curve's *shape*; `ARC_PHASE_MANDATES` puts a firm per-phase event mandate into the planner's arc-pressure guidance; `rewrite_futile` skips the step-7.6 prose rewrite when the gap is too big for prose to close; `arc_phase` lands in per-tick metrics (recorded even when the mandate is off). Gated by `coherence.arc_phase_mandate` (default True). **Validated 2026-07 (`docs/progress_report_20260709.md`, descent re-run vs the June control):** the planner now chooses aftermath events in the resolution phase (final scene 8 to 6 against target 4; resolution drift 2.35 to 1.65), so the June failure mode is gone; residuals: the ending is subdued rather than calm (little descent runway in the default curve), the rising phase ran hotter than control at n=1, and the "close open loops" clause did not bite (ticks 14-15 opened 8 loops, closed 0: direct evidence for loop-aging).
  - **Beat-generation bridge** shipped: in plot-first mode the same curve/phase governs beat *authoring* (`beat_tension_schedule`, `arc_guidance_for_beats`, `reconcile_beat_tension_targets` in `agent/arc_pressure.py`; shares the mandate's gate, no new knob), wired through both generation paths (`plot/manager.py`, `cli/commands/plot.py`); LLM-authored `tension_target`s are reconciled against the schedule after parsing (fill/clamp/replace, sanitize not trust).
  - **Contracts Slice 1** ("contracts ride the beats", per `docs/BLOCKS_CONTRACTS_LANDING_SKETCH.md`) shipped, **default off** (`generation.use_contracts`): `PlotBeat` carries `preconditions`/`postconditions`/`contract_results`; postconditions are authored at beat-generation time from the closed checker vocabulary (`contracts/authoring.py`), sanitized in both paths, evaluated during beat verification (pass upgrades `verification_method` to `contract`; failure routes to keep-pending or horizon revision), and counted in `CoherenceMetrics` (`contract_conditions_checked`/`_failed`). The old `ContractManager`/`contracts.json` store and the separate step-8.7 check are removed. Slices 2-5 (precondition pressure, bounded repair + `event_occurs` judge, scene skeletons, per-sub-block generation A/B) are scoped in the landing sketch.
  - **Throughline gate** (pressure) shipped — `agent/throughline.py` injects the primary goal (`story_goals.primary.description`) into the planner's strategic prompt so scenes serve the throughline (`coherence.throughline_pressure`, default True; dormant until a goal exists). Fixed a latent bug: the planner read `state.get('story_goal')` (never set) and so had never seen the goal.
  - **LLM goal-relevance judge** shipped — the rubric's `goal_relevance` is now an LLM judge (0–10, anchored "serves-the-goal" rubric, `coherence.use_llm_goal_relevance`, default True) instead of embedding cosine similarity to the goal *sentence*. The old gauge measured topical overlap, not "advances the goal," and an A/B showed no change — the same crude-gauge failure as the keyword tension heuristic. `CoherenceMetrics` (`agent/coherence_metrics.py`) now takes the agent's `self.llm`; the judge retries once and falls back to the embedding gauge (scaled to 0–10), recording `goal_relevance_method` (`llm`/`embedding`) + `goal_relevance_rationale`. This is the working *gauge* the throughline gate steers against.
  - Still to come: loop-aging (now twice-evidenced, see above), and the remaining contract slices (2-5).
- **Phase 4 — Setup/payoff foresight** (planted-element ledger for clues/reveals): explicitly deferred until 1–3 prove out.
