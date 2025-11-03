"""Tests for file operations utilities."""
import os
import tempfile
import pytest
from novel_agent.utils.file_ops import (
    open_file,
    write_file,
    read_json,
    write_json,
    validate_json_schema
)


def test_write_and_read_file():
    """Test writing and reading text files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test.txt")
        content = "Hello, StoryDaemon!"
        
        # Write file
        assert write_file(filepath, content)
        
        # Read file
        read_content = open_file(filepath)
        assert read_content == content


def test_write_file_creates_directories():
    """Test that write_file creates parent directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "subdir", "nested", "test.txt")
        content = "Test content"
        
        # Should create directories automatically
        assert write_file(filepath, content)
        assert os.path.exists(filepath)
        assert open_file(filepath) == content


def test_read_nonexistent_file():
    """Test reading a file that doesn't exist."""
    with pytest.raises(FileNotFoundError):
        open_file("/nonexistent/file.txt")


def test_write_and_read_json():
    """Test writing and reading JSON files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test.json")
        data = {
            "name": "Test Novel",
            "tick": 42,
            "characters": ["Alice", "Bob"]
        }
        
        # Write JSON
        assert write_json(filepath, data)
        
        # Read JSON
        read_data = read_json(filepath)
        assert read_data == data


def test_read_invalid_json():
    """Test reading invalid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "invalid.json")
        
        # Write invalid JSON
        with open(filepath, 'w') as f:
            f.write("{invalid json}")
        
        with pytest.raises(ValueError):
            read_json(filepath)


def test_validate_json_schema():
    """Test JSON schema validation."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "number"}
        },
        "required": ["name"]
    }
    
    # Valid data
    valid_data = {"name": "Alice", "age": 30}
    assert validate_json_schema(valid_data, schema)
    
    # Invalid data (missing required field)
    invalid_data = {"age": 30}
    with pytest.raises(ValueError):
        validate_json_schema(invalid_data, schema)
