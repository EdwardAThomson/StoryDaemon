# **Agentic Novel Generation App — Specification Document**

**Language:** Python 3.11+
**Goal:** Create an adaptive, agentic system for creative writing where a large language model (LLM) drives story generation through structured tool use and incremental world-building. The app builds the story step-by-step (“story ticks”), updating its universe—characters, locations, and lore—as it writes.

---

## 1. **Purpose**

The app generates long-form fiction without predefined plot structures or acts.
Instead, the system begins with minimal seed data—one character, one location, and a directional goal—and **lets narrative structure emerge organically** as the LLM iteratively plans, acts, writes, and reflects.

The system’s design philosophy emphasizes:

* **Emergence over planning** — discovery writing powered by structured reasoning.
* **Deep POV realism** — narrative written through the main character’s perceptions.
* **Memory evolution** — persistent and evolving representations of entities (characters, locations, notes).
* **Tool autonomy** — the LLM decides which tools to use based on story needs.

---

## 2. **High-Level Architecture**

| Component         | Description                                                                                                             |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Agent Runtime** | Orchestrates the novel-writing loop. Calls planner → executes tools → calls writer → evaluates results.                 |
| **Tool Registry** | Provides a consistent interface for the LLM to call functions (generate character, update location, write notes, etc.). |
| **Memory System** | Manages persistent entities: characters, locations, open loops, scenes. Stores both raw text and structured JSON.       |
| **Planner LLM**   | Decides next actions using structured JSON (tool use + scene intention).                                                |
| **Writer LLM**    | Generates narrative prose in deep POV based on the active character and current context.                                |
| **Evaluator**     | Performs lightweight deterministic checks (continuity, POV integrity, contradictions).                                  |
| **CLI Interface** | Command-line driver for starting and managing novel generation sessions.                                                |

---

## 3. **Core Loop (“Story Tick”)**

Each tick produces one coherent passage of story text (roughly 500–900 words).
The agent follows this deterministic skeleton:

1. **Summarize State**

   * Collects last passage summary, unresolved threads, active goals, and current scene metadata.
   * Extracts “open loops” (unanswered questions, unresolved conflicts).

2. **Plan**

   * Planner LLM receives:

     * Current summary + open loops
     * Available tools (character.generate, location.update, memory.search, etc.)
     * Constraints (budget, POV, tone)
   * Returns JSON plan:

     ```json
     {
       "rationale": "Tamsin needs to escape the harbor but needs help.",
       "actions": [
         {"tool": "memory.search", "args": {"query": "dockworkers"}},
         {"tool": "character.generate", "args": {"brief": "brutish but loyal dockhand ally"}},
         {"tool": "location.update", "args": {"id": "L0", "changes": {"tension": "guards patrolling"}}}
       ],
       "scene_intention": "Tamsin persuades a dockhand to help her hide."
     }
     ```

3. **Execute Tools**

   * Each planned action runs through a safe local interface (deterministic functions).
   * Results are added to the memory and fed into the writer prompt.

4. **Write**

   * The Writer LLM generates prose in strict **deep POV** for the active character.
   * Prompt contains:

     * Scene intention
     * Relevant memory snippets
     * Current facts (characters, location state)
     * Style/tone instructions

5. **Evaluate**

   * Checks continuity and POV integrity.
   * Minor revisions requested if inconsistencies detected.

6. **Commit**

   * Final passage is saved (e.g., `/scenes/scene_004.md`).
   * Summaries and extracted entities are updated in memory.
   * New or updated facts pushed to vector DB.

---

## 4. **Memory System**

### 4.1 Structure

Memory is stored in JSON + optional vector database for semantic retrieval.

**Each novel has its own working directory** (e.g., `~/novels/my-story/`) containing:

| Entity       | File                           | Purpose                                 |
| ------------ | ------------------------------ | --------------------------------------- |
| Characters   | `memory/characters/{id}.json` | Stores dynamic character data.          |
| Locations    | `memory/locations/{id}.json`  | Stores evolving location info.          |
| Scenes       | `memory/scenes/{n}.json`      | Scene metadata and summaries.           |
| Open Loops   | `memory/open_loops.json`      | Persistent list of unresolved threads.  |
| Vector Index | `memory/index/`               | Embeddings for quick context retrieval. |
| State        | `state.json`                  | Current tick, active character, etc.    |

**Key principle:** Each novel is self-contained in its own directory, separate from the `novel_agent/` code.

---

## 5. **Dynamic Updates**

Both **characters** and **locations** evolve over time.
After each writing tick, the agent extracts new information from the generated text and merges it into the entity files.

### 5.1 Character Update Rules

Each character JSON holds both static and dynamic fields:

```json
{
  "id": "C0",
  "name": "Tamsin Vale",
  "role": "smuggler",
  "personality": ["quick-witted", "defensive"],
  "goals": ["clear brother’s name"],
  "fears": ["capture", "becoming like her handler"],
  "inventory": ["rusted dagger"],
  "relationships": {"NPC1": "ally", "NPC2": "rival"},
  "last_location": "L0",
  "emotional_state": "tense",
  "last_update_tick": 5
}
```

**When to update**

* After every scene where the character is **present**.
* The LLM or deterministic extractor identifies changes in:

  * Relationships (“now trusts X”, “betrayed Y”)
  * Goals (“primary goal partially fulfilled”)
  * Emotional state (“confidence increasing”)
  * Inventory or injuries.

**How to update**

1. Extract summary lines like “Tamsin gained the map” → update `inventory`.
2. If relationship descriptors appear (“trusted”, “angry at”), update `relationships`.
3. Maintain `history` log within file for traceability:

   ```json
   "history": [
     {"tick": 3, "change": "formed alliance with NPC1"},
     {"tick": 5, "change": "acquired map fragment"}
   ]
   ```

**Automatic merging**

* If a key already exists, append new facts rather than overwrite (unless flagged as contradiction by evaluator).
* Outdated or conflicting facts trigger a short LLM summarization to reconcile.

---

### 5.2 Location Update Rules

```json
{
  "id": "L0",
  "name": "Rainmarket Docks",
  "description": "A maze of wet planks and dim lamps.",
  "sensory": ["salt air", "rope creak", "distant gulls"],
  "threats": ["harbor watch patrols"],
  "inhabitants": ["dockhands", "smugglers"],
  "tension_level": 3,
  "history": [
    {"tick": 1, "event": "introduced"},
    {"tick": 4, "event": "guard patrols increased"}
  ]
}
```

**When to update**

* Whenever the scene occurs within that location.
* If environmental factors change (storm begins, patrols increase, night falls).

**How to update**

* Extract new descriptors or entities associated with that location.
* Merge into fields:

  * `sensory` (new ambient details)
  * `threats`
  * `inhabitants`
  * `tension_level` (numeric intensity metric: 1–5)

**Deterministic support functions**

```python
update_location(id: str, changes: dict)
update_character(id: str, changes: dict)
```

LLM proposals can call these explicitly, or the system can trigger them automatically after each write pass using extraction rules.

---

## 6. **Planner and Writer Prompts**

### 6.1 Planner Prompt

* Receives current story state (POV, summary, open loops, recent goals).
* Lists available tools and their usage rules.
* Returns structured JSON (validated by schema).

Guidelines:

* Max 3 tool calls per tick.
* Use `memory.search` before inventing new lore.
* Only generate a new character if story requires new role.
* Escalate tension every 2–3 ticks.

### 6.2 Writer Prompt (Deep POV)

Rules embedded in prompt:

* Write only what the POV character perceives or infers.
* Emotions via sensory and physical cues, not narration.
* Keep style consistent (e.g., noir, cinematic, introspective).
* Target length: ~500–900 words.

Output validated for POV consistency and narrative progression.

---

## 7. **Evaluation & Continuity**

After each writing tick:

1. **Continuity Check**

   * Validate against existing memory for contradictions.
   * Example: ensure “brother alive” fact isn’t contradicted.

2. **POV Check**

   * Detect third-person omniscient leaks (phrases like *“he didn’t realize…”*).

3. **Revision Pass**

   * If violations found, short LLM call fixes text.

4. **Summary Extraction**

   * Generate 3–5 bullet summary and store in scene JSON.
   * Extract updated facts (entities, relationships, locations).

---

## 8. **Data Flow Diagram (Simplified)**

```
[State Summary]
      ↓
[Planner LLM] → JSON plan (tools + scene intention)
      ↓
[Runtime executes tools]
      ↓
[Writer LLM] → scene text
      ↓
[Evaluator] → (fixes or approve)
      ↓
[Memory Update] → characters, locations, open loops
      ↓
[Next Tick]
```

---

## 9. **Tech Stack**

| Layer         | Tech                                       |
| ------------- | ------------------------------------------ |
| Language      | Python 3.11+                               |
| LLM Interface | Codex CLI (GPT-5) via subprocess           |
| Memory        | JSON + Chroma or FAISS for vector indexing |
| Persistence   | Local filesystem                           |
| CLI / UX      | Typer or Click                             |
| Tests         | Pytest                                     |
| Optional      | SQLite layer for tracking history          |

**Note:** Codex CLI provides zero-additional-cost access to GPT-5. Direct API support (OpenAI, Claude, Gemini) can be added later if needed.

---

## 10. **MVP Goals**

✅ Generate a coherent short story (5–10 scenes).
✅ Maintain and update 3–5 characters and 3–4 locations dynamically.
✅ Enforce deep POV and continuity.
✅ Produce readable markdown output (`/scenes/scene_001.md`, etc.).
✅ CLI commands:

* `novel new` — initialize project
* `novel tick` — run one story iteration
* `novel run --n 5` — run multiple ticks
* `novel summarize` — compile summaries

---

## 11. **Stretch Goals**

* Introduce **Character Arcs**: detect recurring emotional changes, export as chart.
* **Branching narratives**: allow “what if” divergences via saved checkpoints.
* **Critic agents**: style, pacing, thematic alignment reviewers.
* **UI dashboard**: simple web dashboard for live story progression.

---

## 12. **Success Criteria**

* Story progression is organic and internally consistent.
* Entities evolve logically from scene to scene.
* No contradictions between character or location files.
* LLM tool use remains efficient (≤3 calls per tick).
* Generated text maintains consistent POV and tone.
