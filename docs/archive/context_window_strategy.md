# Context Window Strategy

**Date:** November 8, 2025  
**Status:** Proposed Enhancement  
**Related:** Phase 7 improvements

---

## Problem Statement

Currently, StoryDaemon only sends **scene summaries** to the writer LLM, never full scene text. While this keeps the context window small, it has drawbacks:

- **Prose style/voice inconsistency** - Writer can't match previous prose style
- **Lost sensory details** - Summaries don't capture atmosphere, sensory details
- **Character voice drift** - Dialogue patterns and internal voice may shift
- **Continuity gaps** - Can't reference specific moments, dialogue, or descriptions

Since scenes are only 200-400 words each, we have room to include recent full text without overwhelming the context window.

---

## Current Implementation

### Planner Context (for planning next scene)
```
- Overall summary (1 line)
- Last 3 scenes (summaries only)
- Open loops (all)
- Active character details (full)
- Character relationships (full)
```

**Token budget:** ~1000 max tokens for plan generation

### Writer Context (for generating prose)
```
- Last 2 scenes (summaries only)
- POV character details (full)
- Location details (full)
- Tool results (what was just created)
- Scene intention (from plan)
```

**Token budget:** ~3000 max tokens for prose generation

---

## Proposed Solution: Hierarchical Memory

Implement a **three-tier context strategy** that balances detail with context window efficiency.

### Tier 1: Immediate Context (Full Text)
**Last 2-3 scenes** - Include complete prose text
- **Purpose:** Maintain prose style, voice, atmosphere
- **Cost:** ~600-1200 words (well within budget)
- **Benefit:** Writer can match tone, pacing, sensory details

### Tier 2: Recent Context (Detailed Summaries)
**Scenes 3-10** - Bullet-point summaries
- **Purpose:** Plot continuity, character arc tracking
- **Cost:** ~200-400 words
- **Benefit:** Story beats without overwhelming detail

### Tier 3: Historical Context (Checkpoint Summaries)
**Older scenes** - Rolled into checkpoint summaries
- **Purpose:** Long-term story arc awareness
- **Cost:** ~100-200 words per checkpoint
- **Benefit:** Maintains awareness of earlier story without bloat

---

## Implementation Plan

### 1. Update Writer Context Builder

**File:** `novel_agent/agent/writer_context.py`

Modify `_format_recent_context()`:
```python
def _format_recent_context(self, full_text_count: int = 2, summary_count: int = 3) -> str:
    """Format recent context with full text for immediate scenes.
    
    Args:
        full_text_count: Number of recent scenes to include full text
        summary_count: Number of older scenes to include as summaries
    
    Returns:
        Formatted context with full text + summaries
    """
    scene_ids = self.memory.list_scenes()
    
    if not scene_ids:
        return "This is the first scene of the novel."
    
    context_parts = []
    
    # Get last N scenes for full text
    full_text_ids = scene_ids[-full_text_count:] if len(scene_ids) >= full_text_count else scene_ids
    
    # Get older scenes for summaries
    summary_start = max(0, len(scene_ids) - full_text_count - summary_count)
    summary_end = len(scene_ids) - full_text_count
    summary_ids = scene_ids[summary_start:summary_end] if summary_end > summary_start else []
    
    # Add summary scenes first
    if summary_ids:
        context_parts.append("## Earlier Scenes (Summaries)\n")
        for scene_id in summary_ids:
            scene = self.memory.load_scene(scene_id)
            if scene:
                context_parts.append(f"**Scene {scene.tick}: {scene.title}**")
                if scene.summary:
                    for bullet in scene.summary:
                        context_parts.append(f"- {bullet}")
                context_parts.append("")
    
    # Add full text scenes
    if full_text_ids:
        context_parts.append("## Recent Scenes (Full Text)\n")
        for scene_id in full_text_ids:
            scene = self.memory.load_scene(scene_id)
            if scene:
                # Load the actual scene markdown file
                scene_file = self.memory.project_dir / "scenes" / f"scene_{scene_id[1:].zfill(3)}.md"
                if scene_file.exists():
                    scene_text = scene_file.read_text()
                    context_parts.append(f"**Scene {scene.tick}: {scene.title}**\n")
                    context_parts.append(scene_text)
                    context_parts.append("\n---\n")
    
    return "\n".join(context_parts).strip()
```

### 2. Add Checkpoint Summary Generation

**File:** `novel_agent/memory/checkpoint.py` (or new file `summarizer.py`)

```python
def generate_checkpoint_summary(
    project_dir: Path,
    start_tick: int,
    end_tick: int,
    llm_interface
) -> str:
    """Generate comprehensive summary for a range of scenes.
    
    Args:
        project_dir: Project directory
        start_tick: Starting tick number
        end_tick: Ending tick number
        llm_interface: LLM for summary generation
    
    Returns:
        Comprehensive summary text
    """
    # Load all scenes in range
    memory = MemoryManager(project_dir)
    scene_ids = [f"S{str(i).zfill(3)}" for i in range(start_tick, end_tick + 1)]
    
    scenes_text = []
    for scene_id in scene_ids:
        scene = memory.load_scene(scene_id)
        if scene and scene.summary:
            scenes_text.append(f"Tick {scene.tick}: {', '.join(scene.summary)}")
    
    # Generate summary with LLM
    prompt = f"""Summarize the following story progression into 3-5 key plot points:

{chr(10).join(scenes_text)}

Provide a concise summary focusing on:
- Major plot developments
- Character changes
- New story threads introduced
- Resolved conflicts

Format as bullet points."""
    
    summary = llm_interface.generate(prompt, max_tokens=500)
    return summary.strip()
```

### 3. Update Configuration

**File:** `novel_agent/configs/config.py`

Add new config options:
```python
DEFAULT_CONFIG = {
    'llm': {
        'codex_bin_path': 'codex',
        'planner_max_tokens': 1000,
        'writer_max_tokens': 3000,
        'extractor_max_tokens': 2000,
        'summarizer_max_tokens': 500,  # NEW
        'timeout': 120,
    },
    'generation': {
        'max_tools_per_tick': 3,
        'recent_scenes_count': 3,
        'full_text_scenes_count': 2,  # NEW - for writer context
        'summary_scenes_count': 3,    # NEW - for writer context
        'checkpoint_summary_interval': 10,  # NEW - generate summary every N ticks
        'include_overall_summary': True,
        'enable_fact_extraction': True,
        'enable_entity_updates': True,
    }
}
```

### 4. Integrate Checkpoint Summaries

**File:** `novel_agent/agent/agent.py`

Add summary generation at checkpoint intervals:
```python
# After scene commit, check if we should generate checkpoint summary
if tick > 0 and tick % self.config.get('generation.checkpoint_summary_interval', 10) == 0:
    print(f"   📊 Generating checkpoint summary for ticks {tick-9} to {tick}...")
    try:
        from ..memory.summarizer import generate_checkpoint_summary
        summary = generate_checkpoint_summary(
            self.project_dir,
            tick - 9,
            tick,
            self.llm
        )
        # Store summary in a special file
        summary_file = self.project_dir / "summaries" / f"checkpoint_{tick}.md"
        summary_file.parent.mkdir(exist_ok=True)
        summary_file.write_text(summary)
        print(f"   ✅ Checkpoint summary saved")
    except Exception as e:
        print(f"   ⚠️  Summary generation failed: {e}")
```

---

## Token Budget Analysis

### Current Writer Context (~800 tokens)
```
- Scene summaries (2 scenes × 100 words): 200 words
- Character details: 200 words
- Location details: 150 words
- Tool results: 100 words
- Prompt template: 150 words
Total: ~800 words = ~1000 tokens
```

### Proposed Writer Context (~2000 tokens)
```
- Full scene text (2 scenes × 300 words): 600 words
- Scene summaries (3 scenes × 100 words): 300 words
- Character details: 200 words
- Location details: 150 words
- Tool results: 100 words
- Prompt template: 150 words
Total: ~1500 words = ~2000 tokens
```

**Remaining budget:** 3000 - 2000 = **1000 tokens for generation** (plenty!)

---

## Benefits

### Prose Quality
- ✅ Consistent voice and style across scenes
- ✅ Matching sensory detail density
- ✅ Continuity of atmosphere and tone
- ✅ Character voice consistency

### Memory Efficiency
- ✅ Full text only for immediate context (2-3 scenes)
- ✅ Summaries for recent context (3-10 scenes)
- ✅ Checkpoint summaries for historical context (10+ scenes)
- ✅ Total context stays under 2000 tokens

### Long-term Coherence
- ✅ Checkpoint summaries prevent drift over 50+ scenes
- ✅ Hierarchical memory mirrors human memory (detailed recent, fuzzy distant)
- ✅ Can reference specific moments from recent scenes
- ✅ Maintains story arc awareness from checkpoint summaries

---

## Rollout Plan

### Phase 1: Full Text Context (Immediate)
- Update `WriterContextBuilder._format_recent_context()`
- Add config options for `full_text_scenes_count`
- Test with existing projects
- Verify prose consistency improves

### Phase 2: Checkpoint Summaries (Next)
- Implement `generate_checkpoint_summary()`
- Integrate into agent tick cycle
- Store summaries in `summaries/` directory
- Add to context builder for historical context

### Phase 3: Dynamic Context (Future)
- Adjust context based on scene length
- If scenes are long (800+ words), reduce full text count
- If scenes are short (200 words), increase full text count
- Smart context window management

---

## Testing Strategy

### Test 1: Style Consistency
- Generate 10 scenes with current system
- Generate 10 scenes with full text context
- Compare prose style metrics:
  - Sentence length variance
  - Vocabulary consistency
  - Sensory detail density
  - Character voice markers

### Test 2: Context Window Usage
- Monitor token usage with full text
- Verify we stay under 3000 token budget
- Test with varying scene lengths

### Test 3: Long-form Coherence
- Generate 50+ scene story
- Check for drift in:
  - Character personality
  - World rules
  - Tone and atmosphere
  - Plot consistency

---

## Configuration Examples

### Conservative (Minimal Context)
```yaml
generation:
  full_text_scenes_count: 1
  summary_scenes_count: 2
  checkpoint_summary_interval: 20
```

### Balanced (Recommended)
```yaml
generation:
  full_text_scenes_count: 2
  summary_scenes_count: 3
  checkpoint_summary_interval: 10
```

### Aggressive (Maximum Context)
```yaml
generation:
  full_text_scenes_count: 3
  summary_scenes_count: 5
  checkpoint_summary_interval: 5
```

---

## Future Enhancements

### Smart Context Selection
Instead of always using the last N scenes, intelligently select:
- Scenes with the POV character
- Scenes in the same location
- Scenes with mentioned characters
- Scenes that resolved/created relevant loops

### Semantic Search Integration
Use vector store to find relevant past scenes:
```python
# Find scenes similar to current intention
relevant_scenes = vector_store.search(
    query=scene_intention,
    filter={"type": "scene"},
    limit=3
)
```

### Adaptive Context Window
Adjust context based on:
- Available token budget
- Scene complexity
- Story phase (early vs. late)
- Genre requirements

---

## Success Metrics

- **Prose consistency:** Measurable style similarity between consecutive scenes
- **Character voice:** Consistent dialogue patterns and internal voice
- **Sensory continuity:** Matching detail density and sensory focus
- **Token efficiency:** Context stays under 2000 tokens
- **Long-term coherence:** No drift over 50+ scenes

---

## References

- Current implementation: `novel_agent/agent/writer_context.py`
- Config system: `novel_agent/configs/config.py`
- Memory manager: `novel_agent/memory/manager.py`
- Related: Phase 6 checkpoint system
