"""Tests for configuration management."""
import os
import tempfile
import pytest
from novel_agent.configs.config import Config


def test_default_config():
    """Test default configuration values."""
    config = Config()
    
    assert config.get('llm.codex_bin_path') == 'codex'
    assert config.get('llm.default_max_tokens') == 2000
    assert config.get('llm.planner_max_tokens') == 1000
    assert config.get('llm.writer_max_tokens') == 3000


def test_get_with_default():
    """Test getting config with default value."""
    config = Config()
    
    # Existing key
    assert config.get('llm.codex_bin_path') == 'codex'
    
    # Non-existing key with default
    assert config.get('nonexistent.key', 'default_value') == 'default_value'


def test_set_config_value():
    """Test setting configuration values."""
    config = Config()
    
    config.set('llm.codex_bin_path', '/custom/path/codex')
    assert config.get('llm.codex_bin_path') == '/custom/path/codex'
    
    # Set nested value
    config.set('custom.nested.value', 42)
    assert config.get('custom.nested.value') == 42


def test_load_config_from_yaml():
    """Test loading configuration from YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.yaml")
        
        # Write test config
        with open(config_path, 'w') as f:
            f.write("""
llm:
  codex_bin_path: /custom/codex
  planner_max_tokens: 1500
paths:
  novels_dir: /custom/novels
""")
        
        config = Config(config_path)
        
        assert config.get('llm.codex_bin_path') == '/custom/codex'
        assert config.get('llm.planner_max_tokens') == 1500
        assert config.get('paths.novels_dir') == '/custom/novels'
        
        # Default values should still be present
        assert config.get('llm.writer_max_tokens') == 3000


def test_save_config():
    """Test saving configuration to YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.yaml")
        
        config = Config()
        config.set('llm.codex_bin_path', '/saved/path')
        config.save(config_path)
        
        # Load saved config
        loaded_config = Config(config_path)
        assert loaded_config.get('llm.codex_bin_path') == '/saved/path'
