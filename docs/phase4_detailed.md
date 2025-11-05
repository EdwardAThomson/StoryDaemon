# Phase 4 — Writer and Evaluator Integration (Detailed Design)

**Goal:** Add scene text generation, quality evaluation, and memory updates to complete the story tick loop.

---

## 1. Overview

Phase 4 completes the story generation pipeline by adding:
- Writer LLM for generating scene prose (500-900 words)
- Evaluator for checking continuity and POV integrity
- Scene commit workflow (save markdown, generate summary, update memory)
- Memory synchronization with vector database

**Key Principle:** Generate high-quality prose in deep POV, validate it, and update the story world accordingly.

---

## 2. Current State (Phase 3 Complete)

### What We Have
- ✅ `StoryAgent.tick()` - Orchestrates planning and tool execution
- ✅ `ContextBuilder` - Gathers story context
- ✅ `PlanExecutor` - Executes tool calls
- ✅ `PlanManager` - Stores plans and errors
- ✅ `CodexInterface` - LLM interface with `send_prompt()`
- ✅ `SceneSummarizer` - Already exists for generating bullet summaries
- ✅ `Scene` dataclass - Has all fields we need (title, summary, word_count, etc.)
- ✅ `MemoryManager` - Has `save_scene()`, `update_character()`, `update_location()`
- ✅ `VectorStore` - Has `index_scene()` for semantic search

### What Phase 3 Does
1. Gather context
2. Generate plan with LLM
3. Execute tools
4. Save plan
5. **STOPS HERE** ← Phase 4 continues from here

---

## 3. Phase 4 Architecture

### 3.1 Extended Story Tick Flow

```
┌─────────────────────────────────────────────────────────┐
│                     STORY TICK N                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [PHASE 3 - Already Complete]                          │
│  1-5. Plan generation and tool execution               │
│                                                         │
│  [PHASE 4 - NEW]                                       │
│  6. WRITER LLM                                         │
│     ├─ Build writer context from plan results         │
│     ├─ Format writer prompt (Deep POV)                │
│     ├─ Generate scene prose (500-900 words)           │
│     └─ Parse and validate output                      │
│                                                         │
│  7. EVALUATOR                                          │
│     ├─ Continuity check (facts vs memory)             │
│     ├─ POV check (deep POV violations)                │
│     ├─ Word count check                               │
│     └─ Revision if needed (optional)                  │
│                                                         │
│  8. COMMIT SCENE                                       │
│     ├─ Save markdown to /scenes/scene_NNN.md          │
│     ├─ Generate summary (3-5 bullets)                 │
│     ├─ Create Scene entity                            │
│     ├─ Save scene metadata to /memory/scenes/         │
│     └─ Index in vector database                       │
│                                                         │
│  9. UPDATE STATE                                       │
│     └─ Increment tick, update last_updated            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Component Design

### 4.1 Writer Prompt Template

**File:** `novel_agent/agent/prompts.py` (add to existing file)

**New constant:** `WRITER_PROMPT_TEMPLATE`

**Context variables needed:**
- `novel_name` - Novel title
- `current_tick` - Tick number
- `scene_intention` - From plan
- `pov_character_name` - Character name
- `pov_character_details` - Full character info
- `location_name` - Location name (if known)
- `location_details` - Location description
- `recent_context` - Summary of recent scenes
- `tool_results_summary` - What tools discovered
- `target_word_count_min` - From config (500)
- `target_word_count_max` - From config (900)

**Prompt structure:**
```
You are a creative fiction writer specializing in deep POV narrative.

## Story Context
Novel: {novel_name}
Tick: {current_tick}

## Recent Story
{recent_context}

## This Scene's Plan
Intention: {scene_intention}
Tool Results: {tool_results_summary}

## POV Character
{pov_character_details}

## Location
{location_details}

## Your Task
Write a scene passage from {pov_character_name}'s deep POV.

CRITICAL RULES:
1. Deep POV only - everything filtered through character perception
2. No omniscient narration
3. Show don't tell
4. Sensory details
5. Internal thoughts and reactions
6. {target_word_count_min}-{target_word_count_max} words

Generate the scene now:
```

---

### 4.2 Writer Context Builder

**File:** `novel_agent/agent/writer_context.py` (NEW)

**Class:** `WriterContextBuilder`

**Methods:**
- `build_writer_context(plan, execution_results, project_state)` - Main method
- `_format_tool_results(execution_results)` - Summarize what tools found
- `_get_location_details(location_id)` - Load and format location
- `_format_recent_context(count=2)` - Last N scene summaries

**Integration point:** Called by `StoryAgent.tick()` after plan execution

---

### 4.3 Scene Writer

**File:** `novel_agent/agent/writer.py` (NEW)

**Class:** `SceneWriter`

**Methods:**
```python
def __init__(self, llm_interface, config):
    self.llm = llm_interface
    self.config = config

def write_scene(self, writer_context: dict) -> dict:
    """Generate scene prose.
    
    Returns:
        {
            "text": str,  # Scene prose
            "word_count": int,
            "title": str  # Extracted or generated
        }
    """
    prompt = self._format_writer_prompt(writer_context)
    max_tokens = self.config.get('llm.writer_max_tokens', 3000)
    
    response = self.llm.send_prompt(prompt, max_tokens=max_tokens)
    
    return self._parse_scene_response(response, writer_context)

def _format_writer_prompt(self, context: dict) -> str:
    """Format writer prompt with context."""
    from .prompts import WRITER_PROMPT_TEMPLATE
    return WRITER_PROMPT_TEMPLATE.format(**context)

def _parse_scene_response(self, response: str, context: dict) -> dict:
    """Parse LLM response into scene data."""
    text = response.strip()
    word_count = len(text.split())
    
    # Try to extract title from first line if it looks like a title
    lines = text.split('\n')
    title = self._extract_title(lines, context)
    
    return {
        "text": text,
        "word_count": word_count,
        "title": title
    }

def _extract_title(self, lines: List[str], context: dict) -> str:
    """Extract or generate scene title."""
    # Check if first line looks like a title (short, no period)
    if lines and len(lines[0]) < 60 and not lines[0].endswith('.'):
        return lines[0].strip('# ').strip()
    
    # Generate from scene intention
    intention = context.get('scene_intention', '')
    if intention:
        # Take first few words
        words = intention.split()[:5]
        return ' '.join(words).capitalize()
    
    return f"Scene {context.get('current_tick', 0)}"
```

---

### 4.4 Evaluator

**File:** `novel_agent/agent/evaluator.py` (NEW)

**Class:** `SceneEvaluator`

**Methods:**
```python
def __init__(self, memory_manager, config):
    self.memory = memory_manager
    self.config = config

def evaluate_scene(self, scene_text: str, scene_context: dict) -> dict:
    """Evaluate scene for quality and consistency.
    
    Returns:
        {
            "passed": bool,
            "issues": List[str],
            "warnings": List[str],
            "checks": {
                "word_count": bool,
                "pov": bool,
                "continuity": bool
            }
        }
    """
    issues = []
    warnings = []
    checks = {}
    
    # 1. Word count check
    word_count = len(scene_text.split())
    min_words = self.config.get('generation.target_word_count_min', 500)
    max_words = self.config.get('generation.target_word_count_max', 900)
    
    checks["word_count"] = min_words <= word_count <= max_words
    if not checks["word_count"]:
        issues.append(f"Word count {word_count} outside range {min_words}-{max_words}")
    
    # 2. POV check (heuristic)
    checks["pov"] = self._check_pov(scene_text, scene_context)
    if not checks["pov"]:
        warnings.append("Possible POV violations detected")
    
    # 3. Continuity check (basic)
    checks["continuity"] = self._check_continuity(scene_text, scene_context)
    if not checks["continuity"]:
        warnings.append("Possible continuity issues detected")
    
    passed = all(checks.values()) and len(issues) == 0
    
    return {
        "passed": passed,
        "issues": issues,
        "warnings": warnings,
        "checks": checks
    }

def _check_pov(self, text: str, context: dict) -> bool:
    """Check for POV violations (heuristic)."""
    # Simple heuristic: look for omniscient phrases
    omniscient_markers = [
        "unknown to",
        "little did",
        "would later",
        "meanwhile",
        "across town",
        "at that moment"
    ]
    
    text_lower = text.lower()
    for marker in omniscient_markers:
        if marker in text_lower:
            return False
    
    return True

def _check_continuity(self, text: str, context: dict) -> bool:
    """Basic continuity check."""
    # For Phase 4, just return True
    # Phase 5 will add more sophisticated checking
    return True
```

---

### 4.5 Scene Committer

**File:** `novel_agent/agent/scene_committer.py` (NEW)

**Class:** `SceneCommitter`

**Methods:**
```python
def __init__(self, memory_manager, vector_store, summarizer, project_path):
    self.memory = memory_manager
    self.vector = vector_store
    self.summarizer = summarizer
    self.project_path = Path(project_path)
    self.scenes_dir = self.project_path / "scenes"

def commit_scene(self, scene_data: dict, tick: int, plan: dict) -> str:
    """Commit scene to disk and memory.
    
    Args:
        scene_data: From SceneWriter (text, word_count, title)
        tick: Current tick number
        plan: Original plan
    
    Returns:
        Scene ID
    """
    # 1. Generate scene ID
    scene_id = self.memory.generate_id("scene")
    
    # 2. Save markdown file
    markdown_file = self._save_markdown(scene_id, scene_data["text"], tick)
    
    # 3. Generate summary
    summary = self.summarizer.summarize_scene(
        scene_data["text"],
        max_bullets=5
    )
    
    # 4. Create Scene entity
    scene = Scene(
        id=scene_id,
        tick=tick,
        title=scene_data["title"],
        pov_character_id=plan.get("pov_character", ""),
        location_id=plan.get("target_location", ""),
        markdown_file=str(markdown_file),
        word_count=scene_data["word_count"],
        summary=summary,
        characters_present=self._extract_characters(plan),
        key_events=[],  # Could extract from summary
        metadata={"plan_rationale": plan.get("rationale", "")}
    )
    
    # 5. Save scene metadata
    self.memory.save_scene(scene)
    
    # 6. Index in vector database
    self.vector.index_scene(scene)
    
    return scene_id

def _save_markdown(self, scene_id: str, text: str, tick: int) -> Path:
    """Save scene text to markdown file."""
    self.scenes_dir.mkdir(parents=True, exist_ok=True)
    filename = f"scene_{tick:03d}.md"
    filepath = self.scenes_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# Scene {tick}\n\n")
        f.write(f"*Scene ID: {scene_id}*\n\n")
        f.write("---\n\n")
        f.write(text)
    
    return filepath

def _extract_characters(self, plan: dict) -> List[str]:
    """Extract character IDs from plan."""
    characters = set()
    
    # Add POV character
    if plan.get("pov_character"):
        characters.add(plan["pov_character"])
    
    # Extract from tool results (if character.generate was used)
    for action in plan.get("actions", []):
        if action["tool"] == "character.generate":
            # Would need to get result from execution_results
            pass
    
    return list(characters)
```

---

## 5. Integration into StoryAgent

**File:** `novel_agent/agent/agent.py` (UPDATE existing)

**Changes to `StoryAgent.__init__()`:**
```python
def __init__(self, project_path, llm_interface, tool_registry, config):
    # ... existing initialization ...
    
    # NEW: Phase 4 components
    from .writer_context import WriterContextBuilder
    from .writer import SceneWriter
    from .evaluator import SceneEvaluator
    from .scene_committer import SceneCommitter
    
    self.writer_context_builder = WriterContextBuilder(
        self.memory,
        self.vector,
        config
    )
    self.writer = SceneWriter(llm_interface, config)
    self.evaluator = SceneEvaluator(self.memory, config)
    self.committer = SceneCommitter(
        self.memory,
        self.vector,
        SceneSummarizer(llm_interface),
        project_path
    )
```

**Changes to `StoryAgent.tick()`:**
```python
def tick(self) -> Dict[str, Any]:
    """Execute one story generation tick."""
    tick = self.state["current_tick"]
    
    try:
        # Steps 1-5: Plan generation and execution (Phase 3)
        context = self.context_builder.build_planner_context(self.state)
        plan = self._generate_plan(context)
        validate_plan(plan)
        execution_results = self.executor.execute_plan(plan, tick)
        plan_file = self.plan_manager.save_plan(tick, plan, execution_results, context)
        
        # NEW: Step 6 - Writer
        writer_context = self.writer_context_builder.build_writer_context(
            plan,
            execution_results,
            self.state
        )
        scene_data = self.writer.write_scene(writer_context)
        
        # NEW: Step 7 - Evaluator
        eval_result = self.evaluator.evaluate_scene(
            scene_data["text"],
            writer_context
        )
        
        # Log evaluation warnings
        if eval_result["warnings"]:
            # Could log to plan file or separate eval log
            pass
        
        # Fail if critical issues
        if not eval_result["passed"]:
            raise ValueError(f"Scene evaluation failed: {eval_result['issues']}")
        
        # NEW: Step 8 - Commit scene
        scene_id = self.committer.commit_scene(scene_data, tick, plan)
        
        # Step 9: Update state
        self.state["current_tick"] += 1
        self._save_state()
        
        return {
            "success": True,
            "tick": tick,
            "plan_file": str(plan_file),
            "scene_id": scene_id,
            "scene_file": f"scenes/scene_{tick:03d}.md",
            "word_count": scene_data["word_count"],
            "actions_executed": len(execution_results.get("actions_executed", []))
        }
    
    except Exception as e:
        # Error handling (existing)
        ...
```

---

## 6. Configuration Updates

**File:** `novel_agent/configs/config.py`

**No changes needed** - Already has:
- `llm.writer_max_tokens: 3000`
- `generation.target_word_count_min: 500`
- `generation.target_word_count_max: 900`

---

## 7. CLI Updates

**File:** `novel_agent/cli/main.py`

**Update tick command output:**
```python
typer.echo(f"\n⚙️  Executing tick {current_tick}...")
typer.echo(f"   1. Gathering context...")
typer.echo(f"   2. Generating plan with LLM...")
typer.echo(f"   3. Validating plan...")
typer.echo(f"   4. Executing tool calls...")
typer.echo(f"   5. Storing plan...")
typer.echo(f"   6. Writing scene prose...")  # NEW
typer.echo(f"   7. Evaluating scene...")      # NEW
typer.echo(f"   8. Committing scene...")      # NEW

result = agent.tick()

typer.echo(f"\n✅ Tick {current_tick} completed successfully!")
typer.echo(f"   Plan: {result['plan_file']}")
typer.echo(f"   Scene: {result['scene_file']}")  # NEW
typer.echo(f"   Word count: {result['word_count']}")  # NEW
typer.echo(f"   Actions: {result['actions_executed']}")
typer.echo(f"   Next tick: {current_tick + 1}")
```

---

## 8. Implementation Order

1. **Writer Prompt Template** (`prompts.py`)
   - Add WRITER_PROMPT_TEMPLATE constant
   
2. **Writer Context Builder** (`writer_context.py`)
   - Implement WriterContextBuilder class
   
3. **Scene Writer** (`writer.py`)
   - Implement SceneWriter class
   
4. **Evaluator** (`evaluator.py`)
   - Implement SceneEvaluator class
   
5. **Scene Committer** (`scene_committer.py`)
   - Implement SceneCommitter class
   
6. **StoryAgent Integration** (`agent.py`)
   - Update __init__ and tick() methods
   
7. **CLI Updates** (`main.py`)
   - Update output messages
   
8. **Testing**
   - Unit tests for each component
   - Integration test for full tick

---

## 9. Testing Strategy

### Unit Tests

**File:** `tests/test_phase4_writer.py`
- Test writer prompt formatting
- Test scene parsing
- Test title extraction

**File:** `tests/test_phase4_evaluator.py`
- Test word count validation
- Test POV heuristics
- Test evaluation result structure

**File:** `tests/test_phase4_committer.py`
- Test markdown file creation
- Test Scene entity creation
- Test summary generation

### Integration Test

**File:** `tests/integration/test_full_tick_phase4.py`
- Create test project
- Run full tick with mocked LLM
- Verify scene file created
- Verify scene metadata saved
- Verify vector indexing

---

## 10. Success Criteria

Phase 4 is complete when:

- ✅ Writer prompt template generates quality prose
- ✅ Scene text is 500-900 words
- ✅ Evaluator checks word count, POV, continuity
- ✅ Scenes saved to `/scenes/scene_NNN.md`
- ✅ Scene metadata saved to `/memory/scenes/`
- ✅ Summaries generated and stored
- ✅ Vector database indexed
- ✅ `novel tick` completes end-to-end
- ✅ Integration tests pass

---

## 11. What Phase 4 Does NOT Include

Deferred to Phase 5:

- ❌ Automatic entity updates from scene content
- ❌ Fact extraction from prose
- ❌ Character emotional state updates
- ❌ Location state changes
- ❌ Open loop creation/resolution from text
- ❌ Advanced continuity checking

Phase 4 focuses on **writing and committing scenes**. Phase 5 will add **dynamic memory updates**.

---

## 12. File Summary

### New Files
- `novel_agent/agent/writer_context.py` - WriterContextBuilder
- `novel_agent/agent/writer.py` - SceneWriter
- `novel_agent/agent/evaluator.py` - SceneEvaluator
- `novel_agent/agent/scene_committer.py` - SceneCommitter
- `tests/test_phase4_writer.py` - Writer tests
- `tests/test_phase4_evaluator.py` - Evaluator tests
- `tests/test_phase4_committer.py` - Committer tests
- `tests/integration/test_full_tick_phase4.py` - Integration test

### Modified Files
- `novel_agent/agent/prompts.py` - Add WRITER_PROMPT_TEMPLATE
- `novel_agent/agent/agent.py` - Integrate Phase 4 components
- `novel_agent/cli/main.py` - Update output messages
- `novel_agent/agent/__init__.py` - Export new classes

### Existing Files Used (No Changes)
- `novel_agent/memory/summarizer.py` - SceneSummarizer
- `novel_agent/memory/entities.py` - Scene dataclass
- `novel_agent/memory/manager.py` - save_scene(), generate_id()
- `novel_agent/memory/vector_store.py` - index_scene()
- `novel_agent/tools/codex_interface.py` - send_prompt()

---

**Phase 4 Status: READY TO IMPLEMENT**

All design decisions made. Clear integration points with Phase 3. Ready to begin coding.
