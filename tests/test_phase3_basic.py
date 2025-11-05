"""Basic tests for Phase 3 components."""

import pytest
from novel_agent.tools import Tool, ToolRegistry
from novel_agent.agent.schemas import validate_plan, PLAN_SCHEMA


class TestToolBase:
    """Test Tool base class."""
    
    def test_tool_creation(self):
        """Test creating a basic tool."""
        tool = Tool(
            name="test.tool",
            description="A test tool",
            parameters={
                "arg1": {"type": "string", "description": "First argument"}
            }
        )
        
        assert tool.name == "test.tool"
        assert tool.description == "A test tool"
        assert "arg1" in tool.parameters
    
    def test_tool_schema(self):
        """Test tool schema generation."""
        tool = Tool(
            name="test.tool",
            description="A test tool",
            parameters={"arg1": {"type": "string"}}
        )
        
        schema = tool.get_schema()
        assert schema["name"] == "test.tool"
        assert schema["description"] == "A test tool"
        assert "parameters" in schema
    
    def test_tool_validate_args_required(self):
        """Test argument validation for required parameters."""
        tool = Tool(
            name="test.tool",
            description="A test tool",
            parameters={
                "required_arg": {"type": "string", "optional": False}
            }
        )
        
        # Should raise ValueError for missing required arg
        with pytest.raises(ValueError, match="Missing required parameter"):
            tool.validate_args({})
        
        # Should pass with required arg
        assert tool.validate_args({"required_arg": "value"})
    
    def test_tool_validate_args_optional(self):
        """Test argument validation for optional parameters."""
        tool = Tool(
            name="test.tool",
            description="A test tool",
            parameters={
                "optional_arg": {"type": "string", "optional": True}
            }
        )
        
        # Should pass without optional arg
        assert tool.validate_args({})
        
        # Should pass with optional arg
        assert tool.validate_args({"optional_arg": "value"})


class TestToolRegistry:
    """Test ToolRegistry."""
    
    def test_registry_creation(self):
        """Test creating a registry."""
        registry = ToolRegistry()
        assert len(registry) == 0
    
    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()
        tool = Tool("test.tool", "Test", {})
        
        registry.register(tool)
        assert len(registry) == 1
        assert "test.tool" in registry
    
    def test_register_duplicate_fails(self):
        """Test that registering duplicate tool fails."""
        registry = ToolRegistry()
        tool = Tool("test.tool", "Test", {})
        
        registry.register(tool)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool)
    
    def test_get_tool(self):
        """Test retrieving a tool."""
        registry = ToolRegistry()
        tool = Tool("test.tool", "Test", {})
        registry.register(tool)
        
        retrieved = registry.get_tool("test.tool")
        assert retrieved is tool
        
        # Non-existent tool returns None
        assert registry.get_tool("nonexistent") is None
    
    def test_list_tools(self):
        """Test listing all tools."""
        registry = ToolRegistry()
        registry.register(Tool("tool1", "Test 1", {}))
        registry.register(Tool("tool2", "Test 2", {}))
        
        tools = registry.list_tools()
        assert len(tools) == 2
        assert "tool1" in tools
        assert "tool2" in tools


class TestPlanSchema:
    """Test plan schema validation."""
    
    def test_valid_plan(self):
        """Test validating a valid plan."""
        plan = {
            "rationale": "Test plan",
            "scene_intention": "Test scene",
            "actions": [
                {
                    "tool": "test.tool",
                    "args": {"arg1": "value1"}
                }
            ]
        }
        
        # Should not raise
        validate_plan(plan)
    
    def test_missing_required_field(self):
        """Test that missing required fields fail validation."""
        plan = {
            "rationale": "Test plan",
            # Missing scene_intention
            "actions": []
        }
        
        with pytest.raises(ValueError, match="validation failed"):
            validate_plan(plan)
    
    def test_invalid_action_structure(self):
        """Test that invalid action structure fails."""
        plan = {
            "rationale": "Test plan",
            "scene_intention": "Test scene",
            "actions": [
                {
                    # Missing 'tool' field
                    "args": {}
                }
            ]
        }
        
        with pytest.raises(ValueError, match="validation failed"):
            validate_plan(plan)
    
    def test_optional_fields(self):
        """Test that optional fields are allowed."""
        plan = {
            "rationale": "Test plan",
            "scene_intention": "Test scene",
            "pov_character": "C0",
            "target_location": "L0",
            "expected_outcomes": ["outcome1", "outcome2"],
            "actions": []
        }
        
        # Should not raise
        validate_plan(plan)
