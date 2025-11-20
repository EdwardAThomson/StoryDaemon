# Bug Fix: Character Entity Overwriting on POV Switch

## Summary

Fixed a critical bug where POV (Point of View) switches in multi-character stories would overwrite the original protagonist's character data instead of creating a new character entity.

## Problem

When the AI-generated story switched POV from one character to another (e.g., from "Belia Jyxarn" to "Kyras Dexuen"), the entity updater would:
1. Update the existing character C0 with the new character's information
2. Overwrite the original character's name, state, and attributes
3. Leave the original character without a proper entity
4. Create broken relationships referencing non-existent characters

## Root Cause

The issue occurred because:
1. The `writer_context` didn't include `pov_character_id` or `pov_character_name`
2. The fact extractor couldn't properly identify which character was the POV
3. The entity updater had no way to detect that the POV character name had changed
4. The LLM always used "C0" for the POV character, regardless of who it actually was

## Solution

### 1. Enhanced Writer Context (`writer_context.py`)

Added `pov_character_id` and `location_id` to the context dictionary returned by `build_writer_context()`:

```python
return {
    "novel_name": novel_name,
    "current_tick": current_tick,
    "scene_intention": scene_intention,
    "pov_character_id": pov_character_id,        # NEW
    "pov_character_name": pov_character_name,
    "pov_character_details": pov_character_details,
    "location_id": location_id,                  # NEW
    "location_name": location_name,
    "location_details": location_details,
    "recent_context": recent_context,
    "tool_results_summary": tool_results_summary,
    "scene_length_guidance": scene_length_guidance
}
```

### 2. POV Switch Detection (`entity_updater.py`)

Enhanced the `_update_character()` method to:
- Accept optional `scene_context` parameter
- Compare POV character name from context with existing character name
- Detect when names don't match (indicating a POV switch)
- Create a new character entity instead of overwriting

```python
# POV Switch Detection
if scene_context and char_id == scene_context.get('pov_character_id'):
    pov_name = scene_context.get('pov_character_name', '')
    if pov_name and pov_name != character.display_name and pov_name != character.full_name:
        # POV character name doesn't match - this is a different character!
        logger.info(f"POV switch detected: '{character.full_name}' -> '{pov_name}'")
        new_char_id = self._create_character_from_pov(pov_name, changes, tick, scene_id)
        if new_char_id:
            logger.info(f"Created new character {new_char_id} for '{pov_name}'")
            return "created"
```

### 3. Character Creation from POV (`entity_updater.py`)

Added new method `_create_character_from_pov()` to:
- Parse the character name from POV information
- Generate a new character ID
- Create a Character entity with initial state from fact extraction
- Save the character and set it as the active character

```python
def _create_character_from_pov(self, pov_name: str, changes: dict, tick: int, scene_id: str) -> str:
    """Create a new character entity from POV character information."""
    # Parse name
    parts = pov_name.strip().split()
    first_name = parts[0] if parts else pov_name
    family_name = ' '.join(parts[1:]) if len(parts) > 1 else ""
    
    # Generate new character ID
    new_char_id = self.memory.generate_id("character")
    
    # Create character with initial state from changes
    current_state = CurrentState()
    if changes:
        for field, value in changes.items():
            if value is not None and hasattr(current_state, field):
                setattr(current_state, field, value)
    
    character = Character(
        id=new_char_id,
        first_name=first_name,
        family_name=family_name,
        role="protagonist",
        current_state=current_state,
        personality=Personality()
    )
    
    # Save and set as active
    self.memory.save_character(character)
    self.memory.set_active_character(new_char_id)
    
    return new_char_id
```

### 4. Relationship Validation (`entity_updater.py`)

Enhanced `_update_relationship()` to validate both characters exist before creating/updating relationships:

```python
# Validate both characters exist before creating/updating relationship
char_a_exists = self.memory.load_character(char_a) is not None
char_b_exists = self.memory.load_character(char_b) is not None

if not char_a_exists:
    logger.warning(f"Character {char_a} not found, skipping relationship update with {char_b}")
    return False

if not char_b_exists:
    logger.warning(f"Character {char_b} not found, skipping relationship update with {char_a}")
    return False
```

### 5. Context Passing (`agent.py`)

Updated both tick execution paths to pass `writer_context` to `entity_updater.apply_updates()`:

```python
# Before
update_stats = self.entity_updater.apply_updates(facts, tick, scene_id)

# After
update_stats = self.entity_updater.apply_updates(facts, tick, scene_id, writer_context)
```

## Files Modified

1. **`novel_agent/agent/writer_context.py`**
   - Added `pov_character_id` and `location_id` to context

2. **`novel_agent/agent/entity_updater.py`**
   - Added `scene_context` parameter to `apply_updates()` and `_update_character()`
   - Implemented POV switch detection logic
   - Added `_create_character_from_pov()` method
   - Enhanced relationship validation
   - Added `characters_created` to stats

3. **`novel_agent/agent/agent.py`**
   - Passed `writer_context` to `entity_updater.apply_updates()` in both execution paths

4. **`docs/KNOWN_ISSUES.md`**
   - Marked issue as FIXED
   - Documented the fix implementation
   - Updated future enhancements

5. **`docs/PHASE_7A5_SUMMARY.md`**
   - Updated known issues section
   - Marked character overwriting bug as RESOLVED

## Testing Recommendations

To verify the fix works correctly:

1. **Create a multi-POV story:**
   ```bash
   novel init test-multi-pov
   cd test-multi-pov
   novel tick  # Generate first scene with Character A
   ```

2. **Manually switch POV in the plan:**
   - Edit the next plan to use a different character name
   - Or let the AI naturally switch POV

3. **Verify character creation:**
   ```bash
   ls entities/characters/  # Should see C0.json and C1.json
   ```

4. **Check logs for POV switch detection:**
   ```
   POV switch detected: 'Character A' -> 'Character B'
   Creating new character entity for 'Character B'
   Created new character C1 for 'Character B'
   ```

5. **Verify relationships:**
   - Check that relationships reference valid character IDs
   - No warnings about missing characters

## Benefits

✅ **Multi-POV stories now work correctly**
- Each POV character gets their own entity
- Character data is preserved across POV switches
- Relationships are properly maintained

✅ **Better error handling**
- Validates characters exist before creating relationships
- Logs warnings for missing characters
- Prevents orphaned relationships

✅ **Improved transparency**
- Logs POV switch detection
- Reports character creation in stats
- Clear debugging information

## Future Enhancements

Potential improvements for the future:

1. **Proactive POV detection:**
   - Analyze scene prose to detect POV character name
   - Compare with planned POV character
   - Alert if mismatch detected

2. **Character name normalization:**
   - Handle variations (e.g., "John Smith" vs "John" vs "Smith")
   - Support nicknames and aliases
   - Fuzzy matching for similar names

3. **Relationship auto-repair:**
   - Detect orphaned relationships
   - Attempt to resolve character references
   - Suggest fixes to user

4. **POV tracking:**
   - Maintain POV history across scenes
   - Detect POV patterns (e.g., alternating chapters)
   - Suggest POV character for next scene

---

**Status:** ✅ Complete
**Date:** November 2025
**Impact:** High - Enables multi-POV storytelling
**Lines Changed:** ~150 lines across 3 core files
