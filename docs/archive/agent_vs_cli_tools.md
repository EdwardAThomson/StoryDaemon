# Agent Tools vs CLI Commands

Understanding the distinction between tools available to the LLM agent and commands available to the user.

---

## Two Separate Layers

StoryDaemon has two distinct layers of functionality:

### 1. Agent Tools (LLM-Callable)
**Location:** `novel_agent/tools/`  
**Purpose:** Functions the LLM agent can call during story generation  
**Access:** Registered in `ToolRegistry` and exposed to the planner LLM

### 2. CLI Commands (User-Facing)
**Location:** `novel_agent/cli/commands/`  
**Purpose:** Commands YOU use to inspect and manage the project  
**Access:** Invoked via `novel <command>` in the terminal

---

## Agent Tools (Phase 2-5)

These are the tools the **LLM agent** can use when generating stories:

| Tool | Purpose | Phase |
|------|---------|-------|
| `memory.search` | Semantic search across entities | 2 |
| `character.generate` | Create new character | 2 |
| `location.generate` | Create new location | 2 |
| `relationship.create` | Create relationship between characters | 5 |
| `relationship.update` | Update existing relationship | 5 |
| `relationship.query` | Query character relationships | 5 |

**How they work:**
1. Agent generates a plan with tool calls
2. Runtime executor calls the tools
3. Tools modify memory/entities
4. Results are passed to the writer

**Example plan:**
```json
{
  "rationale": "Need to introduce the antagonist",
  "actions": [
    {
      "tool": "character.generate",
      "args": {
        "name": "Marcus Chen",
        "role": "antagonist",
        "type": "antagonist"
      }
    },
    {
      "tool": "memory.search",
      "args": {
        "query": "corporate conspiracy"
      }
    }
  ],
  "scene_intention": "Introduce Marcus in his office..."
}
```

---

## CLI Commands (Phase 1 & 6)

These are commands **YOU** use to manage and inspect the project:

### Phase 1 Commands (Core)
| Command | Purpose |
|---------|---------|
| `novel new <name>` | Create new project |
| `novel tick` | Run one generation tick |
| `novel run --n N` | Run N ticks |
| `novel summarize` | Compile summaries |

### Phase 6 Commands (Inspection & Management)
| Command | Purpose |
|---------|---------|
| `novel status` | Show project overview |
| `novel list <type>` | List entities |
| `novel inspect --id <ID>` | Inspect entity details |
| `novel plan` | Preview next plan |
| `novel compile` | Compile manuscript |
| `novel checkpoint <action>` | Manage checkpoints |

**How they work:**
1. You run command in terminal
2. Command reads project files
3. Command displays/modifies data
4. No LLM involvement (except `novel plan`)

---

## Key Differences

| Aspect | Agent Tools | CLI Commands |
|--------|-------------|--------------|
| **Who uses it?** | LLM agent | Human user |
| **When?** | During story generation | Anytime |
| **Purpose** | Generate story content | Inspect/manage project |
| **LLM access** | Yes, via tool registry | No (except `novel plan`) |
| **Modifies story?** | Yes | No (except checkpoints) |
| **Examples** | `character.generate`, `memory.search` | `novel status`, `novel list` |

---

## Why This Separation?

### 1. **Security & Control**
- Agent can't accidentally delete files or corrupt state
- Agent can't create checkpoints (would waste space)
- Agent can't compile manuscripts (not its job)

### 2. **Different Use Cases**
- **Agent tools:** Story generation primitives
- **CLI commands:** Project management and inspection

### 3. **Performance**
- Agent tools are fast, focused operations
- CLI commands can be slower (reading all files, formatting output)

### 4. **Flexibility**
- You can inspect state without affecting generation
- You can preview plans without executing them
- You can restore checkpoints if something goes wrong

---

## Automatic Checkpointing

**Now Implemented!** The `novel run` command automatically creates checkpoints:

```bash
novel run --n 20 --checkpoint-interval 10
```

This will:
- Run 20 ticks
- Create checkpoint at tick 10
- Create checkpoint at tick 20
- Store checkpoints in `checkpoints/` directory

**Default:** Checkpoint every 10 ticks  
**Disable:** Use `--checkpoint-interval 0`

### How It Works

```python
# In novel run command:
for i in range(n):
    # Execute tick
    agent.tick()
    
    # Check if checkpoint needed
    if should_create_checkpoint(current_tick, interval, last_checkpoint):
        create_checkpoint(project_dir, current_tick, "auto")
```

The checkpoint logic uses:
- `should_create_checkpoint()` - Determines if checkpoint needed
- `create_checkpoint()` - Creates the snapshot
- Tracks last checkpoint to avoid duplicates

---

## Could Agent Tools Be CLI Commands?

**Technically yes, but not recommended.**

You could expose agent tools as CLI commands:
```bash
novel character generate --name "John" --role "protagonist"
novel memory search --query "conspiracy"
```

**Why we don't:**
1. **Bypasses the agent** - Defeats the purpose of agentic generation
2. **No context** - Agent tools need story context to work well
3. **Manual work** - You'd have to manually orchestrate everything
4. **Error-prone** - Easy to create inconsistent state

**Better approach:** Use `novel tick` and let the agent decide what tools to use.

---

## Could CLI Commands Be Agent Tools?

**No, and here's why:**

### Commands that make no sense for agent:

**`novel status`** - Agent doesn't need to "see" the overview  
**`novel list`** - Agent already has memory access  
**`novel inspect`** - Agent can use `memory.search` instead  
**`novel compile`** - Agent shouldn't compile manuscripts  
**`novel checkpoint`** - Agent shouldn't manage backups  

### The one exception: `novel plan`

`novel plan` is actually a CLI wrapper around agent planning logic:
- Uses same `ContextBuilder` as agent
- Calls same planner LLM
- Shows what agent would do
- But doesn't execute

This is useful for **debugging** and **previewing** without affecting state.

---

## Future Considerations

### Potential Agent Tools (Future Phases)

These could be added as agent-callable tools:

| Tool | Purpose | Phase |
|------|---------|-------|
| `loop.create` | Create open story loop | 7 |
| `loop.resolve` | Resolve open loop | 7 |
| `tension.increase` | Increase scene tension | 7 |
| `pacing.adjust` | Adjust story pacing | 7 |
| `theme.track` | Track thematic elements | 7 |

### Potential CLI Commands (Future)

These could be added as user-facing commands:

| Command | Purpose |
|---------|---------|
| `novel diff <checkpoint1> <checkpoint2>` | Compare checkpoints |
| `novel search <query>` | Full-text search |
| `novel stats` | Detailed analytics |
| `novel validate` | Check project integrity |
| `novel export --format epub` | Export to EPUB |

---

## Summary

**Agent Tools:**
- ✅ Used BY the agent
- ✅ Called during story generation
- ✅ Modify story state
- ✅ Registered in ToolRegistry
- ❌ Not directly callable by user

**CLI Commands:**
- ✅ Used BY the user
- ✅ Called from terminal
- ✅ Inspect/manage project
- ✅ Registered in Typer app
- ❌ Not callable by agent (except `plan` uses planner logic)

**Automatic Checkpointing:**
- ✅ Implemented in `novel run`
- ✅ Configurable interval
- ✅ Tracks last checkpoint
- ✅ Can be disabled

This separation keeps the system clean, secure, and maintainable!
