# Known Issues

## 1. Character Entity Overwriting Bug (FIXED)

### Issue
When the AI switches POV to a new character mid-story, the entity updater may overwrite the original protagonist's character data instead of creating a new character entity.

### Example
In `scifi-new_0f2360ba`:
- **Tick 0-9:** POV character is "Belia Jyxarn" (created as C0)
- **Tick 10+:** POV switches to "Kyras Dexuen"
- **Bug:** C0's data was overwritten with Kyras's info, leaving Belia without a character entity
- **Result:** Relationships reference C1 (Belia) but C1 doesn't exist as a file

### Impact
- Character count shows 1 instead of 2
- Entity updater warns "Character C1 not found, skipping update"
- Relationships are broken (C0 ↔ C1 exists but C1 is missing)
- Semantic search for Belia won't work properly

### Root Cause
The entity updater (`entity_updater.py`) updates character data based on facts extracted from prose. When a new character becomes POV, the system should:
1. Detect it's a different character
2. Create a new character entity (C1)
3. Update relationships correctly

Instead, it was updating the existing C0 with the new character's data.

### Fix Implemented
✅ **Fixed** - Updated the following files:

1. **`writer_context.py`**: Added `pov_character_id` and `location_id` to writer context so fact extractor can properly identify entities

2. **`entity_updater.py`**: 
   - Added POV switch detection in `_update_character()`
   - Compares POV character name from scene context with existing character name
   - If names don't match, creates a new character entity instead of overwriting
   - New method `_create_character_from_pov()` to create characters from POV information
   - Sets the new character as the active character

3. **`agent.py`**: Passes `writer_context` to `entity_updater.apply_updates()` so it has access to POV character information

### Additional Fix: Relationship Validation
✅ Also added validation to prevent relationship creation with non-existent characters:
- Checks that both characters exist before creating/updating relationships
- Logs warnings when attempting to create relationships with missing characters
- Prevents orphaned relationships

### Status
✅ **Fixed** in current commit

### Priority
~~**Medium**~~ **RESOLVED**

---

## 2. Word Count Not Showing in Stats (FIXED)

### Issue
Story stats showed "0 words" despite scenes having word counts.

### Cause
`memory.list_scenes()` returns scene IDs (strings), not Scene objects.

### Fix
Updated `_show_story_stats()` to load each scene and read `word_count` attribute.

### Status
✅ **Fixed** in commit [current]

---

## Future Enhancements

### 1. POV Switch Detection ✅ IMPLEMENTED
~~Add explicit POV change detection:~~
- ✅ Compare protagonist name across scenes
- ✅ Alert when POV switches (via logging)
- ✅ Auto-create new character when POV switches to different character

### 2. Character Deduplication
- Detect when multiple names refer to same character
- Merge duplicate character entities
- Update all references

### 3. Relationship Validation ✅ IMPLEMENTED
~~- Validate both characters exist before creating relationship~~
- ✅ Validate both characters exist before creating/updating relationships
- ✅ Warn about orphaned relationships (via logging)
- Future: Auto-create missing character entities from relationships (if needed)

---

**Last Updated:** November 2025
**Latest Fix:** Character entity overwriting bug resolved - POV switches now create new characters instead of overwriting existing ones
