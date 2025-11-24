# Phase 5 Implementation Summary: Full Emergent Plot-First Tick

**Date:** November 24, 2025  
**Status:** ✅ Complete

## Overview

Phase 5 integrates the PlotOutlineManager into the StoryAgent's main tick cycle, enabling full emergent plot-first story generation. The agent now automatically generates plot beats, constrains scenes to execute those beats, verifies execution, and tracks beat completion.

## What Was Implemented

### 1. PlotOutlineManager Integration

**File:** `novel_agent/agent/agent.py`

- Changed import from `..memory.plot_outline` to `..plot.manager` to use the version with LLM integration
- Added `self.plot_manager = PlotOutlineManager(self.project_path, llm_interface)` in `__init__`
- Plot manager is now available throughout the agent lifecycle

### 2. Automatic Beat Regeneration

**Location:** `StoryAgent._normal_tick()` method

Added logic at the start of each tick to:
- Check if `generation.use_plot_first` config is enabled
- Call `_needs_beat_regeneration()` to check if pending beats < threshold
- Generate new beats via `plot_manager.generate_next_beats(count)` when needed
- Add generated beats to the outline
- Retrieve the next pending beat for execution
- Fallback to reactive mode if beat generation fails (configurable)

**New Helper Method:** `_needs_beat_regeneration()`
- Checks if pending beats are below `generation.plot_regeneration_threshold` (default: 2)
- Returns boolean indicating whether regeneration is needed

### 3. Beat-Constrained Writer Context

**Files Modified:**
- `novel_agent/agent/agent.py` - Injects beat into plan before building writer context
- `novel_agent/agent/writer_context.py` - Formats beat section for writer prompt
- `novel_agent/agent/prompts.py` - Added `{plot_beat_section}` placeholder to writer prompt

**Flow:**
1. Agent injects `plot_beat` dict into plan with:
   - `description`: What must happen in the scene
   - `characters_involved`: Required characters
   - `location`: Required location
   - `tension_target`: Target tension level
   - `plot_threads`: Plot threads this beat advances

2. `WriterContextBuilder._format_plot_beat_section()` formats this into a prominent section in the writer prompt with emoji marker (🎯) and clear instructions

3. Writer prompt now includes beat as a hard constraint that must be accomplished

### 4. Beat Verification and Status Updates

**New Methods in `StoryAgent`:**

**`_verify_beat_execution(scene_text, beat)`**
- Uses LLM to verify if the scene accomplished the plot beat
- Sends beat description + scene text to LLM
- Parses YES/NO response
- Logs verification result
- Defaults to True on error (graceful degradation)

**`_mark_beat_complete(beat_id, scene_id)`**
- Loads plot outline
- Finds beat by ID
- Updates status to "completed"
- Records `executed_in_scene` and `execution_notes`
- Saves outline back to disk

**Integration in tick cycle:**
- After scene commit, if plot-first mode is enabled and a beat was targeted:
  - Optionally verify beat execution (if `generation.verify_beat_execution` is True)
  - Mark beat as complete if verified
  - Keep as pending if not accomplished (unless `allow_beat_skip` is True)
  - Auto-mark complete without verification if verification is disabled

### 5. Configuration Options

**File:** `novel_agent/configs/config.py`

Added new configuration section under `generation`:

```python
# Phase 5: Plot-first mode configuration
'use_plot_first': False,  # Enable emergent plot-first architecture
'plot_beats_ahead': 5,  # Generate this many beats at a time
'plot_regeneration_threshold': 2,  # Regenerate when pending beats < this
'verify_beat_execution': True,  # Verify beat was accomplished via LLM
'allow_beat_skip': False,  # Allow skipping beats that aren't accomplished
'fallback_to_reactive': True,  # Fall back to reactive mode if beat generation fails
```

## How It Works

### Normal Tick Flow (with Plot-First Enabled)

```
1. Check if use_plot_first is enabled
2. If enabled:
   a. Check if beat regeneration is needed (pending < threshold)
   b. If needed, generate N new beats and add to outline
   c. Get next pending beat
   d. Display beat description to user
3. Gather context (as before)
4. Generate plan (as before, but could use beat-aware planning in guided mode)
5. Validate plan
6. Execute tools
7. Store plan
8. Inject beat into plan as plot_beat dict
9. Build writer context (now includes formatted beat section)
10. Write scene (writer sees beat as hard constraint)
11. Evaluate scene
12. Commit scene
13. Verify beat execution (optional)
14. Mark beat complete if verified
15. Continue with fact extraction, lore, etc.
```

### Fallback Behavior

- If beat generation fails and `fallback_to_reactive` is True, continues without beats
- If beat generation fails and `fallback_to_reactive` is False, raises error
- If no beats available and `fallback_to_reactive` is True, continues reactively
- If beat verification fails, defaults to marking complete (graceful degradation)

## Configuration Modes

### Disabled (Default)
```yaml
generation:
  use_plot_first: false
```
Agent operates in reactive mode as before. No changes to existing behavior.

### Enabled with Verification
```yaml
generation:
  use_plot_first: true
  verify_beat_execution: true
  allow_beat_skip: false
```
Agent generates beats, constrains scenes, verifies execution, and requires beats to be accomplished.

### Enabled without Verification
```yaml
generation:
  use_plot_first: true
  verify_beat_execution: false
```
Agent generates beats and constrains scenes, but auto-marks beats as complete without LLM verification (faster, less LLM calls).

### Lenient Mode
```yaml
generation:
  use_plot_first: true
  verify_beat_execution: true
  allow_beat_skip: true
```
Agent verifies beats but allows story to continue even if beats aren't accomplished.

## Benefits

1. **Forward Momentum** - Story always working toward specific plot goals
2. **Reduced Repetition** - Each beat is unique by design
3. **Better Pacing** - Tension and progression planned ahead
4. **Emergent Yet Structured** - Beats emerge from story state but provide direction
5. **Debugging & Control** - Can inspect beats, see which scenes execute which beats
6. **Graceful Degradation** - Falls back to reactive mode on errors

## Testing Recommendations

1. **Enable on a new project** with a few beats already generated via CLI
2. **Monitor beat execution** - Check if scenes actually accomplish beats
3. **Verify beat quality** - Are generated beats coherent and progressive?
4. **Test fallback** - Disable beat generation temporarily to test reactive fallback
5. **Check verification accuracy** - Does LLM correctly identify beat accomplishment?

## Future Enhancements (Phase 6)

- Multi-arc management
- Beat branching and alternative paths
- Tension curve optimization based on beat targets
- More sophisticated beat generation prompts
- Beat editing/reordering tools
- Migration tool for existing projects

## Files Modified

1. `novel_agent/agent/agent.py` - Main integration, beat regeneration, verification
2. `novel_agent/agent/writer_context.py` - Beat section formatting
3. `novel_agent/agent/prompts.py` - Writer prompt template update
4. `novel_agent/configs/config.py` - Configuration options
5. `docs/IMPLEMENTATION_CHECKLIST_EMERGENT_PLOTTING.md` - Marked Phase 5 complete

## Usage

To enable plot-first mode in a project:

1. Ensure plot beats exist (generate via `novel plot generate --count 5`)
2. Add to project's `config.yaml`:
   ```yaml
   generation:
     use_plot_first: true
   ```
3. Run `novel tick` as normal
4. Agent will automatically use beats to guide scene generation

## Notes

- Plot-first mode is **opt-in** by default to avoid breaking existing projects
- The existing "guided" beat mode (Phase 4B) still works independently
- Plot-first mode can coexist with multi-stage planner
- Beat verification adds ~1 LLM call per scene (can be disabled for speed)
