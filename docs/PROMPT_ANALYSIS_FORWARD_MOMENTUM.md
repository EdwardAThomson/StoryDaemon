# Prompt Analysis: Forward Momentum Issue

## Investigation Results

### Current Planner Prompt Analysis

**Line 39-44 (Current Task):**
```
Create a plan for the next scene. Consider:
1. Which open loops should be addressed or developed?
2. What information do you need to write this scene effectively?
3. Should new characters or locations be introduced?
4. How should relationships evolve?
5. What pacing would serve the story best?
```

### Problems Identified

#### 1. **Weak Forward Momentum Language**
- ❌ "Create a plan for the **next scene**" - implies continuation, not progression
- ❌ "Which open loops should be **addressed or developed**?" - too passive
- ❌ No explicit instruction to **resolve** or **advance** plot threads
- ❌ No requirement to **change** the story state

#### 2. **Open Loops Are Listed But Not Prioritized for Action**
Your story has **multiple high-importance open loops**, but the prompt doesn't demand action:

**Current Open Loops (from your project):**
```
OL0 (high): What is the voice-like signal and who left the palm print?
OL3 (high): What became of the prior courier?
OL4 (high): Will erased courier overwrite Belia's identity?
OL5 (high): Can Kyras escape before relay fails?
... (many more)
```

**Current prompt says:** "Which open loops should be addressed?"
**Should say:** "You MUST make concrete progress on at least one high-priority open loop"

#### 3. **No Explicit "Push Forward" Directive**
The prompt never says:
- "Advance the plot"
- "Resolve a conflict"
- "Change the situation"
- "Create new complications"
- "Move toward resolution"

#### 4. **Scene Intention Is Too Vague**
**Current:** "What should happen in this scene (1-2 sentences)"
**Problem:** Allows for circular, repetitive intentions like:
- "Kyras continues negotiating with the proxy"
- "Kyras tries to maintain the relay connection"
- "Kyras struggles with the failing harness"

These are all **status quo** - nothing changes!

### Your Project Example

Looking at your recent scenes (S010-S017), the pattern is:
```
S010: Kyras negotiates with hostile imprint
S011: Kyras maintains relay while bleeding
S012: Kyras traces gravity sink while in pain
S013: Kyras stabilizes channel against ghost
S014: Kyras holds channel through shared cadence
S015: Kyras leverages pain to keep relay window
S016: Kyras gambles by revealing partial data
S017: Kyras continues negotiation...
```

**Pattern:** Kyras is in the same situation (trapped in relay, negotiating) for **8 consecutive scenes**. The situation hasn't fundamentally changed - only the specific tactics vary.

**Why?** The planner prompt doesn't demand that the situation **change**.

## Proposed Solution: Strengthen Prompts First

### Improved Planner Prompt

```python
PLANNER_PROMPT_TEMPLATE = """You are a creative story planner for an emergent narrative system.

Your task is to analyze the current story state and create a plan for the next scene that ADVANCES THE PLOT.

## Current Story State

**Novel:** {novel_name}
**Current Tick:** {current_tick}
**Active Character:** {active_character_name} ({active_character_id})

### Overall Story Summary
{overall_summary}

### Recent Scenes (Detailed)
{recent_scenes_summary}

### Open Story Loops (PRIORITIZED BY IMPORTANCE)
{open_loops_list}

### Tension Pattern (Pacing Awareness)
{tension_history}

### Active Character Details
{active_character_details}

### Available Relationships
{character_relationships}

## Available Tools

You can use the following tools to gather information or create entities:

{available_tools_description}

## Your Task: ADVANCE THE STORY

Create a plan for the next scene that makes CONCRETE PROGRESS on the plot.

**CRITICAL REQUIREMENTS:**

1. **CHANGE THE SITUATION** - The scene must alter the story state in a meaningful way
   - NOT: "Character continues doing X"
   - YES: "Character succeeds/fails at X, leading to Y"
   - NOT: "Character struggles with problem"
   - YES: "Character discovers new information that changes their approach"

2. **RESOLVE OR ESCALATE** - Pick at least ONE high-priority open loop and either:
   - Make significant progress toward resolution
   - OR create a major complication/escalation
   - DO NOT leave it in the same state

3. **FORWARD MOMENTUM** - The scene must move the story toward:
   - Resolution of a conflict
   - Discovery of crucial information
   - A character making a significant choice
   - A situation reaching a turning point
   - Introduction of a new complication (if current ones are stale)

4. **AVOID REPETITION** - Review recent scenes. Do NOT repeat:
   - Similar situations (e.g., "character negotiates again")
   - Similar actions (e.g., "character struggles with same problem")
   - Similar emotional beats (e.g., "character feels desperate again")

**SPECIFIC GUIDANCE FOR THIS SCENE:**

Look at the open loops above. Identify which ones have been "open" for multiple scenes without progress.
- If a loop has been open for 3+ scenes: RESOLVE IT or ESCALATE IT dramatically
- If a character has been in the same situation for 3+ scenes: CHANGE THE SITUATION
- If tension has been flat for 3+ scenes: CREATE A TURNING POINT

## Planning Questions

Answer these to guide your plan:

1. **What will CHANGE by the end of this scene?**
   - A loop resolved? A new discovery? A choice made? A situation altered?

2. **Which high-priority open loop will you advance?**
   - Pick ONE and make concrete progress

3. **How will this scene be DIFFERENT from recent scenes?**
   - New information? New location? New character? New complication?

4. **What is the TURNING POINT or KEY EVENT?**
   - Every scene needs a moment where something changes

## Output Format

Respond with a JSON object following this structure:

```json
{{
  "rationale": "Brief explanation focusing on HOW this scene advances the plot and WHAT changes",
  "scene_intention": "What CHANGES in this scene - be specific about the outcome/turning point",
  "key_change": "One sentence: What is fundamentally different after this scene?",
  "loops_addressed": ["OL4", "OL5"],  // Which loops you're advancing
  "pov_character": "Character ID for POV",
  "target_location": "Location ID or null",
  "actions": [
    {{
      "tool": "tool.name",
      "args": {{}},
      "reason": "Why this tool is needed"
    }}
  ],
  "expected_outcomes": [
    "Concrete outcome 1 (something that CHANGES)",
    "Concrete outcome 2 (something that CHANGES)"
  ],
  "metadata": {{
    "scene_length": "brief|short|long|extended (optional)"
  }}
}}
```

## Guidelines

- Keep actions focused (2-4 tools maximum per plan)
- Use memory.search to recall relevant context
- Scene intention must describe a CHANGE, not a continuation
- Expected outcomes must be CONCRETE changes to story state
- Every scene must have a turning point or key event
- Avoid repeating recent scene patterns

**REMEMBER: Your job is to ADVANCE the story, not just continue it. Make something CHANGE.**

Generate your plan now:"""
```

### Key Changes to Planner Prompt

1. **Title Change:** "create a plan for the next scene" → "create a plan that ADVANCES THE PLOT"

2. **Added Section:** "CRITICAL REQUIREMENTS" with explicit rules:
   - Must change the situation
   - Must resolve or escalate a loop
   - Must have forward momentum
   - Must avoid repetition

3. **Added Section:** "SPECIFIC GUIDANCE FOR THIS SCENE" with heuristics:
   - Loop open 3+ scenes → resolve or escalate
   - Same situation 3+ scenes → change it
   - Flat tension 3+ scenes → turning point

4. **Added Field:** `"key_change"` - forces planner to articulate what changes

5. **Added Field:** `"loops_addressed"` - makes loop progress explicit

6. **Stronger Language Throughout:**
   - "ADVANCE" not "address"
   - "RESOLVE OR ESCALATE" not "develop"
   - "CHANGE" not "continue"
   - "TURNING POINT" not "moment"

### Improved Writer Prompt

```python
WRITER_PROMPT_TEMPLATE = """You are a creative fiction writer specializing in deep POV narrative.

## Story Context

**Novel:** {novel_name}
**Tick:** {current_tick}

## Recent Story

The following context includes FULL TEXT from the most recent scenes to help you match prose style, voice, and atmosphere. Earlier scenes are summarized for plot continuity.

{recent_context}

## This Scene's Plan

**Intention:** {scene_intention}

**KEY CHANGE THIS SCENE MUST ACCOMPLISH:** {key_change}

**Open Loops Being Addressed:** {loops_addressed}

**Tool Results:** {tool_results_summary}

## POV Character

{pov_character_details}

## Location

{location_details}

## Your Task

Write a scene passage from {pov_character_name}'s deep POV that ACCOMPLISHES THE KEY CHANGE described above.{scene_length_guidance}

**CRITICAL REQUIREMENTS:**

1. **EXECUTE THE CHANGE** - This scene must accomplish the key change specified above
   - The situation at the END must be different from the BEGINNING
   - Something must be resolved, discovered, decided, or escalated
   - DO NOT end with the same status quo as the start

2. **BUILD TO A TURNING POINT** - Structure the scene with:
   - Opening: Establish current situation
   - Rising action: Build tension/conflict
   - Turning point: The moment something CHANGES
   - Resolution: Show the new situation

3. **AVOID REPETITION** - Review the recent context above
   - Do NOT repeat similar actions from recent scenes
   - Do NOT repeat similar emotional beats
   - Find fresh ways to show character state and conflict

**WRITING RULES:**

1. **Use character name naturally** - The POV character is "{pov_character_name}"
   - Use this name in prose, never placeholders
   - Vary between name and pronouns naturally
   - NEVER invent nicknames not provided

2. **Third-person deep POV** - Write in third person
   - Everything filtered through {pov_character_name}'s perception
   - No omniscient narration
   - Show don't tell

3. **Sensory details** - Engage sight, sound, smell, touch, taste

4. **Internal thoughts** - Show character's mental state

5. **Length:** Write as much as needed to accomplish the key change

**AVOID:**
- Ending with the same situation as the start
- Repeating actions/beats from recent scenes
- First-person POV except in dialogue
- Placeholder names
- Head-hopping
- Telling emotions instead of showing

**FOCUS ON:**
- Accomplishing the key change
- The turning point moment
- What {pov_character_name} sees, hears, feels, thinks
- Concrete actions and dialogue
- Fresh approaches (not repetitive)

Generate the scene now:"""
```

### Key Changes to Writer Prompt

1. **Added Fields:**
   - `{key_change}` - The specific change this scene must accomplish
   - `{loops_addressed}` - Which loops are being advanced

2. **New Section:** "CRITICAL REQUIREMENTS" emphasizing:
   - Must execute the change
   - Must have turning point
   - Must avoid repetition

3. **Structural Guidance:** Opening → Rising → Turning Point → Resolution

4. **Explicit Anti-Repetition:** "Review recent context" and "Do NOT repeat"

## Implementation Plan

### Phase 1: Update Prompts (Low Risk, High Impact)

1. ✅ Update `PLANNER_PROMPT_TEMPLATE` in `prompts.py`
2. ✅ Update `WRITER_PROMPT_TEMPLATE` in `prompts.py`
3. ✅ Modify `writer_context.py` to pass `key_change` and `loops_addressed`
4. ✅ Test on your current story

### Phase 2: Add Validation (Medium Risk)

1. Add `validate_plan_advances_plot()` function
   - Check if `key_change` is specified
   - Check if `loops_addressed` is non-empty
   - Warn if scene intention sounds repetitive

2. Add `verify_scene_accomplished_change()` function
   - After scene is written, verify the change happened
   - Use LLM to check: "Did this scene accomplish X?"

### Phase 3: Add Heuristics (Low Risk)

1. Track "scenes since loop mentioned"
2. Track "scenes in same situation"
3. Auto-generate warnings in planner context:
   - "WARNING: OL4 has been open for 8 scenes without progress"
   - "WARNING: Character has been in relay for 8 consecutive scenes"

## Expected Impact

### Before (Current Behavior)
```
Planner: "What should happen next?"
LLM: "Kyras continues negotiating..."
Writer: "Kyras pressed the relay again, pain shooting through..."
Result: Same situation, slightly different wording
```

### After (With Improved Prompts)
```
Planner: "What will CHANGE? Which loop will you ADVANCE?"
LLM: "Kyras must choose: upload feed or sever connection (resolves OL5)"
Writer: "Must accomplish: Kyras makes the choice"
Result: Situation fundamentally changes, plot advances
```

## Testing Plan

### Test 1: Generate Next Scene with New Prompts
1. Apply prompt changes
2. Run `novel tick` on your current story
3. Check if plan includes `key_change` and `loops_addressed`
4. Check if scene actually accomplishes the change

### Test 2: Compare to Current Approach
1. Save current scene S018 (if generated)
2. Regenerate with new prompts
3. Compare:
   - Does new version advance plot more?
   - Does new version avoid repetition?
   - Does new version resolve/escalate a loop?

### Test 3: Multi-Scene Test
1. Generate 3-5 scenes with new prompts
2. Verify each scene changes the situation
3. Verify no repetitive patterns
4. Verify loops are being resolved

## Metrics to Track

### Before/After Comparison
- **Loop resolution rate:** Loops resolved per 10 scenes
- **Situation changes:** How often character's situation fundamentally changes
- **Repetition score:** Similarity between consecutive scenes (use embeddings)
- **Tension progression:** Does tension build or stay flat?

### Your Story Specific
**Current (S010-S017):**
- Loops resolved: 0 (in 8 scenes)
- Situation changes: 0 (Kyras still in relay)
- Repetition: High (similar negotiation beats)

**Target (Next 8 scenes):**
- Loops resolved: 2-3
- Situation changes: 2-3 (e.g., extraction, new location, new threat)
- Repetition: Low (varied situations and actions)

## Conclusion

**Root Cause:** Prompts don't explicitly demand forward momentum or change.

**Solution:** Strengthen prompts with:
- Explicit "ADVANCE" and "CHANGE" language
- Required `key_change` field
- Anti-repetition instructions
- Loop progress tracking
- Turning point structure

**Advantage:** This is a **low-risk, high-impact** change that doesn't require architectural modifications.

**Next Step:** Implement Phase 1 (update prompts) and test on your story.

---

**Created:** November 13, 2025
**Status:** Ready for implementation
**Risk:** Low (prompt changes only)
**Expected Impact:** High (addresses core repetition issue)
