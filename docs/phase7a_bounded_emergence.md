# Phase 7A: Bounded Emergence Framework

**Date:** November 9, 2025  
**Status:** Planning  
**Goal:** Add foundational constraints to prevent random narrative drift while preserving emergent storytelling

---

## Problem Statement

### The Core Tension

**Bottom-up (StoryDaemon):** Story emerges from moment-to-moment decisions  
**Top-down (NovelWriter):** Story follows a predetermined structure

**Current Issue:** StoryDaemon starts with a completely blank slate, which can lead to:
- Random genre drift
- Unfocused narrative
- No clear protagonist
- Inconsistent tone/world rules
- Indeterminate timeframes for story loops
- No ranking of importance between loops

### What We Need

1. **Story boundaries** - Genre, setting, tone constraints
2. **Goal hierarchy** - Protagonist goals that drive the narrative
3. **Tension tracking** - Dynamic pacing to prevent flatness
4. **Lore consistency** - World rules that are tracked and enforced

---

## Current State Assessment

### What You DON'T Have ❌

- No genre specification
- No initial story premise/goal
- No protagonist definition
- No world constraints (setting, tone, themes)
- No tension/pacing tracking
- No goal hierarchy
- No lore/world rule tracking

### What You DO Have ✅

```python
@dataclass
class OpenLoop:
    importance: str = "medium"  # low, medium, high, critical
    category: str = ""  # mystery, relationship, goal, threat, etc.
    status: str = "open"  # open, resolved, abandoned
```

**Current behavior:**
- Open loops are sorted by importance in planner context
- But importance is just a string label
- No temporal structure - loops don't have deadlines or urgency
- No hierarchy - all loops are peers, no "main plot" vs "subplot"
- No goal tracking - loops describe problems, not destinations

---

## Proposed Solution: "Bounded Emergence Framework"

Add just enough structure to prevent randomness while preserving emergence within boundaries.

**Philosophy:**
- Set immutable constraints at project creation (genre, premise, setting)
- Let story goal emerge naturally from protagonist actions (after ~15 scenes)
- Track tension/pacing automatically to guide the AI
- Maintain lore consistency without rigid plotting

---

## Implementation: 3-Tier System

### Tier 1: Story DNA (Set at Creation) - REQUIRED

These are the **immutable constraints** that define the story's identity.

#### Enhanced `novel new` Command

**Interactive mode (recommended):**
```bash
novel new my-story --interactive

📚 Story Foundation Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Genre (e.g., fantasy, sci-fi, thriller, literary): science fiction
Premise (1-2 sentences, the story's core question): A lone engineer discovers an alien signal
Protagonist archetype (personality/role): Curious, isolated technical expert
Setting (time/place/world): Near-future Mars colony, 2087
Tone (mood/atmosphere): Contemplative, mysterious
Themes (optional, comma-separated): isolation, first contact, trust
```

**File-based mode (recommended for complex setups):**
```bash
novel new my-story --foundation foundation.yaml
```

Example `foundation.yaml`:
```yaml
genre: science fiction
premise: |
  A lone engineer discovers an alien signal and must decide 
  whether to report it or investigate alone
protagonist_archetype: Curious, isolated technical expert with trust issues
setting: Near-future Mars colony, 2087
tone: Contemplative, mysterious, with mounting tension
themes:
  - isolation
  - first contact
  - trust vs. paranoia
primary_goal: Decode the alien signal without alerting Earth authorities  # Optional
```

**Command-line mode:**
```bash
novel new my-story \
  --genre "science fiction" \
  --premise "A lone engineer discovers an alien signal" \
  --protagonist "Curious, isolated technical expert" \
  --setting "Near-future Mars colony" \
  --tone "Contemplative, mysterious"
```

#### Data Structure: `state.json`

```json
{
  "novel_name": "my-story",
  "project_id": "a1b2c3d4",
  
  "story_foundation": {
    "genre": "science fiction",
    "premise": "A lone engineer discovers an alien signal and must decide whether to report it or investigate alone",
    "protagonist_archetype": "Curious, isolated technical expert with trust issues",
    "setting": "Near-future Mars colony, 2087",
    "tone": "Contemplative, mysterious, with mounting tension",
    "themes": ["isolation", "first contact", "trust vs. paranoia"],
    "primary_goal": "Decode the alien signal without alerting Earth authorities"
  },
  
  "current_tick": 0,
  "active_character": null
}
```

---

### Tier 2: Goal Hierarchy (Emerges Early) - SEMI-AUTOMATIC

Track protagonist goals and let story goal crystallize naturally.

#### Enhanced Character Dataclass

```python
@dataclass
class Character:
    # Existing fields...
    
    # NEW: Goal hierarchy
    immediate_goals: List[str] = field(default_factory=list)  # "Fix the antenna"
    arc_goal: Optional[str] = None  # "Overcome isolation and trust others"
    story_goal: Optional[str] = None  # "Make contact with alien intelligence"
    
    # NEW: Goal tracking
    goal_progress: Dict[str, float] = field(default_factory=dict)
    goals_completed: List[str] = field(default_factory=list)
    goals_abandoned: List[str] = field(default_factory=list)
```

#### Enhanced OpenLoop Dataclass

```python
@dataclass
class OpenLoop:
    # Existing fields...
    
    # NEW: Tracking fields
    scenes_mentioned: int = 0  # How many scenes has this appeared in?
    last_mentioned_tick: Optional[int] = None
    is_story_goal: bool = False  # Promoted to main story goal?
```

#### Story Goals in State

```json
{
  "story_goals": {
    "primary": {
      "description": "Decode the alien signal without alerting Earth authorities",
      "source": "user_specified",  // or "auto_promoted"
      "promoted_at_tick": 0
    },
    "secondary": [],
    "promotion_candidates": [],
    "promotion_tick": 0
  }
}
```

**Note:** If `primary_goal` is specified in foundation, it's set immediately with `source: "user_specified"`. Otherwise, it auto-promotes during ticks 10-15 if conditions are met (protagonist exists, related loops with 5+ mentions).

#### Auto-Promotion Logic

After 10-15 scenes, the system automatically promotes the most active open loop (related to protagonist, mentioned 5+ times) to become the primary story goal.

```python
def check_goal_promotion(self, tick: int):
    """After 10-15 scenes, promote most active loop to story goal."""
    if tick < 10 or tick > 15:
        return
    
    if self.state.get('story_goals', {}).get('primary'):
        return
    
    # Find most mentioned protagonist-related loop
    top_loop = find_top_protagonist_loop()
    
    if top_loop.scenes_mentioned >= 5:
        promote_to_story_goal(top_loop)
        typer.echo(f"\n🎯 Story Goal Emerged: {top_loop.description}")
```

---

### Phase 7A.3: Tension Tracking - ✅ IMPLEMENTED

Scene-level tension scoring to maintain narrative momentum and pacing awareness.

#### Scene Tension Fields

Each scene now tracks tension automatically:

```python
@dataclass
class Scene:
    # ... existing fields ...
    tension_level: Optional[int] = None  # 0-10 scale
    tension_category: Optional[str] = None  # calm, rising, high, climactic
```

#### Tension Categories

- **calm** (0-3): Low-stakes, peaceful, reflective scenes
- **rising** (4-6): Building conflict, questions, uncertainty
- **high** (7-8): Active conflict, danger, revelations
- **climactic** (9-10): Peak moments, critical decisions, major events

#### TensionEvaluator

Analyzes scene prose using multiple factors:

```python
# Keyword analysis (40% weight)
- High tension: danger, threat, attack, panic, blood, death
- Medium tension: conflict, worry, suspicious, reveal, shock
- Low tension: calm, peace, safe, gentle, comfort

# Sentence structure (20% weight)
- Short sentences = higher tension
- Long, flowing sentences = lower tension

# Emotional intensity (30% weight)
- Exclamations, questions, dashes
- Action verbs: gasped, lunged, fled, screamed

# Open loops (10% weight)
- Creating loops = raising tension
- Resolving loops = lowering tension
```

#### Configuration

Tension tracking can be toggled:

```yaml
# config.yaml
generation:
  enable_tension_tracking: true  # Set to false to disable
```

#### Context Integration

Recent tension pattern appears in planner context:

```
### Tension Pattern
Recent tension: [3, 5, 7, 6, 4] (calm → rising → high → rising → rising)
```

This helps the planner make informed pacing decisions without rigid enforcement.

#### CLI Visualization

**`novel status`** shows tension history:

```
⚡ Tension Pattern:
   Tick   1:  3/10 [██████░░░░░░░░░░░░░░] (calm)
   Tick   2:  5/10 [██████████░░░░░░░░░░] (rising)
   Tick   3:  7/10 [██████████████░░░░░░] (high)
   Tick   4:  6/10 [████████████░░░░░░░░] (rising)
   Tick   5:  4/10 [████████░░░░░░░░░░░░] (rising)
   Progression: calm → rising → high → rising → rising
```

**`novel list scenes`** includes tension levels:

```
📝 Scenes (5 total)

  file          word_count  pov_character  tension_level
  ------------  ----------  -------------  -----------------
  scene_001.md  2,431       CHAR_001       3/10 (calm)
  scene_002.md  2,789       CHAR_001       5/10 (rising)
  scene_003.md  3,102       CHAR_001       7/10 (high)
```

---

## Updated Planner Prompt

```python
PLANNER_PROMPT_TEMPLATE = """You are a creative story planner for an emergent narrative system.

## Story Foundation (IMMUTABLE CONSTRAINTS)

**Genre:** {genre}
**Premise:** {premise}
**Setting:** {setting}
**Tone:** {tone}
**Themes:** {themes}

⚠️ **CRITICAL:** All scenes MUST respect these constraints. Do not drift into other genres or violate the established tone.

## Story Progress

**Current Tick:** {current_tick}
**Active Character (Protagonist):** {active_character_name} ({active_character_id})
  - Archetype: {protagonist_archetype}
  - Current Goals: {protagonist_immediate_goals}
  - Arc Goal: {protagonist_arc_goal}

{story_goal_section}

## Story Dynamics

**Tension Level:** {tension_level}/10 {tension_indicator}
**Stakes:** {stakes}
**Pacing:** {pacing}
**Scenes Since Major Event:** {scenes_since_major_event}

{pacing_guidance}

## Recent Story Context

### Overall Summary
{overall_summary}

### Recent Scenes
{recent_scenes_summary}

### Open Story Loops
{open_loops_list}

### Character Relationships
{character_relationships}

## Your Task

Create a plan for the next scene that:

1. ✅ **Respects the genre, premise, setting, and tone** (non-negotiable)
2. ✅ **Advances the protagonist's goals** (or creates meaningful obstacles)
3. ✅ **Addresses open loops appropriately**
4. {story_goal_guidance}
5. {pacing_guidance_specific}

[Rest of existing prompt structure...]
"""
```

---

## Implementation Phases

### Phase 7A.1: Story Foundation (Week 1)

**Goal:** Add foundational constraints at project creation

**Tasks:**
- [ ] Create `novel_agent/cli/foundation.py` with prompting and file loading functions
- [ ] Enhance `novel new` command with `--interactive` flag
- [ ] Add `--foundation <file>` flag to load from YAML file
- [ ] Add command-line flags for genre, premise, protagonist, setting, tone
- [ ] Update `create_novel_project()` to accept and store foundation
- [ ] Add `story_foundation` section to `state.json`
- [ ] Add foundation display to `novel status` command
- [ ] Write tests for foundation prompting, file loading, and validation

**Deliverables:**
- ✅ `novel new --interactive` prompts for story foundation
- ✅ `novel new --foundation file.yaml` loads from file
- ✅ Foundation stored in `state.json`
- ✅ Foundation visible in `novel status`

**Note:** Planner integration happens in Phase 7A.5 (Multi-Stage Prompts)

---

### Phase 7A.2: Goal Hierarchy (Week 2)

**Goal:** Track protagonist goals and auto-promote story goal

**Tasks:**
- [ ] Enhance `Character` dataclass with goal fields (`immediate_goals`, `arc_goal`)
- [ ] Enhance `OpenLoop` dataclass with tracking fields (`mentions_count`, `last_mentioned_tick`)
- [ ] Add `story_goals` section to `state.json`
- [ ] Implement `check_goal_promotion()` in `StoryAgent`
- [ ] Add goal tracking to fact extractor
- [ ] Create `novel goals` command to view hierarchy
- [ ] Write tests for goal promotion logic

**Deliverables:**
- ✅ Characters track immediate, arc, and story goals
- ✅ Story goal emerges automatically after 10-15 scenes
- ✅ `novel goals` shows goal hierarchy and progress

**Note:** Planner integration happens in Phase 7A.5 (Multi-Stage Prompts)

---

### Phase 7A.3: Tension Tracking (Week 3)

**Goal:** Track and guide story pacing automatically

**Tasks:**
- [ ] Create `novel_agent/agent/dynamics_tracker.py`
- [ ] Add `story_dynamics` to `state.json`
- [ ] Implement tension analysis from scene summaries (keyword-based)
- [ ] Implement pacing calculation from tension history
- [ ] Create `novel dynamics` command
- [ ] Add tension visualization to `novel status`
- [ ] Write tests for dynamics tracking

**Deliverables:**
- ✅ System tracks tension level (1-10)
- ✅ Detects major events and pacing issues
- ✅ `novel dynamics` shows tension graph

**Note:** Planner integration happens in Phase 7A.5 (Multi-Stage Prompts)

---

### Phase 7A.4: Lore Consistency (Week 4)

**Goal:** Track and enforce world rules

**Tasks:**
- [ ] Create `Lore` dataclass in `entities.py`
- [ ] Add lore collection to `VectorStore`
- [ ] Extract lore facts during scene commit (LLM-based)
- [ ] Index lore in vector store for semantic search
- [ ] Create `novel lore` command to list world rules
- [ ] Add lore contradiction detection (basic)
- [ ] Write tests for lore tracking

**Deliverables:**
- ✅ World rules tracked and indexed in vector store
- ✅ `novel lore` lists established world rules
- ✅ Basic contradiction detection

**Note:** Semantic lore retrieval happens in Phase 7A.5 (Multi-Stage Prompts)

---

### Phase 7A.5: Multi-Stage Prompts (Week 5-6)

**Goal:** Overhaul planner to use multi-stage prompting with semantic context selection

**Tasks:**

**Week 5: Core Multi-Stage Architecture**
- [ ] Create `novel_agent/agent/multi_stage_planner.py`
- [ ] Implement Stage 1: Strategic Planning prompt
- [ ] Implement Stage 2: Semantic context gathering (no LLM)
- [ ] Implement Stage 3: Tactical Planning prompt
- [ ] Add semantic loop filtering (simple keyword matching)
- [ ] Update `StoryAgent` to use `MultiStagePlanner`
- [ ] Add `novel plan -v` verbose output with stage statistics
- [ ] Write tests for multi-stage planning flow

**Week 6: Integration & Refinement**
- [ ] Integrate foundation into Stage 1 prompt
- [ ] Integrate goals into Stage 1 prompt
- [ ] Integrate dynamics into Stage 1 prompt
- [ ] Add semantic scene search to Stage 2
- [ ] Add semantic lore search to Stage 2
- [ ] Add configuration for stage token limits
- [ ] Performance testing and optimization
- [ ] Write integration tests

**Deliverables:**
- ✅ Multi-stage planner replaces single-stage planner
- ✅ Stage 1: Strategic planning (foundation + state → intention)
- ✅ Stage 2: Semantic context selection (vector search)
- ✅ Stage 3: Tactical planning (intention + context → plan)
- ✅ `novel plan -v` shows detailed stage statistics
- ✅ All foundation/goals/dynamics integrated into prompts
- ✅ Semantic filtering for scenes, loops, and lore

**Success Metrics:**
- Prompt sizes stay under 1,500 tokens per stage
- Only semantically relevant context included
- Planning quality maintained or improved
- Total planning time < 5 seconds

---

## Example Workflow

```bash
# Create with foundation
novel new mars-signal --interactive

📚 Story Foundation Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Genre: science fiction
Premise: A lone engineer discovers an alien signal
Protagonist: Curious, isolated technical expert
Setting: Mars colony, 2087
Tone: Contemplative, mysterious

✅ Created: mars-signal_f9a2b1c3/

# Generate first 15 scenes (exploration phase)
cd mars-signal_f9a2b1c3/
novel run --n 15

# System auto-promotes goal at tick 15
🎯 Story Goal Emerged: "Decode the alien signal without alerting Earth authorities"

# Check status
novel status
📊 Story Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Genre: Science Fiction
Story Goal: Decode the alien signal (15% progress)
Tension: 6/10 ⚡⚡
Protagonist: Dr. Sarah Chen (C0)
  - Arc Goal: Learn to trust others
  - Current: Repair antenna, avoid detection

# View goal hierarchy
novel goals
🎯 Goal Hierarchy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Story Goal: Decode the alien signal (15%)
  └─ Emerged at tick 15
  └─ Related to loop OL3

Protagonist Goals (C0 - Dr. Sarah Chen):
  Immediate:
    • Repair the antenna array [60%]
    • Avoid detection by colony security [30%]
  
  Arc Goal: Learn to trust others [10%]

# Continue with clear direction
novel run --n 20
```

---

## Benefits of This Approach

✅ **Prevents randomness** - Genre/premise/setting are fixed  
✅ **Preserves emergence** - Story goal discovered, not prescribed  
✅ **Character-driven** - Goals emerge from protagonist actions  
✅ **Pacing guidance** - Tension tracking prevents flatness  
✅ **Lore consistency** - World rules are tracked  
✅ **Minimal overhead** - Most tracking is automatic  
✅ **Flexible** - Can still surprise within boundaries  

---

## Prompt Size Management Strategy

### The Problem

Adding story foundation, goals, dynamics, and lore to the planner prompt will increase token usage significantly. LLM attention is non-linear - important information can get "lost" in large prompts.

### Current Prompt Structure

The planner prompt currently includes:
- Story state (tick, character, relationships) - ~200 tokens
- Recent scenes summary - ~400-800 tokens (configurable)
- Open loops - ~100-300 tokens
- Available tools - ~300 tokens
- Instructions - ~200 tokens

**Current total:** ~1,200-1,800 tokens

### Proposed Additions

- Story foundation - ~150 tokens
- Goal hierarchy - ~100-200 tokens
- Story dynamics - ~100 tokens
- Lore facts - ~200-500 tokens (grows over time)

**New total:** ~1,750-2,650 tokens

### Mitigation Strategies

#### Strategy 1: Hierarchical Context (Alternative - Not Used)

Keep a single prompt but use **strategic placement** and **token budgets**:

```
[IMMUTABLE CONSTRAINTS - Always at top]
Story Foundation (150 tokens max)

[CURRENT STATE - High priority]
Story Goal (100 tokens)
Protagonist Goals (100 tokens)
Story Dynamics (100 tokens)

[RECENT CONTEXT - Medium priority]
Recent Scenes (500 tokens max)
Open Loops (200 tokens max, top 5 by importance)

[REFERENCE INFO - Lower priority]
Available Tools (300 tokens)
Lore Facts (200 tokens max, most relevant)
```

**Benefits:**
- ✅ Single coherent prompt
- ✅ Most important info at top (better attention)
- ✅ Token budgets prevent bloat
- ✅ No architectural changes needed

**Implementation:**
- Add `max_tokens` parameter to each context builder method
- Truncate less important sections when needed
- Prioritize by recency/importance

#### Strategy 2: Multi-Stage Prompting (Chosen for Phase 7A.5)

Break planning into multiple focused LLM calls:

**Stage 1: Strategic Planning (Small prompt)**
```
Foundation + Goals + Dynamics → High-level intention
Output: "Focus on protagonist's trust issues, raise tension"
```

**Stage 2: Tactical Planning (Medium prompt)**
```
Strategic intention + Recent context + Tools → Specific actions
Output: Tool calls and scene intention
```

**Stage 3: Validation (Small prompt)**
```
Plan + Foundation + Lore → Consistency check
Output: Approved or revision needed
```

**Benefits:**
- ✅ Each prompt stays focused and small
- ✅ Better attention on specific tasks
- ✅ Can use different models for different stages

**Drawbacks:**
- ❌ More complex architecture
- ❌ More LLM calls (slower, more expensive)
- ❌ Requires careful orchestration

#### Strategy 3: Dynamic Context Selection (Chosen for Phase 7A.5)

Use semantic search to select only relevant context:

```python
def build_context(self, scene_intention_preview: str):
    # Get relevant lore based on scene intention
    relevant_lore = vector_search(scene_intention_preview, lore_db, top_k=3)
    
    # Get relevant loops based on protagonist goals
    relevant_loops = filter_loops_by_relevance(protagonist_goals, all_loops)
    
    # Build minimal context
    return build_prompt(foundation, relevant_lore, relevant_loops)
```

**Benefits:**
- ✅ Only includes relevant information
- ✅ Scales better as story grows
- ✅ Maintains focus

**Drawbacks:**
- ❌ Risk of missing important context
- ❌ Requires good relevance scoring
- ❌ More complex logic

### Recommendation for Phase 7A

**Use Strategy 2 (Multi-Stage Prompting) + Strategy 3 (Semantic Selection)** because:

1. **You already have vector search** - Just not using it for context building yet
2. **Better attention** - Each prompt stays focused on one task
3. **Semantic relevance** - Include only what matters for this scene
4. **Scalable** - Works even with 100+ scenes and loops
5. **Clearer separation** - Strategic thinking vs tactical planning

**Note:** This is more complex than Strategy 1, but you have the infrastructure already (ChromaDB is set up and working).

### Implementation Details: Multi-Stage + Semantic

**File:** `novel_agent/agent/multi_stage_planner.py` (new)

```python
class MultiStagePlanner:
    """Multi-stage planning with semantic context selection."""
    
    def __init__(self, memory_manager, vector_store, config):
        self.memory = memory_manager
        self.vector = vector_store
        self.config = config
    
    def plan(self, project_state: dict) -> dict:
        """Execute multi-stage planning."""
        
        # Stage 1: Strategic Planning (Small prompt)
        scene_intention = self._strategic_planning(project_state)
        
        # Stage 2: Semantic Context Gathering (No LLM)
        relevant_context = self._gather_relevant_context(
            scene_intention, 
            project_state
        )
        
        # Stage 3: Tactical Planning (Medium prompt)
        plan = self._tactical_planning(
            scene_intention,
            relevant_context,
            project_state
        )
        
        return plan
    
    def _strategic_planning(self, state: dict) -> str:
        """Stage 1: High-level scene intention.
        
        Prompt size: ~500 tokens
        """
        prompt = f"""You are planning the next scene in a story.

## Story Foundation (IMMUTABLE)
Genre: {state['story_foundation']['genre']}
Premise: {state['story_foundation']['premise']}
Setting: {state['story_foundation']['setting']}
Tone: {state['story_foundation']['tone']}

## Current State
Tick: {state['current_tick']}
Story Goal: {state.get('story_goals', {}).get('primary', {}).get('description', 'Still emerging')}
Tension: {state.get('story_dynamics', {}).get('tension_level', 3)}/10
Pacing: {state.get('story_dynamics', {}).get('pacing', 'steady')}

## Protagonist
{self._format_protagonist_brief(state)}

## Task
Based on the story foundation, current state, and pacing, what should happen in the next scene?

Respond with a single sentence describing the scene intention.
Example: "Protagonist discovers a clue about the signal's origin, raising tension"

Scene intention:"""
        
        # Call LLM (small, focused)
        response = send_prompt(prompt, max_tokens=100)
        return response.strip()
    
    def _gather_relevant_context(self, scene_intention: str, state: dict) -> dict:
        """Stage 2: Semantic context selection (No LLM call).
        
        Uses vector search to find relevant entities.
        """
        context = {}
        
        # Semantic search for relevant scenes
        relevant_scenes = self.vector.search_scenes(
            query=scene_intention,
            limit=3
        )
        context['relevant_scenes'] = self._format_scene_results(relevant_scenes)
        
        # Semantic filter for open loops
        all_loops = self.memory.get_open_loops()
        context['relevant_loops'] = self._semantic_filter_loops(
            scene_intention,
            all_loops,
            top_k=5
        )
        
        # Get protagonist's relationships (always relevant)
        protagonist_id = state.get('active_character')
        if protagonist_id:
            context['relationships'] = self.memory.get_character_relationships(
                protagonist_id
            )
        
        # Future: Semantic search for lore
        # context['relevant_lore'] = self.vector.search_lore(scene_intention, limit=3)
        
        return context
    
    def _semantic_filter_loops(self, query: str, loops: list, top_k: int) -> list:
        """Filter loops by semantic relevance to query."""
        # Create searchable text for each loop
        loop_texts = [
            f"{loop.category}: {loop.description}" 
            for loop in loops
        ]
        
        # Use vector store to find most relevant
        # (Could use a temporary collection or embed directly)
        scored_loops = []
        for i, loop in enumerate(loops):
            # Simple keyword matching for now
            # TODO: Use proper embedding similarity
            score = self._simple_relevance_score(query, loop_texts[i])
            scored_loops.append((score, loop))
        
        # Sort by score and return top K
        scored_loops.sort(reverse=True, key=lambda x: x[0])
        return [loop for score, loop in scored_loops[:top_k]]
    
    def _simple_relevance_score(self, query: str, text: str) -> float:
        """Simple keyword-based relevance (placeholder for embedding similarity)."""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())
        overlap = len(query_words & text_words)
        return overlap / max(len(query_words), 1)
    
    def _tactical_planning(self, scene_intention: str, context: dict, state: dict) -> dict:
        """Stage 3: Detailed plan with tool calls.
        
        Prompt size: ~1,000 tokens (only relevant context)
        """
        prompt = f"""You are creating a detailed plan for the next scene.

## Scene Intention
{scene_intention}

## Relevant Context

### Relevant Past Scenes
{context.get('relevant_scenes', 'None')}

### Relevant Open Loops
{self._format_loops(context.get('relevant_loops', []))}

### Character Relationships
{self._format_relationships(context.get('relationships', []))}

## Available Tools
{self._format_tools()}

## Task
Create a detailed plan to execute the scene intention.

Output JSON:
{{
  "rationale": "Why these actions support the scene intention",
  "actions": [
    {{"tool": "tool.name", "args": {{}}, "reason": "why"}}
  ],
  "expected_outcomes": ["outcome1", "outcome2"]
}}

Plan:"""
        
        # Call LLM (medium, focused)
        response = send_prompt(prompt, max_tokens=800)
        return parse_json(response)
```

**Key Differences from Current Approach:**

1. **Strategic prompt** (~500 tokens) - Just foundation + state → intention
2. **Semantic selection** (no LLM) - Vector search for relevant context
3. **Tactical prompt** (~1,000 tokens) - Intention + relevant context → actions

**Total LLM calls:** 2 (vs 1 currently)
**Total tokens:** ~1,500 (vs ~1,800 currently, but more focused)
**Relevance:** High (only includes semantically relevant context)

### Monitoring

Add to `novel plan -v` output:

```
📊 Multi-Stage Planning Statistics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Stage 1: Strategic Planning
  Input:  485 tokens (foundation + state + protagonist)
  Output: 18 tokens (scene intention)
  Time:   1.2s

Stage 2: Semantic Context Selection
  Scene intention: "Protagonist discovers clue about signal origin"
  Relevant scenes: 3 found (from 47 total)
  Relevant loops:  5 found (from 12 total)
  Relationships:   2 (protagonist's connections)
  Time:   0.3s (vector search)

Stage 3: Tactical Planning
  Input:  1,045 tokens (intention + relevant context + tools)
  Output: 312 tokens (plan JSON)
  Time:   2.1s

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total LLM calls: 2
Total tokens:    1,860 (input + output)
Total time:      3.6s
Relevance:       Only semantically relevant context included
```

### Future Enhancements to Multi-Stage

Once the basic multi-stage system is working:

1. **Improve semantic filtering** - Use proper embedding similarity instead of keyword matching for loop filtering
2. **Add lore collection** - Create vector store collection for world rules/lore facts
3. **Optimize stage 1** - Could cache strategic intention if story state hasn't changed much
4. **Add validation stage** - Optional 3rd LLM call to check plan consistency with foundation
5. **Parallel execution** - Run stage 1 and some context gathering in parallel

---

## Design Questions

1. **Foundation input method:** Interactive, command-line, or file-based?
   - Recommendation: Support all three - `--interactive` (default), `--foundation file.yaml`, or individual flags
   - File-based is best for complex setups and version control

2. **Foundation requirements:** Should genre/premise be required, or allow blank slate option?
   - Recommendation: Required for `--interactive`, optional for command-line (defaults to prompts)

3. **Goal promotion timing:** Auto-promote at tick 15, or manual command?
   - Recommendation: Auto-promote with notification, allow manual override with `novel goals promote --loop OL3`

4. **Lore tracking:** How detailed? Just major rules or everything?
   - Recommendation: Start with major rules (magic systems, tech limits, world facts), expand later

5. **Prompt architecture:** Single large prompt or multi-stage?
   - Recommendation: Multi-stage (Strategy 2 + 3) because:
     * You already have vector search infrastructure
     * Better attention and focus per prompt
     * Semantic relevance improves quality
     * Scales better as stories grow
   - Trade-off: 2 LLM calls instead of 1 (slightly slower, but more focused)

6. **Semantic filtering:** How to score loop relevance?
   - Recommendation: Start with simple keyword matching (fast, good enough)
   - Upgrade to embedding similarity in Phase 7B if needed
   - ChromaDB can handle this with temporary collections

7. **Lore tracking:** Index in vector store or separate file?
   - Recommendation: Add lore collection to vector store (consistent with other entities)
   - Allows semantic search for relevant world rules
   - Implement in Phase 7A.4

---

## Success Criteria

Phase 7A is complete when all sub-phases are done:

**Phase 7A.1: Story Foundation**
- [ ] `novel new --interactive` prompts for and stores story foundation
- [ ] `novel new --foundation file.yaml` loads foundation from YAML file
- [ ] Foundation visible in `novel status`

**Phase 7A.2: Goal Hierarchy**
- [ ] Characters track immediate, arc, and story goals
- [ ] Story goal emerges automatically after 10-15 scenes
- [ ] `novel goals` shows goal hierarchy and progress

**Phase 7A.3: Tension Tracking**
- [ ] System tracks tension level (1-10) after each scene
- [ ] `novel dynamics` shows tension graph
- [ ] Pacing detection working (slow/steady/accelerating/climactic)

**Phase 7A.4: Lore Consistency**
- [ ] World rules tracked and indexed in vector store
- [ ] `novel lore` lists established world rules
- [ ] Basic contradiction detection working

**Phase 7A.5: Multi-Stage Prompts**
- [ ] Multi-stage planner replaces single-stage planner
- [ ] Stage 1: Strategic planning (foundation + state → intention)
- [ ] Stage 2: Semantic context selection (vector search)
- [ ] Stage 3: Tactical planning (intention + context → plan)
- [ ] `novel plan -v` shows detailed stage statistics
- [ ] All foundation/goals/dynamics integrated into prompts
- [ ] Semantic filtering for scenes, loops, and lore

**Overall:**
- [ ] All features have unit tests
- [ ] Integration tests pass
- [ ] Documentation is complete
- [ ] Performance acceptable (< 5s per tick)

---

## Future Enhancements (Phase 7B+)

**Prompt Improvements:**
- **Advanced token budgets** - More sophisticated token management if needed
- **Embedding-based loop filtering** - Replace keyword matching with proper embeddings
- **Validation stage** - Optional 3rd LLM call to check plan consistency
- **Prompt caching** - Cache strategic intention if state hasn't changed

**Feature Enhancements:**
- **Multi-protagonist support** - Track goals for multiple POV characters
- **Phase system** - Optional act structure (setup, development, climax, resolution)
- **Critic agent** - LLM-based quality assessment of genre consistency
- **Advanced lore contradiction detection** - LLM-based consistency checking
- **Tension visualization** - Interactive graph of tension over time
- **Goal progress estimation** - LLM-based progress assessment
- **Theme tracking** - Ensure themes are explored throughout story

---

## Related Documentation

- [Implementation Plan](plan.md) - Overall project roadmap
- [Phase 6 Complete](PHASE6_COMPLETE.md) - CLI enhancements
- [Project Safety](project_safety_improvements.md) - UUID system
- [Technical Specification](spec.md) - System architecture
