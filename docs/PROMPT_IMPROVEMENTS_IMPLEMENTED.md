# Prompt Improvements Implemented

## Summary

Strengthened planner and writer prompts to explicitly demand forward momentum and avoid repetition, addressing the core issue of circular plotting without requiring architectural changes.

## Changes Made

### 1. Planner Prompt (`prompts.py`)

#### Title Change
- **Before:** "create a plan for the next scene"
- **After:** "create a plan for the next scene that ADVANCES THE PLOT"

#### Added Section: CRITICAL REQUIREMENTS
```
1. CHANGE THE SITUATION - Scene must alter story state
2. RESOLVE OR ESCALATE - Pick a high-priority loop and advance it
3. FORWARD MOMENTUM - Move toward resolution/discovery/choice/turning point
4. AVOID REPETITION - Don't repeat recent situations/actions/beats
```

#### Added Section: PLANNING QUESTIONS
```
1. What will CHANGE by the end of this scene?
2. Which high-priority open loop will you advance?
3. How will this scene be DIFFERENT from recent scenes?
4. What is the TURNING POINT or KEY EVENT?
```

#### New Required Fields
```json
{
  "key_change": "What is fundamentally different after this scene?",
  "loops_addressed": ["OL4", "OL5"]
}
```

#### Strengthened Language
- "Open Story Loops" → "Open Story Loops (PRIORITIZED BY IMPORTANCE)"
- "addressed or developed" → "RESOLVE OR ESCALATE"
- "scene intention" → "What CHANGES in this scene"
- "expected outcomes" → "Concrete outcomes (something that CHANGES)"

#### Added Reminder
```
REMEMBER: Your job is to ADVANCE the story, not just continue it. Make something CHANGE.
```

### 2. Writer Prompt (`prompts.py`)

#### Added Key Change Display
```
**KEY CHANGE THIS SCENE MUST ACCOMPLISH:** {key_change}
```

#### Task Emphasis
- **Before:** "Write a scene passage from X's deep POV"
- **After:** "Write a scene passage that ACCOMPLISHES THE KEY CHANGE described above"

#### Added Section: CRITICAL REQUIREMENTS
```
1. EXECUTE THE CHANGE - Situation at END must differ from BEGINNING
2. BUILD TO A TURNING POINT - Structure: Opening → Rising → Turning Point → Resolution
3. AVOID REPETITION - Don't repeat actions/beats from recent scenes
```

#### Reordered AVOID Section
- **First item:** "Ending with the same situation as the start"
- **Second item:** "Repeating actions/beats from recent scenes"

#### Reordered FOCUS Section
- **First item:** "Accomplishing the key change"
- **Second item:** "The turning point moment"

### 3. Writer Context Builder (`writer_context.py`)

#### Extract key_change from plan
```python
key_change = plan.get("key_change", "Advance the plot")
```

#### Pass to writer context
```python
return {
    # ... other fields ...
    "key_change": key_change,
    # ... other fields ...
}
```

## Expected Impact

### Before (Current Behavior)
```
Planner: "What should happen next?"
LLM: "Kyras continues negotiating with proxy..."
Writer: "Kyras pressed the relay again, pain shooting through..."
Result: Same situation, slightly different wording
```

### After (With Improvements)
```
Planner: "What will CHANGE? Which loop will you ADVANCE?"
LLM: "Kyras must choose: upload feed or sever connection (resolves OL5)"
       key_change: "Kyras makes the critical choice, changing his relationship with Belia"
       loops_addressed: ["OL5"]
Writer: "Must accomplish: Kyras makes the choice"
Result: Situation fundamentally changes, plot advances
```

## Testing

### Test on Your Story
```bash
cd /home/edward/novels/scifi-new_0f2360ba
novel tick
```

**Look for in the plan:**
- `key_change` field present and specific
- `loops_addressed` field lists actual loop IDs
- `scene_intention` describes a change, not continuation
- `rationale` explains what will change

**Look for in the scene:**
- Situation at end differs from beginning
- Clear turning point moment
- Concrete progress on a loop
- No repetition of recent beats

### Compare Metrics

**Current (S010-S017):**
- Loops resolved: 0 in 8 scenes
- Situation changes: 0 (Kyras still in relay)
- Repetition: High (similar negotiation beats)

**Target (Next 8 scenes):**
- Loops resolved: 2-3
- Situation changes: 2-3
- Repetition: Low (varied situations)

## Files Modified

1. `/home/edward/Projects/StoryDaemon/novel_agent/agent/prompts.py`
   - Updated `PLANNER_PROMPT_TEMPLATE`
   - Updated `WRITER_PROMPT_TEMPLATE`

2. `/home/edward/Projects/StoryDaemon/novel_agent/agent/writer_context.py`
   - Extract `key_change` from plan
   - Pass to writer context

## Advantages of This Approach

1. **Low Risk** - Only prompt changes, no architectural modifications
2. **High Impact** - Directly addresses repetition and momentum issues
3. **Immediate** - Can test right away
4. **Reversible** - Easy to revert if needed
5. **Foundation** - Sets groundwork for future plot-first architecture

## Next Steps

### Immediate
1. ✅ Implement prompt changes (DONE)
2. ⬜ Test on your current story
3. ⬜ Evaluate results (does it advance plot better?)

### Short-term
1. ⬜ Add validation: warn if `key_change` is missing
2. ⬜ Add validation: warn if `loops_addressed` is empty
3. ⬜ Track metrics: loops resolved per N scenes

### Long-term
1. ⬜ If successful, consider plot-first architecture
2. ⬜ Add beat verification step
3. ⬜ Add heuristics (warn if loop open 3+ scenes)

## Documentation

Related documents:
- `PROMPT_ANALYSIS_FORWARD_MOMENTUM.md` - Detailed analysis
- `ARCHITECTURE_PROPOSAL_EMERGENT_PLOTTING.md` - Future architecture

---

**Created:** November 13, 2025
**Status:** Implemented, ready for testing
**Risk:** Low (prompt changes only)
**Expected Impact:** High (addresses core repetition issue)
