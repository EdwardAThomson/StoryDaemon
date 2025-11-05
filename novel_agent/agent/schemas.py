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
        "pov_character": {
            "type": "string",
            "description": "Character ID for POV (optional, can be inferred)"
        },
        "target_location": {
            "type": "string",
            "description": "Location ID where scene takes place (optional)"
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
