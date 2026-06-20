"""Tests for file operations utilities."""
import json
import os
import tempfile
import pytest
from novel_agent.utils.file_ops import (
    open_file,
    write_file,
    read_json,
    write_json,
    load_schema,
    validate_json_schema,
    save_prompt_to_file,
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


def test_validate_json_schema_error_message():
    """The ValidationError should be surfaced as a ValueError with a message."""
    schema = {"type": "object", "properties": {"age": {"type": "number"}}}
    with pytest.raises(ValueError) as exc_info:
        validate_json_schema({"age": "not a number"}, schema)
    # The wrapped message comes from jsonschema's ValidationError.message
    assert "JSON validation error" in str(exc_info.value)


# ---------------------------------------------------------------------------
# load_schema
# ---------------------------------------------------------------------------

def test_load_schema_success():
    """load_schema reads and parses a JSON schema file."""
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        schema_path = os.path.join(tmpdir, "schema.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f)

        loaded = load_schema(schema_path)
        assert loaded == schema


def test_load_schema_missing_file():
    """load_schema raises FileNotFoundError when the schema is absent."""
    with pytest.raises(FileNotFoundError):
        load_schema("/nonexistent/schema.json")


def test_load_schema_invalid_json():
    """load_schema raises ValueError when the schema file is not valid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        schema_path = os.path.join(tmpdir, "bad_schema.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write("{not valid json}")

        with pytest.raises(ValueError):
            load_schema(schema_path)


# ---------------------------------------------------------------------------
# save_prompt_to_file
# ---------------------------------------------------------------------------

def test_save_prompt_to_file_writes_content():
    """save_prompt_to_file creates a timestamped file containing the content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        content = "This is a planner prompt."
        filepath = save_prompt_to_file(tmpdir, "planner_prompt", content)

        assert os.path.exists(filepath)
        assert open_file(filepath) == content
        # Default subfolder is "prompts" and default extension ".md"
        assert os.path.dirname(filepath) == os.path.join(tmpdir, "prompts")
        assert filepath.endswith(".md")


def test_save_prompt_to_file_sanitizes_base_name():
    """The base name is lowercased and spaces become underscores."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = save_prompt_to_file(tmpdir, "My Planner Prompt", "x")
        filename = os.path.basename(filepath)
        assert filename.startswith("my_planner_prompt_")


def test_save_prompt_to_file_custom_subfolder_and_ext():
    """save_prompt_to_file honors custom subfolder and extension."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = save_prompt_to_file(
            tmpdir, "writer", "content", subfolder="debug", ext=".txt"
        )
        assert os.path.dirname(filepath) == os.path.join(tmpdir, "debug")
        assert filepath.endswith(".txt")


def test_save_prompt_to_file_wraps_error():
    """save_prompt_to_file wraps a makedirs failure as IOError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # output_dir is an existing *file*, so os.makedirs(<file>/prompts) fails.
        file_as_dir = os.path.join(tmpdir, "not_a_dir")
        with open(file_as_dir, "w", encoding="utf-8") as f:
            f.write("x")

        with pytest.raises(IOError):
            save_prompt_to_file(file_as_dir, "p", "content")


# ---------------------------------------------------------------------------
# Unicode preservation
# ---------------------------------------------------------------------------

def test_write_json_preserves_unicode():
    """write_json uses ensure_ascii=False so non-ASCII chars stay literal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "unicode.json")
        data = {"name": "Élodie", "place": "Café — Москва 東京", "emoji": "🗡️"}

        assert write_json(filepath, data)

        # Round-trips losslessly through read_json
        assert read_json(filepath) == data

        # And the raw bytes on disk contain the literal characters, not \uXXXX escapes
        raw = open_file(filepath)
        assert "Élodie" in raw
        assert "東京" in raw
        assert "🗡️" in raw
        assert "\\u" not in raw


# ---------------------------------------------------------------------------
# Error-wrapping branches (reachable IOError / FileNotFound / ValueError paths)
# ---------------------------------------------------------------------------

def test_open_file_wraps_read_error():
    """open_file wraps a read failure (e.g. path is a directory) as IOError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # The directory exists, so the FileNotFoundError guard passes, but
        # opening it for reading fails -> wrapped as IOError.
        with pytest.raises(IOError):
            open_file(tmpdir)


def test_write_file_wraps_write_error():
    """write_file wraps a write failure (target is an existing directory) as IOError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(IOError):
            write_file(tmpdir, "data")


def test_read_json_missing_file():
    """read_json raises FileNotFoundError for an absent path."""
    with pytest.raises(FileNotFoundError):
        read_json("/nonexistent/data.json")


def test_read_json_wraps_read_error():
    """read_json wraps a non-JSONDecode read failure as IOError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Path exists (directory) so the guard passes, but json.load on a
        # directory handle raises a non-JSONDecodeError -> wrapped as IOError.
        with pytest.raises(IOError):
            read_json(tmpdir)


def test_write_json_wraps_write_error():
    """write_json wraps a write failure (target is an existing directory) as IOError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(IOError):
            write_json(tmpdir, {"a": 1})
