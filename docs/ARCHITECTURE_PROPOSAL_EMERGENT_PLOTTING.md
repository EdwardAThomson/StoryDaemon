# Architecture Proposal: Emergent Plot-First Generation

## Problem Statement

### Current Issues
1. **Repetitive wording** - LLM falls into similar phrasing patterns
2. **Circular plotting** - Characters repeat similar actions without progression
3. **Lack of forward momentum** - Story doesn't feel like it's building toward anything
4. **Reactive planning** - Each scene only considers immediate context

### Current Architecture (Reactive)

```
┌─────────────────────────────────────────────────────────────┐
│                    CURRENT FLOW (Per Tick)                   │
└─────────────────────────────────────────────────────────────┘

Tick N:
  1. Load recent scenes (summaries + full text)
  2. Strategic Planning: "What should happen next?"
     └─> Scene intention (1 sentence)
  3. Tactical Planning: "How to execute this scene?"
     └─> Tool calls, POV, location
  4. Execute tools (create entities, search memory)
  5. Write scene prose (500-800 words)
  6. Extract facts from prose
  7. Update entities
  8. Commit scene
  
Tick N+1:
  └─> Repeat (only knows about previous scenes)

PROBLEM: No long-term plot structure
         No forward planning beyond 1 scene
         No arc awareness
```

_Note (2025-11):_ The production system now layers additional **forward-momentum constraints** (planner `key_change` / `progress_milestone` and writer enforcement) and a per-scene **QA pass** that feeds back into planning on top of this reactive loop. Structurally, however, it still plans one scene at a time without a multi-beat plot outline, so this section remains a good description of the **current plot-level architecture** (reactive, but with stronger local constraints).

## Proposed Architecture: Emergent Plot-First

### Core Concept

**Separate plot development from prose writing:**
- **Plot Layer**: Factual, structured, emergent (like pseudocode)
- **Prose Layer**: Literary, detailed, executed against plot

### Two-Phase Approach

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 1: PLOT DEVELOPMENT                 │
│                    (Every N ticks or on-demand)              │
└─────────────────────────────────────────────────────────────┘

1. ANALYZE CURRENT STATE
   ├─> What plot threads exist?
   ├─> What character arcs are active?
   ├─> What tensions need resolution?
   └─> What's the current story momentum?

2. GENERATE PLOT OUTLINE (Next 5-10 beats)
   ├─> Beat 1: [Factual event description]
   ├─> Beat 2: [Factual event description]
   ├─> Beat 3: [Factual event description]
   └─> ...
   
   Format: Pseudocode-like, factual, no prose
   Example:
   - "Kyras discovers the gravity sink is sentient"
   - "Belia confronts Kyras about stolen credentials"
   - "The sink attempts to copy Belia's identity"
   - "Kyras must choose: save Belia or preserve data"
   - "Extraction window opens for 60 seconds"

3. VALIDATE PLOT COHERENCE
   ├─> Check against character goals
   ├─> Check against established lore
   ├─> Check for progression (not repetition)
   └─> Check for tension arc

4. COMMIT PLOT OUTLINE
   └─> Save as structured data (plot_outline.json)

┌─────────────────────────────────────────────────────────────┐
│                    PHASE 2: PROSE EXECUTION                  │
│                    (Every tick)                              │
└─────────────────────────────────────────────────────────────┘

Tick N:
  1. Load next plot beat from outline
  2. Plan scene to execute this beat
     └─> Tools, POV, location (tactical only)
  3. Execute tools
  4. Write prose WITH PLOT BEAT AS CONSTRAINT
     └─> "You must accomplish: [beat description]"
  5. Verify beat was accomplished
  6. Mark beat as complete
  7. Extract facts & update entities
  8. Commit scene
  
Tick N+1:
  └─> Load next beat, repeat

BENEFIT: Clear direction for each scene
         No repetition (beats are unique)
         Forward momentum (following plot)
         Better prose (knows where it's going)
```

## Implementation Design

### New Components

#### 1. PlotOutlineManager

```python
class PlotOutlineManager:
    """Manages the emergent plot outline."""
    
    def __init__(self, memory_manager, llm_interface):
        self.memory = memory_manager
        self.llm = llm_interface
        self.outline_file = memory_manager.project_path / "plot_outline.json"
    
    def load_outline(self) -> PlotOutline:
        """Load current plot outline."""
        if self.outline_file.exists():
            return PlotOutline.from_json(self.outline_file)
        return PlotOutline(beats=[])
    
    def generate_next_beats(self, count: int = 5) -> List[PlotBeat]:
        """Generate next N plot beats based on current state."""
        # Analyze current story state
        analysis = self._analyze_story_state()
        
        # Generate beats using LLM
        prompt = self._build_plot_generation_prompt(analysis, count)
        response = self.llm.generate(prompt)
        
        # Parse beats from response
        beats = self._parse_beats(response)
        
        # Validate beats
        validated_beats = self._validate_beats(beats)
        
        return validated_beats
    
    def get_next_beat(self) -> Optional[PlotBeat]:
        """Get the next unexecuted beat."""
        outline = self.load_outline()
        for beat in outline.beats:
            if beat.status == "pending":
                return beat
        return None
    
    def mark_beat_complete(self, beat_id: str, scene_id: str):
        """Mark a beat as executed."""
        outline = self.load_outline()
        for beat in outline.beats:
            if beat.id == beat_id:
                beat.status = "completed"
                beat.executed_in_scene = scene_id
                break
        self.save_outline(outline)
    
    def needs_regeneration(self) -> bool:
        """Check if we need to generate more beats."""
        outline = self.load_outline()
        pending = [b for b in outline.beats if b.status == "pending"]
        return len(pending) < 2  # Regenerate when < 2 beats remaining
```

#### 2. PlotBeat Entity

```python
@dataclass
class PlotBeat:
    """A single plot beat (factual event)."""
    id: str  # PB001, PB002, etc.
    description: str  # Factual description of what happens
    characters_involved: List[str]  # Character IDs
    location: Optional[str]  # Location ID
    plot_threads: List[str]  # Which threads this advances
    tension_target: int  # Target tension level (0-10)
    prerequisites: List[str]  # Beat IDs that must happen first
    status: str = "pending"  # pending, in_progress, completed, skipped
    created_at: str = ""
    executed_in_scene: Optional[str] = None
    execution_notes: str = ""
    
    # Metadata for validation
    advances_character_arcs: List[str] = field(default_factory=list)
    resolves_loops: List[str] = field(default_factory=list)
    creates_loops: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlotBeat":
        return cls(**data)


@dataclass
class PlotOutline:
    """Collection of plot beats."""
    beats: List[PlotBeat]
    created_at: str = ""
    last_updated: str = ""
    current_arc: str = ""  # Name of current story arc
    arc_progress: float = 0.0  # 0.0 to 1.0
    
    def to_json(self, filepath: Path):
        """Save to JSON file."""
        data = {
            "beats": [b.to_dict() for b in self.beats],
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "current_arc": self.current_arc,
            "arc_progress": self.arc_progress
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def from_json(cls, filepath: Path) -> "PlotOutline":
        """Load from JSON file."""
        with open(filepath) as f:
            data = json.load(f)
        beats = [PlotBeat.from_dict(b) for b in data["beats"]]
        return cls(
            beats=beats,
            created_at=data.get("created_at", ""),
            last_updated=data.get("last_updated", ""),
            current_arc=data.get("current_arc", ""),
            arc_progress=data.get("arc_progress", 0.0)
        )
```

#### 3. Modified Agent Flow

```python
class StoryAgent:
    """Modified agent with plot-first architecture."""
    
    def __init__(self, ...):
        # ... existing init ...
        self.plot_manager = PlotOutlineManager(self.memory, llm_interface)
    
    def tick(self, verbose: bool = False) -> dict:
        """Execute one story tick with plot-first approach."""
        tick = self.state["current_tick"]
        
        # === PLOT LAYER ===
        # Check if we need to generate more plot beats
        if self.plot_manager.needs_regeneration():
            print("   Generating plot outline...")
            new_beats = self.plot_manager.generate_next_beats(count=5)
            print(f"   Generated {len(new_beats)} plot beats")
        
        # Get next beat to execute
        current_beat = self.plot_manager.get_next_beat()
        
        if not current_beat:
            print("   No plot beats available. Generating...")
            new_beats = self.plot_manager.generate_next_beats(count=5)
            current_beat = new_beats[0] if new_beats else None
        
        if not current_beat:
            raise RuntimeError("Failed to generate plot beats")
        
        print(f"   Executing beat: {current_beat.description}")
        
        # === PROSE LAYER ===
        # PHASE 1: Planning (with beat constraint)
        print("   Phase 1: Planning scene...")
        plan = self._generate_plan_for_beat(current_beat)
        
        # Execute entity generation
        entity_results = self._execute_entity_generation_only(plan, tick)
        self._update_plan_with_entity_ids(plan, entity_results)
        
        # PHASE 2: Scene Writing (with beat constraint)
        print("   Phase 2: Writing scene...")
        writer_context = self.writer_context_builder.build_writer_context(
            plan, entity_results, self.state
        )
        
        # ADD BEAT CONSTRAINT TO CONTEXT
        writer_context["plot_beat"] = current_beat.description
        writer_context["plot_beat_requirements"] = {
            "characters": current_beat.characters_involved,
            "location": current_beat.location,
            "tension_target": current_beat.tension_target
        }
        
        scene_data = self.writer.write_scene(writer_context)
        
        # PHASE 3: Verification
        print("   Phase 3: Verifying beat execution...")
        beat_accomplished = self._verify_beat_execution(
            scene_data["text"],
            current_beat
        )
        
        if not beat_accomplished:
            print("   WARNING: Beat may not have been fully executed")
        
        # Mark beat as complete
        scene_id = self.committer.commit_scene(scene_data, tick, plan)
        self.plot_manager.mark_beat_complete(current_beat.id, scene_id)
        
        # ... rest of tick (fact extraction, etc.) ...
        
        return results
    
    def _generate_plan_for_beat(self, beat: PlotBeat) -> dict:
        """Generate tactical plan to execute a plot beat."""
        # Build context with beat information
        context = self.context_builder.build_planner_context(self.state)
        context["plot_beat"] = beat.description
        context["beat_characters"] = beat.characters_involved
        context["beat_location"] = beat.location
        
        # Use tactical planner (not strategic)
        # We already know WHAT to do (the beat)
        # We just need to figure out HOW (tools, POV, etc.)
        plan = self._tactical_planning_for_beat(context, beat)
        
        return plan
    
    def _verify_beat_execution(self, scene_text: str, beat: PlotBeat) -> bool:
        """Verify that the scene actually executed the beat."""
        prompt = f"""Did this scene accomplish the following plot beat?

Plot Beat: {beat.description}

Scene Text:
{scene_text}

Answer with YES or NO and brief explanation."""
        
        response = self.llm.generate(prompt, max_tokens=100)
        return response.strip().upper().startswith("YES")
```

### Plot Generation Prompt

```python
PLOT_GENERATION_PROMPT = """You are a plot architect for a story. Your job is to generate the next {count} plot beats.

## Current Story State

**Novel:** {novel_name}
**Current Tick:** {current_tick}
**Scenes Written:** {scenes_count}

**Active Character Arcs:**
{character_arcs}

**Open Plot Threads:**
{open_loops}

**Recent Events (Last 3 Scenes):**
{recent_scenes}

**Tension History:**
{tension_history}

## Your Task

Generate the next {count} plot beats. Each beat should:
1. Be FACTUAL (not prose) - describe what happens, not how it's written
2. ADVANCE the story - no repetition of previous events
3. Build TENSION - create rising action
4. Serve CHARACTER ARCS - develop characters meaningfully
5. Resolve or complicate PLOT THREADS

Format each beat as:
```
BEAT [number]:
Description: [One sentence describing what happens]
Characters: [Character IDs involved]
Location: [Location ID or "new"]
Tension: [0-10]
Advances: [Which plot threads/arcs this advances]
```

Example beats (from a different story):
```
BEAT 1:
Description: Detective discovers the victim's phone contains encrypted messages to an unknown contact
Characters: C0
Location: L2
Tension: 5
Advances: murder_investigation, C0_trust_issues

BEAT 2:
Description: Unknown contact responds to detective's bait message, revealing they know about the cover-up
Characters: C0, C3
Location: L2
Tension: 7
Advances: murder_investigation, conspiracy_thread
```

Generate {count} beats that continue THIS story:
"""
```

## Migration Path

### Phase 1: Add Plot Layer (Non-Breaking)
1. Implement `PlotOutlineManager` and entities
2. Add optional `--plot-mode` flag to CLI
3. Generate plot outline on demand
4. Store in `plot_outline.json`
5. **Don't change existing flow yet**

### Phase 2: Integrate Plot Constraints
1. Modify writer context to include plot beat
2. Update writer prompt to emphasize beat execution
3. Add beat verification step
4. **Still optional via config flag**

### Phase 3: Make Plot-First Default
1. Enable by default for new projects
2. Add migration tool for existing projects
3. Deprecate pure reactive mode

### Phase 4: Advanced Features
1. Multi-arc management
2. Beat branching (alternative paths)
3. Tension curve optimization
4. Character arc tracking

## Configuration

```yaml
# config.yaml
generation:
  # Plot-first mode
  use_plot_first: true
  plot_beats_ahead: 5  # Generate this many beats at a time
  plot_regeneration_threshold: 2  # Regenerate when this many left
  
  # Beat verification
  verify_beat_execution: true
  allow_beat_skip: false  # Strict mode: must execute beats in order
  
  # Fallback to reactive mode if plot generation fails
  fallback_to_reactive: true
```

## Benefits

### 1. **Forward Momentum**
- ✅ Story always moving toward specific goals
- ✅ No circular plotting
- ✅ Clear progression

### 2. **Reduced Repetition**
- ✅ Each beat is unique by design
- ✅ LLM has clear target to hit
- ✅ Validation prevents drift

### 3. **Better Pacing**
- ✅ Tension curve planned ahead
- ✅ Beats can be reordered for optimal flow
- ✅ Arc awareness

### 4. **Emergent Yet Structured**
- ✅ Plot emerges from story state (not pre-planned)
- ✅ AI figures out where to go next
- ✅ But commits to direction before writing prose

### 5. **Debugging & Control**
- ✅ Can inspect plot outline
- ✅ Can manually edit beats
- ✅ Can see which beat each scene executes
- ✅ Can regenerate beats if needed

## Example: Your Current Story

### Current State (Tick 17)
```
Kyras is trapped in relay, negotiating with hostile proxy
Belia's identity at risk of being copied
Gravity sink is artificial and dangerous
Extraction window is critical
```

### Reactive Mode (Current)
```
Tick 18: Plan scene → Write prose → Hope it advances plot
         (Might repeat similar negotiation beats)
```

### Plot-First Mode (Proposed)
```
GENERATE PLOT OUTLINE:

BEAT PB018:
Description: Proxy grants conditional extraction but demands full corpse feed first
Characters: C0 (Kyras)
Location: L0 (Relay)
Tension: 8
Advances: extraction_negotiation, trust_dilemma

BEAT PB019:
Description: Kyras uploads partial feed but gravity sink surges, threatening to collapse relay
Characters: C0 (Kyras)
Location: L0 (Relay)
Tension: 9
Advances: gravity_sink_threat, time_pressure

BEAT PB020:
Description: Belia's cadence destabilizes as sink attempts to copy her signature
Characters: C0 (Kyras), C1 (Belia)
Location: L0 (Relay)
Tension: 9
Advances: identity_theft_threat, C0_C1_relationship

BEAT PB021:
Description: Kyras must choose: complete upload for extraction or sever connection to save Belia
Characters: C0 (Kyras), C1 (Belia)
Location: L0 (Relay)
Tension: 10
Advances: moral_choice, character_arc_C0

BEAT PB022:
Description: Kyras severs connection, sink collapses, extraction shuttle arrives but Belia's status unknown
Characters: C0 (Kyras)
Location: L0 (Relay)
Tension: 8
Advances: extraction_success, belia_fate_mystery

---

Tick 18: Execute BEAT PB018
         Writer knows: "Proxy must grant extraction but demand feed"
         Prose written to accomplish this specific beat
         
Tick 19: Execute BEAT PB019
         Writer knows: "Sink surges during upload"
         No repetition - clear new event
         
... etc.
```

## Comparison to NovelWriter

### NovelWriter (Top-Down)
```
Human writes:
├─> Complete plot outline
├─> Chapter summaries
├─> Scene summaries
└─> AI fills in prose
```

### StoryDaemon Current (Bottom-Up)
```
AI generates:
└─> Scene by scene, reactive
    (No plot structure)
```

### StoryDaemon Proposed (Emergent Middle-Out)
```
AI generates:
├─> Plot beats (5-10 ahead)
│   └─> Emergent from story state
│   └─> Factual, structured
└─> Prose to execute beats
    └─> Constrained by beat goals
```

**Key Difference:** Plot emerges from AI analysis, but commits to structure before writing prose.

## Risks & Mitigations

### Risk 1: Plot beats too rigid
**Mitigation:** Allow beat editing, skipping, reordering

### Risk 2: LLM fails to execute beat
**Mitigation:** Verification step, retry with stronger constraint

### Risk 3: Plot generation fails
**Mitigation:** Fallback to reactive mode

### Risk 4: Beats become repetitive
**Mitigation:** Validation against previous beats, diversity scoring

## Next Steps

### Immediate (Phase 1)
1. ✅ Design architecture (this document)
2. ⬜ Implement `PlotBeat` and `PlotOutline` entities
3. ⬜ Implement `PlotOutlineManager`
4. ⬜ Create plot generation prompt
5. ⬜ Add CLI command: `novel plot generate`
6. ⬜ Test plot generation on existing story

### Short-term (Phase 2)
1. ⬜ Modify writer context to include beat
2. ⬜ Update writer prompt
3. ⬜ Add beat verification
4. ⬜ Test on new story with plot-first mode

### Long-term (Phase 3+)
1. ⬜ Make plot-first default
2. ⬜ Add beat editing UI
3. ⬜ Multi-arc management
4. ⬜ Tension curve optimization

---

## Conclusion

This architecture addresses your concerns:
- ✅ **Reduces repetition** - Each beat is unique
- ✅ **Forward momentum** - Always working toward specific goals
- ✅ **Emergent plotting** - AI figures out where to go
- ✅ **Structured execution** - Commits to direction before writing

The plot layer acts as a **"narrative compiler"** - translating story state into factual beats, then executing those beats as prose.

**Recommendation:** Start with Phase 1 (non-breaking addition) and test on your current story.

---

**Created:** November 13, 2025
**Status:** Proposal - Awaiting approval
**Impact:** Major architectural change
**Breaking:** No (with feature flag)
