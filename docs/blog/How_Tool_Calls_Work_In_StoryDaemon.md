# How Tool Calls Work in StoryDaemon

The StoryDaemon app uses a structured tool system that allows the AI agent to interact with the story world in a controlled, deterministic way. 

Here's the complete flow:


## 1. Tool Architecture


### Base Tool Class (base.py)

Every tool inherits from the Tool base class, which provides:

* Name: Identifier like "character.generate" or "memory.search"
* Description: What the tool does (shown to LLM)
* Parameters: JSON schema defining required/optional arguments
* execute(): The actual function that runs when called
* validate_args(): Ensures required parameters are present

### Tool Registry (registry.py)

A central registry that:

* Stores all available tools
* Provides tool descriptions to the LLM
* Retrieves tools by name for execution


## 2. The Complete Tool Call Flow

### Step 1: LLM Sees Available Tools

The planner LLM receives a formatted list of all available tools in its prompt (prompts.py):

```markdown
## Available Tools

You can use the following tools to gather information or create entities:

**memory.search** - Search for relevant characters, locations, or scenes using natural language
  Args: query (string), entity_types (array) (optional), limit (integer) (optional)

**character.generate** - Create a new character with initial attributes
  Args: role (string), description (string), name (string) (optional), ...

**location.generate** - Create a new location with initial attributes
  Args: name (string), description (string), ...

```

### Step 2: LLM Decides Which Tools to Use

The LLM analyzes the story state and returns a JSON plan with tool calls (prompts.py):

```json
{
  "rationale": "Need to introduce an ally for the protagonist",
  "scene_intention": "Protagonist meets a potential ally",
  "actions": [
    {
      "tool": "memory.search",
      "args": {
        "query": "dockworkers",
        "limit": 3
      },
      "reason": "Check if any dockworkers already exist"
    },
    {
      "tool": "character.generate",
      "args": {
        "role": "supporting",
        "description": "A gruff but loyal dockhand",
        "traits": ["loyal", "cautious"]
      },
      "reason": "Create the ally character"
    }
  ]
}
```


### Step 3: Plan Execution

The PlanExecutor (runtime.py) executes each action sequentially:

1. Get the tool from the registry (runtime.py)
2. Validate arguments against the tool's schema (runtime.py)
3. Execute the tool with the provided arguments (runtime.py)
4. Collect results for the writer prompt
5. **STOP on first error** - if any tool fails, execution halts

#### Example: What Happens Inside a Tool

When `character.generate` is called, here's what happens internally (memory_tools.py):

1. Auto-generates a name if not provided (using name generator)
2. Checks for duplicates (same name or unique role like "protagonist")
3. Creates a Character entity with all attributes
4. Saves to disk (`memory/characters/C0.json`)
5. Indexes in vector store for semantic search
6. Returns result:

```json
{
  "success": true,
  "character_id": "C0",
  "name": "Kaelen Voss"
}
```

### Step 4: Results Feed Into Writer

All tool results are formatted and included in the writer prompt (writer_context.py):

```markdown
**Tool Results:**
- Searched memory for 'dockworkers': Found 0 results
- Generated new character: Kaelen Voss
```

The writer LLM then uses this information to write the scene.

---

### Putting It All Together: Complete Flow Diagram

Here's the complete flow from planning to scene generation:

┌─────────────────────────────────────────────────────────────┐
│ 1. PLANNER LLM RECEIVES CONTEXT                            │
│    - Recent scenes, open loops, available tools            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. PLANNER RETURNS JSON PLAN                                │
│    {                                                        │
│      "actions": [                                           │
│        {"tool": "character.generate", "args": {...}},       │
│        {"tool": "relationship.create", "args": {...}}       │
│      ]                                                      │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. PLAN EXECUTOR RUNS EACH ACTION                          │
│    - Get tool from registry                                │
│    - Validate arguments                                    │
│    - Execute tool.execute(**args)                          │
│    - Collect results                                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. TOOL PERFORMS OPERATION                                 │
│    - Creates entity (Character, Location, etc.)            │
│    - Saves to disk (memory/characters/C0.json)             │
│    - Indexes in vector store                               │
│    - Returns result {"success": true, "character_id": "C0"}│
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. RESULTS FEED INTO WRITER PROMPT                         │
│    "Tool Results: Generated new character: Kaelen Voss"    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. WRITER LLM WRITES SCENE                                 │
│    Uses character info to write prose                      │
└─────────────────────────────────────────────────────────────┘


## 3. Available Tools

StoryDaemon app has 10 tools organized by domain:

### Memory Tools (`memory_tools.py`)

| Tool | Purpose | Example Use |
|------|---------|-------------|
| `memory.search` | Semantic search across entities | Find characters related to "rebellion" |
| `character.generate` | Create new character | Generate protagonist or NPC |
| `location.generate` | Create new location | Generate a spaceport or hideout |
| `relationship.create` | Establish relationship | Create "mentor-student" bond |
| `relationship.update` | Modify relationship | Change status to "hostile" |
| `relationship.query` | Get character's relationships | See who protagonist knows |
| `faction.generate` | Create organization | Generate a corporation or guild |
| `faction.update` | Modify faction | Update faction's influence |
| `faction.query` | Search factions | Find all "corporate" factions |

### Name Generator (`name_generator.py`)

| Tool | Purpose |
|------|---------|
| `name.generate` | Generate character names |


## 4. Key Design Principles

### Deterministic & Safe

* Tools are deterministic functions, not LLM calls
* They perform controlled operations (create file, search database)
* No direct file system access for the LLM - everything goes through tools

### Fail-Fast Execution

* Execution stops on first error
* Prevents cascading failures
* Makes debugging easier

### Automatic Indexing

* When entities are created/updated, they're automatically indexed in the vector store
* Enables semantic search in future scenes

### Smart Chaining

**What it is:** A mechanism that allows the LLM to pass results from one tool call to the next tool call in the same plan.

**How it works:** When the LLM wants to generate a character name first and then use that name to create a character, it can use a special placeholder syntax: `"<from name.generate>"`.

**Example scenario:**

The LLM plans to create a new character but wants a unique sci-fi name generated first:

```json
{
  "actions": [
    {
      "tool": "name.generate",
      "args": {
        "gender": "neutral",
        "style": "sci-fi"
      },
      "reason": "Generate a unique name for the new ally"
    },
    {
      "tool": "character.generate",
      "args": {
        "role": "supporting",
        "description": "A gruff but loyal dockhand",
        "name": "<from name.generate>"
      },
      "reason": "Create the character with the generated name"
    }
  ]
}
```

**What happens:**

1. `name.generate` executes first and returns: `{"success": true, "full_name": "Kaelen Voss"}`
2. The executor detects the placeholder `"<from name.generate>"` in the next action
3. It **automatically substitutes** the placeholder with the actual generated name: `"Kaelen Voss"`
4. `character.generate` executes with the real name instead of the placeholder

**Why this matters:**

- **Prevents duplicate work**: The LLM doesn't need to invent names (which might conflict with existing characters)
- **Ensures consistency**: The same name is used across tool calls
- **Keeps the system deterministic**: Name generation is handled by a dedicated tool, not hallucinated by the LLM

This is a simple but effective pattern that allows tools to work together sequentially within a single plan.


## Summary

Tool calls are the bridge between the LLM's creative decisions and the deterministic story world state. 

They allow the AI to:

* ✅ Search for relevant past context (semantic memory)
* ✅ Create new entities (characters, locations, factions)
* ✅ Update existing entities (relationships, goals)
* ✅ Query the story state (who knows whom, what factions exist)

All while maintaining data integrity, preventing hallucinations, and ensuring persistent memory across hundreds of scenes.