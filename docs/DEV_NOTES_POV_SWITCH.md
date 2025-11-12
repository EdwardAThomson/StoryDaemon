# Developer Notes: POV Switch Detection

## Quick Reference

### How It Works

1. **Writer Context** provides POV character name and ID
2. **Entity Updater** compares POV name with existing character name
3. **If names differ** → Create new character instead of updating
4. **If names match** → Update existing character normally

### Key Files

```
novel_agent/agent/
├── writer_context.py      # Provides pov_character_id & pov_character_name
├── entity_updater.py      # Detects POV switches, creates characters
└── agent.py               # Passes context to entity_updater

tests/unit/
└── test_entity_updater.py # Unit tests for POV detection
```

### Data Flow

```
Plan (from planner)
  └─> pov_character: "C0"
       └─> WriterContextBuilder.build_writer_context()
            ├─> Loads character C0 from memory
            ├─> Extracts character.full_name → "Alice Smith"
            └─> Returns context with:
                 - pov_character_id: "C0"
                 - pov_character_name: "Alice Smith"
                      └─> Agent.tick()
                           └─> EntityUpdater.apply_updates(facts, tick, scene_id, writer_context)
                                └─> _update_character(update, tick, scene_id, scene_context)
                                     ├─> Loads character C0
                                     ├─> Compares names:
                                     │    - C0.full_name = "Alice Smith"
                                     │    - scene_context.pov_character_name = "Bob Johnson"
                                     │    - Names differ! → POV switch detected
                                     └─> _create_character_from_pov("Bob Johnson", changes, tick, scene_id)
                                          ├─> Generates new ID: "C1"
                                          ├─> Creates Character(id="C1", first_name="Bob", family_name="Johnson")
                                          ├─> Saves to memory
                                          └─> Sets as active character
```

### Edge Cases Handled

#### 1. Name Variations
```python
# Handles both display_name and full_name
if pov_name != character.display_name and pov_name != character.full_name:
    # POV switch detected
```

**Example:**
- `character.first_name = "Alice"`
- `character.family_name = "Smith"`
- `character.display_name = "Alice"` (property)
- `character.full_name = "Alice Smith"` (property)
- POV name "Alice" → Matches display_name → No switch
- POV name "Alice Smith" → Matches full_name → No switch
- POV name "Bob" → Matches neither → POV switch!

#### 2. Empty/Missing Context
```python
if scene_context and char_id == scene_context.get('pov_character_id'):
    # Only check if context provided and this is POV character
```

**Behavior:**
- No context → Normal update (backward compatible)
- Context but different char_id → Normal update
- Context and POV char_id → Check for switch

#### 3. Non-POV Character Updates
```python
# Only POV character triggers switch detection
if char_id == scene_context.get('pov_character_id'):
    # Check for switch
```

**Example:**
- Update for C0 (POV) → Check for switch
- Update for C1 (non-POV) → Normal update

#### 4. Missing Characters in Relationships
```python
# Validate both characters exist
char_a_exists = self.memory.load_character(char_a) is not None
char_b_exists = self.memory.load_character(char_b) is not None

if not char_a_exists or not char_b_exists:
    logger.warning(f"Character not found, skipping relationship")
    return False
```

**Prevents:**
- Orphaned relationships
- References to non-existent characters
- Database inconsistencies

### Return Values

#### `_update_character()` Returns:
- `"updated"` - Character was updated successfully
- `"created"` - New character was created (POV switch)
- `""` - Nothing happened (character not found or no changes)

#### Usage in `apply_updates()`:
```python
result = self._update_character(char_update, tick, scene_id, scene_context)
if result == "updated":
    stats["characters_updated"] += 1
elif result == "created":
    stats["characters_created"] += 1
```

### Common Scenarios

#### Scenario 1: Single POV Story
```
Tick 0: POV = "Alice Smith" (C0 created)
Tick 1: POV = "Alice Smith" (C0 updated)
Tick 2: POV = "Alice Smith" (C0 updated)
...
Result: Only C0 exists, normal updates
```

#### Scenario 2: POV Switch
```
Tick 0-9:  POV = "Alice Smith" (C0 created, then updated)
Tick 10:   POV = "Bob Johnson" (C1 created, C0 preserved)
Tick 11:   POV = "Bob Johnson" (C1 updated)
Tick 12:   POV = "Alice Smith" (C0 updated - back to Alice)
...
Result: C0 and C1 both exist, switching between them
```

#### Scenario 3: Multiple POV Characters
```
Tick 0:  POV = "Alice" (C0 created)
Tick 1:  POV = "Bob" (C1 created)
Tick 2:  POV = "Carol" (C2 created)
Tick 3:  POV = "Alice" (C0 updated)
Tick 4:  POV = "Bob" (C1 updated)
...
Result: C0, C1, C2 all exist, rotating POV
```

### Debugging

#### Enable Debug Logging
```python
import logging
logging.getLogger('novel_agent.agent.entity_updater').setLevel(logging.DEBUG)
```

#### Log Messages to Watch For
```
INFO: POV switch detected: 'Alice Smith' -> 'Bob Johnson'
INFO: Creating new character entity for 'Bob Johnson'
INFO: Created new character C1 for 'Bob Johnson'
DEBUG: Updated character C0: ['emotional_state', 'physical_state']
WARNING: Character C2 not found, skipping relationship update with C1
```

#### Check Character Files
```bash
# List all characters
ls entities/characters/

# Expected after POV switch:
# C0.json  (Alice Smith)
# C1.json  (Bob Johnson)

# View character data
cat entities/characters/C0.json | jq '.first_name, .family_name'
```

### Testing

#### Manual Test
```bash
# 1. Create project
novel init test-pov-switch
cd test-pov-switch

# 2. Generate first scene (creates C0)
novel tick

# 3. Check character
cat entities/characters/C0.json | jq '.first_name, .family_name'

# 4. Manually edit plan to switch POV
# (or let AI naturally switch)

# 5. Generate next scene
novel tick

# 6. Check for new character
ls entities/characters/
# Should see C0.json and C1.json

# 7. Check logs for POV switch message
# Look for: "POV switch detected"
```

#### Unit Test
```bash
# Run specific test
python3 -m pytest tests/unit/test_entity_updater.py::test_pov_switch_detection_creates_new_character -v

# Run all entity updater tests
python3 -m pytest tests/unit/test_entity_updater.py -v
```

### Troubleshooting

#### Problem: POV switch not detected
**Possible causes:**
1. Context not passed to `apply_updates()`
   - Check: `entity_updater.apply_updates(facts, tick, scene_id, writer_context)`
2. POV character name not in context
   - Check: `writer_context['pov_character_name']` exists
3. Names match (not actually a switch)
   - Check: Compare `character.full_name` with `pov_character_name`

#### Problem: Character created every tick
**Possible causes:**
1. POV character name changing each tick
   - Check: Plan's `pov_character` field
2. Name comparison too strict
   - Check: Both `display_name` and `full_name` are compared

#### Problem: Relationships failing
**Possible causes:**
1. Character doesn't exist yet
   - Check: Character created before relationship update
2. Wrong character ID
   - Check: Relationship uses correct character IDs

### Performance Considerations

#### Character Name Comparison
- **Cost:** O(1) string comparison
- **Frequency:** Once per character update (typically 1-2 per tick)
- **Impact:** Negligible

#### Character Creation
- **Cost:** File I/O + JSON serialization
- **Frequency:** Only on POV switch (rare)
- **Impact:** Minimal (< 100ms)

#### Relationship Validation
- **Cost:** 2x character load operations
- **Frequency:** Per relationship update (0-5 per tick)
- **Impact:** Low (< 50ms total)

### Future Improvements

#### 1. Name Normalization
```python
def normalize_name(name: str) -> str:
    """Normalize character name for comparison."""
    # Remove titles, lowercase, strip whitespace
    return name.lower().strip()
```

#### 2. Fuzzy Matching
```python
from difflib import SequenceMatcher

def names_similar(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """Check if names are similar (handles typos)."""
    ratio = SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
    return ratio >= threshold
```

#### 3. Character Alias Support
```python
# In Character entity
nicknames: List[str] = field(default_factory=list)

# In POV detection
if pov_name in character.nicknames:
    # Same character, just using nickname
    pass
```

#### 4. POV History Tracking
```python
# In project state
pov_history: List[Dict[str, Any]] = [
    {"tick": 0, "character_id": "C0", "character_name": "Alice Smith"},
    {"tick": 10, "character_id": "C1", "character_name": "Bob Johnson"},
    # ...
]
```

### API Reference

#### `EntityUpdater.apply_updates()`
```python
def apply_updates(
    self,
    facts: dict,
    tick: int,
    scene_id: str,
    scene_context: dict = None
) -> dict:
    """
    Apply extracted facts to entities.
    
    Args:
        facts: Extracted facts from FactExtractor
        tick: Current tick number
        scene_id: Scene ID for history tracking
        scene_context: Optional scene context with:
            - pov_character_id: str
            - pov_character_name: str
            - location_id: str
    
    Returns:
        Statistics dictionary:
        {
            "characters_updated": int,
            "characters_created": int,
            "locations_updated": int,
            "loops_created": int,
            "loops_resolved": int,
            "relationships_updated": int
        }
    """
```

#### `EntityUpdater._create_character_from_pov()`
```python
def _create_character_from_pov(
    self,
    pov_name: str,
    changes: dict,
    tick: int,
    scene_id: str
) -> str:
    """
    Create a new character entity from POV character information.
    
    Args:
        pov_name: Full name of POV character (e.g., "Bob Johnson")
        changes: Character changes from fact extraction
        tick: Current tick number
        scene_id: Current scene ID
    
    Returns:
        New character ID if successful, None otherwise
    """
```

---

**Last Updated:** November 12, 2025
**Related Docs:** BUGFIX_POV_SWITCH.md, FIXES_SUMMARY.md, KNOWN_ISSUES.md
