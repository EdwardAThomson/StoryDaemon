"""JSON schemas for agent plans and validation."""

# Plan schema for validating planner LLM output
PLAN_SCHEMA = {
    "type": "object",
    "required": ["rationale", "actions", "scene_intention"],
    "properties": {
        "rationale": {
            "type": "string",
            "description": "Why this plan makes sense for the story"
        },
        "scene_intention": {
            "type": "string",
            "description": "What should happen in this scene"
        },
        "key_change": {
            "type": ["string", "null"],
            "description": "One sentence describing what is fundamentally different after this scene"
        },
        "progress_milestone": {
            "type": ["string", "null"],
            "description": "Specific milestone achieved toward resolving an open loop (optional)"
        },
        "progress_step": {
            "type": ["string", "null"],
            "description": "High-level step type (setup|complication|reversal|revelation|decision|resolution)"
        },
        "scene_mode": {
            "type": ["string", "null"],
            "description": "Primary mode for this scene: dialogue|political|action|technical|introspective"
        },
        "palette_shift": {
            "type": ["string", "null"],
            "description": "Short description of the scene's sensory/emotional palette"
        },
        "transition_path": {
            "type": ["string", "null"],
            "description": "1-3 sentence outline of how we move from the previous scene/location to this one"
        },
        "dialogue_targets": {
            "type": ["object", "string", "null"],
            "description": "Dialogue goals for this scene (e.g. min_exchanges, conflict_axis, participants)"
        },
        "pov_character": {
            "type": ["string", "null"],
            "description": "Character ID for POV (optional, can be inferred)"
        },
        "target_location": {
            "type": ["string", "null"],
            "description": "Location ID where scene takes place (optional)"
        },
        "beat_target": {
            "type": ["object", "null"],
            "description": "Optional targeting of a specific plot beat for this scene",
            "properties": {
                "beat_id": {
                    "type": ["string", "null"],
                    "description": "ID of the plot beat this scene is primarily serving (or null)"
                },
                "strategy": {
                    "type": ["string", "null"],
                    "description": "How this scene relates to the beat: direct|setup|followup|skip"
                },
                "notes": {
                    "type": ["string", "null"],
                    "description": "Planner explanation of why the beat is executed, deferred, or skipped"
                }
            }
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tool", "args"],
                "properties": {
                    "tool": {
                        "type": "string",
                        "description": "Tool name (e.g., memory.search)"
                    },
                    "args": {
                        "type": "object",
                        "description": "Tool arguments"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this tool is needed (optional)"
                    }
                }
            }
        },
        "expected_outcomes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What should result from this scene"
        },
        "metadata": {
            "type": "object",
            "description": "Optional metadata for planner hints (e.g. scene_length)"
        }
    }
}


# Error file schema for storing execution errors
ERROR_SCHEMA = {
    "type": "object",
    "required": ["tick", "timestamp", "error", "plan"],
    "properties": {
        "tick": {
            "type": "integer",
            "description": "Tick number where error occurred"
        },
        "timestamp": {
            "type": "string",
            "description": "ISO 8601 timestamp"
        },
        "error": {
            "type": "object",
            "required": ["type", "message"],
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Error type/class name"
                },
                "message": {
                    "type": "string",
                    "description": "Error message"
                },
                "traceback": {
                    "type": "string",
                    "description": "Full traceback"
                }
            }
        },
        "plan": {
            "type": "object",
            "description": "The plan that was being executed"
        },
        "execution": {
            "type": "object",
            "description": "Partial execution results before error"
        },
        "instructions": {
            "type": "string",
            "description": "Instructions for human review"
        }
    }
}


def validate_plan(plan: dict) -> None:
    """Validate a plan against the schema.
    
    Args:
        plan: Plan dictionary to validate
    
    Raises:
        ValueError: If plan is invalid
    """
    from jsonschema import validate, ValidationError
    
    try:
        validate(instance=plan, schema=PLAN_SCHEMA)
    except ValidationError as e:
        raise ValueError(f"Plan validation failed: {e.message}")
