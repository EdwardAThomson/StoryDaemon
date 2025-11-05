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

# Generate multiple scenes
novel run --n 5
```

## How It Works

StoryDaemon uses a **story tick loop** where each tick produces one scene passage (500-900 words):

1. **Summarize State** - Collect context from previous passages and memory
2. **Plan** - Planner LLM decides which tools to use and scene intention
3. **Execute Tools** - Run character generation, memory search, etc.
4. **Write** - Writer LLM generates prose in deep POV
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
│   ├── agent/           # Agent runtime
│   ├── tools/           # LLM interface and tools
│   ├── memory/          # Memory management
│   ├── cli/             # Command-line interface
│   ├── configs/         # Configuration
│   └── utils/           # Utilities
├── tests/               # Test suite
├── docs/                # Documentation
│   ├── spec.md         # Technical specification
│   ├── plan.md         # Implementation plan
│   └── phase1_implementation.md
└── ~/novels/            # Generated novels (separate)
    └── my-story/
        ├── memory/
        ├── scenes/
        └── plans/
```

## CLI Commands

```bash
# Create new novel project
novel new <name> [--dir <path>]

# Generate one scene
novel tick [--project <path>]

# Generate multiple scenes
novel run --n <count> [--project <path>]

# Show project status
novel status [--project <path>]

# Compile scene summaries
novel summarize [--project <path>]
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
  target_word_count_min: 500
  target_word_count_max: 900
  max_tools_per_tick: 3
  recent_scenes_count: 3           # Context for planner
  include_overall_summary: true    # Include story-wide summary
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

**Phase 4: Writer and Evaluator** (Next)
- [ ] Writer LLM prompt template
- [ ] Scene text generation
- [ ] Evaluator for continuity/POV checks
- [ ] Scene commit and summarization
- [ ] Memory updates from scenes

**Phase 5-7:** See [docs/plan.md](docs/plan.md) for full roadmap.

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
