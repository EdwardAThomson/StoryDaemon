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
- ⚡ **Tension Tracking** - Automatic scene tension scoring (0-10) for pacing awareness
- 💰 **Zero Additional Cost** - Uses Codex CLI for GPT-5 access (included in subscription)
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
# Create a new novel project (gets unique UUID automatically)
novel new my-story --dir work/novels
# → Creates: work/novels/my-story_a1b2c3d4/

# Create with story foundation (interactive mode)
novel new my-story --interactive

# Or from a YAML file
novel new my-story --foundation foundation.yaml

# Or via command-line arguments
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
```

## How It Works

StoryDaemon uses a **story tick loop** where each tick produces one scene passage:

1. **Summarize State** - Collect context from previous passages and memory
2. **Plan** - Planner LLM decides which tools to use, scene intention, and optional length guidance
3. **Execute Tools** - Run character generation, memory search, etc.
4. **Write** - Writer LLM generates prose in deep POV (flexible length based on scene needs)
5. **Evaluate** - Check continuity and POV integrity
6. **Evaluate Tension** - Analyze scene tension (0-10 scale) for pacing awareness
7. **Commit** - Save scene and update memory
8. **Extract Facts** - Update character/location state from scene content
9. **Check Goals** - Promote story goals when conditions are met

### Real-World Example

Here's what tension tracking looks like in a generated story:

```bash
$ novel list scenes

📝 Scenes (5 total)

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
- **Characters** - Dynamic character data with goals, relationships, emotional state
- **Locations** - Evolving location descriptions with sensory details
- **Scenes** - Scene metadata and summaries
- **Open Loops** - Unresolved narrative threads with mention tracking
- **Goal Hierarchy** - Protagonist immediate/arc/story goals with progress tracking
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
│   ├── cli/             # Command-line interface
│   │   ├── main.py             # CLI entry point
│   │   ├── project.py          # Project management
│   │   ├── foundation.py       # Story foundation setup
│   │   ├── recent_projects.py  # Recent projects tracker
│   │   └── commands/           # CLI commands
│   │       ├── status.py       # Status command
│   │       ├── goals.py        # Goals command
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
# Create new novel project (automatically gets UUID suffix)
novel new <name> [--dir <path>]
# Example: novel new my-story → creates my-story_a1b2c3d4/

# Create with story foundation
novel new <name> --interactive                    # Interactive prompts
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

**Phase 7A: Bounded Emergence Framework** 🚧 In Progress
- [x] **7A.1: Story Foundation** - Optional immutable constraints (genre, premise, protagonist, setting, tone, themes, primary goal)
  - [x] Interactive/file/CLI input modes
  - [x] Foundation display in `novel status`
  - [x] Tests for foundation functionality
- [x] **7A.2: Goal Hierarchy** - Protagonist goals and auto-promotion
  - [x] Character goal fields (immediate, arc, story goals)
  - [x] OpenLoop tracking fields (scenes_mentioned, is_story_goal)
  - [x] Auto-promotion logic (ticks 10-15, 5+ mentions)
  - [x] User-specified primary goal support
  - [x] `novel goals` command to view hierarchy
  - [x] Tests for goal promotion logic
- [x] **7A.3: Tension Tracking** - Scene-level tension scoring (0-10 scale) ✅ **TESTED IN PRODUCTION**
  - [x] TensionEvaluator with keyword/structure/emotion analysis
  - [x] Configurable on/off via `enable_tension_tracking`
  - [x] Tension history in planner context with gentle pacing guidance
  - [x] Adaptive suggestions (steady/high/low tension patterns)
  - [x] Visualization in `novel status` and `novel list scenes`
  - [x] Tests for tension evaluation and guidance
  - [x] Real-world story generation test (5 scenes, accurate scoring)
- [ ] **7A.4: Lore Consistency** - World rules and constraint checking
- [ ] **7A.5: Multi-Stage Prompts** - Foundation/goals in planning context

**Phase 7A.1-7A.3 Status:** ✅ Production ready and tested with real story generation

**Phase 7B+:** See [docs/phase7a_bounded_emergence.md](docs/phase7a_bounded_emergence.md) for full roadmap.

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

# Run manual test suite (comprehensive verification)
python tests/manual_tension_test.py
```

### Test Coverage

- **Unit Tests:** 22 tests for tension evaluation and guidance
  - 15 tests for tension evaluation (keyword analysis, structure, emotion, config)
  - 7 tests for tension guidance (steady/high/low patterns, config handling)
- **Integration Tests:** 10 tests for end-to-end tension tracking in story generation
- **Manual Tests:** 4 comprehensive test suites with real scene generation
- **Production Test:** Successfully generated 5-scene story with accurate tension scoring

All Phase 7A.1-7A.3 features have been tested in real story generation and are production-ready.

## Documentation

### Core Documentation
- [Technical Specification](docs/spec.md) - Detailed system design
- [Implementation Plan](docs/plan.md) - Phase-by-phase roadmap

### Phase Documentation
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

### Feature Documentation
- [Phase 7A: Bounded Emergence Framework](docs/phase7a_bounded_emergence.md) - Story foundation and goal hierarchy
- [Name Generator Implementation](docs/name_generator_implementation_plan.md) - Syllable-based name generation
- [Project Safety Improvements](docs/project_safety_improvements.md) - UUID system and scene titles
- [Resume Workflow](docs/resume_workflow.md) - Recent projects and resume commands
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
