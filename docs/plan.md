# 🧭 **Implementation Plan — Agentic Novel Generation App**

**Author:** Ed T.
**Language:** Python 3.11+
**Target:** CLI-based local app (expandable to web or GUI later)

---

## 1. **Objective**

To implement a modular Python application where:

* An **LLM acts as an autonomous creative agent**.
* The **agent** makes decisions using tool calls (generate characters, update memory, write scenes, etc.).
* The **novel evolves** dynamically through iterative “story ticks.”
* The system maintains **persistent memory** (characters, locations, open loops) and updates entities as the story grows.

---

## 2. **Phase Breakdown**

### **Phase 1 — Core Framework Setup**

**Goal:** Establish a working foundation for agent runtime, tool registry, and CLI.

**Tasks**

1. Create folder structure:

   **Python package structure (code):**
   ```
   novel_agent/
     agent/
     tools/
     memory/
     cli/
     configs/
   tests/
   ```

   **Novel working directories (created by `novel new <name>`):**
   
   Each novel gets its own isolated directory:
   ```
   ~/novels/<novel-name>/
     memory/
       characters/
       locations/
       scenes/
       open_loops.json
       index/          # Vector DB files
     scenes/
       scene_001.md
       scene_002.md
       ...
     plans/
       plan_001.json
       plan_002.json
       ...
     config.yaml       # Novel-specific config
     state.json        # Current tick, active character, etc.
   ```
   
   **Key principle:** Code lives in `novel_agent/`, generated content lives in `~/novels/<novel-name>/` (or user-specified directory).
2. Implement `Tool` base class and registry system.
3. Implement deterministic filesystem-safe tools (foundational layer):

   * `fs.ls`, `fs.read`, `fs.write`
4. Implement Codex CLI wrapper for LLM text generation:

   * `CodexInterface` class — spawns Codex CLI subprocess
   * `llm_interface.py` — simple `send_prompt()` function for GPT-5
   * Error handling and retry logic
   * Configuration for token limits (planner vs writer)

   **Note:** Using Codex CLI provides zero-additional-cost access to GPT-5. Direct API support can be added later if needed.
   
   **Note:** Domain-specific tools (`character.generate`, `character.update`, `location.update`, `memory.search`, etc.) will be implemented in Phases 2-5 using the `entity.action` naming convention.
5. Build CLI (`Typer` or `Click`) with basic commands:

   * `novel new <name> [--dir <path>]` → create new story project in `~/novels/<name>/` (or custom path)
   * `novel tick [--project <path>]` → run one generation step (uses current dir or specified path)
   * `novel run --n 5 [--project <path>]` → run multiple ticks
   * `novel summarize [--project <path>]` → compile summaries of all scenes
   
   **Working directory logic:** Commands look for novel project in current directory first, then fall back to `--project` flag.
6. Define configuration file (`config.yaml`) with:

   * Codex CLI binary path
   * Token limits (planner, writer)
   * Output paths
   * Optional: API keys for fallback providers (if implemented later)

**Deliverable:**
✅ Working CLI with `novel new`, `novel tick`, `novel run`, `novel summarize` commands.
✅ Can call GPT-5 via Codex CLI wrapper and write output to `/scenes/scene_001.md`.
✅ Codex CLI integration verified and working.

---

### **Phase 2 — Memory and Data Structures**

**Goal:** Add persistent structured memory for entities and scenes.

**Tasks**

1. Create JSON schema and Python dataclasses for:

   * `Character`
   * `Location`
   * `OpenLoop`
   * `Scene`
2. Implement memory manager with CRUD operations:

   * `load_entity`, `save_entity`, `update_entity`
3. Add automatic ID assignment (e.g. `C0`, `L0`, etc.).
4. Integrate a **lightweight vector store** (e.g., Chroma) for semantic search.
5. Implement memory-related tools:

   * `memory.search` — semantic search across stored entities
   * `memory.upsert` — insert or update memory entries
   * `character.generate` — create new character with initial attributes
   * `location.generate` — create new location with initial attributes
6. Add summarization helper to generate 3-bullet summaries for scenes.

**Deliverable:**
✅ Character and location files created and persisted under `/memory/characters` and `/memory/locations`.
✅ Vector search returns relevant snippets.

---

### **Phase 3 — Planner and Execution Loop**

**Goal:** Build the agent runtime that decides and acts using tool calls.

**Tasks**

1. Implement **Planner LLM** prompt:

   * Inputs: story summary, open loops, available tools, current POV.
   * Output: structured JSON plan (validated).
2. Define and enforce schema:

   ```json
   {
     "rationale": "string",
     "actions": [{"tool": "string", "args": "object"}],
     "scene_intention": "string"
   }
   ```
3. Implement `runtime.execute_plan()`:

   * Iterates through each action.
   * Executes corresponding tool.
   * Aggregates results for writer prompt.
4. Store the plan and results in a structured log (`/plans/plan_00N.json`).

**Deliverable:**
✅ LLM planner returns structured tool calls and executes them deterministically.
✅ Plan logs stored for transparency.

---

### **Phase 4 — Writer and Evaluator Integration**

**Goal:** Integrate narrative writing and quality checks.

**Tasks**

1. Implement **Writer LLM** prompt template (Deep POV, scene intention, context).
2. Implement **Evaluator** with:

   * **Continuity check** — validate against existing memory for contradictions
   * **POV check** — detect third-person omniscient leaks (regex/heuristic)
   * **Revision pass** — short LLM call to fix violations if detected
3. Add auto-revision step if evaluation fails.
4. Commit final scene:

   * Save markdown text to `/scenes/scene_NNN.md`
   * **Summary extraction** — generate 3-5 bullet summary and store in scene JSON
   * Extract updated facts (entities, relationships, locations)
   * Update entity files (characters, locations)
   * Sync to vector memory

**Deliverable:**
✅ End-to-end flow: plan → execute tools → write scene → evaluate → commit.
✅ Text output adheres to POV rules and updates memory accordingly.

---

### **Phase 5 — Dynamic Entity Updates**

**Goal:** Enable live updates to characters and locations as story progresses.

**Tasks**

1. Implement deterministic update tools:

   * `character.update` — update character attributes (wraps `update_character(id, changes)`)
   * `location.update` — update location attributes (wraps `update_location(id, changes)`)
2. After each tick, extract new facts from scene text:

   * LLM-based extractor (JSON output):

     ```json
     {
       "character_updates": [
         {"id": "C0", "changes": {"emotional_state": "tense", "inventory": ["map fragment"]}}
       ],
       "location_updates": [
         {"id": "L0", "changes": {"tension_level": 4}}
       ]
     }
     ```
3. Merge extracted data into memory files.
4. Maintain `history` array within each entity for traceability.
5. Integrate updates into automatic vector DB sync.

**Deliverable:**
✅ Characters and locations evolve consistently based on generated text.
✅ Facts extracted and merged without overwriting older context.

---

### **Phase 6 — CLI Enhancements and Workflow**

**Goal:** Make the CLI experience smooth for iterative writing and debugging.

**Tasks**

1. Add additional commands:

   * `novel status` — show summary of current state.
   * `novel list` — show all characters, locations, open loops.
   * `novel inspect --id C0` — print entity file.
   * `novel plan` — preview next plan without executing.

   **Note:** Core commands (`new`, `tick`, `run`, `summarize`) implemented in Phase 1.
2. Add configuration flags:

   * `--dry-run`
   * `--verbose`
   * `--debug`
3. Implement checkpointing every N ticks.
4. Add “compile” command to merge all scene markdowns into a full draft.

**Deliverable:**
✅ Usable CLI with complete control and visibility over generation flow.

---

### **Phase 7 — Polishing and Extensions**

**Goal:** Refine and expand system behavior for higher quality writing.

**Tasks**

1. Improve planner heuristics (e.g., avoid redundant tool use).
2. Introduce **tension & cost trackers** for pacing control.
3. Add optional **Critic agent** (style, theme, emotion analysis).
4. Add simple **GUI viewer** (streamlit or flask) for viewing characters, scenes, and world map.

**Deliverable:**
✅ Stable base system with optional advanced features.

---

## 3. **Development Timeline (Rough)**

| Phase   | Description           | Duration |
| ------- | --------------------- | -------- |
| Phase 1 | Framework & CLI setup | 2–3 days |
| Phase 2 | Memory system         | 3–4 days |
| Phase 3 | Planner loop          | 2–3 days |
| Phase 4 | Writer + Evaluator    | 3 days   |
| Phase 5 | Entity updates        | 3–4 days |
| Phase 6 | CLI polish            | 2 days   |
| Phase 7 | Refinements           | ongoing  |

---

## 4. **Key Design Decisions**

* **No pre-outlining**: story emerges from iterative goals and tool use.
* **POV discipline**: writer prompt always locks to one active character.
* **Safe tool execution**: deterministic layer prevents LLM from direct file system control.
* **Composable design**: new tools (e.g., `item.generate`, `emotion.track`) can be added easily.
* **Semantic memory**: vector DB ensures the agent can recall context even after hundreds of scenes.

---

## 5. **Testing Strategy**

| Test Type           | Purpose                                          |
| ------------------- | ------------------------------------------------ |
| Unit Tests          | Validate tool interfaces and schema adherence.   |
| Integration Tests   | End-to-end run for 3 ticks, verify file outputs. |
| Schema Validation   | JSON plans validated via `jsonschema`.           |
| Golden Output Tests | Sample scenes used for regression testing.       |
| Performance         | Ensure low memory footprint across 10+ scenes.   |

---

## 6. **Deliverables Summary**

| Deliverable          | Description                                                                |
| -------------------- | -------------------------------------------------------------------------- |
| `novel_agent/` repo  | Python package with modules for agent, tools, memory, and CLI.             |
| `/memory/`           | Project output directory containing evolving story state (characters, etc). |
| `/scenes/`           | Project output directory with markdown for each generated scene.           |
| `/plans/`            | Project output directory with JSON plan logs for each tick.                |
| `/tests/`            | Unit and integration test files within the package.                        |
| `config.yaml`        | Configuration template for API keys and settings.                          |

---

## 7. **Long-term Vision**

Future enhancements may include:

* Multi-agent collaboration (planner, critic, world-builder).
* Branching storylines and replayable seeds.
* Integration with web-based editor or Notion-like interface.
* Character and world visualizers (map, relationship graphs).
* Multi-model orchestration (e.g., GPT for prose, Claude for reasoning).

