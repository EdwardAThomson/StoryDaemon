# StoryDaemon

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/EdwardAThomson)

**Agentic Novel Generation System with Emergent Narrative**

StoryDaemon is a Python-based system that generates long-form fiction through an autonomous agent that plans, writes, and evolves stories organically. Unlike my previous [story generator](https://github.com/EdwardAThomson/NovelWriter), StoryDaemon emphasizes emergence over pre-planning, allowing narrative structure to develop naturally through iterative "story ticks."

## YouTube Explainer

An introduction and overview.

* [StoryDaemon: The Future of Story Generation?](https://youtu.be/vIBRLavyxbs)

## Features

- 🤖 **Agentic Architecture** - LLM-driven agent makes autonomous decisions using structured tools
- 📖 **Deep POV Writing** - Strict point-of-view discipline for immersive narrative
- 🧠 **Evolving Memory** - Characters, locations, and story elements dynamically update
- 🎯 **Emergent Structure** - No pre-outlining; story develops organically
- 📚 **Story Foundation** - Optional genre, premise, setting, tone to guide emergence
- 🎯 **Goal Hierarchy** - Protagonist goals emerge naturally or can be user-specified
- 📋 **Plot-First Mode** - Optional emergent plot beats guide scene generation for forward momentum
- ⚡ **Tension Tracking** - LLM-rated scene tension scoring (0-10) for pacing awareness
- 🦴 **Scene Skeletons** (experimental, off by default) - typed paragraph plans sampled from a block grammar measured on 21 classic novels guide the writer toward master-like prose structure, with per-paragraph compliance tracking
- 🎚️ **Coherence Pressures** - Arc-tension targeting, a throughline gate, and contradiction detection keep emergent prose on canon and on arc (see the Emergent Coherence roadmap)
- 💰 **Flexible LLM Backends** - Codex CLI, Gemini CLI, Claude Code CLI (zero additional cost), or API backends (GPT-5.5, Claude Sonnet/Haiku 4.5, Gemini 3, a self-hosted endpoint, or OpenRouter)
- 🔧 **Tool-Based System** - Extensible tool registry for character generation, memory search, etc.
- 🔍 **Rich Inspection Tools** - Status, list, inspect, goals commands for full project visibility
- 💾 **Automatic Checkpointing** - Snapshot and restore project state at any point
- 📝 **Manuscript Compilation** - Export to Markdown, HTML, prose, EPUB, or PDF with scene filtering
- 🎲 **Unique Name Generation** - Syllable-based name generator with 4M+ combinations
- 🔄 **Resume Workflow** - Easily continue recent projects with `novel resume`
- 🆔 **UUID Safety** - Automatic project IDs prevent accidental overwrites

## Quick Start

### Prerequisites

- Python 3.11+
- Codex CLI installed and authenticated (default backend)
  ```bash
  npm install -g @openai/codex-cli
  codex auth
  ```
- (Optional) API access for OpenAI / Claude / Gemini backends
  - OpenAI GPT-5.5 (default) / 5.4 / 5.2
  - Anthropic Claude Sonnet 4.5 / Haiku 4.5
  - Google Gemini 3 (flash/pro preview) or 2.5 (pro/flash)
  - Self-hosted, OpenAI-compatible endpoint via `HOSTED_LLM_URL`, `HOSTED_LLM_PORT`, `HOSTED_LLM_API_KEY`, `HOSTED_LLM_MODEL` env variables (`hosted-llm`)
  - OpenRouter (https://openrouter.ai), a hosted OpenAI-compatible router over many models, via `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` env variables (`openrouter`)
  - Venice (https://venice.ai), an OpenAI-compatible host of open-weight models including uncensored variants, via `VENICE_API_KEY` and `VENICE_MODEL` env variables (`venice`)
- (Optional) Gemini CLI installed (for `llm.backend = gemini-cli`)
  - https://github.com/google-gemini/gemini-cli
- (Optional) Claude Code CLI installed (for `llm.backend = claude-cli`)
  - https://github.com/anthropics/claude-code

### Installation

```bash
# Clone the repository
git clone https://github.com/EdwardAThomson/StoryDaemon.git
cd StoryDaemon

# (Recommended) Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\\Scripts\\activate

# Install dependencies into the virtual environment
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"

# For PDF export, add the optional export extra (pulls in WeasyPrint, which
# also needs the Pango/Cairo system libraries; pandoc is used automatically if
# present). EPUB export works out of the box.
pip install -e ".[export]"
```

### Create Your First Novel

```bash
# Recommended: create a new novel project with interactive story foundation
novel new my-story --dir work/novels
#  Creates: work/novels/my-story_a1b2c3d4/
#  You will be prompted for genre, premise, protagonist, setting, tone, etc.,
#  and to choose the LLM backend/model to store in this project's config.

# Advanced: create a bare project without interactive setup
novel new my-story --dir work/novels --no-interactive

# Or create from a YAML foundation file (non-interactive)
novel new my-story --foundation foundation.yaml

# Or via command-line arguments (non-interactive)
novel new my-story \
  --genre "science fiction" \
  --premise "A lone engineer discovers an alien signal" \
  --protagonist "Curious, isolated technical expert" \
  --setting "Near-future Mars colony" \
  --tone "Contemplative, mysterious"

# Generate your first scene
cd work/novels/my-story_a1b2c3d4
novel tick

# Or generate from anywhere
novel tick --project work/novels/my-story_a1b2c3d4

# Check project status (includes story foundation)
novel status

# View goal hierarchy
novel goals

# Generate multiple scenes with automatic checkpointing
novel run --n 10 --checkpoint-interval 10

# See recent projects (shows UUIDs)
novel recent

# Resume most recent project (no need to type full path!)
novel resume

# Resume specific project by UUID
novel resume --uuid a1b2

# Resume and run multiple ticks
novel resume --n 5

# List what was created (includes tension levels!)
novel list characters
novel list locations
novel list scenes  # Shows tension: 6/10 (rising), 5/10 (rising), etc.

# Inspect a character
novel inspect --id C000

# Compile a manuscript
novel compile --output draft.md

# Save prompts for inspection (Phase 7A.5)
novel tick --save-prompts  # Saves to prompts/ directory

# View lore items (Phase 7A.4)
novel lore list
novel lore list --category world_rules
novel lore list --importance high

# Plot-first mode commands
novel plot generate --count 5    # Generate plot beats
novel plot status --detailed     # View beat status
novel plot next                  # See next pending beat
novel plot clear                 # Clear all beats (with confirmation)

# Use API backend instead of Codex
novel tick --llm-backend api --llm-model gpt-5.5          # OpenAI GPT-5.5 (default)
novel tick --llm-backend api --llm-model claude-sonnet-4.5  # Anthropic Claude Sonnet 4.5
novel tick --llm-backend api --llm-model gemini-3-pro-preview  # Gemini 3 Pro
novel tick --llm-backend api --llm-model hosted-llm      # Self-hosted OpenAI-compatible endpoint
novel tick --llm-backend api --llm-model openrouter      # OpenRouter (routes to whatever OPENROUTER_MODEL names)
novel tick --llm-backend api --llm-model venice          # Venice (uses whatever VENICE_MODEL names, e.g. venice-uncensored)

# Use Gemini CLI backend (local `gemini` binary)
novel tick --llm-backend gemini-cli --llm-model gemini-3-flash-preview

# Use Claude Code CLI backend (local `claude` binary, headless mode)
novel tick --llm-backend claude-cli --llm-model claude-sonnet-4.5
```

## How It Works

StoryDaemon uses a **story tick loop** where each tick produces one scene passage:

1. **Check Plot Beats** (if plot-first mode enabled) - Regenerate beats if needed, get next beat to execute
2. **Summarize State** - Collect context from previous passages and memory
3. **Plan** - Planner LLM decides which tools to use, scene intention, and optional length guidance
4. **Execute Tools** - Run character generation, memory search, etc.
5. **Write** - Writer LLM generates prose in deep POV (flexible length based on scene needs)
   - In plot-first mode, beat constraints are injected into writer context as hard requirements
6. **Evaluate** - Check continuity and POV integrity and compute QA metrics (change/milestone, dialogue density, transitions, mode, novelty) that feed back into planning
7. **Evaluate Tension** - Analyze scene tension (0-10 scale) for pacing awareness
8. **Commit** - Save scene and update memory
9. **Verify Beat** (if plot-first mode enabled) - Check if scene accomplished the target beat, mark complete
10. **Extract Facts** - Update character/location state from scene content
11. **Extract Lore** - Identify world rules, constraints, and capabilities
12. **Check Goals** - Promote story goals when conditions are met

### Real-World Example

Here's what tension tracking looks like in a generated story:

```bash
$ novel list scenes

 Scenes (5 total)

  file          word_count  pov_character  tension_level
  ------------  ----------  -------------  -----------------
  scene_000.md  451         Jynyn          None
  scene_001.md  281         Jynyn          6/10 (rising)
  scene_002.md  340         Jynyn          5/10 (rising)
  scene_003.md  863         Jynyn          6/10 (rising)
  scene_004.md  518         Jynyn          5/10 (rising)
```

**Scene 1 (6/10 - rising):** Discovery of mysterious conduit under ice shelf  
**Scene 2 (5/10 - rising):** Descending into the structure  
**Scene 3 (6/10 - rising):** Examining ancient machinery  
**Scene 4 (5/10 - rising):** Uncovering hidden messages  

The tension naturally oscillates between 5-6/10, maintaining engagement without exhaustion - perfect for a mystery/investigation narrative!

### Memory System

Each novel maintains its own working directory with:

- **Story Foundation** - Optional immutable constraints (genre, premise, protagonist, setting, tone, themes, primary goal)
- **Plot Outline** - Optional emergent plot beats for forward momentum (plot-first mode)
- **Characters** - Dynamic character data with goals, relationships, emotional state
- **Locations** - Evolving location descriptions with sensory details
- **Scenes** - Scene metadata and summaries
- **Open Loops** - Unresolved narrative threads with mention tracking
- **Goal Hierarchy** - Protagonist immediate/arc/story goals with progress tracking
- **Lore** - World rules, constraints, and capabilities with contradiction detection
- **Vector Index** - Semantic search for context retrieval

## Project Structure

```
StoryDaemon/
├── novel_agent/          # Python package (code)
│   ├── agent/           # Agent runtime and orchestration
│   │   ├── agent.py            # StoryAgent orchestrator
│   │   ├── context.py          # Context builder
│   │   ├── writer_context.py   # Writer context builder
│   │   ├── writer.py           # Scene prose generator
│   │   ├── scene_skeleton.py   # Masters-grammar paragraph plans (Slice 4)
│   │   ├── evaluator.py        # Scene quality evaluator
│   │   ├── scene_committer.py  # Scene persistence
│   │   └── prompts.py          # LLM prompt templates
│   ├── tools/           # LLM interface and tools
│   │   ├── name_generator.py   # Syllable-based name generation
│   │   └── ...
│   ├── memory/          # Memory management
│   │   ├── manager.py          # MemoryManager
│   │   ├── entities.py         # Entity dataclasses
│   │   ├── vector_store.py     # ChromaDB integration
│   │   └── checkpoint.py       # Checkpoint system
│   ├── plot/            # Plot management (emergent plotting)
│   │   ├── manager.py          # PlotOutlineManager
│   │   └── entities.py         # PlotBeat, PlotOutline
│   ├── cli/             # Command-line interface
│   │   ├── main.py             # CLI entry point
│   │   ├── project.py          # Project management
│   │   ├── foundation.py       # Story foundation setup
│   │   ├── recent_projects.py  # Recent projects tracker
│   │   └── commands/           # CLI commands
│   │       ├── status.py       # Status command
│   │       ├── goals.py        # Goals command
│   │       ├── lore.py         # Lore command
│   │       ├── plot.py         # Plot commands (generate, status, next)
│   │       ├── list.py         # List commands
│   │       ├── inspect.py      # Inspect command
│   │       ├── plan.py         # Plan preview
│   │       ├── compile.py      # Manuscript compilation
│   │       └── checkpoint.py   # Checkpoint management
│   ├── export/          # Manuscript writers (Markdown, HTML, prose, EPUB, PDF)
│   ├── configs/         # Configuration
│   ├── data/            # Static data files
│   │   ├── names/       # Name generation syllables and titles
│   │   └── block_grammar_v1.json  # Masters block grammar (scene skeletons)
│   └── utils/           # Utilities
├── work/                # Development working directory (gitignored)
│   ├── recent_projects.json  # Recent projects tracker
│   ├── novels/          # Test novels with UUID suffixes
│   │   └── my-story_a1b2c3d4/
│   │       ├── memory/      # Entity storage
│   │       ├── scenes/      # Generated scene markdown files
│   │       ├── plans/       # Plan JSON files
│   │       ├── plot_outline.json  # Plot beats (if using plot-first mode)
│   │       ├── checkpoints/ # Project snapshots
│   │       └── errors/      # Error logs
│   ├── experiments/     # Quick experiments
│   └── scratch/         # Temporary files
├── scripts/             # Analysis and maintenance scripts (corpus tables, repairs)
├── experiments/         # Standalone research experiments (block grammar PoC)
├── tests/               # Test suite
└── docs/                # Documentation
    ├── spec.md         # Technical specification
    ├── plan.md         # Implementation plan
    ├── name_generator_implementation_plan.md  # Name generator design
    ├── project_safety_improvements.md         # UUID and title improvements
    ├── resume_workflow.md                     # Resume command workflow
    └── phase*_*.md     # Phase-specific documentation
```

## CLI Commands

### Core Generation Commands

```bash
# Create new novel project (interactive foundation by default, UUID suffix)
novel new <name> [--dir <path>]
# Example: novel new my-story  creates my-story_a1b2c3d4/ and runs the foundation wizard

# Disable interactive wizard (bare project)
novel new <name> --no-interactive [--dir <path>]

# Create with story foundation (non-interactive variants)
novel new <name> --foundation <yaml_file>         # From YAML file
novel new <name> --genre <genre> --premise <text> # Command-line args

# Generate one scene
novel tick [--project <path>]

# Generate multiple scenes with automatic checkpointing
novel run --n <count> [--checkpoint-interval 10] [--project <path>]

# Compile scene summaries
novel summarize [--project <path>]
```

### Project Management Commands

```bash
# Show recently accessed projects with UUIDs
novel recent [--limit 10]

# Resume most recent project
novel resume [--n 1]

# Resume specific project by UUID (supports partial match)
novel resume --uuid <uuid> [--n 1]
# Example: novel resume --uuid a1b2
```

### Inspection & Management Commands

```bash
# Show project overview (includes story foundation)
novel status [--json] [--project <path>]

# Show goal hierarchy and protagonist goals
novel goals [--json] [--project <path>]

# Show per-tick coherence metrics (loop churn, contradictions, tension vs. target, goal relevance)
novel metrics [--json] [--project <path>]

# List story threads (scenes served, tick run pattern, tension range, members, last activity)
novel threads [--json] [--project <path>]

# Show world lore and rules
novel lore [--group-by category|type|none] [--category <cat>] [--type <type>] [--importance <level>] [--stats] [--json] [--project <path>]

# List entities
novel list characters [-v] [--json] [--project <path>]
novel list locations [-v] [--json] [--project <path>]
novel list loops [-v] [--json] [--project <path>]
novel list scenes [-v] [--json] [--project <path>]

# Inspect entity details
novel inspect --id <ID> [--history-limit 5] [--raw] [--project <path>]
novel inspect --file <path> [--raw]

# Preview next plan without executing
novel plan [--save <file>] [-v] [--project <path>]

# Compile scenes into manuscript
novel compile [--output <file>] [--format markdown|html|prose|epub|pdf] [--include-metadata/--no-metadata] [--scenes <range>] [--project <path>]

# Generate LLM title suggestions from the story's foundation and content
novel titles [--count 10] [--output <file>] [--project <path>]

# Manage checkpoints
novel checkpoint create [--message <msg>] [--project <path>]
novel checkpoint list [--project <path>]
novel checkpoint restore --id <checkpoint_id> [--project <path>]
novel checkpoint delete --id <checkpoint_id> [--project <path>]

# Plot-first mode commands
novel plot generate [--count 5] [--project <path>]
novel plot status [--detailed] [--project <path>]
novel plot next [--project <path>]
novel plot clear [--yes] [--project <path>]
```

## Configuration

Global configuration in `~/.storydaemon/config.yaml`:

```yaml
llm:
  backend: codex              # "codex" (Codex CLI), "api" (multi-provider API), "gemini-cli" (Gemini CLI), or "claude-cli" (Claude Code CLI)
  codex_bin_path: codex
  model: gpt-5.5             # Generic API model (gpt-5.5/5.4/5.2, claude-sonnet-4.5, claude-haiku-4.5, gemini-3-pro-preview, gemini-3-flash-preview, gemini-2.5-pro)
  openai_model: gpt-5.5       # Legacy OpenAI-specific key (still honored)
  planner_max_tokens: 1000
  writer_max_tokens: 3000

paths:
  novels_dir: ~/novels

generation:
  max_tools_per_tick: 3
  recent_scenes_count: 3           # Context for planner
  include_overall_summary: true    # Include story-wide summary
  # Scene length is flexible - planner can optionally suggest "brief", "short", "long", or "extended"
  
  # Scene skeletons (experimental, disabled by default): typed paragraph
  # plans sampled from the masters block grammar guide prose structure
  enable_scene_skeleton: false

  # Plot-first mode (optional, disabled by default)
  use_plot_first: false            # Enable emergent plot-first architecture
  plot_beats_ahead: 5              # Generate this many beats at a time
  plot_regeneration_threshold: 2   # Regenerate when pending beats < this
  verify_beat_execution: true      # Verify beat was accomplished via LLM
  allow_beat_skip: false           # Allow skipping beats that aren't accomplished
  fallback_to_reactive: true       # Fall back to reactive mode if beat generation fails
```

Project-specific configuration in `<project>/config.yaml`.

### API Environment Variables

For API backends, set these environment variables (e.g., in a `.env` file):

```text
OPENAI_API_KEY   # OpenAI GPT-5.5 / 5.4 / 5.2
CLAUDE_API_KEY   # Anthropic Claude Sonnet 4.5 / Haiku 4.5
GEMINI_API_KEY   # Google Gemini 3 / 2.5
OPENROUTER_API_KEY   # OpenRouter (model "openrouter")
OPENROUTER_MODEL     # OpenRouter model to route to, e.g. "anthropic/claude-3.7-sonnet"
VENICE_API_KEY       # Venice (model "venice")
VENICE_MODEL         # Venice model to use, e.g. "venice-uncensored" or "llama-3.3-70b"
```

## Development Status & Roadmap

StoryDaemon has a mature end-to-end pipeline (agent, memory, writer, evaluator, CLI, multi-stage planner, and optional plot-first mode). The active direction is **Emergent Coherence** — *emergent content under high structural constraint*: the LLM decides **what happens** while Python holds it to canon, arc shape, and a short revisable "rolling horizon" of beats regenerated from the prose just written.

The active roadmap is [docs/EMERGENT_COHERENCE_PLAN.md](docs/EMERGENT_COHERENCE_PLAN.md). Current status:

- **Phase 1 — Grounded identity** (the LLM *selects* names/IDs, never authors them) — **shipped.** Python-grounded `name.generate`, resolved entity references, similarity-pre-filtered + LLM-judged contradiction detection.
- **Phase 2 — Rolling horizon** (lookahead emerges *from* the prose; beats are revisable) — **shipped.** Plus the `novel plot revise` trigger.
- **Phase 3 — Constraint-as-pressure** — **in progress.** Shipped: the per-tick coherence rubric (`novel metrics`), contradiction enforcement (disputed-lore quarantine), an **LLM tension scorer** + **arc-pressure** (a target tension curve injected into planner and writer), a **throughline gate** with an **LLM goal-relevance judge**, and the first slice of the **block/sub-block DSL**: scene skeletons (`generation.enable_scene_skeleton`), typed paragraph plans sampled from a block grammar measured on the masters corpus, validated by a production A/B (see [the grammar study](docs/MASTERS_BLOCK_GRAMMAR_STUDY.md) and [the Slice 4 results](docs/SLICE4_SCENE_SKELETON_RESULTS.md)). Still to come: loop-aging and the deeper DSL slices.
- **Phase 4 — Setup/payoff foresight** (planted-element ledger for clues/reveals) — deferred until 1–3 prove out.

Plot-first mode (Phase 5 of the *legacy* roadmap) is complete and available — automatic beat generation, beat-constrained writing, and beat verification — see the guide below. Note the two phase-numbering schemes differ: the legacy roadmap lives in [docs/plan.md](docs/plan.md), the active one in [docs/EMERGENT_COHERENCE_PLAN.md](docs/EMERGENT_COHERENCE_PLAN.md).

- [Emergent Coherence Roadmap](docs/EMERGENT_COHERENCE_PLAN.md) - active direction and status
- [Plot-First Mode User Guide](docs/PLOT_FIRST_MODE_GUIDE.md)
- [Phase 5 Implementation Summary](docs/PHASE5_IMPLEMENTATION_SUMMARY.md)
- [Legacy Implementation Plan](docs/plan.md)

Historical phase documents and older roadmap notes live under `docs/archive/`.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=novel_agent

# Run specific test file
pytest tests/unit/test_file_ops.py

# Run tension tracking tests
pytest tests/unit/test_tension_evaluator.py -v
pytest tests/integration/test_tension_integration.py -v

# Run lore tracking tests
pytest tests/unit/test_lore_tracking.py -v

# Run manual test suite (comprehensive verification)
python tests/manual_tension_test.py
```

### Test Coverage

- **Automated suite:** 800+ tests across `tests/unit/` and `tests/integration/`, covering the
  tick loop, memory/entities, planner, tension scoring, arc-pressure, lore + contradiction
  detection, the coherence rubric, scene skeletons, and the CLI commands. Run with `pytest`.
- **Manual checks:** `python tests/manual_tension_test.py` exercises tension scoring on real
  scene generation (not auto-discovered by pytest).

## Documentation

### Core Documentation
- [Technical Specification](docs/spec.md) - Detailed system design
- [Implementation Plan](docs/plan.md) - Phase-by-phase roadmap

### Phase Documentation
- [Phase 1 Guide](docs/archive/phase1_implementation.md) - Core framework implementation
- [Phase 2 Detailed Plan](docs/archive/phase2_detailed.md) - Memory system design
- [Phase 2 Completion](docs/archive/phase2_completion.md) - Implementation summary
- [Phase 3 Detailed Plan](docs/archive/phase3_detailed.md) - Planner and execution loop design
- [Phase 3 Completion](docs/archive/phase3_completion.md) - Implementation summary
- [Phase 4 Detailed Plan](docs/archive/phase4_detailed.md) - Writer and evaluator design
- [Phase 4 Implementation Summary](docs/archive/phase4_implementation_summary.md) - Implementation summary
- [Phase 5 Detailed Plan](docs/archive/phase5_detailed.md) - Dynamic entity updates design
- [Phase 6 Detailed Plan](docs/archive/phase6_detailed_plan.md) - CLI enhancements design
- [Phase 6 Implementation Summary](docs/archive/phase6_implementation_summary.md) - Implementation summary
- [Phase 6 Quick Reference](docs/archive/phase6_quick_reference.md) - Command reference guide
- [Phase 6 Complete](docs/archive/PHASE6_COMPLETE.md) - Completion summary

### Feature Documentation
- [Phase 7A: Bounded Emergence Framework](docs/archive/phase7a_bounded_emergence.md) - Story foundation and goal hierarchy
- [Plot-First Mode Guide](docs/PLOT_FIRST_MODE_GUIDE.md) - User guide for emergent plot-first generation
- [Phase 5 Implementation Summary](docs/PHASE5_IMPLEMENTATION_SUMMARY.md) - Technical details of plot-first implementation
- [Masters Block Grammar Study](docs/MASTERS_BLOCK_GRAMMAR_STUDY.md) - Block-ordering statistics measured on 21 classic novels; the data behind scene skeletons
- [Scene Skeleton Results](docs/SLICE4_SCENE_SKELETON_RESULTS.md) - Production A/B results, surface-quality pass, and reading notes for Slice 4
- [Name Generator Implementation](docs/archive/name_generator_implementation_plan.md) - Syllable-based name generation
- [Project Safety Improvements](docs/archive/project_safety_improvements.md) - UUID system and scene titles
- [Resume Workflow](docs/archive/resume_workflow.md) - Recent projects and resume commands
- [Agent vs CLI Tools](docs/archive/agent_vs_cli_tools.md) - Understanding tool layers

## Philosophy

StoryDaemon emphasizes:

- **Emergence over planning** - Discovery writing powered by structured reasoning
- **Deep POV realism** - Narrative written through character perception
- **Memory evolution** - Entities grow and change organically
- **Tool autonomy** - LLM decides which tools to use based on story needs

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by my own [NovelWriter](https://github.com/EdwardAThomson/NovelWriter)
- Originally built in Windsurf; later development with Claude Code
- Runs on multi-provider LLM backends (OpenAI, Claude, Gemini, OpenRouter, Venice) and local agent CLIs (Codex, Claude Code, Gemini)
- Uses Typer for CLI, Chroma for vector storage

---

**Created by Edward A. Thomson**  
[GitHub](https://github.com/EdwardAThomson/StoryDaemon)
