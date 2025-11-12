# New Features: Story Stats & Prompt Logging

## 1. Story Statistics Display

### Feature
After each tick, the system now displays comprehensive story statistics showing the current state of your narrative.

### Output Example
```
📖 Story Stats:
   Scenes: 16 (9,725 words)
   Characters: 1
   Locations: 1
   Open Loops: 9
   Lore Items: 30
   Avg Tension: 6.9/10
```

### What's Included
- **Scenes:** Total count with cumulative word count
- **Characters:** Number of unique characters
- **Locations:** Number of unique locations
- **Open Loops:** Active story threads
- **Lore Items:** Extracted world-building facts
- **Avg Tension:** Average tension level across all scenes (0-10 scale)

### Implementation
- Automatically displayed after every `novel tick`
- Loads and aggregates data from scene metadata
- Calculates real-time statistics from memory system

---

## 2. Multi-Stage Planning Statistics

### Feature
When using the multi-stage planner (Phase 7A.5), detailed performance statistics are displayed after each tick.

### Output Example
```
📊 Multi-Stage Planning Stats:
   Stage 1 (Strategic): 206 tokens, 2.34s
   Stage 2 (Semantic): 14 items, 0.18s
   Stage 3 (Tactical): 1063 tokens, 16.52s
   Total: 1269 tokens, 19.04s
```

### What's Included
- **Stage 1 (Strategic):** Token count and time for high-level planning
- **Stage 2 (Semantic):** Number of relevant items found and search time
- **Stage 3 (Tactical):** Token count and time for detailed planning
- **Total:** Combined token usage and total planning time

### Benefits
- **Transparency:** See exactly how the planner is working
- **Performance monitoring:** Track planning efficiency
- **Proof of optimization:** Verify token reduction (50-70% vs single-stage)

---

## 3. Prompt Logging (--save-prompts)

### Feature
Save all LLM prompts and responses to disk for inspection, debugging, and verification.

### Usage
```bash
novel tick --save-prompts
```

### Output Location
Prompts are saved to `{project_dir}/prompts/`:
```
prompts/
├── tick_013_stage1_strategic.txt    # Strategic planning prompt
├── tick_013_stage1_response.txt     # Scene intention response
├── tick_013_stage3_tactical.txt     # Tactical planning prompt
└── tick_013_stage3_response.txt     # Detailed plan response
```

### File Format
Each prompt file includes:
- Stage identifier
- Tick number
- Approximate token count
- Full prompt text

Example header:
```
=== STAGE 1: STRATEGIC PLANNING ===
Tick: 13
Tokens (approx): 207

[prompt content...]
```

### Use Cases
1. **Verify token reduction:** Compare prompt sizes across stages
2. **Debug planning issues:** Inspect what context the LLM received
3. **Optimize prompts:** Analyze prompt structure and content
4. **Documentation:** Create examples for documentation
5. **Research:** Study how context affects planning quality

### Performance Impact
- Minimal: ~10-20ms per tick for file I/O
- Prompts are written asynchronously
- No impact on LLM calls

---

## Configuration

### Enable/Disable Features

**Multi-Stage Planner:**
```yaml
# config.yaml
generation:
  use_multi_stage_planner: true  # default
```

**Prompt Logging:**
```bash
# Per-tick basis
novel tick --save-prompts

# Or set in config (future enhancement)
generation:
  save_prompts: false  # default
```

---

## Implementation Details

### Files Modified
1. `/novel_agent/cli/main.py`
   - Added `_show_story_stats()` helper
   - Added `_show_stage_stats()` helper
   - Added `--save-prompts` flag to `tick` command
   - Integrated stats display into tick flow

2. `/novel_agent/agent/agent.py`
   - Added `save_prompts` parameter to `__init__`
   - Pass stage stats to result dictionary
   - Forward prompt saving flag to multi-stage planner

3. `/novel_agent/agent/multi_stage_planner.py`
   - Added `save_prompts` and `prompts_dir` parameters
   - Save prompts before each LLM call
   - Save responses after each LLM call
   - Include metadata (tick, tokens, stage) in saved files

### Backward Compatibility
✅ All features are optional and backward compatible
✅ Default behavior unchanged (no prompt saving)
✅ Stats display is non-intrusive
✅ Can disable multi-stage planner if needed

---

## Examples

### Proof of Token Reduction

**Stage 1 Prompt (Strategic):**
- Size: 1,447 bytes
- Tokens: ~207
- Content: Foundation + protagonist + simple instruction

**Stage 3 Prompt (Tactical):**
- Size: 7,461 bytes
- Tokens: ~1,048
- Content: Scene intention + relevant context + tools

**Total Multi-Stage:**
- Tokens: 1,255
- Reduction: 50-70% vs single-stage (~2,500-4,000 tokens)

**Comparison Document:**
See `{project}/PROMPT_COMPARISON.md` for detailed analysis.

---

## Benefits Summary

### 1. Story Stats
✅ **Visibility:** See story progress at a glance
✅ **Tracking:** Monitor growth (word count, entities, tension)
✅ **Quality:** Verify tension pacing and loop management

### 2. Planning Stats
✅ **Transparency:** Understand planning performance
✅ **Optimization:** Verify token reduction claims
✅ **Debugging:** Identify performance bottlenecks

### 3. Prompt Logging
✅ **Verification:** Prove smaller prompts are being sent
✅ **Debugging:** Inspect exact LLM inputs
✅ **Documentation:** Generate examples for docs
✅ **Research:** Study prompt engineering effectiveness

---

**Status:** ✅ Production Ready
**Phase:** 7A.5 Enhancement
**Date:** November 2025
