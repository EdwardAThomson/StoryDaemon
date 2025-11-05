"""Tool registry for managing available agent tools."""

from typing import Dict, List, Optional
from .base import Tool


class ToolRegistry:
    """Registry for managing and accessing agent tools.
    
    The registry stores all available tools and provides methods to
    retrieve them by name or get descriptions for LLM prompts.
    """
    
    def __init__(self):
        """Initialize an empty tool registry."""
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Register a tool in the registry.
        
        Args:
            tool: Tool instance to register
        
        Raises:
            ValueError: If a tool with the same name is already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        
        self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name.
        
        Args:
            name: Tool name (e.g., "memory.search")
        
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """Get list of all registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_tools_description(self) -> str:
        """Get formatted description of all tools for LLM prompt.
        
        Returns:
            Multi-line string describing all available tools
        """
        if not self._tools:
            return "No tools available."
        
        descriptions = []
        for tool in self._tools.values():
            # Format tool name and description
            desc_lines = [f"**{tool.name}** - {tool.description}"]
            
            # Format parameters
            if tool.parameters:
                param_parts = []
                for param_name, param_spec in tool.parameters.items():
                    param_type = param_spec.get("type", "any")
                    is_optional = param_spec.get("optional", False)
                    optional_marker = " (optional)" if is_optional else ""
                    param_parts.append(f"{param_name} ({param_type}){optional_marker}")
                
                desc_lines.append(f"  Args: {', '.join(param_parts)}")
            
            descriptions.append("\n".join(desc_lines))
        
        return "\n\n".join(descriptions)
    
    def get_all_schemas(self) -> List[Dict]:
        """Get schemas for all registered tools.
        
        Returns:
            List of tool schema dictionaries
        """
        return [tool.get_schema() for tool in self._tools.values()]
    
    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
    
    def __repr__(self) -> str:
        return f"ToolRegistry(tools={len(self._tools)})"
