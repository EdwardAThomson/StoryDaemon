# How They Currently Interact

**Complementary aspects:**

1. **Beat generation uses open loops** - When generating new beats, the system passes open loops to the LLM (`plot/manager.py` lines 97-104). The prompt explicitly shows open loops so beats can address them.

2. **Beats can declare loop relationships** - `PlotBeat` has `resolves_loops` and `creates_loops` fields (lines 574-575), so beats can explicitly state "this beat will resolve OL23" or "this beat creates a new mystery."

3. **Both feed into context** - The planner sees both open loops and the current beat when planning a scene.


## Potential Conflicts

**1. Competing priorities:**
- A beat says "Prisoss escapes the Hounds" 
- But there are 5 high-importance open loops demanding attention
- The AI might try to cram loop resolution into a beat-focused scene, diluting both

**2. Granularity mismatch:**
- Beats are atomic ("one action, one consequence")
- Open loops are often broad ("What is the nature of the Hounds?")
- A loop might need multiple beats to resolve, but there's no explicit multi-beat planning

**3. No enforcement of declared relationships:**
- A beat can *declare* `resolves_loops: ["OL45"]` but nothing verifies the loop actually got resolved
- The loop resolution is a separate manual/automatic process

**4. Emergent loops vs planned beats:**
- Open loops emerge organically from scenes (bottom-up)
- Beats are generated ahead of time (top-down)
- A scene might create new loops that conflict with upcoming beats

## Suggestions

The systems are designed to complement each other, but could be tightened:

1. **Loop-aware beat verification** - When verifying a beat, also check if declared `resolves_loops` actually happened
2. **Beat prerequisites from loops** - Auto-generate beat prerequisites based on critical open loops
3. **Loop staleness detection** - Flag loops that haven't been addressed in N beats
4. **Conflict detection** - Warn if a beat's `creates_loops` would conflict with upcoming beats

Would you like me to explore any of these improvements, or add this architectural consideration to your design docs?