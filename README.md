# StoryDaemon

**Agentic Novel Generation System with Emergent Narrative**

StoryDaemon is a Python-based system that generates long-form fiction through an autonomous agent that plans, writes, and evolves stories organically. Unlike traditional story generators, StoryDaemon emphasizes emergence over pre-planning, allowing narrative structure to develop naturally through iterative "story ticks."

## Features

- 🤖 **Agentic Architecture** - LLM-driven agent makes autonomous decisions using structured tools
- 📖 **Deep POV Writing** - Strict point-of-view discipline for immersive narrative
- 🧠 **Evolving Memory** - Characters, locations, and story elements dynamically update
- 🎯 **Emergent Structure** - No pre-outlining; story develops organically
- 💰 **Zero Additional Cost** - Uses Codex CLI for GPT-5 access (included in subscription)
- 🔧 **Tool-Based System** - Extensible tool registry for character generation, memory search, etc.
- 🔍 **Rich Inspection Tools** - Status, list, inspect commands for full project visibility
- 💾 **Automatic Checkpointing** - Snapshot and restore project state at any point
- 📝 **Manuscript Compilation** - Export to Markdown or HTML with scene filtering

## Quick Start

### Prerequisites

- Python 3.11+
- Codex CLI installed and authenticated
  ```bash
  npm install -g @openai/codex-cli
  codex auth
  ```

### Installation

```bash
# Clone the repository
git clone https://github.com/EdwardAThomson/StoryDaemon.git
cd StoryDaemon

# Install dependencies
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Create Your First Novel

```bash
# Create a new novel project
novel new my-story

# Navigate to the project
cd ~/novels/my-story

# Generate your first scene
novel tick

# Check project status
novel status

# Generate multiple scenes with automatic checkpointing
novel run --n 10 --checkpoint-interval 10

# List what was created
novel list characters
novel list locations

# Inspect a character
novel inspect --id C0

# Compile a manuscript
novel compile --output draft.md
```

## How It Works

StoryDaemon uses a **story tick loop** where each tick produces one scene passage:

1. **Summarize State** - Collect context from previous passages and memory
2. **Plan** - Planner LLM decides which tools to use, scene intention, and optional length guidance
3. **Execute Tools** - Run character generation, memory search, etc.
4. **Write** - Writer LLM generates prose in deep POV (flexible length based on scene needs)
5. **Evaluate** - Check continuity and POV integrity
6. **Commit** - Save scene and update memory

### Memory System

Each novel maintains its own working directory with:

- **Characters** - Dynamic character data with goals, relationships, emotional state
- **Locations** - Evolving location descriptions with sensory details
- **Scenes** - Scene metadata and summaries
- **Open Loops** - Unresolved narrative threads
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
│   ├── memory/          # Memory management
│   │   ├── manager.py          # MemoryManager
│   │   ├── entities.py         # Entity dataclasses
│   │   ├── vector_store.py     # ChromaDB integration
│   │   └── checkpoint.py       # Checkpoint system
│   ├── cli/             # Command-line interface
│   │   ├── main.py             # CLI entry point
│   │   ├── project.py          # Project management
│   │   └── commands/           # Phase 6 commands
│   │       ├── status.py       # Status command
│   │       ├── list.py         # List commands
│   │       ├── inspect.py      # Inspect command
│   │       ├── plan.py         # Plan preview
│   │       ├── compile.py      # Manuscript compilation
│   │       └── checkpoint.py   # Checkpoint management
│   ├── configs/         # Configuration
│   └── utils/           # Utilities
├── tests/               # Test suite
├── docs/                # Documentation
│   ├── spec.md         # Technical specification
│   ├── plan.md         # Implementation plan
│   └── phase*_*.md     # Phase-specific documentation
└── ~/novels/            # Generated novels (separate)
    └── my-story/
        ├── memory/      # Entity storage
        ├── scenes/      # Generated scene markdown files
        ├── plans/       # Plan JSON files
        ├── checkpoints/ # Project snapshots
        └── errors/      # Error logs
```

## CLI Commands

### Core Generation Commands

```bash
# Create new novel project
novel new <name> [--dir <path>]

# Generate one scene
novel tick [--project <path>]

# Generate multiple scenes with automatic checkpointing
novel run --n <count> [--checkpoint-interval 10] [--project <path>]

# Compile scene summaries
novel summarize [--project <path>]
```

### Inspection & Management Commands (Phase 6)

```bash
# Show project overview
novel status [--json] [--project <path>]

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
```

## Configuration

Global configuration in `~/.storydaemon/config.yaml`:

```yaml
llm:
  codex_bin_path: codex
  planner_max_tokens: 1000
  writer_max_tokens: 3000

paths:
  novels_dir: ~/novels

generation:
  max_tools_per_tick: 3
  recent_scenes_count: 3           # Context for planner
  include_overall_summary: true    # Include story-wide summary
  # Scene length is flexible - planner can optionally suggest "brief", "short", "long", or "extended"
```

Project-specific configuration in `<project>/config.yaml`.

## Development Status

**Phase 1: Core Framework** ✅ Complete
- [x] Project structure
- [x] File I/O utilities
- [x] Codex CLI interface
- [x] Configuration management
- [x] Basic CLI commands
- [x] Tool base classes

**Phase 2: Memory System** ✅ Complete
- [x] Character/Location/Scene/OpenLoop dataclasses
- [x] Relationship graph with bidirectional perspectives
- [x] Memory manager with CRUD operations
- [x] ChromaDB vector database integration
- [x] Memory tools (search, character.generate, location.generate)
- [x] Relationship tools (create, update, query)
- [x] Scene summarization
- [x] 39 tests passing

**Phase 3: Planner and Execution Loop** ✅ Complete
- [x] Tool base class and ToolRegistry
- [x] Planner LLM prompt template
- [x] Plan JSON schema validation
- [x] Context builder for story state
- [x] Plan executor with error handling
- [x] Plan storage and error logging
- [x] StoryAgent orchestrator
- [x] CLI integration
- [x] 52 tests passing

**Phase 4: Writer and Evaluator** ✅ Complete
- [x] Writer LLM prompt template with deep POV instructions
- [x] WriterContextBuilder for gathering scene context
- [x] SceneWriter for generating 500-900 word prose
- [x] SceneEvaluator for quality checks (word count, POV, continuity)
- [x] SceneCommitter for persisting scenes to disk and memory
- [x] Full integration into StoryAgent tick cycle
- [x] Enhanced CLI output with scene generation steps
- [x] Complete end-to-end scene generation pipeline

**Phase 5: Dynamic Memory Updates** ✅ Complete
- [x] Fact extraction from scene prose
- [x] Character emotional state updates
- [x] Character inventory, goals, and beliefs tracking
- [x] Location state changes
- [x] Open loop creation/resolution from text
- [x] Relationship tracking and updates
- [x] Entity history tracking
- [x] Enhanced continuity checking
- [x] Graceful error handling with retry logic

**Phase 6: CLI Enhancements and Workflow** ✅ Complete
- [x] Enhanced status command with statistics
- [x] List commands (characters, locations, loops, scenes)
- [x] Inspect command for deep entity examination
- [x] Plan preview command (non-destructive)
- [x] Compile command (Markdown/HTML export)
- [x] Checkpoint system (create, list, restore, delete)
- [x] Automatic checkpointing in `novel run`
- [x] JSON output support for all commands
- [x] 10 tests passing

**Phase 7:** See [docs/plan.md](docs/plan.md) for future enhancements.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=novel_agent

# Run specific test file
pytest tests/unit/test_file_ops.py
```

## Documentation

- [Technical Specification](docs/spec.md) - Detailed system design
- [Implementation Plan](docs/plan.md) - Phase-by-phase roadmap
- [Phase 1 Guide](docs/phase1_implementation.md) - Core framework implementation
- [Phase 2 Detailed Plan](docs/phase2_detailed.md) - Memory system design
- [Phase 2 Completion](docs/phase2_completion.md) - Implementation summary
- [Phase 3 Detailed Plan](docs/phase3_detailed.md) - Planner and execution loop design
- [Phase 3 Completion](docs/phase3_completion.md) - Implementation summary
- [Phase 4 Detailed Plan](docs/phase4_detailed.md) - Writer and evaluator design
- [Phase 4 Implementation Summary](docs/phase4_implementation_summary.md) - Implementation summary
- [Phase 5 Detailed Plan](docs/phase5_detailed.md) - Dynamic entity updates design
- [Phase 6 Detailed Plan](docs/phase6_detailed_plan.md) - CLI enhancements design
- [Phase 6 Implementation Summary](docs/phase6_implementation_summary.md) - Implementation summary
- [Phase 6 Quick Reference](docs/phase6_quick_reference.md) - Command reference guide
- [Phase 6 Complete](docs/PHASE6_COMPLETE.md) - Completion summary
- [Agent vs CLI Tools](docs/agent_vs_cli_tools.md) - Understanding tool layers

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
- Built with Codex CLI for GPT-5 access
- Uses Typer for CLI, Chroma for vector storage

---

**Created by Edward A. Thomson**  
[GitHub](https://github.com/EdwardAThomson/StoryDaemon)
