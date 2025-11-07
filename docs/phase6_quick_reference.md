# Phase 6 CLI Quick Reference

Quick reference for all Phase 6 commands.

---

## 📊 Status Command

**Show project overview**

```bash
novel status                    # Display status with emojis
novel status --json             # JSON output for scripting
```

**Output includes:**
- Novel name and location
- Current tick number
- Active POV character
- Entity counts (characters, locations, loops)
- Last scene info (file, word count, timestamp)

---

## 📋 List Commands

**List entities in the project**

```bash
novel list characters           # List all characters
novel list characters -v        # Verbose with details
novel list characters --json    # JSON output

novel list locations            # List all locations
novel list locations -v         # Verbose with details

novel list loops                # List open loops
novel list loops -v             # Verbose with details

novel list scenes               # List all scenes
novel list scenes -v            # Verbose with details
```

---

## 🔍 Inspect Command

**Deep-dive into entity details**

```bash
novel inspect --id C0                           # Inspect character C0
novel inspect --id L3                           # Inspect location L3
novel inspect --id S001                         # Inspect scene S001

novel inspect --id C0 --history-limit 10        # Show 10 history entries
novel inspect --id C0 --raw                     # Raw JSON output

novel inspect --file memory/characters/C0.json  # Direct file path
```

**Shows for characters:**
- Name, type, role
- Current state (emotional, physical, location)
- Physical traits and personality
- Relationships with other characters
- History timeline

**Shows for locations:**
- Name, type, atmosphere
- Description and sensory details
- Significance
- Current occupants
- History timeline

---

## 🎯 Plan Preview Command

**Preview next plan without executing**

```bash
novel plan                      # Preview next plan
novel plan --save preview.json  # Save plan to file
novel plan --verbose            # Show full context and prompts
```

**Output includes:**
- Rationale for the plan
- List of actions to execute
- Scene intention
- POV character
- Estimated token count

**Note:** Plan is NOT executed. Use `novel tick` to execute.

---

## 📝 Compile Command

**Compile scenes into manuscript**

```bash
novel compile                                   # Compile to manuscript.md
novel compile --output draft.md                 # Custom output file
novel compile --format html                     # HTML output
novel compile --output book.html --format html  # HTML with custom name

novel compile --scenes 1-10                     # Compile scenes 1-10
novel compile --scenes 5,7,9                    # Compile specific scenes
novel compile --scenes 1-5,10-15                # Multiple ranges

novel compile --no-metadata                     # Exclude metadata appendix
```

**Formats:**
- `markdown` (default) - Clean markdown format
- `html` - Styled HTML with CSS

**Output includes:**
- Title and metadata header
- All scenes with separators
- Optional appendix with stats

---

## 💾 Checkpoint Commands

**Manage project checkpoints**

### Create Checkpoint

```bash
novel checkpoint create                                 # Create checkpoint
novel checkpoint create --message "Before plot twist"   # With description
```

### List Checkpoints

```bash
novel checkpoint list
```

**Shows:**
- Checkpoint ID
- Tick number
- Creation timestamp
- Entity counts
- Size in MB
- Creation message

### Restore Checkpoint

```bash
novel checkpoint restore --id checkpoint_tick_010
```

**Note:** Current state is automatically backed up before restore.

### Delete Checkpoint

```bash
novel checkpoint delete --id checkpoint_tick_005
```

**Note:** Requires confirmation prompt.

---

## 🔧 Common Workflows

### Daily Writing Session

```bash
# Check where you left off
novel status

# Preview what's next
novel plan

# Generate next scene
novel tick

# Review what was created
novel list characters
novel inspect --id C0
```

### Review and Compile

```bash
# Check project status
novel status

# List all scenes
novel list scenes

# Compile for review
novel compile --output draft.md

# Or compile specific range
novel compile --output act1.md --scenes 1-20
```

### Checkpoint Management

```bash
# Before major changes
novel checkpoint create --message "End of Act 1"

# Make changes...
novel tick
novel tick
novel tick

# If needed, restore
novel checkpoint list
novel checkpoint restore --id checkpoint_tick_015
```

### Debugging

```bash
# Verbose plan to see context
novel plan --verbose

# Check entity states
novel list characters -v
novel inspect --id C0 --history-limit 20

# Check raw data
novel inspect --id C0 --raw
```

### Export for Sharing

```bash
# Markdown for editing
novel compile --output manuscript.md

# HTML for reading
novel compile --format html --output novel.html

# Specific chapters
novel compile --output chapter1.md --scenes 1-10
novel compile --output chapter2.md --scenes 11-20
```

---

## 💡 Tips

1. **Use `--json` for scripting:** All list/inspect commands support JSON output
2. **Checkpoint regularly:** Create checkpoints before major plot points
3. **Preview plans:** Use `novel plan` to see what will happen before executing
4. **Compile incrementally:** Review sections as you write with `--scenes`
5. **Inspect history:** Use `--history-limit` to see entity evolution over time

---

## 🎨 Output Formats

### Status Output
```
📖 Novel: The Crimson Tower
📍 Location: ~/novels/crimson-tower/
🎬 Current Tick: 23
👤 Active POV: C0 (Elena Voss)
📝 Scenes Written: 23
👥 Characters: 5
🗺️  Locations: 8
🔗 Open Loops: 3
```

### List Output (Table)
```
👥 Characters (5 total)

  id  name           role         type
  --  -------------  -----------  ------------
  C0  Elena Voss     Detective    protagonist
  C1  Marcus Chen    Executive    antagonist
  C2  Dr. Sarah Kim  Scientist    supporting
```

### Inspect Output
```
🔍 Inspecting Character: C0

Name: Elena Voss
Type: protagonist
Role: Detective

Current State:
  Emotional: determined
  Physical: exhausted
  Location: L5
  Inventory: badge, notebook, phone

History (last 5 updates):
  [Tick 23] emotional_state: anxious → determined
  [Tick 21] inventory: added 'notebook'
  [Tick 18] relationships: added C2 (allied)
```

### Plan Preview Output
```
📋 Plan Preview (Tick 24)

Rationale:
  Elena needs to confront Marcus about the missing files...

Actions (3):
  1. memory.search
      query: Marcus Chen background corporate
  2. location.update
      id: L5
      changes: {'tension_level': 8}
  3. character.update
      id: C0
      changes: {'emotional_state': 'confrontational'}

Scene Intention:
  Tense confrontation in Marcus's office...

POV Character: C0 (Elena Voss)
Estimated Tokens: ~2,400

⚠️  This plan has NOT been executed. Use 'novel tick' to execute.
```

---

## 🆘 Troubleshooting

**"No novel project found"**
- Run from project directory, or use `--project /path/to/project`

**"Entity not found"**
- Check entity ID with `novel list characters` or `novel list locations`
- Use exact ID format: C0, L3, S001

**"Checkpoint already exists"**
- Checkpoints are created per tick
- Delete old checkpoint or run more ticks first

**"Could not extract JSON from LLM response"**
- LLM may have failed to generate valid plan
- Try again or use `--verbose` to see raw response

---

## 📚 Related Documentation

- [Phase 6 Detailed Plan](phase6_detailed_plan.md) - Full implementation specifications
- [Phase 6 Implementation Summary](phase6_implementation_summary.md) - What was built
- [Main Plan](plan.md) - Overall project roadmap
