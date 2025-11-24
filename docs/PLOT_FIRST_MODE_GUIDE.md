# Plot-First Mode User Guide

## Quick Start

### 1. Generate Initial Beats

Before enabling plot-first mode, generate some plot beats for your story:

```bash
cd ~/novels/your-novel
novel plot generate --count 5
```

This creates a `plot_outline.json` file with 5 plot beats based on your current story state.

### 2. Review the Beats

Check what beats were generated:

```bash
novel plot status
```

Or see detailed beat information:

```bash
novel plot status --detailed
```

### 3. Enable Plot-First Mode

Add to your project's `config.yaml`:

```yaml
generation:
  use_plot_first: true
  plot_beats_ahead: 5
  plot_regeneration_threshold: 2
  verify_beat_execution: true
```

### 4. Run Ticks Normally

```bash
novel tick
```

The agent will now:
- Automatically regenerate beats when running low
- Execute the next pending beat in each scene
- Verify beat accomplishment
- Mark beats as complete

## Configuration Options

### Core Settings

**`use_plot_first`** (default: `false`)
- Enable/disable plot-first mode
- When false, agent operates in reactive mode as before

**`plot_beats_ahead`** (default: `5`)
- How many beats to generate at a time
- Larger values = less frequent generation, but longer generation time

**`plot_regeneration_threshold`** (default: `2`)
- Regenerate beats when pending count drops below this
- Lower values = more frequent regeneration

### Verification Settings

**`verify_beat_execution`** (default: `true`)
- Use LLM to verify if beat was accomplished
- Adds ~1 LLM call per scene
- Set to `false` for faster ticks (auto-marks complete)

**`allow_beat_skip`** (default: `false`)
- If `true`, story continues even if beat isn't accomplished
- If `false`, beat stays pending until accomplished
- Recommended: keep `false` for tighter plot control

### Fallback Settings

**`fallback_to_reactive`** (default: `true`)
- If beat generation fails, continue in reactive mode
- If `false`, tick fails when beat generation fails
- Recommended: keep `true` for robustness

## Usage Patterns

### Pattern 1: Strict Plot-First (Recommended)

```yaml
generation:
  use_plot_first: true
  verify_beat_execution: true
  allow_beat_skip: false
  fallback_to_reactive: true
```

**Behavior:**
- Beats must be accomplished to progress
- LLM verifies accomplishment
- Falls back gracefully on errors
- Best for maintaining plot coherence

### Pattern 2: Fast Plot-First

```yaml
generation:
  use_plot_first: true
  verify_beat_execution: false
  allow_beat_skip: false
  fallback_to_reactive: true
```

**Behavior:**
- Beats guide scenes but no verification
- Faster (fewer LLM calls)
- Auto-marks beats complete
- Good for rapid drafting

### Pattern 3: Lenient Plot-First

```yaml
generation:
  use_plot_first: true
  verify_beat_execution: true
  allow_beat_skip: true
  fallback_to_reactive: true
```

**Behavior:**
- Beats guide scenes
- Verifies but doesn't block on failure
- Story can diverge from beats
- Good for exploratory writing

## CLI Commands

### Generate Beats

```bash
# Generate 5 beats
novel plot generate --count 5

# Generate 10 beats
novel plot generate --count 10
```

### View Beats

```bash
# Summary view
novel plot status

# Detailed view with all beat info
novel plot status --detailed

# View next pending beat
novel plot next
```

### Manual Beat Management

You can manually edit `plot_outline.json` to:
- Reorder beats
- Edit beat descriptions
- Change beat status
- Add/remove beats

Format:
```json
{
  "beats": [
    {
      "id": "PB001",
      "description": "Character discovers the secret",
      "characters_involved": ["C0"],
      "location": "L1",
      "plot_threads": ["mystery_thread"],
      "tension_target": 7,
      "status": "pending",
      "prerequisites": [],
      "created_at": "2025-11-24T19:00:00Z",
      "executed_in_scene": null,
      "execution_notes": ""
    }
  ],
  "created_at": "2025-11-24T19:00:00Z",
  "last_updated": "2025-11-24T19:00:00Z",
  "current_arc": "",
  "arc_progress": 0.0
}
```

## Monitoring Beat Execution

### During Tick

Watch for these indicators:

```
📖 Generating plot beats...
    Generated 5 new plot beats
🎯 Executing beat: Character discovers the hidden message
...
8.5. Verifying beat execution...
    ✓ Beat PB001 accomplished
```

### After Tick

Check beat status:

```bash
novel plot status --detailed
```

Look for:
- `status: "completed"` - Beat was accomplished
- `executed_in_scene: "S005"` - Which scene executed it
- `execution_notes` - Details about execution

## Troubleshooting

### Beats Not Being Generated

**Symptom:** No beats in outline, agent runs reactively

**Solutions:**
1. Manually generate beats: `novel plot generate --count 5`
2. Check config: `use_plot_first: true`
3. Check for errors in beat generation (LLM issues)

### Beats Not Being Accomplished

**Symptom:** Beat stays pending across multiple scenes

**Possible Causes:**
1. Beat is too vague or complex
2. Beat requires setup that hasn't happened yet
3. Writer is ignoring beat constraint

**Solutions:**
1. Edit beat description to be more specific
2. Add prerequisite beats for setup
3. Check writer prompt is receiving beat info
4. Temporarily set `verify_beat_execution: false` to see if it's a verification issue

### Beat Generation Fails

**Symptom:** Error during beat generation

**Solutions:**
1. Check LLM is accessible
2. Ensure story has enough context (scenes, loops, characters)
3. Check `fallback_to_reactive: true` to continue despite errors
4. Review beat generation prompt in logs

### Beats Are Repetitive

**Symptom:** Generated beats repeat similar actions

**Solutions:**
1. Ensure story has diverse open loops
2. Add more character goals and conflicts
3. Manually edit/delete repetitive beats
4. Regenerate with more context

## Best Practices

### 1. Start with Manual Beats

For your first plot-first story:
1. Generate 5-10 beats manually
2. Review and edit them
3. Enable plot-first mode
4. Let agent execute and regenerate

### 2. Monitor First Few Scenes

Watch closely for the first 3-5 scenes:
- Are beats being accomplished?
- Is verification accurate?
- Are generated beats coherent?

### 3. Adjust Regeneration Threshold

- If beats run out frequently: increase `plot_beats_ahead`
- If generation is slow: decrease `plot_beats_ahead`
- If you want tighter control: lower `plot_regeneration_threshold` to 1

### 4. Combine with Guided Mode

Plot-first mode works alongside Phase 4B's guided beat mode:

```yaml
generation:
  use_plot_first: true

plot:
  beat_mode: guided
```

This gives you both automatic beat execution AND planner beat targeting.

### 5. Use for Mid-Story

Plot-first mode is especially useful when:
- Story has established characters and conflicts
- Multiple plot threads are active
- You want to maintain momentum
- You need to avoid circular plotting

## Example Workflow

```bash
# 1. Start a new novel
novel init my-story

# 2. Write first few scenes reactively
novel tick
novel tick
novel tick

# 3. Generate initial beats
novel plot generate --count 5

# 4. Review beats
novel plot status --detailed

# 5. Edit beats if needed
vim plot_outline.json

# 6. Enable plot-first mode
echo "generation:
  use_plot_first: true" >> config.yaml

# 7. Continue writing with beats
novel tick
novel tick

# 8. Monitor beat execution
novel plot status

# 9. Agent auto-regenerates when needed
novel tick  # Generates new beats automatically
```

## Comparison: Reactive vs Plot-First

### Reactive Mode (Default)

```
Tick N:
  → Plan: "What should happen next?"
  → Write: Execute plan
  → Result: Scene emerges from immediate context
```

**Pros:** Flexible, emergent, no planning overhead  
**Cons:** Can be repetitive, lacks direction, circular plots

### Plot-First Mode

```
Tick N:
  → Check beats (regenerate if needed)
  → Get next beat: "Character discovers secret"
  → Plan: "How to execute this beat?"
  → Write: Scene must accomplish beat
  → Verify: Did beat happen?
  → Mark complete
```

**Pros:** Forward momentum, unique scenes, clear direction  
**Cons:** Less flexible, requires beat generation, more LLM calls

## Advanced: Custom Beat Generation

You can customize beat generation by editing the prompt in:
`novel_agent/agent/prompts.py` → `format_plot_generation_prompt()`

Or by manually creating beats with specific structure:

```python
from novel_agent.memory.entities import PlotBeat

beat = PlotBeat(
    id="",  # Auto-assigned
    description="Character confronts antagonist about betrayal",
    characters_involved=["C0", "C1"],
    location="L3",
    plot_threads=["betrayal_arc", "trust_issues"],
    tension_target=9,
    prerequisites=["PB005"],  # Must happen after PB005
    resolves_loops=["L002"],  # Resolves this open loop
    creates_loops=["L010"]    # Creates new conflict
)
```

## FAQ

**Q: Can I use plot-first mode on an existing story?**  
A: Yes! Generate beats from current state, review them, then enable the mode.

**Q: What if I don't like a generated beat?**  
A: Edit `plot_outline.json` directly or delete the beat and regenerate.

**Q: Can I mix plot-first and reactive modes?**  
A: Yes, toggle `use_plot_first` on/off as needed. Beats persist.

**Q: How many beats should I keep ahead?**  
A: 3-5 is usually good. More for long-term planning, fewer for flexibility.

**Q: Does this work with multi-stage planner?**  
A: Yes, they work together. Beat provides "what", planner provides "how".

**Q: Can I see the beat in the writer prompt?**  
A: Yes, check `prompts/writer_prompt_tick_NNN.txt` if `save_prompts: true`.
