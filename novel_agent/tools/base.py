"""Base Tool class for agent tools."""

from typing import Dict, Any, Optional


class Tool:
    """Base class for all agent tools.
    
    Tools are callable functions that the agent can use to interact with
    the story world (memory, entities, etc.). Each tool has a name,
    description, and parameter schema that the LLM can use to decide
    when and how to call it.
    """
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any]):
        """Initialize a tool.
        
        Args:
            name: Tool identifier (e.g., "memory.search", "character.generate")
            description: Human-readable description of what the tool does
            parameters: JSON schema-like dict describing tool parameters
        """
        self.name = name
        self.description = description
        self.parameters = parameters
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given arguments.
        
        Args:
            **kwargs: Tool-specific arguments
        
        Returns:
            Result dictionary with at least a "success" key
        
        Raises:
            NotImplementedError: If subclass doesn't implement this method
        """
        raise NotImplementedError(f"Tool {self.name} must implement execute()")
    
    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for LLM prompt.
        
        Returns:
            Dictionary with name, description, and parameters
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
    
    def validate_args(self, args: Dict[str, Any]) -> bool:
        """Validate arguments against parameter schema.
        
        Args:
            args: Arguments to validate
        
        Returns:
            True if valid
        
        Raises:
            ValueError: If required parameters are missing
        """
        # Check required parameters
        for param_name, param_spec in self.parameters.items():
            is_optional = param_spec.get("optional", False)
            if not is_optional and param_name not in args:
                raise ValueError(
                    f"Missing required parameter '{param_name}' for tool {self.name}"
                )
        
        return True
    
    def __repr__(self) -> str:
        return f"Tool(name='{self.name}')"
