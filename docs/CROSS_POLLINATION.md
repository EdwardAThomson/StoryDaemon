# Cross-pollination: StoryDaemon and NovelWriter

_Status: draft · created 2026-07-14_

> Purpose: capture what the two novel-generation projects should learn from each
> other, and scope the one piece of shared infrastructure worth extracting. Both
> are Edward's, both generate long-form fiction with LLMs, and today they are fully
> independent codebases with zero shared code. This doc is analysis and planning,
> not a commitment to merge them.

## The two projects at a glance

They are near-opposite designs, which is exactly why the learnings transfer well.

| | **NovelWriter** | **StoryDaemon** |
|---|---|---|
| Philosophy | Outline-first, pre-planned | Emergent, prose-first |
| Interface | Tkinter GUI, human-in-the-loop | `novel` CLI, autonomous |
| Structure | Human clicks staged tabs | Autonomous "story tick" loop |
| Core strength | Genre-deep generation (8 genres, `Generators/`) | Coherence machinery (arc/tension/contracts) |
| Memory | JSON snapshots; ChromaDB RAG built but **unwired** | `MemoryManager` + working `VectorStore` (ChromaDB) |
| Maturity of R&D | Genre generators mature; agentic/QA layer half-built | Coherence subsystems mature, tested, live-validated |
| Activity | Dormant lately | Active (the emergent-coherence roadmap) |

The key asymmetry: StoryDaemon fights to *estimate* "where am I in the story?" from
emergent prose, but NovelWriter **has an outline**, so story position is a real
coordinate. StoryDaemon's hard-won position-aware machinery lands on easier ground
in NovelWriter.

## Learnings that should flow

### StoryDaemon into NovelWriter (the larger opportunity)

Ranked by value-to-effort. These fill gaps NovelWriter has today, several of which
are its own designed-but-inert subsystems.

1. **Tension / arc-pressure stack** (`novel_agent/agent/arc_pressure.py`,
   `tension_scale.py`, `tension_evaluator.py`). Near drop-in: depends only on a
   config object and an optional LLM handle; "tick" is just an integer position
   parameter that maps cleanly to outline position. NovelWriter has **no tension
   control at all**. Most validated code in StoryDaemon (many unit tests + cited
   live-run reports). Transferable insight: make the writer aim at exactly what the
   grader grades (shared 0-10 rubric in `tension_scale.py`).

2. **Grounded name generation** (`novel_agent/tools/name_generator.py` + the three
   JSON banks under `novel_agent/data/names/`). A self-contained class with no LLM,
   memory, config, or tick dependency. Copy-paste port. Makes the LLM *select and
   justify* names from Python-minted, deduped candidates rather than inventing them.
   Caveat: only the sci-fi bank is populated today.

3. **Contradiction detection** (`agent/lore_contradiction_detector.py`): similarity
   pre-filter -> LLM judge -> older-wins canon policy. NovelWriter's consistency
   tracking is string-match + JSON snapshots (`agents/consistency/consistency_tools.py`).
   Algorithm ports; rewrite the checker bodies against NovelWriter's entity shapes.

4. **Wire up NovelWriter's own dormant memory, using StoryDaemon's `VectorStore` as
   the reference.** NovelWriter already has `core/generation/rag_helper.py` (ChromaDB
   + embeddings) that is **commented out and unwired**. StoryDaemon's
   `VectorStore.compute_semantic_similarity()` is a working blueprint.

5. **"Enforce, don't advise" QA lesson.** NovelWriter's review system
   (`agents/writing/chapter_writing_agent.py`) computes quality scores and
   `retry_recommended` flags but **never actually regenerates** (the retry loop was
   designed and left inert). StoryDaemon's bounded rewrite-toward-target
   (`SceneWriter.revise_for_tension`, kept only if closer) is the fix template.

### NovelWriter into StoryDaemon (smaller, but real)

1. **Genre-specialized generation** (`Generators/` + `GenreHandlers/`, ~12.5k LOC
   across 8 genres). NovelWriter's genuine core competency; StoryDaemon's entity and
   world generation is comparatively generic. The genre-conditioning knowledge could
   enrich StoryDaemon's foundation and character generation.

2. **A GUI / inspection surface.** StoryDaemon is CLI-only. NovelWriter's Tkinter tab
   layout is a reference if a visual way to inspect or steer a run is ever wanted.
   Bigger lift, lower priority.

## Recommended minimum

One concrete, low-risk first step: **port the tension/arc-pressure stack into
NovelWriter.** Self-contained, most-validated code available, fills a real gap, and
fits an outline-first tool naturally. Grounded name generation is the easy runner-up.

The LLM-backend consolidation below is higher value but higher touch; treat it as a
separate deliberate project, not the minimum.

---

## Scope: shared LLM-backend library

### Why

Both projects already **duplicate the entire LLM backend layer**, and it is drifting
by hand:

| Shared file | Differing lines (SD vs NW) |
|---|---|
| `multi_provider_llm.py` | 623 (SD ~28KB vs NW ~9KB) |
| `llm_interface.py` | 107 |
| `codex_interface.py` | 78 |
| `claude_cli_interface.py` | 56 |
| `gemini_cli_interface.py` | 46 |

Neither copy is a clean superset:

- **StoryDaemon is ahead on capability**: CLI-agent isolation (`tools/agent_cwd.py:neutral_cwd()`),
  per-call timeouts and model forwarding, the `hosted-llm` and `openrouter` providers,
  and a larger, newer model registry (`gpt-5.5`/`5.4`/`5.2`, `claude-sonnet-4.5`/`haiku-4.5`,
  `gemini-3-*`). It also has unit tests.
- **NovelWriter is ahead on GUI ergonomics**: static `is_available()` probes on each
  CLI interface (used by `check_cli_availability()` to populate backend dropdowns) and
  a `generate_with_retry()` facade. Its model list is **older** (`gpt-4o`, `o3`/`o4-mini`,
  `claude-opus-4-5`), which is itself a symptom of the drift.

### What LLM-Remote-Runner is (and is not)

`LLM-Remote-Runner` is a **TypeScript / pnpm monorepo** (NestJS gateway, SDK, web,
mobile). Models are declared in TS (e.g. `gateway/src/config/app.config.ts`, the
per-provider adapters under `gateway/src/adapters/`). It is therefore the canonical
model-name list **by convention**, not a Python package the two apps can import.
StoryDaemon's `CLAUDE.md` already treats it as the model source of truth and asks that
the Python `_model_config` registry be kept in sync with it by hand.

Implication: the shared artifact must be a **new Python package**, with its own model
registry that is reconciled against LLM-Remote-Runner's TS list (ideally by a small
check, not by memory).

### Proposed package

A standalone, pip-installable Python package (working name `llm-backends`) that both
Python projects depend on. Based on StoryDaemon's more advanced implementation, with
NovelWriter's GUI-oriented additions folded into the common interface.

Contents:

- **Four backend interfaces**: `CodexInterface`, `MultiProviderInterface` (the `api`
  backend routing OpenAI/Anthropic/Gemini + `hosted-llm` + `openrouter`),
  `ClaudeCliInterface`, `GeminiCliInterface`.
- **CLI-agent isolation**: `neutral_cwd()` (all three CLI backends run their
  subprocess from a neutral scratch dir so they do not act on the host repo).
- **Uniform interface protocol**, the union of what both apps need:
  - `generate(prompt, max_tokens=..., timeout=...) -> str`
  - `generate_with_retry(...)` (from NovelWriter)
  - `is_available()` static probe on every interface (from NovelWriter, generalized)
- **Dispatch**: `initialize_llm(backend, model, codex_bin, timeout)` with the existing
  back-compat aliases (`openai`->`api`, `gemini`->`gemini-cli`, `claude`->`claude-cli`).
- **Single model registry**: the `_model_config` key->callable map plus
  `get_supported_models()`, as the one Python source of model truth.
- **Its own tests** (carry StoryDaemon's over; NovelWriter has none for this layer).

Env vars stay as-is (`OPENAI_API_KEY`, `CLAUDE_API_KEY`, `GEMINI_API_KEY`, plus
`HOSTED_LLM_*` and `OPENROUTER_*`).

### Migration plan

1. **Extract.** Create the package from StoryDaemon's `novel_agent/tools/{llm_interface,
   multi_provider_llm,codex_interface,claude_cli_interface,gemini_cli_interface,
   agent_cwd}.py`. Add NovelWriter's `is_available()` probes and `generate_with_retry()`
   to the common interface. Port StoryDaemon's tests.
2. **StoryDaemon adopts it.** Replace those six modules with imports from the package.
   Preserve the current behavior that the agent receives an **explicit** LLM instance
   (not the module-level `_llm_client` singleton). After this, the `gpt-5.5` fallback
   literals in `cli/main.py` and `cli/commands/*.py` should read defaults from the
   package rather than hardcoding (removes the "update the registry AND the fallbacks
   together" footgun noted in `CLAUDE.md`).
3. **NovelWriter adopts it.** `core/generation/ai_helper.py` becomes a thin shim over
   the package. GUI backend/model dropdowns read `get_supported_models()`; the
   availability dropdowns read `is_available()`. This also bumps NovelWriter onto the
   current model list (verify its callers pass models explicitly or update defaults).
4. **Keep LLM-Remote-Runner as the naming source.** Add a lightweight reconciliation
   note or check so the package registry and the TS list cannot silently diverge.

### Risks and watch-items

- **Interface signature mismatch.** NovelWriter's CLI interfaces default to a 120s
  timeout and ignore `max_tokens`; StoryDaemon's add model forwarding, longer
  timeouts, and `neutral_cwd`. The common interface must be a deliberate superset.
- **Model-list bump for NovelWriter.** Adopting the package moves NovelWriter off
  `gpt-4o`/`claude-opus-4-5`. Confirm no caller relies on those exact defaults.
- **Singleton semantics.** StoryDaemon deliberately avoids the `_llm_client` singleton
  in the agent path; the package must keep the explicit-instance pattern available.
- **Distribution.** For two personal repos, `pip install -e` from a local path or a
  git URL is enough; PyPI is optional.

### Open questions (for Edward)

- **Home**: standalone repo (recommended, mirrors the LLM-Remote-Runner "source of
  truth" pattern) vs a package living inside one of the two repos.
- **Name**: `llm-backends`? something else?
- **Distribution**: local editable install / git dependency vs PyPI.

### Effort

Moderate. The extraction plus StoryDaemon migration is the bulk of the work
(StoryDaemon is the richer, tested implementation and the natural base). The
NovelWriter migration is smaller because `ai_helper.py` is already a facade over its
`llm_interface/` package.
