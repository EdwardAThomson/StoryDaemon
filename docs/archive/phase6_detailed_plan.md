# 📋 **Phase 6 Detailed Implementation Plan**

**Phase:** CLI Enhancements and Workflow  
**Goal:** Make the CLI experience smooth for iterative writing and debugging  
**Duration:** 2 days  
**Prerequisites:** Phases 1-5 completed

---

## 1. **Overview**

Phase 6 focuses on enhancing the user experience by adding visibility, control, and convenience features to the CLI. While core commands (`new`, `tick`, `run`, `summarize`) were implemented in Phase 1, this phase adds inspection, debugging, and compilation capabilities.

**Key Principles:**
- **Transparency:** Users should be able to inspect any part of the story state
- **Control:** Users need fine-grained control over execution (dry-run, verbose, debug)
- **Convenience:** Common workflows should be streamlined (compile, checkpoint)
- **Safety:** Dry-run mode prevents accidental overwrites

---

## 2. **Task Breakdown**

### **Task 6.1 — Status and Inspection Commands**

**Objective:** Provide visibility into current story state and entities.

#### **6.1.1 — Implement `novel status` command**

**Purpose:** Display high-level overview of the current novel project.

**Output Format:**
```
📖 Novel: The Crimson Tower
📍 Location: ~/novels/crimson-tower/
🎬 Current Tick: 23
👤 Active POV: C0 (Elena Voss)
📝 Scenes Written: 23
👥 Characters: 5
🗺️  Locations: 8
🔗 Open Loops: 3

Last Scene: scene_023.md (1,247 words)
Last Updated: 2025-11-07 10:32:15
```

**Implementation Details:**
- Read `state.json` for tick count, active character
- Count files in `/scenes/`, `/memory/characters/`, `/memory/locations/`
- Parse `open_loops.json` for loop count
- Get last scene file stats (word count, timestamp)
- Use rich/colorama for formatted output

**File Location:** `novel_agent/cli/commands/status.py`

**Function Signature:**
```python
@app.command()
def status(
    project: Optional[Path] = typer.Option(None, help="Path to novel project"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
) -> None:
    """Display current status of the novel project."""
```

---

#### **6.1.2 — Implement `novel list` command**

**Purpose:** List all entities with filtering and formatting options.

**Subcommands:**
- `novel list characters` — list all characters with IDs and names
- `novel list locations` — list all locations with IDs and names
- `novel list loops` — list all open loops with priorities
- `novel list scenes` — list all scenes with metadata

**Output Format (characters):**
```
👥 Characters (5 total)

  C0  Elena Voss          [POV] Protagonist, detective
  C1  Marcus Chen         Antagonist, corporate executive
  C2  Dr. Sarah Kim       Supporting, scientist
  C3  James Porter        Supporting, journalist
  C4  The Stranger        Mysterious, unknown affiliation
```

**Implementation Details:**
- Load all entity files from respective directories
- Support `--verbose` flag for detailed attributes
- Support `--format json|table|simple` for output formatting
- Add filtering: `--active`, `--pov-only`, `--type <type>`

**File Location:** `novel_agent/cli/commands/list.py`

**Function Signatures:**
```python
@app.command()
def list_characters(
    project: Optional[Path] = typer.Option(None),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    format: str = typer.Option("table", "--format", help="Output format")
) -> None:
    """List all characters in the novel."""

@app.command()
def list_locations(
    project: Optional[Path] = typer.Option(None),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    format: str = typer.Option("table", "--format")
) -> None:
    """List all locations in the novel."""

@app.command()
def list_loops(
    project: Optional[Path] = typer.Option(None),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    format: str = typer.Option("table", "--format")
) -> None:
    """List all open loops in the novel."""

@app.command()
def list_scenes(
    project: Optional[Path] = typer.Option(None),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    format: str = typer.Option("table", "--format")
) -> None:
    """List all scenes in the novel."""
```

---

#### **6.1.3 — Implement `novel inspect` command**

**Purpose:** Deep-dive into a specific entity's complete state.

**Usage:**
```bash
novel inspect --id C0
novel inspect --id L3
novel inspect --id scene_015
novel inspect --file memory/characters/C0.json
```

**Output Format:**
```
🔍 Inspecting Character: C0

Name: Elena Voss
Type: protagonist
Role: Detective
Emotional State: determined, anxious
Inventory: [badge, notebook, phone]
Relationships:
  - C1 (Marcus Chen): antagonistic, suspicious
  - C2 (Dr. Sarah Kim): allied, trusting

Attributes:
  age: 34
  occupation: Homicide Detective
  skills: [investigation, interrogation, forensics]

History (last 5 updates):
  [Tick 23] emotional_state: anxious → determined
  [Tick 21] inventory: added 'notebook'
  [Tick 18] relationships: added C2 (allied)
  [Tick 15] location: moved to L3
  [Tick 12] emotional_state: confident → anxious

Full JSON: /path/to/memory/characters/C0.json
```

**Implementation Details:**
- Support ID-based lookup (C0, L3) and file path lookup
- Pretty-print JSON with syntax highlighting
- Show history timeline in reverse chronological order
- Support `--raw` flag for unformatted JSON output
- Support `--history-limit N` to control history display

**File Location:** `novel_agent/cli/commands/inspect.py`

**Function Signature:**
```python
@app.command()
def inspect(
    id: Optional[str] = typer.Option(None, "--id", help="Entity ID (C0, L3, etc.)"),
    file: Optional[Path] = typer.Option(None, "--file", help="Direct file path"),
    project: Optional[Path] = typer.Option(None),
    raw: bool = typer.Option(False, "--raw", help="Output raw JSON"),
    history_limit: int = typer.Option(5, "--history-limit", help="Number of history entries")
) -> None:
    """Inspect detailed information about an entity."""
```

---

### **Task 6.2 — Plan Preview Command**

**Objective:** Allow users to preview the next plan without executing it.

#### **6.2.1 — Implement `novel plan` command**

**Purpose:** Generate and display the next plan without executing tools or writing scenes.

**Usage:**
```bash
novel plan                    # Preview next plan
novel plan --save preview.json  # Save plan to file
novel plan --verbose          # Show full context sent to planner
```

**Output Format:**
```
📋 Plan Preview (Tick 24)

Rationale:
  Elena needs to confront Marcus about the missing files. This scene
  will escalate tension and reveal his connection to the conspiracy.

Actions:
  1. memory.search(query="Marcus Chen background corporate")
  2. location.update(id="L5", changes={"tension_level": 8})
  3. character.update(id="C0", changes={"emotional_state": "confrontational"})

Scene Intention:
  Tense confrontation in Marcus's office. Elena discovers evidence
  linking him to the cover-up. Deep POV from Elena's perspective.

Estimated Tokens: ~2,400
POV Character: C0 (Elena Voss)

[This plan has NOT been executed. Use 'novel tick' to execute.]
```

**Implementation Details:**
- Reuse planner logic from Phase 3 (`runtime.generate_plan()`)
- Do NOT execute any tools
- Display plan in human-readable format
- Support `--save <file>` to export plan JSON
- Support `--verbose` to show full planner prompt and context
- Add warning that plan is not executed

**File Location:** `novel_agent/cli/commands/plan.py`

**Function Signature:**
```python
@app.command()
def plan(
    project: Optional[Path] = typer.Option(None),
    save: Optional[Path] = typer.Option(None, "--save", help="Save plan to file"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show full context")
) -> None:
    """Preview the next plan without executing it."""
```

---

### **Task 6.3 — Configuration Flags**

**Objective:** Add global flags for controlling execution behavior.

#### **6.3.1 — Implement `--dry-run` flag**

**Purpose:** Simulate execution without making any changes to files.

**Behavior:**
- All file writes are logged but not executed
- LLM calls are made (to validate prompts work)
- Tool execution is simulated
- Clear indication in output that this is a dry-run

**Implementation:**
- Add `dry_run: bool` to global config context
- Modify file write operations to check `dry_run` flag
- Add logging: `[DRY-RUN] Would write to: /path/to/file`
- Wrap in context manager for clean state management

**Example Usage:**
```bash
novel tick --dry-run
novel run --n 3 --dry-run
```

**File Location:** `novel_agent/cli/main.py` (global flag)

---

#### **6.3.2 — Implement `--verbose` flag**

**Purpose:** Show detailed execution information.

**Behavior:**
- Display full prompts sent to LLM
- Show tool execution details (args, results)
- Display token counts for each LLM call
- Show timing information for each step

**Implementation:**
- Add `verbose: bool` to global config context
- Enhance logging throughout codebase
- Use structured logging (loguru or structlog)
- Add timing decorators to key functions

**Example Output:**
```
[VERBOSE] Loading project from: ~/novels/crimson-tower/
[VERBOSE] Current tick: 23
[VERBOSE] Generating plan...
[VERBOSE] Planner prompt (1,234 tokens):
  ┌─────────────────────────────────────
  │ You are a creative writing agent...
  │ [full prompt shown]
  └─────────────────────────────────────
[VERBOSE] Plan generated (456 tokens, 2.3s)
[VERBOSE] Executing action 1/3: memory.search
[VERBOSE]   Args: {"query": "Marcus Chen background"}
[VERBOSE]   Result: 3 matches found (0.1s)
```

**File Location:** `novel_agent/cli/main.py` (global flag)

---

#### **6.3.3 — Implement `--debug` flag**

**Purpose:** Enable maximum debugging information for troubleshooting.

**Behavior:**
- All verbose output plus:
- Stack traces for all errors (not just critical)
- Intermediate data structures (JSON dumps)
- Vector DB query details
- File I/O operations logged
- LLM response raw JSON

**Implementation:**
- Set logging level to DEBUG
- Add debug-only log statements throughout
- Dump intermediate state to `/debug/` directory
- Include system information in output

**File Location:** `novel_agent/cli/main.py` (global flag)

---

### **Task 6.4 — Checkpointing System**

**Objective:** Automatically save project state at regular intervals.

#### **6.4.1 — Implement automatic checkpointing**

**Purpose:** Create snapshots of project state for rollback and safety.

**Checkpoint Structure:**
```
~/novels/<novel-name>/checkpoints/
  checkpoint_tick_010/
    memory/
    scenes/
    plans/
    state.json
    config.yaml
    manifest.json  # Metadata about checkpoint
  checkpoint_tick_020/
    ...
```

**Manifest Format:**
```json
{
  "checkpoint_id": "checkpoint_tick_020",
  "tick": 20,
  "timestamp": "2025-11-07T10:32:15Z",
  "scenes_count": 20,
  "characters_count": 5,
  "locations_count": 8,
  "size_bytes": 1048576,
  "created_by": "novel run --n 10"
}
```

**Implementation Details:**
- Checkpoint every N ticks (configurable, default: 10)
- Use `shutil.copytree` for directory copying
- Compress old checkpoints (optional, configurable)
- Limit number of checkpoints (keep last N, default: 5)
- Add `--checkpoint-interval N` flag to `run` command

**File Location:** `novel_agent/memory/checkpoint.py`

**Function Signatures:**
```python
def create_checkpoint(project_path: Path, tick: int) -> Path:
    """Create a checkpoint of the current project state."""

def list_checkpoints(project_path: Path) -> List[CheckpointManifest]:
    """List all available checkpoints."""

def restore_checkpoint(project_path: Path, checkpoint_id: str) -> None:
    """Restore project state from a checkpoint."""

def cleanup_old_checkpoints(project_path: Path, keep_last: int = 5) -> None:
    """Remove old checkpoints, keeping only the most recent N."""
```

---

#### **6.4.2 — Implement checkpoint management commands**

**Commands:**
- `novel checkpoint create` — manually create checkpoint
- `novel checkpoint list` — list all checkpoints
- `novel checkpoint restore <id>` — restore from checkpoint
- `novel checkpoint delete <id>` — delete a checkpoint

**Example Usage:**
```bash
novel checkpoint create --message "Before major plot twist"
novel checkpoint list
novel checkpoint restore checkpoint_tick_020
novel checkpoint delete checkpoint_tick_010
```

**File Location:** `novel_agent/cli/commands/checkpoint.py`

---

### **Task 6.5 — Compile Command**

**Objective:** Merge all scenes into a single readable manuscript.

#### **6.5.1 — Implement `novel compile` command**

**Purpose:** Combine all scene markdown files into a single document.

**Output Format:**
```markdown
# The Crimson Tower

**Author:** Generated by StoryDaemon  
**Scenes:** 23  
**Generated:** 2025-11-07

---

## Scene 1

[Content of scene_001.md]

---

## Scene 2

[Content of scene_002.md]

---

[... continues for all scenes ...]

---

## Appendix

**Characters:** 5  
**Locations:** 8  
**Total Words:** 28,456
```

**Implementation Details:**
- Read all scene files in order (scene_001.md, scene_002.md, ...)
- Add scene separators and headers
- Include metadata header
- Support `--output <file>` to specify output path (default: `manuscript.md`)
- Support `--format markdown|html|pdf` (PDF requires pandoc)
- Support `--include-metadata` to append character/location lists
- Calculate total word count

**File Location:** `novel_agent/cli/commands/compile.py`

**Function Signature:**
```python
@app.command()
def compile(
    project: Optional[Path] = typer.Option(None),
    output: Path = typer.Option("manuscript.md", "--output", "-o"),
    format: str = typer.Option("markdown", "--format", help="Output format"),
    include_metadata: bool = typer.Option(True, "--include-metadata"),
    scenes: Optional[str] = typer.Option(None, "--scenes", help="Range: 1-10 or 5,7,9")
) -> None:
    """Compile all scenes into a single manuscript."""
```

---

#### **6.5.2 — Add HTML and PDF export (optional)**

**Purpose:** Generate formatted output for reading/sharing.

**HTML Output:**
- Use simple CSS template for readability
- Include table of contents with anchor links
- Responsive design for mobile reading

**PDF Output:**
- Require pandoc installation (check and warn if missing)
- Use pandoc to convert markdown → PDF
- Support custom templates (optional)

**Implementation:**
```python
def compile_to_html(scenes: List[str], output: Path, metadata: dict) -> None:
    """Compile scenes to HTML with styling."""

def compile_to_pdf(scenes: List[str], output: Path, metadata: dict) -> None:
    """Compile scenes to PDF using pandoc."""
```

---

## 3. **File Structure Changes**

```
novel_agent/
  cli/
    commands/
      status.py          # NEW: status command
      list.py            # NEW: list command
      inspect.py         # NEW: inspect command
      plan.py            # NEW: plan preview command
      checkpoint.py      # NEW: checkpoint management
      compile.py         # NEW: compile command
    main.py              # MODIFIED: add global flags
  memory/
    checkpoint.py        # NEW: checkpoint utilities
  utils/
    formatting.py        # NEW: output formatting helpers
    validation.py        # MODIFIED: add dry-run checks
```

---

## 4. **Configuration Updates**

Add to `config.yaml`:

```yaml
cli:
  # Checkpoint settings
  checkpoint_interval: 10  # Create checkpoint every N ticks
  checkpoint_keep_last: 5  # Keep only last N checkpoints
  checkpoint_compress: false  # Compress old checkpoints
  
  # Output formatting
  default_format: table  # table, json, simple
  color_output: true  # Use colored output
  
  # Compile settings
  compile_include_metadata: true
  compile_default_format: markdown
```

---

## 5. **Testing Requirements**

### **Unit Tests**

- `test_status_command.py` — test status output with mock data
- `test_list_command.py` — test listing with various filters
- `test_inspect_command.py` — test entity inspection
- `test_plan_preview.py` — test plan generation without execution
- `test_checkpoint.py` — test checkpoint creation/restoration
- `test_compile.py` — test scene compilation

### **Integration Tests**

- `test_cli_workflow.py` — test complete workflow with all commands
- `test_dry_run.py` — verify dry-run doesn't modify files
- `test_checkpoint_restore.py` — create checkpoint, modify state, restore

### **Edge Cases**

- Empty project (no scenes yet)
- Missing entities (deleted character file)
- Corrupted JSON files
- Invalid checkpoint IDs
- Compile with no scenes

---

## 6. **Implementation Order**

**Day 1:**
1. ✅ Implement `novel status` command (6.1.1)
2. ✅ Implement `novel list` command (6.1.2)
3. ✅ Implement `novel inspect` command (6.1.3)
4. ✅ Add `--dry-run` flag (6.3.1)
5. ✅ Add `--verbose` flag (6.3.2)

**Day 2:**
6. ✅ Implement `novel plan` command (6.2.1)
7. ✅ Implement checkpointing system (6.4.1)
8. ✅ Implement checkpoint commands (6.4.2)
9. ✅ Implement `novel compile` command (6.5.1)
10. ✅ Add `--debug` flag (6.3.3)

**Testing & Polish:**
- Write unit tests for all new commands
- Integration testing with sample project
- Documentation updates
- Error handling and edge cases

---

## 7. **Success Criteria**

**Phase 6 is complete when:**

✅ All inspection commands work (`status`, `list`, `inspect`, `plan`)  
✅ Global flags (`--dry-run`, `--verbose`, `--debug`) function correctly  
✅ Checkpointing system creates and restores snapshots  
✅ Compile command generates readable manuscript  
✅ All commands have comprehensive error handling  
✅ Unit tests pass with >90% coverage  
✅ Integration tests validate end-to-end workflows  
✅ Documentation updated with new command examples

---

## 8. **Dependencies**

**Required Packages:**
- `typer` — CLI framework (already in Phase 1)
- `rich` — Terminal formatting and tables
- `colorama` — Cross-platform colored output
- `tabulate` — Table formatting (alternative to rich)

**Optional Packages:**
- `pandoc` — PDF export (external binary)
- `jinja2` — HTML template rendering

**Add to `requirements.txt`:**
```
rich>=13.0.0
colorama>=0.4.6
tabulate>=0.9.0
jinja2>=3.1.0  # optional
```

---

## 9. **User Experience Examples**

### **Example 1: Checking Project Status**

```bash
$ novel status

📖 Novel: The Crimson Tower
📍 Location: ~/novels/crimson-tower/
🎬 Current Tick: 23
👤 Active POV: C0 (Elena Voss)
📝 Scenes Written: 23
👥 Characters: 5
🗺️  Locations: 8
🔗 Open Loops: 3

Last Scene: scene_023.md (1,247 words)
Last Updated: 2025-11-07 10:32:15
```

### **Example 2: Inspecting a Character**

```bash
$ novel inspect --id C0

🔍 Inspecting Character: C0

Name: Elena Voss
Type: protagonist
Emotional State: determined
Inventory: [badge, notebook, phone]

[... full details ...]
```

### **Example 3: Preview Next Plan**

```bash
$ novel plan

📋 Plan Preview (Tick 24)

Rationale: Elena needs to confront Marcus...

Actions:
  1. memory.search(query="Marcus Chen")
  2. location.update(id="L5", tension_level=8)

[This plan has NOT been executed]
```

### **Example 4: Dry-Run Execution**

```bash
$ novel tick --dry-run

[DRY-RUN] Would execute plan for tick 24
[DRY-RUN] Would call memory.search(query="Marcus Chen")
[DRY-RUN] Would update location L5
[DRY-RUN] Would write scene to: scenes/scene_024.md
[DRY-RUN] No changes made to project
```

### **Example 5: Compile Manuscript**

```bash
$ novel compile --output draft.md --scenes 1-10

✅ Compiled 10 scenes to draft.md
📊 Total words: 12,456
```

---

## 10. **Documentation Updates**

**Files to Update:**
- `README.md` — Add Phase 6 commands to CLI reference
- `docs/cli_reference.md` — Detailed command documentation
- `docs/user_guide.md` — Add workflow examples
- `CHANGELOG.md` — Document Phase 6 additions

**New Documentation:**
- `docs/inspection_guide.md` — How to use inspection commands
- `docs/checkpoint_guide.md` — Checkpoint best practices
- `docs/compilation_guide.md` — Compiling and exporting

---

## 11. **Future Enhancements (Post-Phase 6)**

Ideas for future CLI improvements:

- **Interactive mode:** `novel interactive` — REPL for commands
- **Diff command:** `novel diff <checkpoint1> <checkpoint2>` — compare states
- **Export command:** `novel export --format json` — export entire project
- **Import command:** `novel import <file>` — import project/entities
- **Search command:** `novel search <query>` — full-text search across scenes
- **Stats command:** `novel stats` — detailed analytics (word count trends, character appearances)
- **Validate command:** `novel validate` — check project integrity
- **Repair command:** `novel repair` — fix corrupted files

---

## 12. **Notes**

- Keep commands fast (<1s for inspection commands)
- Use caching where appropriate (entity lists, scene counts)
- Provide helpful error messages with suggestions
- Follow UNIX philosophy: do one thing well
- Support piping and scripting (JSON output mode)
- Maintain backwards compatibility with Phase 1 commands
