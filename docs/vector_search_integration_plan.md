# Vector Search Integration Plan

**Date:** November 8, 2025  
**Status:** Proposed Enhancement  
**Related:** Context Window Strategy - Phase 2/3

---

## Problem Statement

Currently, we have a **fully functional vector database** (ChromaDB) that indexes all entities, but we're **not using it for context building**. Instead, we rely on:

1. **Chronological selection** - Always the last N scenes
2. **Direct JSON lookups** - Load specific entity by ID
3. **Linear scanning** - Iterate through all entities to find matches

### Why This is Limiting:

**JSON Lists are Hard to Search:**
- We store characters in `memory/characters/*.json`
- We store scenes in `memory/scenes/*.json`
- We store locations in `memory/locations/*.json`

To find "scenes where the protagonist felt afraid" we'd need to:
1. Load ALL scene JSON files
2. Parse each one
3. Check if summary mentions "afraid"
4. Check if POV character is protagonist
5. Manually rank by relevance

**Vector search does this in milliseconds with semantic understanding.**

---

## Current State

### What We Index (Already Working!)

**Characters:**
```python
# Indexed fields:
- name
- description
- role
- personality traits
- backstory
- current goals
```

**Locations:**
```python
# Indexed fields:
- name
- description
- type
- atmosphere
- features
```

**Scenes:**
```python
# Indexed fields:
- title
- summary (bullet points joined)
- key events
- emotional beats
```

### What We DON'T Use It For

❌ Building planner context  
❌ Building writer context  
❌ Finding relevant past scenes  
❌ Finding similar characters  
❌ Finding thematically related content  

### What We DO Use It For

✅ `memory.search` tool (agent can call this during planning)  
✅ That's it!

---

## Proposed Integration

### Phase 1: Smart Scene Selection for Writer Context

**Goal:** Instead of always using the last 2 scenes, use vector search to find the most relevant recent scenes.

#### Current Approach:
```python
# Always chronological
recent_scenes = scenes[-2:]  # Last 2 scenes
```

#### Proposed Approach:
```python
# Semantic relevance
query = scene_intention  # "Character confronts their fear"
relevant_scenes = vector_store.search_scenes(query, limit=5)

# Mix of chronological + relevant
full_text_scenes = [
    most_recent_scene,  # Always include last scene
    most_relevant_scene_from_search  # Add most relevant
]
```

**Benefits:**
- Writer sees scenes with similar themes/emotions
- Better continuity for recurring elements
- Can reference earlier setup for payoffs
- Maintains recent context (last scene always included)

---

### Phase 2: Character-Aware Context

**Goal:** When writing from a character's POV, include past scenes featuring that character.

#### Implementation:
```python
# Find scenes with this POV character
query = f"scenes featuring {character_name}"
character_scenes = vector_store.search_scenes(
    query,
    limit=3,
    filter={"pov_character_id": character_id}  # If we add metadata filtering
)

# Or simpler:
# Load all scenes, filter by pov_character_id, then rank by relevance
```

**Benefits:**
- Character voice consistency across their scenes
- Reference character's past experiences
- Maintain character arc continuity
- Better internal monologue consistency

---

### Phase 3: Location-Aware Context

**Goal:** When writing in a location, include past scenes in that location.

#### Implementation:
```python
# Find previous scenes in this location
if current_location_id:
    location_scenes = vector_store.search_scenes(
        query=f"scenes in {location_name}",
        limit=2
    )
```

**Benefits:**
- Consistent location descriptions
- Reference previous events in this location
- Maintain spatial continuity
- Reuse established sensory details

---

### Phase 4: Thematic Continuity

**Goal:** Find scenes with similar themes/emotions for tonal consistency.

#### Implementation:
```python
# Extract themes from scene intention
if "fear" in scene_intention.lower():
    thematic_scenes = vector_store.search_scenes(
        query="fear, anxiety, danger, threat",
        limit=2
    )
```

**Benefits:**
- Consistent emotional tone
- Thematic callbacks and echoes
- Better pacing (vary or maintain intensity)
- Payoff for earlier setup

---

## Detailed Implementation Plan

### Step 1: Enhance WriterContextBuilder

**File:** `novel_agent/agent/writer_context.py`

Add new method:
```python
def _get_relevant_scenes(
    self,
    scene_intention: str,
    pov_character_id: str,
    location_id: Optional[str],
    full_text_count: int = 2,
    summary_count: int = 3
) -> tuple[List[str], List[str]]:
    """Get relevant scenes using vector search.
    
    Args:
        scene_intention: What should happen in this scene
        pov_character_id: POV character ID
        location_id: Current location ID (if any)
        full_text_count: Number of scenes for full text
        summary_count: Number of scenes for summaries
    
    Returns:
        Tuple of (full_text_scene_ids, summary_scene_ids)
    """
    all_scene_ids = self.memory.list_scenes()
    
    if not all_scene_ids:
        return [], []
    
    # Strategy: Mix chronological + semantic relevance
    
    # 1. Always include the most recent scene (continuity)
    most_recent = all_scene_ids[-1] if all_scene_ids else None
    
    # 2. Search for semantically relevant scenes
    search_results = self.vector.search_scenes(
        query=scene_intention,
        limit=full_text_count + summary_count + 5  # Get extras to filter
    )
    
    # 3. Filter out the most recent (already included)
    relevant_ids = [
        r["entity_id"] for r in search_results 
        if r["entity_id"] != most_recent
    ]
    
    # 4. Optionally boost scenes with same POV character
    character_boosted = []
    for scene_id in relevant_ids:
        scene = self.memory.load_scene(scene_id)
        if scene and scene.pov_character_id == pov_character_id:
            character_boosted.insert(0, scene_id)  # Prioritize
        else:
            character_boosted.append(scene_id)
    
    # 5. Build final lists
    full_text_ids = [most_recent] if most_recent else []
    full_text_ids.extend(character_boosted[:full_text_count - 1])
    
    summary_ids = character_boosted[full_text_count - 1:full_text_count + summary_count - 1]
    
    return full_text_ids, summary_ids
```

Update `_format_recent_context()` to use this:
```python
def _format_recent_context(self, full_text_count: int = 2, summary_count: int = 3) -> str:
    # Get scene intention from context
    scene_intention = self.current_scene_intention  # Need to store this
    pov_character_id = self.current_pov_character_id
    location_id = self.current_location_id
    
    # Use vector search to find relevant scenes
    full_text_ids, summary_ids = self._get_relevant_scenes(
        scene_intention,
        pov_character_id,
        location_id,
        full_text_count,
        summary_count
    )
    
    # Rest of formatting logic...
```

---

### Step 2: Add Configuration Options

**File:** `novel_agent/configs/config.py`

```python
'generation': {
    # Existing
    'full_text_scenes_count': 2,
    'summary_scenes_count': 3,
    
    # New
    'use_vector_search_for_context': True,  # Enable/disable
    'vector_search_boost_same_character': True,  # Boost scenes with same POV
    'vector_search_boost_same_location': True,  # Boost scenes in same location
    'vector_search_recency_weight': 0.3,  # Balance relevance vs recency (0-1)
}
```

---

### Step 3: Enhance Vector Store with Metadata Filtering

**File:** `novel_agent/memory/vector_store.py`

Add metadata filtering to search:
```python
def search_scenes(
    self,
    query: str,
    limit: int = 5,
    pov_character_id: Optional[str] = None,
    location_id: Optional[str] = None,
    min_tick: Optional[int] = None,
    max_tick: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Search for relevant scenes with optional filters.
    
    Args:
        query: Search query
        limit: Max results
        pov_character_id: Filter by POV character
        location_id: Filter by location
        min_tick: Filter by minimum tick
        max_tick: Filter by maximum tick
    
    Returns:
        List of matching scenes
    """
    # Build ChromaDB where clause
    where = {}
    if pov_character_id:
        where["pov_character_id"] = pov_character_id
    if location_id:
        where["location_id"] = location_id
    
    # Search with filters
    results = self.scenes_collection.query(
        query_texts=[query],
        n_results=limit,
        where=where if where else None
    )
    
    # Post-filter by tick range if needed
    formatted = self._format_results(results)
    if min_tick is not None or max_tick is not None:
        formatted = [
            r for r in formatted
            if (min_tick is None or r["metadata"].get("tick", 0) >= min_tick)
            and (max_tick is None or r["metadata"].get("tick", 999) <= max_tick)
        ]
    
    return formatted
```

---

### Step 4: Update Scene Indexing to Include More Metadata

**File:** `novel_agent/memory/vector_store.py`

Enhance `index_scene()` to store more searchable metadata:
```python
def index_scene(self, scene: Scene):
    """Add or update scene in vector index."""
    
    # Build richer text for embedding
    text_parts = [
        f"Title: {scene.title}",
        f"Summary: {' '.join(scene.summary)}",
    ]
    
    if scene.key_events:
        text_parts.append(f"Events: {' '.join(scene.key_events)}")
    
    if scene.emotional_beats:
        text_parts.append(f"Emotions: {' '.join(scene.emotional_beats)}")
    
    text = "\n".join(text_parts)
    
    # Enhanced metadata
    metadata = {
        "entity_type": "scene",
        "name": scene.title,
        "tick": scene.tick,
        "pov_character_id": scene.pov_character_id,  # NEW
        "location_id": scene.location_id,  # NEW
        "word_count": scene.word_count,  # NEW
        "has_dialogue": len(scene.key_events) > 0,  # NEW (approximate)
    }
    
    self.scenes_collection.upsert(
        ids=[scene.id],
        documents=[text],
        metadatas=[metadata]
    )
```

---

## Hybrid Approach: Best of Both Worlds

Instead of pure vector search OR pure chronological, use a **hybrid scoring system**:

```python
def _score_scene_relevance(
    self,
    scene_id: str,
    vector_score: float,
    recency_weight: float = 0.3
) -> float:
    """Score scene by combining semantic relevance and recency.
    
    Args:
        scene_id: Scene ID
        vector_score: Semantic similarity score (0-1)
        recency_weight: How much to weight recency (0-1)
    
    Returns:
        Combined score (0-1)
    """
    all_scenes = self.memory.list_scenes()
    scene_index = all_scenes.index(scene_id)
    
    # Recency score: 1.0 for most recent, 0.0 for oldest
    recency_score = scene_index / len(all_scenes) if all_scenes else 0
    
    # Combine scores
    relevance_weight = 1.0 - recency_weight
    combined = (vector_score * relevance_weight) + (recency_score * recency_weight)
    
    return combined
```

**Example with recency_weight = 0.3:**
- Most recent scene: vector=0.6, recency=1.0 → score = 0.6*0.7 + 1.0*0.3 = 0.72
- Very relevant old scene: vector=0.9, recency=0.2 → score = 0.9*0.7 + 0.2*0.3 = 0.69
- Recent scene wins slightly, but strong relevance can overcome recency

---

## Use Cases & Examples

### Use Case 1: Callback to Earlier Event

**Scenario:** Scene 50 needs to reference an event from Scene 5

**Without vector search:**
- Writer context has scenes 48-49 (full text)
- Writer context has scenes 45-47 (summaries)
- Scene 5 is not in context at all
- LLM can't reference specific details from Scene 5

**With vector search:**
```python
scene_intention = "Character remembers the betrayal and confronts the traitor"
# Vector search finds Scene 5: "Betrayal revealed in the warehouse"
# Scene 5 is included in context
# LLM can reference specific details: warehouse, what was said, how it felt
```

### Use Case 2: Character Arc Continuity

**Scenario:** Writing Scene 30 from Character A's POV

**Without vector search:**
- Context has scenes 28-29 (might be from Character B's POV)
- Character A's voice from Scene 20 is not in context
- Character A's internal voice may drift

**With vector search:**
```python
# Boost scenes with same POV character
# Finds Scene 20, 15, 8 (all Character A's POV)
# Character A's voice and thought patterns are in context
# Consistent internal monologue style
```

### Use Case 3: Location Atmosphere

**Scenario:** Returning to a location after 20 scenes

**Without vector search:**
- Original location description from Scene 10 not in context
- Writer might describe it differently
- Sensory details might contradict

**With vector search:**
```python
# Search for scenes in this location
# Finds Scene 10: "Dark alley with broken streetlight, smell of rain"
# New scene maintains: darkness, broken streetlight, rain smell
# Consistent atmosphere
```

---

## Configuration Strategies

### Conservative (Minimal Change)
```yaml
generation:
  use_vector_search_for_context: false  # Disabled
  # Falls back to chronological selection
```

### Balanced (Recommended)
```yaml
generation:
  use_vector_search_for_context: true
  vector_search_recency_weight: 0.3  # 70% relevance, 30% recency
  vector_search_boost_same_character: true
  vector_search_boost_same_location: false  # Don't force location matches
```

### Aggressive (Maximum Relevance)
```yaml
generation:
  use_vector_search_for_context: true
  vector_search_recency_weight: 0.1  # 90% relevance, 10% recency
  vector_search_boost_same_character: true
  vector_search_boost_same_location: true
```

---

## Testing Strategy

### Test 1: Relevance Quality
- Generate 50 scenes
- At scene 50, create intention referencing scene 5
- Verify scene 5 appears in context
- Measure: Did LLM successfully reference scene 5 details?

### Test 2: Character Voice Consistency
- Generate 30 scenes with multiple POV characters
- Measure: Consistency of internal voice for each character
- Compare: Vector search vs chronological selection

### Test 3: Performance Impact
- Measure: Context building time with vector search
- Baseline: ~10-20ms without vector search
- Target: <50ms with vector search
- ChromaDB should be fast enough

### Test 4: Hybrid Scoring
- Test different recency_weight values (0.1, 0.3, 0.5, 0.7)
- Measure: Balance of relevance vs continuity
- Find optimal weight for story quality

---

## Rollout Plan

### Phase 1: Foundation (Week 1)
1. Add metadata filtering to `vector_store.search_scenes()`
2. Enhance scene indexing with POV character and location
3. Add configuration options
4. Write unit tests for vector search

### Phase 2: Basic Integration (Week 2)
1. Implement `_get_relevant_scenes()` in WriterContextBuilder
2. Add hybrid scoring (relevance + recency)
3. Make it configurable (can disable)
4. Test with 10-20 scene stories

### Phase 3: Advanced Features (Week 3)
1. Add character POV boosting
2. Add location boosting
3. Implement thematic search
4. Test with 50+ scene stories

### Phase 4: Optimization (Week 4)
1. Performance profiling
2. Tune recency weights
3. Add caching if needed
4. Production testing

---

## Potential Issues & Solutions

### Issue 1: Vector Search Too Slow
**Solution:** Cache recent search results, limit search to recent N scenes

### Issue 2: Irrelevant Results
**Solution:** Tune recency weight higher, add minimum relevance threshold

### Issue 3: Missing Recent Context
**Solution:** Always include most recent scene, use hybrid scoring

### Issue 4: Too Much Context (Token Budget)
**Solution:** Reduce full_text_count when using vector search, prioritize quality over quantity

---

## Success Metrics

- **Relevance:** Scenes in context are thematically related to current scene
- **Continuity:** Character voice remains consistent across 50+ scenes
- **Callbacks:** LLM successfully references earlier events when relevant
- **Performance:** Context building stays under 100ms
- **Quality:** Subjective improvement in story coherence

---

## Future Enhancements

### Smart Summary Generation
Use vector search to find relevant past events for checkpoint summaries

### Cross-Story Learning
Index scenes from multiple novels, find similar situations for inspiration

### Adaptive Context Window
Dynamically adjust context size based on scene complexity

### Semantic Clustering
Group related scenes for better chapter/act structure

---

## Conclusion

Vector search integration would transform our context building from **chronological** to **semantic**, enabling:

1. **Better callbacks** - Reference earlier events naturally
2. **Character consistency** - Maintain voice across long stories
3. **Thematic continuity** - Echo and develop themes
4. **Smarter context** - Include what's relevant, not just what's recent

The infrastructure is already in place - we just need to use it!

**Recommendation:** Start with Phase 1 (basic integration) and measure impact before adding complexity.
