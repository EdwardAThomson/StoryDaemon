"""Prompt templates for agent LLM interactions."""

PLANNER_PROMPT_TEMPLATE = """You are a creative story planner for an emergent narrative system.

Your task is to analyze the current story state and create a plan for the next scene.

## Current Story State

**Novel:** {novel_name}
**Current Tick:** {current_tick}
**Active Character:** {active_character_name} ({active_character_id})

### Overall Story Summary
{overall_summary}

### Recent Scenes (Detailed)
{recent_scenes_summary}

### Open Story Loops
{open_loops_list}

### Tension Pattern
{tension_history}

### Active Character Details
{active_character_details}

### Available Relationships
{character_relationships}

## Available Tools

You can use the following tools to gather information or create entities:

{available_tools_description}

## Your Task

Create a plan for the next scene. Consider:
1. Which open loops should be addressed or developed?
2. What information do you need to write this scene effectively?
3. Should new characters or locations be introduced?
4. How should relationships evolve?

## Output Format

Respond with a JSON object following this structure:

```json
{{
  "rationale": "Brief explanation of your planning decisions",
  "scene_intention": "What should happen in this scene (1-2 sentences)",
  "pov_character": "Character ID for POV (use {active_character_id} or specify another)",
  "target_location": "Location ID where scene takes place (or null for new location)",
  "actions": [
    {{
      "tool": "tool.name",
      "args": {{
        "arg1": "value1"
      }},
      "reason": "Why this tool is needed"
    }}
  ],
  "expected_outcomes": [
    "Outcome 1",
    "Outcome 2"
  ],
  "metadata": {{
    "scene_length": "brief|short|long|extended (optional - only if you want to guide scene length)"
  }}
}}
```

## Guidelines

- Keep actions focused (2-4 tools maximum per plan)
- Use memory.search to recall relevant context
- Use character.generate to create characters - names will be auto-generated uniquely
- Use relationship.create when characters first interact significantly
- Use relationship.update to track relationship changes
- Scene intention should be specific and actionable
- Expected outcomes should be concrete story developments
- Scene length is optional: use "brief" for quick transitions, "short" for focused moments, "long" for developed scenes, "extended" for major events. Omit if the scene should be whatever length it needs.

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

**Tool Results:** {tool_results_summary}

## POV Character

{pov_character_details}

## Location

{location_details}

## Your Task

Write a scene passage from {pov_character_name}'s deep POV.{scene_length_guidance}

**CRITICAL RULES:**

1. **Use exact character name** - The POV character is named "{pov_character_name}" - use this exact name, do not invent nicknames or alternate names
   - NEVER use placeholder formats like "char_name" or "character_name"
   - ALWAYS use the actual name: "{pov_character_name}"
2. **Third-person POV** - Write in third person using "{pov_character_name}" or pronouns (he/she)
   - NEVER use first person ("I", "my", "me") unless in dialogue
   - Example: "{pov_character_name} pressed a palm against..." NOT "I pressed my palm against..."
3. **Deep POV only** - Everything filtered through {pov_character_name}'s perception
4. **No omniscient narration** - Don't reveal what the character can't know
5. **Show don't tell** - Use actions, dialogue, and sensory details
6. **Sensory details** - Engage sight, sound, smell, touch, taste
7. **Internal thoughts and reactions** - Show character's mental state
8. **Length:** Write as much as the scene needs - no arbitrary limits

**AVOID:**
- First-person POV ("I", "my", "me") except in dialogue
- Placeholder formats like "char_elliot" or "character_name" - use the real name!
- Phrases like "unknown to them", "little did they know", "meanwhile"
- Head-hopping to other characters' thoughts
- Future foreshadowing the POV character couldn't know
- Telling emotions instead of showing them

**FOCUS ON:**
- What {pov_character_name} sees, hears, feels, thinks
- Immediate sensory experience
- Character voice and personality
- Concrete actions and dialogue
- Subtext and implication

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
