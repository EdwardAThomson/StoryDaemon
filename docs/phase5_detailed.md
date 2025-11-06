# Phase 5 — Dynamic Entity Updates (Detailed Design)

**Goal:** Enable automatic extraction and updating of character states, locations, and narrative threads from generated scene prose.

---

## 1. Overview

Phase 5 adds intelligence to the story tick loop by extracting structured information from scene prose and updating the story world accordingly. This creates a feedback loop where:
- Characters evolve emotionally and physically
- Locations change based on events
- Open loops are created and resolved organically
- Memory stays synchronized with narrative reality

**Key Principle:** The story world should reflect what actually happened in the prose, not just what was planned.

---

## 2. Current State (Phase 4 Complete)

### What We Have
- ✅ Full scene generation pipeline (plan → execute → write → evaluate → commit)
- ✅ `Scene` entities with summaries stored in memory
- ✅ `Character` and `Location` entities with rich attributes
- ✅ `OpenLoop` entities for tracking narrative threads
- ✅ `MemoryManager` with update methods (`update_character`, `update_location`)
- ✅ `VectorStore` for semantic search
- ✅ `SceneCommitter` that saves scenes and creates Scene entities

### What Phase 4 Does
1. Generate scene prose (500-900 words)
2. Evaluate quality (word count, POV, continuity)
3. Save markdown file
4. Generate summary
5. Create Scene entity
6. Index in vector database
7. **STOPS HERE** ← Phase 5 continues from here

### The Gap
Currently, if a scene describes:
- "Sarah's hands trembled as she clutched the stolen key"
- "The tavern was now empty, chairs overturned"
- "She had to find her brother before dawn"

...none of this updates Sarah's emotional state, the tavern's description, or creates an open loop about finding her brother.

---

## 3. Phase 5 Architecture

### 3.1 Extended Story Tick Flow

```
┌─────────────────────────────────────────────────────────┐
│                     STORY TICK N                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [PHASE 4 - Already Complete]                          │
│  1-8. Plan, execute, write, evaluate, commit scene     │
│                                                         │
│  [PHASE 5 - NEW]                                       │
│  9. FACT EXTRACTION                                    │
│     ├─ Extract character updates from prose           │
│     ├─ Extract location changes from prose            │
│     ├─ Extract open loops (created/resolved)          │
│     └─ Extract relationship changes                   │
│                                                         │
│  10. ENTITY UPDATES                                    │
│     ├─ Apply character updates to memory              │
│     ├─ Apply location updates to memory               │
│     ├─ Create/resolve open loops                      │
│     ├─ Update relationships                           │
│     └─ Maintain entity history                        │
│                                                         │
│  11. VECTOR SYNC                                       │
│     └─ Re-index updated entities                      │
│                                                         │
│  12. UPDATE STATE                                      │
│     └─ Increment tick, update last_updated            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Design Decisions

### 4.1 Storage Structure

**Open Loops:** Single JSON file at `/memory/open_loops.json` containing array of OpenLoop entities
- Simpler than individual files
- Can optimize later if needed

**Relationships:** Single JSON file at `/memory/relationships.json` containing array of RelationshipGraph entities
- Maintains bidirectional graph structure
- Uses existing `RelationshipGraph` entity with `perspective_a` and `perspective_b`

### 4.2 Error Handling

**Fact Extraction Failures:**
1. Attempt extraction from scene prose
2. If JSON parsing fails → log warning, retry once
3. If retry fails → log error, continue tick WITHOUT entity updates
4. Scene is still saved successfully

**Rationale:** Don't lose a good scene due to extraction issues. Graceful degradation is better than tick failure.

### 4.3 Entity Field Usage

**Existing Fields (No Changes Needed):**
- `Character.current_state.emotional_state` ✅
- `Character.current_state.physical_state` ✅
- `Character.current_state.inventory` ✅
- `Character.current_state.goals` ✅
- `Character.history` ✅
- `Location.description` ✅
- `Location.atmosphere` ✅
- `Location.features` (use for notable_features) ✅
- `Location.history` ✅

**New Field Required:**
- `Character.current_state.beliefs: List[str]` - Add to `CurrentState` dataclass

**History Growth:**
- Keep unbounded history for Phase 5
- Can add pruning/archiving in Phase 6+ if needed

---

## 5. Component Design

### 5.1 Fact Extractor

**File:** `novel_agent/agent/fact_extractor.py` (NEW)

**Class:** `FactExtractor`

**Purpose:** Use LLM to extract structured updates from scene prose

**Key Methods:**
- `extract_facts(scene_text, scene_context)` - Main extraction method
- `_build_extraction_prompt(scene_text, scene_context)` - Build LLM prompt
- `_parse_extraction_response(response)` - Parse JSON response

**Returns structured dict with:**
- `character_updates` - Emotional state, physical state, inventory, goals, beliefs
- `location_updates` - Description, atmosphere, notable features
- `open_loops_created` - New narrative threads
- `open_loops_resolved` - Resolved thread IDs
- `relationship_changes` - Trust level, emotional tone shifts

---

### 5.2 Fact Extraction Prompt Template

**File:** `novel_agent/agent/prompts.py` (UPDATE existing)

**New constant:** `FACT_EXTRACTION_PROMPT_TEMPLATE`

**Prompt instructs LLM to:**
1. Analyze scene prose
2. Extract only facts explicitly shown or strongly implied
3. Return valid JSON with specific schema
4. Be conservative - only extract what's clearly present
5. Use null for fields with no updates

**JSON Schema:**
```json
{
  "character_updates": [
    {
      "id": "C0",
      "changes": {
        "emotional_state": "string or null",
        "physical_state": "string or null",
        "inventory": ["item1"] or null,
        "goals": ["goal1"] or null,
        "beliefs": ["belief1"] or null
      }
    }
  ],
  "location_updates": [...],
  "open_loops_created": [...],
  "open_loops_resolved": ["OL1"],
  "relationship_changes": [...]
}
```

---

### 5.3 Entity Updater

**File:** `novel_agent/agent/entity_updater.py` (NEW)

**Class:** `EntityUpdater`

**Purpose:** Apply extracted facts to memory entities with history tracking

**Key Methods:**
- `apply_updates(facts, tick, scene_id)` - Main update method
- `_update_character(update, tick, scene_id)` - Update character with history
- `_update_location(update, tick, scene_id)` - Update location with history
- `_create_open_loop(loop_data, tick, scene_id)` - Create new loop
- `_resolve_open_loop(loop_id, tick, scene_id)` - Mark loop resolved
- `_update_relationship(change, tick, scene_id)` - Update relationship

**History Tracking:**
Each update adds entry to entity's history array:
```python
{
  "tick": 5,
  "scene_id": "S5",
  "changes": {
    "emotional_state": {"old": "calm", "new": "anxious"},
    "inventory": "added: ['stolen key']"
  }
}
```

---

### 5.4 Advanced Continuity Checker

**File:** `novel_agent/agent/evaluator.py` (UPDATE existing)

**Enhancement:** Update `_check_continuity()` method to use extracted facts

Can check for:
- Character using items they don't have
- Character in location they can't reach
- Character knowing things they shouldn't
- Contradictions with established facts

---

## 6. Integration into StoryAgent

**File:** `novel_agent/agent/agent.py` (UPDATE existing)

**Add to `__init__()`:**
```python
from .fact_extractor import FactExtractor
from .entity_updater import EntityUpdater

self.fact_extractor = FactExtractor(llm_interface, config)
self.entity_updater = EntityUpdater(self.memory, config)
```

**Extend `tick()` method:**
After scene commit (step 8):
```python
# Step 9: Extract facts
facts = self.fact_extractor.extract_facts(scene_data["text"], writer_context)

# Step 10: Apply updates
update_stats = self.entity_updater.apply_updates(facts, tick, scene_id)

# Step 11: Re-index updated entities
self._reindex_updated_entities(facts)

# Step 12: Update state
self.state["current_tick"] += 1
self._save_state()
```

---

## 7. Configuration Updates

**File:** `novel_agent/configs/config.py` (UPDATE)

**Add new settings:**
```yaml
llm:
  extractor_max_tokens: 2000  # NEW

generation:
  enable_fact_extraction: true  # NEW - can disable for testing
  enable_entity_updates: true   # NEW - can disable for testing
```

---

## 8. Memory Manager Enhancements

**File:** `novel_agent/memory/manager.py` (UPDATE)

**Add new methods for single-file storage:**
- `load_open_loops()` - Load all open loops from `/memory/open_loops.json`
- `save_open_loops(loops)` - Save all open loops to single file
- `get_open_loop(loop_id)` - Get specific loop from loaded data
- `add_open_loop(open_loop)` - Add new loop to file
- `update_open_loop(loop_id, updates)` - Update specific loop
- `load_relationships()` - Load all relationships from `/memory/relationships.json`
- `save_relationships(relationships)` - Save all relationships to single file
- `get_relationship(char_a, char_b)` - Get relationship between characters
- `add_relationship(relationship)` - Add new relationship
- `update_relationship(char_a, char_b, updates)` - Update specific relationship

---

## 9. Entity Schema Updates

**File:** `novel_agent/memory/entities.py` (UPDATE)

**Add beliefs field to CurrentState:**
```python
@dataclass
class CurrentState:
    """Current state of a character."""
    location_id: Optional[str] = None
    emotional_state: str = ""
    physical_state: str = ""
    inventory: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    beliefs: List[str] = field(default_factory=list)  # NEW
```

**Note:** `history` field already exists on Character and Location entities!

**OpenLoop entity already exists with needed fields:**
- Uses `importance` instead of `urgency` (low, medium, high, critical)
- Uses `created_in_scene` instead of `created_scene`
- Uses `resolved_in_scene` instead of `resolved_scene`
- Has `category` field for classification
- Has `resolution_summary` for resolved loops

---

## 10. CLI Updates

**File:** `novel_agent/cli/main.py` (UPDATE)

**Enhanced output showing entity updates:**
```python
typer.echo(f"   9. Extracting facts...")
typer.echo(f"   10. Updating entities...")
typer.echo(f"   11. Syncing vector database...")

# After tick completes
entities = result.get('entities_updated', {})
if any(entities.values()):
    typer.echo(f"\n📊 Entity Updates:")
    if entities.get('characters'):
        typer.echo(f"   Characters: {entities['characters']}")
    if entities.get('locations'):
        typer.echo(f"   Locations: {entities['locations']}")
    if entities.get('loops_created'):
        typer.echo(f"   Loops created: {entities['loops_created']}")
    if entities.get('loops_resolved'):
        typer.echo(f"   Loops resolved: {entities['loops_resolved']}")
```

---

## 11. Implementation Order

1. **Update Entity Schemas** (`entities.py`)
   - Add `beliefs` field to `CurrentState` dataclass
   - Verify existing fields are sufficient

2. **Update Memory Manager** (`manager.py`)
   - Add open loops methods (single file storage)
   - Add relationships methods (single file storage)

3. **Fact Extraction Prompt** (`prompts.py`)
   - Add FACT_EXTRACTION_PROMPT_TEMPLATE

4. **Fact Extractor** (`fact_extractor.py`)
   - Implement FactExtractor class

5. **Entity Updater** (`entity_updater.py`)
   - Implement EntityUpdater class

6. **Evaluator Enhancement** (`evaluator.py`)
   - Update _check_continuity() method

7. **StoryAgent Integration** (`agent.py`)
   - Add Phase 5 components to __init__
   - Update tick() method

8. **Configuration** (`config.py`)
   - Add extractor_max_tokens
   - Add enable flags

9. **CLI Updates** (`main.py`)
   - Update output messages

10. **Testing**
    - Unit tests for each component
    - Integration test for full tick with updates

---

## 12. Testing Strategy

### Unit Tests

**File:** `tests/unit/test_fact_extractor.py`
- Test extraction prompt formatting
- Test JSON parsing
- Test handling of malformed LLM responses
- Test extraction with various scene types

**File:** `tests/unit/test_entity_updater.py`
- Test character updates with history tracking
- Test location updates with history tracking
- Test open loop creation
- Test open loop resolution
- Test relationship updates
- Test list field merging (inventory, goals, beliefs)

**File:** `tests/unit/test_continuity.py`
- Test enhanced continuity checking
- Test contradiction detection

### Integration Tests

**File:** `tests/integration/test_full_tick_phase5.py`
- Create test project
- Generate character and location
- Run full tick with mocked LLM responses
- Verify scene generated
- Verify facts extracted
- Verify entities updated
- Verify history tracked
- Verify vector re-indexing

**File:** `tests/integration/test_open_loops.py`
- Test loop creation from scene
- Test loop resolution in later scene
- Test loop persistence across ticks

---

## 13. Success Criteria

Phase 5 is complete when:

- ✅ Fact extraction prompt generates valid JSON
- ✅ Character emotional/physical states update from prose
- ✅ Character inventory, goals, beliefs update from prose
- ✅ Location descriptions update from prose
- ✅ Open loops created from narrative threads
- ✅ Open loops resolved when threads conclude
- ✅ Relationships update based on interactions
- ✅ Entity history tracks all changes with tick/scene references
- ✅ Vector database re-indexes updated entities
- ✅ CLI shows entity update statistics
- ✅ Integration tests pass
- ✅ Memory stays consistent with narrative

---

## 14. What Phase 5 Does NOT Include

Deferred to Phase 6+:

- ❌ Multi-agent collaboration (critic, world-builder)
- ❌ Branching storylines
- ❌ Advanced pacing control (tension trackers)
- ❌ GUI viewer for entities
- ❌ Relationship graph visualization
- ❌ Automatic contradiction resolution

Phase 5 focuses on **dynamic entity updates from prose**. Later phases will add more sophisticated analysis and control.

---

## 15. File Summary

### New Files
- `novel_agent/agent/fact_extractor.py` - FactExtractor class
- `novel_agent/agent/entity_updater.py` - EntityUpdater class
- `tests/unit/test_fact_extractor.py` - Extractor tests
- `tests/unit/test_entity_updater.py` - Updater tests
- `tests/unit/test_continuity.py` - Continuity tests
- `tests/integration/test_full_tick_phase5.py` - Full tick test
- `tests/integration/test_open_loops.py` - Open loop tests

### Modified Files
- `novel_agent/agent/prompts.py` - Add FACT_EXTRACTION_PROMPT_TEMPLATE
- `novel_agent/agent/agent.py` - Integrate Phase 5 components
- `novel_agent/agent/evaluator.py` - Enhanced continuity checking
- `novel_agent/memory/entities.py` - Add history fields
- `novel_agent/memory/manager.py` - Add open loop and relationship methods
- `novel_agent/configs/config.py` - Add extractor settings
- `novel_agent/cli/main.py` - Update output messages
- `novel_agent/agent/__init__.py` - Export new classes

### Existing Files Used (No Changes)
- `novel_agent/tools/codex_interface.py` - send_prompt()
- `novel_agent/memory/vector_store.py` - index_character(), index_location()

---

## 16. Design Considerations

### Why LLM-Based Extraction?
- More flexible than regex/NLP parsing
- Can understand context and implications
- Can extract abstract concepts (emotions, beliefs)
- Can be refined with better prompts

### Why History Tracking?
- Enables debugging ("when did this change?")
- Supports future features (undo, branching)
- Provides audit trail for entity evolution
- Helps with continuity checking

### Why Conservative Extraction?
- Prevents hallucination of facts not in prose
- Maintains narrative integrity
- Reduces false positives
- Keeps memory grounded in actual story

### Why Separate Extractor and Updater?
- Single responsibility principle
- Easier to test independently
- Can swap extraction strategies
- Can add validation layer between them

---

**Phase 5 Status: READY TO IMPLEMENT**

All design decisions made. Clear integration points with Phase 4. Ready to begin coding.
