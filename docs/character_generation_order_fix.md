# Character Generation Order Fix

**Date:** November 8, 2025  
**Status:** Issue Analysis & Proposed Solution  
**Priority:** High - Affects story quality

---

## Problem Statement

### Issue 1: Character Names in First Scene
In the first scene (tick 0), character placeholders like `"char_elliot_warden"` were appearing in prose instead of actual character names like "Elliot Warden".

### Issue 2: Unintended First-Person POV
After implementing a fix (updating `plan["pov_character"]` after character generation), the LLM now frequently chooses **first-person POV** instead of third-person, which is not the desired default behavior.

**Example from `/tmp/novels/test-fix/scenes/scene_000.md`:**
```
Cool stone slicks against my palm as I edge sideways...
"Inventory first," I mutter, voice swallowed by the vault...
```

This is first-person ("I", "my") when we want third-person ("she", "her name").

---

## Root Cause Analysis

### Current Flow (Problematic)

```
Tick 0 (First Scene):
1. Planner generates plan
   └─ pov_character: "char_elliot_warden" (placeholder)
   └─ actions: [character.generate with name="Elliot Warden"]

2. Plan is validated ✓

3. Tools are executed
   └─ character.generate creates C0 with name="Elliot Warden"

4. Post-execution fix (our recent patch)
   └─ Updates plan["pov_character"] = "C0"

5. Writer context is built
   └─ Loads character C0
   └─ Gets name: "Elliot Warden"
   └─ Sends to writer prompt

6. Writer LLM generates prose
   └─ BUT: Sees that character was JUST created
   └─ Interprets this as "introduce character"
   └─ Chooses first-person as introduction style
```

### Why First-Person Happens

The writer prompt receives:
- **Tool Results:** "Generated new character: Dr. Mara Ellion"
- **Character Details:** Full character info
- **Scene Intention:** "Introduce a brilliant but anxious..."

The LLM interprets "introduce" + "just created" as a signal to use first-person POV for immediacy and character introduction, even though we want third-person.

---

## Why Current Fix is Inadequate

The current fix (lines 136-137 in `agent.py`):
```python
if plan.get("pov_character") and not plan["pov_character"].startswith("C"):
    plan["pov_character"] = char_id
```

**Problems:**
1. ✅ Fixes the placeholder name issue
2. ❌ Character is still created DURING scene generation
3. ❌ Writer sees "Generated new character" in tool results
4. ❌ LLM interprets this as "use first-person for introduction"
5. ❌ No explicit instruction about POV preference

---

## Proposed Solution: Two-Phase Tick for First Scene

### Approach: Pre-Generate Essential Entities

For the **first scene only** (tick 0), split into two phases:

**Phase 1: Entity Setup**
- Generate plan
- Execute ONLY entity generation tools (character.generate, location.generate)
- Do NOT write scene yet
- Store generated entity IDs

**Phase 2: Scene Writing**
- Rebuild plan with real entity IDs
- Execute remaining tools (memory.search, relationship.create, etc.)
- Write scene with fully established entities
- Character is no longer "just created" - it's established

### Benefits

1. ✅ Character has real ID before scene writing
2. ✅ Character name is known before prose generation
3. ✅ Writer doesn't see "Generated new character" in tool results
4. ✅ LLM treats character as established, not being introduced
5. ✅ Third-person POV is natural choice
6. ✅ No placeholder names in any context

---

## Detailed Implementation

### Option A: Two-Phase First Tick (Recommended)

**File:** `novel_agent/agent/agent.py`

Add special handling for tick 0:

```python
def tick(self) -> Dict[str, Any]:
    """Execute one story generation tick."""
    
    tick = self.state['current_tick']
    
    # Special handling for first tick
    if tick == 0:
        return self._first_tick()
    else:
        return self._normal_tick()

def _first_tick(self) -> Dict[str, Any]:
    """Execute first tick with two-phase entity generation.
    
    Phase 1: Generate entities
    Phase 2: Write scene with established entities
    """
    tick = 0
    
    print("⚙️  Executing tick 0 (two-phase initialization)...")
    
    # PHASE 1: Entity Generation
    print("   Phase 1: Generating entities...")
    
    # Step 1: Gather context
    print("   1. Gathering context...")
    context = self.context_builder.build_planner_context(self.state)
    
    # Step 2: Generate plan
    print("   2. Generating plan with LLM...")
    plan = self._generate_plan(context)
    
    # Step 3: Validate plan
    print("   3. Validating plan...")
    validate_plan(plan)
    
    # Step 4: Execute ONLY entity generation tools
    print("   4. Pre-generating entities...")
    entity_results = self._execute_entity_generation_only(plan, tick)
    
    # Step 5: Update plan with real entity IDs
    print("   5. Updating plan with entity IDs...")
    self._update_plan_with_entity_ids(plan, entity_results)
    
    # Step 6: Set active character
    if self.state.get("active_character") is None:
        for action in entity_results.get("actions_executed", []):
            if action.get("tool") == "character.generate" and action.get("success"):
                char_id = action.get("result", {}).get("character_id")
                if char_id:
                    self.state["active_character"] = char_id
                    plan["pov_character"] = char_id
                    break
    
    # PHASE 2: Scene Writing
    print("   Phase 2: Writing scene...")
    
    # Step 7: Execute remaining tools (if any)
    print("   6. Executing remaining tools...")
    remaining_results = self._execute_remaining_tools(plan, tick, entity_results)
    
    # Merge results
    execution_results = self._merge_execution_results(entity_results, remaining_results)
    
    # Step 8: Store plan
    print("   7. Storing plan...")
    plan_file = self.plan_manager.save_plan(tick, plan, execution_results, context)
    
    # Step 9: Write scene (entities are now established)
    print("   8. Writing scene prose...")
    writer_context = self.writer_context_builder.build_writer_context(
        plan,
        execution_results,
        self.state
    )
    scene_data = self.writer.write_scene(writer_context)
    
    # Continue with normal flow (evaluate, commit, etc.)
    # ... rest of tick logic ...

def _execute_entity_generation_only(self, plan: Dict, tick: int) -> Dict:
    """Execute only entity generation tools from plan.
    
    Args:
        plan: The generated plan
        tick: Current tick number
    
    Returns:
        Execution results for entity generation tools only
    """
    entity_tools = ["character.generate", "location.generate"]
    
    filtered_actions = [
        action for action in plan.get("actions", [])
        if action.get("tool") in entity_tools
    ]
    
    # Create temporary plan with only entity actions
    entity_plan = {**plan, "actions": filtered_actions}
    
    return self.executor.execute_plan(entity_plan, tick)

def _execute_remaining_tools(self, plan: Dict, tick: int, entity_results: Dict) -> Dict:
    """Execute non-entity tools from plan.
    
    Args:
        plan: The generated plan (with updated entity IDs)
        tick: Current tick number
        entity_results: Results from entity generation
    
    Returns:
        Execution results for remaining tools
    """
    entity_tools = ["character.generate", "location.generate"]
    
    remaining_actions = [
        action for action in plan.get("actions", [])
        if action.get("tool") not in entity_tools
    ]
    
    if not remaining_actions:
        return {"actions_executed": [], "errors": [], "success": True}
    
    # Create temporary plan with only remaining actions
    remaining_plan = {**plan, "actions": remaining_actions}
    
    return self.executor.execute_plan(remaining_plan, tick)

def _update_plan_with_entity_ids(self, plan: Dict, entity_results: Dict):
    """Update plan with real entity IDs after generation.
    
    Args:
        plan: The plan to update (modified in place)
        entity_results: Results from entity generation
    """
    for action in entity_results.get("actions_executed", []):
        if action.get("tool") == "character.generate" and action.get("success"):
            char_id = action.get("result", {}).get("character_id")
            if char_id and plan.get("pov_character"):
                # Replace placeholder with real ID
                if not plan["pov_character"].startswith("C"):
                    plan["pov_character"] = char_id
        
        elif action.get("tool") == "location.generate" and action.get("success"):
            loc_id = action.get("result", {}).get("location_id")
            if loc_id and plan.get("target_location"):
                # Replace placeholder with real ID
                if not plan["target_location"].startswith("L"):
                    plan["target_location"] = loc_id

def _merge_execution_results(self, entity_results: Dict, remaining_results: Dict) -> Dict:
    """Merge entity and remaining execution results.
    
    Args:
        entity_results: Results from entity generation
        remaining_results: Results from remaining tools
    
    Returns:
        Combined execution results
    """
    return {
        "actions_executed": (
            entity_results.get("actions_executed", []) +
            remaining_results.get("actions_executed", [])
        ),
        "errors": (
            entity_results.get("errors", []) +
            remaining_results.get("errors", [])
        ),
        "success": entity_results.get("success", True) and remaining_results.get("success", True)
    }

def _normal_tick(self) -> Dict[str, Any]:
    """Execute normal tick (tick 1+).
    
    This is the current tick logic, unchanged.
    """
    # Current tick() implementation goes here
    # ... existing code ...
```

---

### Option B: Simpler - Filter Tool Results in Writer Context

**File:** `novel_agent/agent/writer_context.py`

Hide entity generation from tool results summary:

```python
def _format_tool_results(self, execution_results: Dict[str, Any]) -> str:
    """Format tool execution results into readable summary.
    
    EXCLUDES entity generation tools to avoid first-person bias.
    """
    if not execution_results:
        return "No tools were executed for this scene."
    
    actions_executed = execution_results.get("actions_executed", [])
    
    if not actions_executed:
        return "No tools were executed for this scene."
    
    summary_parts = []
    
    # FILTER OUT entity generation tools
    entity_tools = ["character.generate", "location.generate"]
    
    for action in actions_executed:
        tool_name = action.get("tool", "unknown")
        
        # Skip entity generation tools
        if tool_name in entity_tools:
            continue
        
        result = action.get("result", {})
        
        # Format based on tool type
        if tool_name == "memory.search":
            query = action.get("args", {}).get("query", "")
            results = result.get("results", [])
            summary_parts.append(f"- Searched memory for '{query}': Found {len(results)} results")
        
        elif tool_name == "relationship.create":
            summary_parts.append(f"- Created new relationship")
        
        elif tool_name == "relationship.update":
            summary_parts.append(f"- Updated relationship")
        
        else:
            summary_parts.append(f"- Executed {tool_name}")
    
    if not summary_parts:
        return "No significant tool results to report."
    
    return "\n".join(summary_parts)
```

**Plus add explicit POV instruction to writer prompt:**

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

**Tool Results:** {tool_results_summary}

## POV Character

{pov_character_details}

## Location

{location_details}

## Your Task

Write a scene passage from {pov_character_name}'s deep POV.{scene_length_guidance}

**CRITICAL RULES:**

1. **Use exact character name** - The POV character is named "{pov_character_name}" - use this exact name, do not invent nicknames or alternate names
   - NEVER use placeholder formats like "char_name" or "character_name"
   - ALWAYS use the actual name: "{pov_character_name}"
2. **Third-person POV** - Write in third person using "{pov_character_name}" or pronouns (he/she/they)
   - NEVER use first person ("I", "my", "me") unless in dialogue
   - Example: "{pov_character_name} pressed a palm against..." NOT "I pressed my palm against..."
3. **Deep POV only** - Everything filtered through {pov_character_name}'s perception
4. **No omniscient narration** - Don't reveal what the character can't know
5. **Show don't tell** - Use actions, dialogue, and sensory details
6. **Sensory details** - Engage sight, sound, smell, touch, taste
7. **Internal thoughts and reactions** - Show character's mental state
8. **Length:** Write as much as the scene needs - no arbitrary limits

**AVOID:**
- First-person POV ("I", "my", "me") except in dialogue
- Placeholder formats like "char_elliot" or "character_name" - use the real name!
- Phrases like "unknown to them", "little did they know", "meanwhile"
- Head-hopping to other characters' thoughts
- Future foreshadowing the POV character couldn't know
- Telling emotions instead of showing them

**FOCUS ON:**
- What {pov_character_name} sees, hears, feels, thinks
- Immediate sensory experience
- Character voice and personality
- Concrete actions and dialogue
- Subtext and implication

Generate the scene now:"""
```

---

## Comparison of Options

### Option A: Two-Phase First Tick

**Pros:**
- ✅ Clean separation of concerns
- ✅ Entities truly established before scene writing
- ✅ No "Generated new character" in writer context
- ✅ More architecturally sound
- ✅ Easier to debug

**Cons:**
- ❌ More code changes
- ❌ Special case for tick 0
- ❌ Slightly more complex flow

### Option B: Filter Tool Results + Explicit POV

**Pros:**
- ✅ Minimal code changes
- ✅ Quick to implement
- ✅ Works for all ticks
- ✅ Explicit POV instruction helps

**Cons:**
- ❌ Hides information from writer
- ❌ Doesn't fully solve "just created" perception
- ❌ Relies on prompt engineering
- ❌ May not be 100% reliable

---

## Recommendation

**Implement Option B first** (quick fix), then **Option A later** (proper solution).

### Phase 1: Quick Fix (Option B)
1. Filter entity generation from tool results
2. Add explicit third-person POV instruction
3. Test with 5-10 stories
4. Measure: % of first scenes using third-person

### Phase 2: Proper Fix (Option A)
1. Implement two-phase first tick
2. Test thoroughly
3. Measure: Consistency across 20+ stories
4. Compare quality with Phase 1

---

## Testing Strategy

### Test 1: POV Consistency
- Generate 20 new stories
- Check first scene POV
- Target: 95%+ third-person

### Test 2: Character Names
- Verify no placeholder names appear
- Check all first scenes
- Target: 100% real names

### Test 3: Quality Check
- Compare first scenes before/after fix
- Subjective quality assessment
- Ensure no regression in prose quality

### Test 4: Edge Cases
- Multiple characters in first scene
- No character in first scene
- Character generated mid-scene

---

## Implementation Checklist

### Option B (Quick Fix)
- [ ] Update `_format_tool_results()` to filter entity generation
- [ ] Add explicit third-person instruction to writer prompt
- [ ] Test with 5 new stories
- [ ] Verify POV consistency
- [ ] Commit and document

### Option A (Proper Fix)
- [ ] Create `_first_tick()` method
- [ ] Create `_execute_entity_generation_only()` method
- [ ] Create `_execute_remaining_tools()` method
- [ ] Create `_update_plan_with_entity_ids()` method
- [ ] Create `_merge_execution_results()` method
- [ ] Refactor current `tick()` into `_normal_tick()`
- [ ] Update tick routing logic
- [ ] Test with 10 new stories
- [ ] Verify no regressions
- [ ] Update documentation

---

## Success Criteria

✅ **No placeholder names** in any scene  
✅ **Third-person POV** in 95%+ of first scenes  
✅ **Character names** appear correctly from first mention  
✅ **No quality regression** in prose  
✅ **Backward compatible** with existing projects  

---

## Related Issues

- Original placeholder name bug (fixed with current patch)
- First-person POV bias (this document addresses)
- Character voice consistency (related to vector search integration)

---

## Future Enhancements

### Smart POV Selection
Allow planner to specify POV preference:
```json
{
  "pov_character": "C0",
  "pov_style": "third-person-limited"  // or "first-person"
}
```

### Multi-Character First Scene
Handle cases where multiple characters are introduced in first scene

### POV Switching
Support intentional POV changes between scenes
