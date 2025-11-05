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
  ]
}}
```

## Guidelines

- Keep actions focused (2-4 tools maximum per plan)
- Use memory.search to recall relevant context
- Use character.generate only when introducing new characters
- Use relationship.create when characters first interact significantly
- Use relationship.update to track relationship changes
- Scene intention should be specific and actionable
- Expected outcomes should be concrete story developments

Generate your plan now:"""


def format_planner_prompt(context: dict) -> str:
    """Format the planner prompt with context variables.
    
    Args:
        context: Dictionary with all context variables
    
    Returns:
        Formatted prompt string
    """
    return PLANNER_PROMPT_TEMPLATE.format(**context)
