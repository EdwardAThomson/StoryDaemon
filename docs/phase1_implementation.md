# Phase 1 Implementation Guide

**Goal:** Establish a working foundation for agent runtime, tool registry, and CLI.

**Duration:** 2-3 days

---

## Overview

Phase 1 creates the skeleton of StoryDaemon with:
- Basic CLI that can create novel projects
- Codex CLI integration for GPT-5 access
- File I/O utilities
- Tool registry foundation
- Configuration management

---

## Implementation Order

### **Step 1: Project Structure** (30 min)

Create the basic directory structure:

```bash
mkdir -p novel_agent/{agent,tools,memory,cli,configs}
mkdir -p tests/{unit,integration}
touch novel_agent/__init__.py
touch tests/__init__.py
```

Create initial files:
- `novel_agent/__init__.py` — Package marker
- `novel_agent/cli/__init__.py` — CLI module
- `novel_agent/tools/__init__.py` — Tools module
- `novel_agent/configs/__init__.py` — Config module
- `setup.py` or `pyproject.toml` — Package configuration
- `requirements.txt` — Dependencies

---

### **Step 2: File I/O Utilities** (1-2 hours)

**File:** `novel_agent/utils/file_ops.py`

Adapt from NovelWriter's `helper_fns.py`:

```python
"""File I/O utilities for StoryDaemon."""
import os
import json
import jsonschema
from typing import Any, Dict

def open_file(full_path: str) -> str:
    """Open and read a file. Raises FileNotFoundError if missing."""
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"File not found: {full_path}")
    with open(full_path, "r", encoding="utf-8") as file:
        return file.read()

def write_file(full_path: str, data: str) -> bool:
    """Write data to file, creating directories as needed."""
    dir_name = os.path.dirname(full_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as file:
        file.write(data)
    return True

def read_json(full_path: str) -> Dict[str, Any]:
    """Read and parse JSON file."""
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"File not found: {full_path}")
    with open(full_path, "r", encoding="utf-8") as file:
        return json.load(file)

def write_json(full_path: str, data: Dict[str, Any]) -> bool:
    """Write dictionary to JSON file with pretty-print."""
    dir_name = os.path.dirname(full_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    return True

def load_schema(schema_path: str) -> Dict[str, Any]:
    """Load JSON schema from file."""
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as file:
        return json.load(file)

def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """Validate data against JSON schema."""
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.exceptions.ValidationError as e:
        raise ValueError(f"JSON validation error: {e.message}")
```

**Test:** `tests/unit/test_file_ops.py`

---

### **Step 3: Codex CLI Interface** (2-3 hours)

**File:** `novel_agent/tools/codex_interface.py`

```python
"""Wrapper for calling Codex CLI from Python."""
import subprocess
import shutil
from typing import Optional

class CodexInterface:
    """Interface for calling Codex CLI to access GPT-5."""
    
    def __init__(self, codex_bin: str = "codex"):
        """Initialize Codex interface.
        
        Args:
            codex_bin: Path to codex binary (default: 'codex' in PATH)
        """
        self.codex_bin = codex_bin
        self._verify_codex_installed()
    
    def _verify_codex_installed(self):
        """Check if Codex CLI is installed and accessible."""
        if not shutil.which(self.codex_bin):
            raise RuntimeError(
                f"Codex CLI not found at '{self.codex_bin}'. "
                "Install with: npm install -g @openai/codex-cli"
            )
    
    def generate(self, prompt: str, max_tokens: int = 2000, 
                 timeout: int = 120) -> str:
        """Generate text using Codex CLI.
        
        Args:
            prompt: The prompt to send to Codex
            max_tokens: Maximum tokens to generate
            timeout: Timeout in seconds
            
        Returns:
            Generated text from GPT-5
            
        Raises:
            RuntimeError: If Codex CLI returns an error
            subprocess.TimeoutExpired: If generation times out
        """
        try:
            # TODO: Verify correct Codex CLI arguments
            result = subprocess.run(
                [self.codex_bin, prompt, '--max-tokens', str(max_tokens)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Codex CLI error: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Codex CLI timed out after {timeout}s")
```

**File:** `novel_agent/tools/llm_interface.py`

```python
"""LLM interface for StoryDaemon."""
from .codex_interface import CodexInterface

# Initialize Codex interface
_codex_interface = None

def initialize_llm(codex_bin: str = "codex"):
    """Initialize the LLM interface."""
    global _codex_interface
    _codex_interface = CodexInterface(codex_bin)

def send_prompt(prompt: str, max_tokens: int = 2000) -> str:
    """
    Send prompt to GPT-5 via Codex CLI.
    
    Args:
        prompt: The prompt to send
        max_tokens: Maximum tokens to generate
        
    Returns:
        Generated text from GPT-5
    """
    if _codex_interface is None:
        initialize_llm()
    return _codex_interface.generate(prompt, max_tokens=max_tokens)
```

**Test:** `tests/unit/test_codex_interface.py` (mock subprocess calls)

---

### **Step 4: Configuration Management** (1 hour)

**File:** `novel_agent/configs/config.py`

```python
"""Configuration management for StoryDaemon."""
import os
import yaml
from typing import Dict, Any

DEFAULT_CONFIG = {
    'llm': {
        'codex_bin_path': 'codex',
        'default_max_tokens': 2000,
        'planner_max_tokens': 1000,
        'writer_max_tokens': 3000,
    },
    'paths': {
        'novels_dir': os.path.expanduser('~/novels'),
    }
}

class Config:
    """Configuration manager."""
    
    def __init__(self, config_path: str = None):
        """Load configuration from file or use defaults."""
        self.config = DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            self.load(config_path)
    
    def load(self, config_path: str):
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            user_config = yaml.safe_load(f)
            self._merge_config(user_config)
    
    def _merge_config(self, user_config: Dict[str, Any]):
        """Merge user config with defaults."""
        # Deep merge logic here
        for key, value in user_config.items():
            if isinstance(value, dict) and key in self.config:
                self.config[key].update(value)
            else:
                self.config[key] = value
    
    def get(self, key: str, default=None):
        """Get config value by dot-notation key."""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
```

---

### **Step 5: Novel Project Structure** (1 hour)

**File:** `novel_agent/cli/project.py`

```python
"""Novel project management."""
import os
from ..utils.file_ops import write_json, write_file
from ..configs.config import Config

def create_novel_project(name: str, base_dir: str = None) -> str:
    """
    Create a new novel project directory structure.
    
    Args:
        name: Name of the novel
        base_dir: Base directory (default: ~/novels)
        
    Returns:
        Path to created project directory
    """
    config = Config()
    if base_dir is None:
        base_dir = config.get('paths.novels_dir')
    
    project_dir = os.path.join(base_dir, name)
    
    if os.path.exists(project_dir):
        raise ValueError(f"Project already exists: {project_dir}")
    
    # Create directory structure
    os.makedirs(os.path.join(project_dir, 'memory', 'characters'))
    os.makedirs(os.path.join(project_dir, 'memory', 'locations'))
    os.makedirs(os.path.join(project_dir, 'memory', 'scenes'))
    os.makedirs(os.path.join(project_dir, 'memory', 'index'))
    os.makedirs(os.path.join(project_dir, 'scenes'))
    os.makedirs(os.path.join(project_dir, 'plans'))
    
    # Create initial state file
    initial_state = {
        'novel_name': name,
        'current_tick': 0,
        'active_character': None,
        'created_at': None,  # Add timestamp
    }
    write_json(os.path.join(project_dir, 'state.json'), initial_state)
    
    # Create initial config
    novel_config = {
        'llm': {
            'planner_max_tokens': 1000,
            'writer_max_tokens': 3000,
        }
    }
    write_file(
        os.path.join(project_dir, 'config.yaml'),
        yaml.dump(novel_config)
    )
    
    # Create README
    readme = f"# {name}\n\nGenerated by StoryDaemon\n"
    write_file(os.path.join(project_dir, 'README.md'), readme)
    
    return project_dir

def find_project_dir(start_dir: str = None) -> str:
    """
    Find novel project directory by looking for state.json.
    
    Args:
        start_dir: Directory to start search (default: current dir)
        
    Returns:
        Path to project directory
        
    Raises:
        ValueError: If no project found
    """
    if start_dir is None:
        start_dir = os.getcwd()
    
    # Check current directory
    if os.path.exists(os.path.join(start_dir, 'state.json')):
        return start_dir
    
    raise ValueError(
        "No novel project found. Run 'novel new <name>' to create one, "
        "or use --project flag to specify path."
    )
```

---

### **Step 6: Basic CLI** (2-3 hours)

**File:** `novel_agent/cli/main.py`

```python
"""Main CLI entry point."""
import typer
from typing import Optional
from .project import create_novel_project, find_project_dir
from ..tools.llm_interface import initialize_llm, send_prompt

app = typer.Typer()

@app.command()
def new(
    name: str,
    dir: Optional[str] = typer.Option(None, help="Base directory for novel")
):
    """Create a new novel project."""
    try:
        project_dir = create_novel_project(name, dir)
        typer.echo(f"✅ Created novel project: {project_dir}")
        typer.echo(f"\nNext steps:")
        typer.echo(f"  cd {project_dir}")
        typer.echo(f"  novel tick")
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def tick(
    project: Optional[str] = typer.Option(None, help="Path to novel project")
):
    """Run one story generation tick."""
    try:
        project_dir = find_project_dir(project)
        typer.echo(f"Running tick for project: {project_dir}")
        
        # TODO: Implement actual tick logic
        # For now, just test Codex CLI
        initialize_llm()
        response = send_prompt("Write a single sentence.", max_tokens=50)
        typer.echo(f"\nTest generation: {response}")
        
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def run(
    n: int = typer.Option(5, help="Number of ticks to run"),
    project: Optional[str] = typer.Option(None, help="Path to novel project")
):
    """Run multiple story generation ticks."""
    typer.echo(f"Running {n} ticks...")
    # TODO: Implement

@app.command()
def summarize(
    project: Optional[str] = typer.Option(None, help="Path to novel project")
):
    """Compile summaries of all scenes."""
    # TODO: Implement
    pass

def main():
    """Entry point for CLI."""
    app()

if __name__ == "__main__":
    main()
```

**File:** `setup.py` or `pyproject.toml`

```python
# setup.py
from setuptools import setup, find_packages

setup(
    name="storydaemon",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "typer>=0.9.0",
        "jsonschema>=4.0.0",
        "pyyaml>=6.0.0",
    ],
    entry_points={
        "console_scripts": [
            "novel=novel_agent.cli.main:main",
        ],
    },
)
```

---

### **Step 7: Testing & Verification** (1-2 hours)

Create basic tests:

**File:** `tests/unit/test_file_ops.py`
**File:** `tests/unit/test_codex_interface.py` (with mocks)
**File:** `tests/integration/test_cli.py`

Run tests:
```bash
pytest tests/
```

Manual verification:
```bash
# Install in development mode
pip install -e .

# Test CLI
novel new test-story
cd ~/novels/test-story
novel tick
```

---

## Deliverables Checklist

- [ ] File I/O utilities working and tested
- [ ] Codex CLI wrapper can call GPT-5
- [ ] Configuration management loads YAML
- [ ] `novel new` creates project structure
- [ ] `novel tick` finds project and calls Codex CLI
- [ ] All unit tests passing
- [ ] Integration test creates project and runs tick

---

## Next Phase Preview

Phase 2 will add:
- Character/Location/Scene dataclasses
- Memory manager with CRUD operations
- Vector database integration (Chroma)
- Actual tool implementations (character.generate, etc.)

---

## Notes

- **Codex CLI verification:** Test Codex CLI arguments early - the exact flags may differ from examples
- **Error handling:** Add comprehensive error messages for common issues (Codex not installed, not authenticated, etc.)
- **Logging:** Consider adding basic logging early for debugging
- **Working directory:** All file operations should be relative to the novel project directory
