# Phase 3 Plan Updates

**Date:** November 4, 2025  
**Status:** Design updated based on feedback

---

## Changes Made

### 1. Error Handling ✅

**Decision:** STOP on first tool execution error

**Implementation:**
- `PlanExecutor.execute_plan()` raises `RuntimeError` on first tool failure
- Error details saved to `/errors/error_NNN.json` (structured)
- Human-readable log saved to `/errors/error_NNN.log`
- Error file includes:
  - Full traceback
  - Plan that was being executed
  - Partial execution results
  - Instructions for human review (fix, edit, skip)

**Rationale:** When a tool fails, something is seriously wrong. Better to stop and let a human review than continue with potentially corrupted state.

**Example Error File:**
```json
{
  "tick": 5,
  "timestamp": "2024-11-04T20:30:00Z",
  "error": {
    "type": "ValueError",
    "message": "Character C5 not found",
    "traceback": "..."
  },
  "plan": {...},
  "execution": {...},
  "instructions": "Review error and either: 1. Fix issue, 2. Edit plan, 3. Skip tick"
}
```

---

### 2. Context Configuration ✅

**Decision:** Overall summary + configurable recent scenes

**Implementation:**
- **Overall Summary:** High-level view of entire story
  - Uses first bullet point from each scene
  - Format: "Tick N: [summary]"
  - Gives planner big-picture context
  
- **Recent Scenes:** Detailed summaries of last N scenes
  - Default: 3 scenes
  - Configurable via `generation.recent_scenes_count`
  - Full bullet-point summaries

- **Configuration Options:**
  ```yaml
  generation:
    recent_scenes_count: 3
    include_overall_summary: true
  ```

**Rationale:** Need both macro (where is story going?) and micro (what just happened?) context. Configuration allows adjustment based on real-world testing.

**Updated Prompt Structure:**
```
## Current Story State

### Overall Story Summary
Tick 1: Elena discovers a mysterious map fragment
Tick 2: She confronts her mentor about its origin
Tick 3: A hidden message is revealed in the archive
...

### Recent Scenes (Detailed)
**The Confrontation** (Tick 3):
  - Elena demands answers from Marcus
  - Marcus reveals connection to her father
  - Tension escalates between them
```

---

### 3. Project Structure Updates

**New Directory:**
- `~/novels/<novel-name>/errors/` - Created automatically

**New Files:**
- `error_NNN.json` - Structured error data
- `error_NNN.log` - Human-readable error log

---

### 4. Configuration Defaults

**Added to `novel_agent/configs/config.py`:**
```python
'generation': {
    'target_word_count_min': 500,
    'target_word_count_max': 900,
    'max_tools_per_tick': 3,
    'recent_scenes_count': 3,           # NEW
    'include_overall_summary': True,    # NEW
}
```

---

## Updated Components

### ContextBuilder
- Now accepts `config` parameter
- Reads `recent_scenes_count` and `include_overall_summary` from config
- New method: `_get_overall_summary()`
- Updated method: `_get_recent_scenes_summary()` uses configurable count

### PlanExecutor
- `execute_plan()` now raises `RuntimeError` on first error
- Stops execution immediately when tool fails
- Returns partial results before raising

### PlanManager
- New method: `save_error()` - Saves error details for human review
- New method: `list_errors()` - Lists all error tick numbers
- Creates `/errors/` directory automatically
- Writes both JSON and LOG formats

### StoryAgent
- `tick()` wrapped in try/except
- Catches all exceptions and saves error details
- Re-raises exception for CLI to handle

### CLI (tick command)
- Catches `RuntimeError` separately from other exceptions
- Provides helpful error message with recovery options
- Points user to `/errors/` directory

### Project Creation
- Creates `/errors/` directory
- Updates README to mention error logs

---

## Testing Implications

### New Tests Needed

1. **Error Handling Tests:**
   - Test tool execution failure
   - Verify error file creation
   - Check error file contents
   - Test partial execution results

2. **Context Configuration Tests:**
   - Test with different `recent_scenes_count` values
   - Test with `include_overall_summary` on/off
   - Verify overall summary format
   - Test with 0 scenes, 1 scene, many scenes

3. **Integration Tests:**
   - Test full tick with tool failure
   - Verify state not updated on error
   - Test error recovery workflow

---

## Human Workflow for Errors

When a tick fails:

1. **Review Error:**
   ```bash
   cat ~/novels/my-story/errors/error_005.log
   ```

2. **Fix Issue:**
   - Option A: Fix underlying problem (e.g., create missing entity)
   - Option B: Manually edit plan and retry
   - Option C: Skip this tick and continue

3. **Continue:**
   ```bash
   # After fixing, retry same tick
   novel tick
   
   # Or skip to next tick (edit state.json current_tick)
   ```

---

## Benefits

### Error Handling
- ✅ Clear failure points
- ✅ Complete debugging information
- ✅ Human can make informed decision
- ✅ No silent failures or corrupted state

### Context Configuration
- ✅ Flexible context size
- ✅ Both macro and micro views
- ✅ Adjustable based on testing
- ✅ Can disable overall summary if too verbose

---

## Phase 3 Status

**Ready to implement** with updated design:
- Error handling: Stop-on-error with detailed logging
- Context: Overall summary + configurable recent scenes
- All components updated in detailed plan
- Configuration defaults added
- Project structure includes `/errors/`

---

**Next:** Begin Phase 3 implementation with these updates
