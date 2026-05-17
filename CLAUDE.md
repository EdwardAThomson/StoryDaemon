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
7. In plot-first mode, inject `plot_beat` into the plan before building writer context.
8. `WriterContextBuilder.build_writer_context()` → `SceneWriter.write_scene()` → `SceneEvaluator.evaluate_scene()` (raises if `eval_result["passed"]` is False).
9. `TensionEvaluator.evaluate_tension()` (0–10) + `SceneCommitter.commit_scene()` writes the scene and updates summaries/vector index.
10. Beat verification: trust planner if `beat_target.beat_id` matches the current beat (record semantic score as reference); otherwise compute semantic similarity and mark complete if ≥ `beat_verification_threshold`. `_mark_beat_complete()` persists status/score/method to the outline.
11. `CharacterDetector` flags new named entities in prose (`auto_create_minor_characters` controls whether stubs are created).
12. `FactExtractor` → `EntityUpdater.apply_updates()` mutates characters/locations and `_reindex_updated_entities()` re-embeds them.
13. `LoreExtractor` → `_save_lore_items()` persists Lore items, indexes them, and runs `LoreContradictionDetector.update_contradictions()`.
14. `_check_goal_promotion()` (tick 10–15 only) auto-promotes the most-mentioned protagonist loop into `state.story_goals.primary` if it has ≥5 mentions and the user didn't set a primary goal.
15. `state.current_tick += 1` and save.

Failures route through `PlanManager.save_error()` (writes to `errors/`) and re-raise.

### Memory & storage (`novel_agent/memory/`)

Each novel lives in its own directory (`<base>/<name>_<8charUUID>/`) with `state.json`, `config.yaml`, `memory/` (entities, counters, qa, vector index), `scenes/`, `plans/`, `errors/`, `checkpoints/`, optional `plot_outline.json`, optional `prompts/`. `MemoryManager` is the single read/write surface for entities (characters, locations, scenes, factions, lore, open loops, relationships) and owns ID counters in `memory/counters.json` — its constructor backfills any missing counter and reconciles the character counter against files on disk to prevent ID reuse on legacy projects.

`VectorStore` (ChromaDB, `memory/index/`) keeps parallel collections for characters/locations/scenes/lore/factions. Anything mutated in `MemoryManager` should also be re-indexed (the agent does this via `_reindex_updated_entities` and the lore save path). `VectorStore.compute_semantic_similarity()` is what beat verification uses — keep that contract.

### LLM backends (`novel_agent/tools/`)

`initialize_llm(backend, codex_bin, model)` in `llm_interface.py` dispatches to one of four interfaces — `codex` (CodexInterface), `api` (`MultiProviderInterface` routes by model name across OpenAI/Anthropic/Gemini), `gemini-cli`, `claude-cli`. The aliases `openai` → `api`, `gemini` → `gemini-cli`, `claude` → `claude-cli` are supported for back-compat. There is a module-level singleton `_llm_client` used by `send_prompt*`, but the agent receives an explicit instance — don't rely on the singleton inside the agent path.

API env vars: `OPENAI_API_KEY`, `CLAUDE_API_KEY`, `GEMINI_API_KEY`.

### Tools (`novel_agent/tools/`)

Subclasses of `tools/base.py:Tool` register into a `ToolRegistry` in `cli/main.py` (`tick`/`run`). Tool names use dotted form (`character.generate`, `memory.search`, …). The planner sees these tools via `ToolRegistry.get_tools_description()`. `CharacterGenerateTool` takes a `beat_mode` argument that tightens name-generation behavior when plot-first runs in `guided` mode. New tools must be registered in **both** `tick()` and `run()` in `cli/main.py` — these blocks are duplicated; updating only one will silently break the multi-tick flow.

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

`config.plot.beat_mode` is an older switch (`off | soft_hint | guided | strict`) that predates the full plot-first toggle. `guided` triggers `_update_beats_from_evaluation` to mark beats complete based on `eval_result["beat_hint_alignment"]`. New work should prefer `generation.use_plot_first`.

### Configuration

Defaults live in `novel_agent/configs/config.py:DEFAULT_CONFIG`. `Config.get('llm.model')` uses dot notation; everything in the agent reads through this. Project-level `config.yaml` (created by `create_novel_project`) overrides global. `Config.get()` returns `None` for missing keys unless a default is passed — code in this repo frequently passes a fallback (e.g. `config.get('generation.plot_beats_ahead', 5)`); preserve that pattern, don't assume keys exist.

`llm.model` is the canonical model key; `llm.openai_model` is legacy and still read as a fallback in CLI resolution — keep both paths working.

### CLI (`novel_agent/cli/`)

`main.py` is the Typer app exposing `new`, `tick`, `run`, `resume`, `recent`, `status`, `goals`, `lore`, `list`, `inspect`, `plan`, `compile`, `checkpoint`, `titles`, plus the `plot` sub-app (`plot status|next|generate|clear`). `find_project_dir()` walks up to 3 parents looking for `state.json`, so most commands work from any subdirectory of a project.

Typer quirk worked around in `tick()`: when `tick()` is called programmatically from `resume()`, Typer passes `OptionInfo` objects for unset options. The function defensively coerces them to `None`. Apply the same pattern if you add new programmatically-called commands.

### State machine constraints

- `state["current_tick"]` is the single source of truth for tick number; `_first_tick` runs iff `current_tick == 0`.
- `state["active_character"]` is set lazily on the first tick that produces a character; downstream code (writer context, goal promotion) assumes it can be `None` for tick 0.
- `state["story_goals"]["primary"]` with `source: "user_specified"` blocks the tick-10–15 auto-promotion; `source: "auto_promoted"` records a promotion that happened.

## Conventions specific to this codebase

- IDs are short prefixed strings: `C0`, `L0`, `S001`, `F0`, etc. Counters are persisted in `memory/counters.json`; allocate via `MemoryManager.generate_*_id()` rather than computing them manually.
- Graceful degradation is the rule for LLM-dependent extractors (`_extract_facts_with_retry`, `_extract_lore_with_retry`, `_verify_beat_execution`): retry once, log, return empty/`True`/`None` on second failure. Don't change these into hard failures without considering the multi-tick `run` loop, which stops on uncaught exceptions.
- `work/` is the gitignored scratch area where test novels are created (`work/novels/`); never commit anything inside `work/` (the `.gitignore` whitelists only `work/README.md` and `work/.gitkeep`).
- Phase numbers in comments (`# Phase 5`, `# Phase 7A.4`) refer to the roadmap in `docs/plan.md` and `docs/archive/`. They tag features, not gated code paths.
