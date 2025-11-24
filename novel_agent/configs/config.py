"""Configuration management for StoryDaemon."""
import os
import yaml
from typing import Dict, Any, Optional


# Default configuration
DEFAULT_CONFIG = {
    'llm': {
        'backend': 'codex',
        'codex_bin_path': 'codex',
        'default_max_tokens': 2000,
        'planner_max_tokens': 1000,
        'writer_max_tokens': 3000,
        'extractor_max_tokens': 2000,
        'timeout': 120,
        'model': 'gpt-5.1',  # Generic model name for API backend (OpenAI/Gemini/Claude)
        'openai_model': 'gpt-5.1',
        'openai_api_key_env': 'OPENAI_API_KEY',
    },
    'paths': {
        'novels_dir': os.path.expanduser('~/novels'),
    },
    'generation': {
        'max_tools_per_tick': 3,
        'recent_scenes_count': 3,
        'full_text_scenes_count': 2,  # Number of recent scenes to include as full text in writer context
        'summary_scenes_count': 3,    # Number of older scenes to include as summaries in writer context
        'include_overall_summary': True,
        'enable_fact_extraction': True,
        'enable_entity_updates': True,
        'enable_tension_tracking': True,  # Phase 7A.3: Track scene tension levels
        'enable_lore_tracking': True,  # Phase 7A.4: Track world rules and lore
    },
    'lore': {
        'contradiction_threshold': 0.5,  # Similarity threshold for flagging contradictions (0.0-2.0)
    },
    'plot': {
        # Beat integration mode: controls how strongly the agent treats plot beats.
        #
        #   off       - no beat hints or QA integration
        #   soft_hint - expose next_plot_beat and compute beat_hint_alignment (default)
        #   guided    - planner expected to fill beat_target and beats may be updated
        #   strict    - future: hard validation around beat usage
        'beat_mode': 'soft_hint',
    }
}


class Config:
    """Configuration manager for StoryDaemon."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration.
        
        Args:
            config_path: Path to YAML config file (optional)
        """
        self.config = self._deep_copy(DEFAULT_CONFIG)
        
        if config_path and os.path.exists(config_path):
            self.load(config_path)
    
    def load(self, config_path: str):
        """Load configuration from YAML file.
        
        Args:
            config_path: Path to YAML config file
            
        Raises:
            IOError: If file cannot be read
            ValueError: If YAML is invalid
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    self._merge_config(user_config)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {config_path}: {e}")
        except Exception as e:
            raise IOError(f"Error reading config from {config_path}: {e}")
    
    def _merge_config(self, user_config: Dict[str, Any]):
        """Merge user config with defaults (deep merge).
        
        Args:
            user_config: User configuration dictionary
        """
        self._deep_merge(self.config, user_config)
    
    def _deep_merge(self, base: Dict, update: Dict):
        """Recursively merge update dict into base dict.
        
        Args:
            base: Base dictionary to merge into
            update: Dictionary with updates
        """
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def _deep_copy(self, d: Dict) -> Dict:
        """Create a deep copy of a dictionary.
        
        Args:
            d: Dictionary to copy
            
        Returns:
            Deep copy of dictionary
        """
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                result[key] = self._deep_copy(value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key.
        
        Args:
            key: Dot-notation key (e.g., 'llm.codex_bin_path')
            default: Default value if key not found
            
        Returns:
            Config value or default
            
        Examples:
            >>> config.get('llm.codex_bin_path')
            'codex'
            >>> config.get('llm.planner_max_tokens')
            1000
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set config value by dot-notation key.
        
        Args:
            key: Dot-notation key (e.g., 'llm.codex_bin_path')
            value: Value to set
            
        Examples:
            >>> config.set('llm.codex_bin_path', '/usr/local/bin/codex')
        """
        keys = key.split('.')
        target = self.config
        
        # Navigate to the parent dict
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        # Set the value
        target[keys[-1]] = value
    
    def save(self, config_path: str):
        """Save current configuration to YAML file.
        
        Args:
            config_path: Path to save config file
            
        Raises:
            IOError: If file cannot be written
        """
        try:
            dir_name = os.path.dirname(config_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise IOError(f"Error saving config to {config_path}: {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary.
        
        Returns:
            Configuration dictionary
        """
        return self._deep_copy(self.config)
