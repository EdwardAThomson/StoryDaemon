"""Prompt templates for agent LLM interactions."""

PLANNER_PROMPT_TEMPLATE = """You are a creative story planner for an emergent narrative system.

Your task is to analyze the current story state and create a plan for the next scene that ADVANCES THE PLOT.

## Current Story State

**Novel:** {novel_name}
**Current Tick:** {current_tick}
**Active Character:** {active_character_name} ({active_character_id})

### Overall Story Summary
{overall_summary}

### Recent Scenes (Detailed)
{recent_scenes_summary}

### Open Story Loops (PRIORITIZED BY IMPORTANCE)
{open_loops_list}

### Tension Pattern (Pacing Awareness)
{tension_history}

### Recent QA Feedback (Scene Quality & Momentum)
{qa_feedback}

### Active Character Details
{active_character_details}

### Available Relationships
{character_relationships}

### Factions (Organizations)
{factions_summary}

## Available Tools

You can use the following tools to gather information or create entities:

{available_tools_description}

## Your Task: ADVANCE THE STORY

Create a plan for the next scene that makes CONCRETE PROGRESS on the plot.

**CRITICAL REQUIREMENTS:**

1. **CHANGE THE SITUATION** - The scene must alter the story state in a meaningful way
   - NOT: "Character continues doing X"
   - YES: "Character succeeds/fails at X, leading to Y"
   - NOT: "Character struggles with problem"
   - YES: "Character discovers new information that changes their approach"

2. **ADVANCE OR ESCALATE** - Select at least ONE high-priority open loop and:
   - Make measurable progress toward resolution (milestones over multiple scenes are OK)
   - OR introduce a meaningful complication/escalation that moves it forward
   - If full resolution is premature, specify a 'progress_milestone' for this scene

3. **FORWARD MOMENTUM** - The scene must move the story toward:
   - Resolution of a conflict
   - Discovery of crucial information
   - A character making a significant choice
   - A situation reaching a turning point
   - Introduction of a new complication (if current ones are stale)

4. **AVOID REPETITION** - Review recent scenes. Do NOT repeat:
   - Similar situations (e.g., "character negotiates again")
   - Similar actions (e.g., "character struggles with same problem")
   - Similar emotional beats (e.g., "character feels desperate again")

**PLANNING QUESTIONS:**

1. What will CHANGE by the end of this scene?
2. Which high-priority open loop will you advance?
3. How will this scene be DIFFERENT from recent scenes?
4. What is the TURNING POINT or KEY EVENT?

## Output Format

Before you respond, make deliberate choices for these planning fields using the **Recent Scenes**, **Tension Pattern**, and **Recent QA Feedback** sections above:

- `scene_mode`  Primary mode for this scene. Choose from `dialogue`, `political`, `action`, `technical`, or `introspective`.
  - Prefer a different `scene_mode` than the last few scenes when possible.
  - If recent QA or recent scenes show repeated `technical` mode, bias this scene toward `dialogue` or `political` to vary texture.
- `palette_shift`  Short phrase or list that changes the sensory/emotional palette (e.g., `"heat, copper, crowd-noise"` or `"administrative neon, recycled air, clipped voices"`).
- `transition_path`  1-3 sentence outline of how we move from the end of the previous scene into this one (physical/temporal bridge). Use this when changing location, time, or situation.
- `dialogue_targets`  Optional dialogue goals. Prefer a structured object (e.g. `{ "min_exchanges": 6, "conflict_axis": "leverage vs trust", "participants": ["C0", "corp_proxy"] }`).

Then emit the JSON object below:

```json
{
  "rationale": "Brief explanation focusing on HOW this scene advances the plot and WHAT changes",
  "scene_intention": "What CHANGES in this scene - be specific about the outcome/turning point",
  "key_change": "One sentence: What is fundamentally different after this scene?",
  "progress_milestone": "Specific milestone achieved toward resolving a loop (optional)",
  "progress_step": "setup|complication|reversal|revelation|decision|resolution (optional)",
  "scene_mode": "dialogue|political|action|technical|introspective (choose mode that differs from the previous scene when possible)",
  "palette_shift": "Short description of the scene's sensory/emotional palette (e.g., 'heat, copper, crowd-noise')",
  "transition_path": "1–3 sentence description of how we move from the previous scene/location to this one (optional if no transition is needed)",
  "dialogue_targets": "Optional description of dialogue goals (e.g., 'at least 6 exchanges, conflict axis: leverage vs trust, participants: C0 and corp_proxy')",
  "loops_addressed": ["OL4", "OL5"],
  "pov_character": "Character ID for POV (use {active_character_id} or specify another)",
  "target_location": "Location ID where scene takes place (or null for new location)",
  "actions": [
    {
      "tool": "tool.name",
      "args": {
        "arg1": "value1"
      },
      "reason": "Why this tool is needed"
    }
  ],
  "expected_outcomes": [
    "Concrete outcome 1 (something that CHANGES)",
    "Concrete outcome 2 (something that CHANGES)"
  ],
  "metadata": {
    "scene_length": "brief|short|long|extended (optional - only if you want to guide scene length)"
  }
}
```

## Guidelines

- Keep actions focused (2-4 tools maximum per plan)
- Use memory.search to recall relevant context
- Use character.generate to create characters - names will be auto-generated uniquely
- Use location.generate to create locations as needed
- Use relationship.create when characters first interact significantly
- Use relationship.update to track relationship changes
- Use faction.generate/update/query to ground organizations when referenced (avoid generic “corporate”)
- Scene intention must describe a CHANGE, not a continuation
- Expected outcomes must be CONCRETE changes to story state (or a clear progress milestone)
- Every scene should contain a turning point or a clear setup beat that commits to future change
- Avoid repeating recent scene patterns
- Scene length is optional: use "brief" for quick transitions, "short" for focused moments, "long" for developed scenes, "extended" for major events

**REMEMBER: Your job is to ADVANCE the story, not just continue it. Make something CHANGE.**

Generate your plan now:"""


WRITER_PROMPT_TEMPLATE = """You are a creative fiction writer specializing in deep POV narrative.

## Story Context

**Novel:** {novel_name}
**Tick:** {current_tick}

## Recent Story

The following context includes FULL TEXT from the most recent scenes to help you match prose style, voice, and atmosphere. Earlier scenes are summarized for plot continuity.

{recent_context}

## This Scene's Plan

**Intention:** {scene_intention}

**KEY CHANGE THIS SCENE MUST ACCOMPLISH:** {key_change}
**PROGRESS MILESTONE (if not resolving):** {progress_milestone}

**Scene Mode:** {scene_mode}
**Palette Shift:** {palette_shift}
**Transition Path (if provided):** {transition_path}
**Dialogue Targets (if provided):** {dialogue_targets}

**Tool Results:** {tool_results_summary}

## POV Character

{pov_character_details}

## Location

{location_details}

## Your Task

Write a scene passage from {pov_character_name}'s deep POV that ACCOMPLISHES THE KEY CHANGE or CLEARLY ACHIEVES THE PROGRESS MILESTONE described above.{scene_length_guidance}

**CRITICAL REQUIREMENTS:**

1. **EXECUTE THE CHANGE OR ACHIEVE THE MILESTONE** - This scene must accomplish the key change or clearly achieve the specified progress milestone
   - The situation at the END must be meaningfully different from the BEGINNING
   - Something must be resolved, discovered, decided, escalated, or firmly set up
   - DO NOT end with the same status quo as the start

2. **BUILD TO A TURNING POINT** - Structure the scene with:
   - Opening: Establish current situation
   - Rising action: Build tension/conflict
   - Turning point: The moment something CHANGES
   - Resolution: Show the new situation

3. **USE THE PLANNED TRANSITION (IF PROVIDED)**
   - If a transition path is provided in the plan, include a brief bridge sequence that moves the reader from the end of the previous scene into this one (anchor-from → traversal → anchor-to).
   - Make the transition concrete in space/time or situation so the shift never feels like a hard cut.

4. **HONOR DIALOGUE TARGETS (IF PROVIDED)**
   - If the plan specifies a minimum number of dialogue exchanges, ensure at least that many back-and-forths between the specified participants.
   - Use those exchanges to drive a visible power shift, decision, or change in leverage by the end of the scene.

5. **APPLY THE PALETTE SHIFT**
   - Weave in details that reflect the planned sensory/emotional palette (sounds, textures, light, smells, emotional tone), without simply repeating the palette list verbatim.
   - Use these details throughout the scene to make this passage feel distinct from recent scenes.

6. **AVOID REPETITION** - Review the recent context above
   - Do NOT repeat similar actions from recent scenes
   - Do NOT repeat similar emotional beats
   - Find fresh ways to show character state and conflict

**WRITING RULES:**

1. **Use character name naturally** - The POV character is "{pov_character_name}" - use this name in prose
   - NEVER use placeholder formats like "char_name" or "character_name"
   - Use "{pov_character_name}" when introducing the character or for clarity
   - After introduction, you can vary between the name and pronouns naturally
   - NEVER invent nicknames or alternate names not provided
2. **Third-person POV** - Write in third person using "{pov_character_name}" or pronouns (he/she)
   - NEVER use first person ("I", "my", "me") unless in dialogue
   - Example: "{pov_character_name} pressed a palm against..." NOT "I pressed my palm against..."
3. **Deep POV only** - Everything filtered through {pov_character_name}'s perception
4. **No omniscient narration** - Don't reveal what the character can't know
5. **Show don't tell** - Use actions, dialogue, and sensory details
6. **Sensory details** - Engage sight, sound, smell, touch, taste
7. **Internal thoughts and reactions** - Show character's mental state
8. **Length:** Write as much as the scene needs - no arbitrary limits
9. **Ground factions** - When an organization appears for the first time, include a brief identity line (who they are) or use a generated faction representative in dialogue

**AVOID:**
- Ending with the same situation as the start
- Repeating actions/beats from recent scenes
- First-person POV except in dialogue
- Placeholder names
- Head-hopping
- Telling emotions instead of showing

**FOCUS ON:**
- Accomplishing the key change
- The turning point moment
- What {pov_character_name} sees, hears, feels, thinks
- Concrete actions and dialogue
- Fresh approaches (not repetitive)

Generate the scene now:"""


def format_planner_prompt(context: dict) -> str:
    """Format the planner prompt with context variables.
    
    Args:
        context: Dictionary with all context variables
    
    Returns:
        Formatted prompt string
    """
    return PLANNER_PROMPT_TEMPLATE.format(**context)


FACT_EXTRACTION_PROMPT_TEMPLATE = """Extract structured updates from this scene.

Scene: {scene_text}

POV: {pov_character_id} | Location: {location_id}

Open Loops: {existing_open_loops}

Return ONLY JSON with these updates:

```json
{{
  "character_updates": [
    {{
      "id": "C0",
      "changes": {{
        "emotional_state": "string or null",
        "physical_state": "string or null",
        "inventory": ["item1", "item2"] or null,
        "goals": ["goal1", "goal2"] or null,
        "beliefs": ["belief1", "belief2"] or null
      }}
    }}
  ],
  "location_updates": [
    {{
      "id": "L0",
      "changes": {{
        "description": "string or null",
        "atmosphere": "string or null",
        "features": ["feature1", "feature2"] or null
      }}
    }}
  ],
  "open_loops_created": [
    {{
      "description": "string",
      "importance": "low|medium|high|critical",
      "category": "mystery|relationship|goal|threat|etc",
      "related_characters": ["C0"],
      "related_locations": ["L0"]
    }}
  ],
  "open_loops_resolved": ["OL1", "OL2"],
  "relationship_changes": [
    {{
      "character_a": "C0",
      "character_b": "C1",
      "changes": {{
        "status": "string or null",
        "perspective_a": "string or null",
        "perspective_b": "string or null",
        "intensity": 0-10 or null
      }}
    }}
  ]
}}
```

Rules: Use null for no change. Only extract what's clearly shown. For lists, only include NEW items."""


def format_planner_prompt(context: dict) -> str:
    """Format the planner prompt with context variables.
    
    Args:
        context: Dictionary with all context variables
    
    Returns:
        Formatted prompt string
    """
    return PLANNER_PROMPT_TEMPLATE.format(**context)


def format_writer_prompt(context: dict) -> str:
    """Format the writer prompt with context variables.
    
    Args:
        context: Dictionary with all context variables
    
    Returns:
        Formatted prompt string
    """
    return WRITER_PROMPT_TEMPLATE.format(**context)


def format_fact_extraction_prompt(context: dict) -> str:
    """Format the fact extraction prompt with context variables.
    
    Args:
        context: Dictionary with all context variables
    
    Returns:
        Formatted prompt string
    """
    return FACT_EXTRACTION_PROMPT_TEMPLATE.format(**context)
