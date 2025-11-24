# StoryDaemon

**Agentic Novel Generation System with Emergent Narrative**

StoryDaemon is a Python-based system that generates long-form fiction through an autonomous agent that plans, writes, and evolves stories organically. Unlike traditional story generators, StoryDaemon emphasizes emergence over pre-planning, allowing narrative structure to develop naturally through iterative "story ticks."

## Features

- 🤖 **Agentic Architecture** - LLM-driven agent makes autonomous decisions using structured tools
- 📖 **Deep POV Writing** - Strict point-of-view discipline for immersive narrative
- 🧠 **Evolving Memory** - Characters, locations, and story elements dynamically update
- 🎯 **Emergent Structure** - No pre-outlining; story develops organically
- 📚 **Story Foundation** - Optional genre, premise, setting, tone to guide emergence
- 🎯 **Goal Hierarchy** - Protagonist goals emerge naturally or can be user-specified
- 📋 **Plot-First Mode** - Optional emergent plot beats guide scene generation for forward momentum
- ⚡ **Tension Tracking** - Automatic scene tension scoring (0-10) for pacing awareness
- 💰 **Flexible LLM Backends** - Codex CLI, Gemini CLI, Claude Code CLI (zero additional cost), or API backends (GPT-5/5.1, Claude 4.5, Gemini 2.5 Pro)
- 🔧 **Tool-Based System** - Extensible tool registry for character generation, memory search, etc.
- 🔍 **Rich Inspection Tools** - Status, list, inspect, goals commands for full project visibility
- 💾 **Automatic Checkpointing** - Snapshot and restore project state at any point
- 📝 **Manuscript Compilation** - Export to Markdown or HTML with scene filtering
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
  - OpenAI GPT-5/5.1 or newer
  - Claude 4.5 (Anthropic)
  - Gemini 2.5 Pro
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
novel inspect --id C0

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

# Use API backend instead of Codex
novel tick --llm-backend api --llm-model gpt-5.1      # OpenAI GPT-5.1
novel tick --llm-backend api --llm-model claude-4.5   # Anthropic Claude 4.5
novel tick --llm-backend api --llm-model gemini-2.5-pro  # Gemini 2.5 Pro

# Use Gemini CLI backend (local `gemini` binary)
novel tick --llm-backend gemini-cli --llm-model gemini-2.5-pro

# Use Claude Code CLI backend (local `claude` binary, headless mode)
novel tick --llm-backend claude-cli --llm-model claude-4.5
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
│   ├── configs/         # Configuration
│   ├── data/            # Static data files
│   │   └── names/       # Name generation syllables and titles
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
novel compile [--output <file>] [--format markdown|html] [--scenes <range>] [--project <path>]

# Manage checkpoints
novel checkpoint create [--message <msg>] [--project <path>]
novel checkpoint list [--project <path>]
novel checkpoint restore --id <checkpoint_id> [--project <path>]
novel checkpoint delete --id <checkpoint_id> [--project <path>]

# Plot-first mode commands
novel plot generate [--count 5] [--project <path>]
novel plot status [--detailed] [--project <path>]
novel plot next [--project <path>]
```

## Configuration

Global configuration in `~/.storydaemon/config.yaml`:

```yaml
llm:
  backend: codex              # "codex" (Codex CLI), "api" (multi-provider API), "gemini-cli" (Gemini CLI), or "claude-cli" (Claude Code CLI)
  codex_bin_path: codex
  model: gpt-5.1              # Generic API model (gpt-5, gpt-5.1, claude-4.5, gemini-2.5-pro)
  openai_model: gpt-5.1       # Legacy OpenAI-specific key (still honored)
  planner_max_tokens: 1000
  writer_max_tokens: 3000

paths:
  novels_dir: ~/novels

generation:
  max_tools_per_tick: 3
  recent_scenes_count: 3           # Context for planner
  include_overall_summary: true    # Include story-wide summary
  # Scene length is flexible - planner can optionally suggest "brief", "short", "long", or "extended"
  
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
OPENAI_API_KEY   # OpenAI GPT-5/5.1
CLAUDE_API_KEY   # Claude 4.5 (Anthropic)
GEMINI_API_KEY   # Gemini 2.5 Pro
```

## Development Status & Roadmap

StoryDaemon has a mature end-to-end pipeline (agent, memory, writer, evaluator, CLI, and multi-stage planner) and is actively evolving around **emergent plotting and plot-first generation**.

- **High-level status:** Phases 1–7A (bounded emergence) are implemented and used in real projects.
- **Latest:** Phase 5 (Full Emergent Plot-First Tick) is complete - optional plot-first mode with automatic beat generation, beat-constrained writing, and beat verification.
- **Current focus:** Testing plot-first mode in production, Phase 6 enhancements (multi-arc management, beat branching).

For detailed documentation on plot-first mode and emergent plotting:

- [Plot-First Mode User Guide](docs/PLOT_FIRST_MODE_GUIDE.md)
- [Phase 5 Implementation Summary](docs/PHASE5_IMPLEMENTATION_SUMMARY.md)
- [Emergent Plotting Implementation Checklist](docs/IMPLEMENTATION_CHECKLIST_EMERGENT_PLOTTING.md)
- [Architecture Proposal](docs/ARCHITECTURE_PROPOSAL_EMERGENT_PLOTTING.md)
- [Implementation Plan](docs/plan.md)

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

- **Unit Tests:** 34 total tests
  - 22 tests for tension evaluation and guidance
  - 12 tests for lore tracking (dataclass, persistence, vector search, contradictions)
- **Integration Tests:** 10 tests for end-to-end tension tracking in story generation
- **Manual Tests:** 4 comprehensive test suites with real scene generation
- **Production Test:** Successfully generated 5-scene story with accurate tension scoring

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
- Built with Codex CLI and multi-provider API backends (OpenAI, Claude, Gemini)
- Uses Typer for CLI, Chroma for vector storage

---

**Created by Edward A. Thomson**  
[GitHub](https://github.com/EdwardAThomson/StoryDaemon)
