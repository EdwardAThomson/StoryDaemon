"""File I/O utilities for StoryDaemon.

Adapted from NovelWriter's helper_fns.py with improvements for StoryDaemon's needs.
"""
import os
import json
import jsonschema
from typing import Any, Dict
from datetime import datetime


def open_file(full_path: str) -> str:
    """Open and read a file.
    
    Args:
        full_path: Absolute path to the file
        
    Returns:
        File contents as string
        
    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"File not found: {full_path}")
    
    try:
        with open(full_path, "r", encoding="utf-8") as file:
            return file.read()
    except Exception as e:
        raise IOError(f"Error reading {full_path}: {e}")


def write_file(full_path: str, data: str) -> bool:
    """Write data to file, creating directories as needed.
    
    Args:
        full_path: Absolute path to the file
        data: String data to write
        
    Returns:
        True if successful
        
    Raises:
        IOError: If file cannot be written
    """
    try:
        dir_name = os.path.dirname(full_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as file:
            file.write(data)
        return True
    except Exception as e:
        raise IOError(f"Error writing {full_path}: {e}")


def read_json(full_path: str) -> Dict[str, Any]:
    """Read and parse JSON file.
    
    Args:
        full_path: Absolute path to JSON file
        
    Returns:
        Parsed JSON as dictionary
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid
        IOError: If file cannot be read
    """
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"File not found: {full_path}")
    
    try:
        with open(full_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {full_path}: {e}")
    except Exception as e:
        raise IOError(f"Error reading {full_path}: {e}")


def write_json(full_path: str, data: Dict[str, Any]) -> bool:
    """Write dictionary to JSON file with pretty-print.
    
    Args:
        full_path: Absolute path to JSON file
        data: Dictionary to write
        
    Returns:
        True if successful
        
    Raises:
        IOError: If file cannot be written
    """
    try:
        dir_name = os.path.dirname(full_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        raise IOError(f"Error writing {full_path}: {e}")


def load_schema(schema_path: str) -> Dict[str, Any]:
    """Load JSON schema from file.
    
    Args:
        schema_path: Path to schema file
        
    Returns:
        Schema as dictionary
        
    Raises:
        FileNotFoundError: If schema file doesn't exist
        ValueError: If schema is invalid JSON
    """
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    
    try:
        with open(schema_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON schema in {schema_path}: {e}")


def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """Validate data against JSON schema.
    
    Args:
        data: Data to validate
        schema: JSON schema dictionary
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If validation fails
    """
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.exceptions.ValidationError as e:
        raise ValueError(f"JSON validation error: {e.message}")


def save_prompt_to_file(
    output_dir: str,
    base_name: str,
    content: str,
    subfolder: str = "prompts",
    ext: str = ".md"
) -> str:
    """Save prompt content to timestamped file for debugging.
    
    Args:
        output_dir: Base output directory
        base_name: Base name for the file (e.g., 'planner_prompt')
        content: Prompt content to save
        subfolder: Subfolder within output_dir (default: 'prompts')
        ext: File extension (default: '.md')
        
    Returns:
        Path to saved file
        
    Raises:
        IOError: If file cannot be written
    """
    try:
        target_dir = os.path.join(output_dir, subfolder)
        os.makedirs(target_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_base_name = base_name.replace(' ', '_').lower()
        filename = f"{safe_base_name}_{timestamp}{ext}"
        filepath = os.path.join(target_dir, filename)
        
        write_file(filepath, content)
        return filepath
    except Exception as e:
        raise IOError(f"Error saving prompt file: {e}")
