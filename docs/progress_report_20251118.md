# Progress Report 18th November 2025 (GPT-5.1)

From your README and project layout, I have a solid picture of what StoryDaemon does and how it’s structured. I’ll briefly summarize my understanding so you can confirm I’m aligned, then you can point me to any area you’d like to work on next (e.g., agent loop, memory/vector store, CLI, tests).

## What StoryDaemon Is

- **Goal:** An *agentic long-form fiction generator* that produces scenes iteratively (“story ticks”) rather than from a fixed outline.
- **Core idea:** Narrative structure emerges over time from:
  - A planner LLM choosing tools and scene intentions
  - A writer LLM producing deep-POV prose
  - A rich memory system that tracks characters, locations, goals, open loops, lore, and vectorized context
- **Backend:** Uses Codex CLI (GPT-5 via `codex`) instead of direct API calls, plus Chroma as a vector store, Typer for CLI.

## How the System Works (Tick Loop)

Each `novel tick` roughly does:

1. **Summarize state:** Build context from recent scenes, summaries, memory, lore, goals.
2. **Plan:** Planner LLM produces a JSON plan (tools to call, scene intention, sometimes length guidance).
3. **Execute tools:** Character/location generation, memory search, relationship updates, etc.
4. **Write:** Writer LLM generates the actual scene prose in strict deep POV.
5. **Evaluate:** SceneEvaluator checks POV integrity, continuity, length, etc.
6. **Tension tracking:** Assigns a 0–10 tension score and updates pacing history.
7. **Commit:** SceneCommitter persists scene text and metadata to disk and memory.
8. **Extract facts & lore:** Update entities, open loops, and world rules.
9. **Goal updates:** Track mentions and auto-promote important open loops into higher-level goals.

## Architecture Overview

- **[novel_agent/](cci:7://file:///home/edward/Projects/StoryDaemon/novel_agent:0:0-0:0) (main package)**
  - **`agent/`**
    - [agent.py](cci:7://file:///home/edward/Projects/StoryDaemon/home/edward/Projects/StoryDaemon/novel_agent/agent/agent.py:0:0-0:0): `StoryAgent` orchestrator and main tick loop.
    - `context.py` / `writer_context.py`: Build planner/writer contexts from memory + config.
    - `writer.py`: Scene prose generator.
    - `evaluator.py`: Scene-level checks (quality, continuity, POV).
    - `scene_committer.py`: Handles persistence of scenes and related metadata.
    - `prompts.py`: Prompt templates for planner, writer, evaluator, etc.
  - **`tools/`**
    - Tool base classes + concrete tools:
      - Character/location generation
      - Memory search
      - Relationship tools
      - Name generator (`name_generator.py`, using syllable datasets under `data/names/`)
  - **`memory/`**
    - `entities.py`: Dataclasses for Characters, Locations, Scenes, OpenLoops, Lore, Goals, etc.
    - `manager.py`: `MemoryManager` for CRUD ops, persistence, summaries.
    - `vector_store.py`: Chroma-backed semantic index for scenes/lore/facts.
    - `checkpoint.py`: Snapshot/restore full project state.
  - **`cli/`**
    - `main.py`: Typer-based `novel` CLI entry point.
    - `project.py`: Locate/create project directories, handle UUID-suffixed paths, recent projects.
    - `foundation.py`: Story foundation (genre, premise, protagonist, tone, themes, primary goal).
    - `recent_projects.py`: Global `work/recent_projects.json` handling.
    - `commands/`: Individual CLI commands:
      - `status.py`, `goals.py`, `lore.py`, `list.py`, `inspect.py`, `plan.py`, `compile.py`, `checkpoint.py`, etc.
  - **`configs/`**: Defaults and config helpers.
  - **`data/names/`**: Syllable lists, titles for unique name generation.
  - **`utils/`**: General helpers (file ops, config loading, etc.).

- **Runtime layout ([work/](cci:7://file:///home/edward/Projects/StoryDaemon/work:0:0-0:0))**
  - `work/recent_projects.json`: Global tracker of recent projects (used by `novel recent` / `novel resume`).
  - `work/novels/<title>_<uuid>/`
    - `memory/`: Stored entities and summaries.
    - `scenes/`: Markdown scene files.
    - `plans/`: JSON plans per tick.
    - `checkpoints/`: Snapshots for restore.
    - `errors/`: Error logs, failed plans, etc.
    - `config.yaml`: Project-specific configuration.

- **[docs/](cci:7://file:///home/edward/Projects/StoryDaemon/docs:0:0-0:0)**
  - Detailed spec ([spec.md](cci:7://file:///home/edward/Projects/StoryDaemon/home/edward/Projects/StoryDaemon/docs/spec.md:0:0-0:0)), phased plans and completion notes (`phase*_*.md`), feature docs (tension tracking, lore tracking, name generator, resume workflow, bounded emergence, etc.).
  - This doubles as architecture and evolution history.

- **[tests/](cci:7://file:///home/edward/Projects/StoryDaemon/tests:0:0-0:0)**
  - Unit + integration tests for memory, planner, tools, tension evaluator, lore tracking, CLI workflows, etc.
  - Some manual test scripts for end-to-end validation (e.g., tension tracking on generated stories).

## Feature Pillars I See

- **Bounded Emergence Framework (Phase 7A):**
  - Story foundation (optional but helps shape emergence).
  - Goal hierarchy with auto-promotion based on mentions and ticks.
  - Tension tracking with pacing guidance.
  - Lore extraction and contradiction detection using vector search.
  - Multi-stage planner with semantic context selection to save tokens.

- **Safety & Workflow:**
  - UUID-suffixed project directories to prevent collisions.
  - Recent-projects and resume workflow (`novel recent`, `novel resume`).
  - Configurable per-user and per-project YAML.
  - Automatic checkpointing during multi-tick runs.

---

If you’d like, I can next:

- Walk through a specific subsystem in more depth (e.g., `memory/vector_store.py` since that’s open in your editor).
- Review for design consistency or potential refactors.
- Help extend a particular feature (e.g., new tool, different vector backend, alternative planner strategy).