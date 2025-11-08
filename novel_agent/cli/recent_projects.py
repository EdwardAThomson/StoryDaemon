"""Track and manage recently accessed novel projects."""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class RecentProjects:
    """Manage list of recently accessed projects."""
    
    def __init__(self, max_recent: int = 10, work_dir: Optional[Path] = None):
        """Initialize recent projects tracker.
        
        Args:
            max_recent: Maximum number of recent projects to track
            work_dir: Working directory for storing recent projects file
                     (defaults to project_root/work/)
        """
        self.max_recent = max_recent
        
        # Use work/ directory in project root
        if work_dir is None:
            # Find project root (where this file is located)
            project_root = Path(__file__).parent.parent.parent
            work_dir = project_root / "work"
        
        self.config_dir = work_dir
        self.recent_file = self.config_dir / "recent_projects.json"
        self._ensure_config_dir()
    
    def _ensure_config_dir(self):
        """Ensure config directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_recent(self) -> List[Dict]:
        """Load recent projects from file.
        
        Returns:
            List of recent project dictionaries
        """
        if not self.recent_file.exists():
            return []
        
        try:
            with open(self.recent_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    
    def _save_recent(self, projects: List[Dict]):
        """Save recent projects to file.
        
        Args:
            projects: List of project dictionaries to save
        """
        try:
            with open(self.recent_file, 'w', encoding='utf-8') as f:
                json.dump(projects, f, indent=2)
        except IOError:
            pass  # Silently fail if we can't write
    
    def add_project(self, project_path: str, project_name: Optional[str] = None):
        """Add or update a project in recent list.
        
        Args:
            project_path: Absolute path to project directory
            project_name: Optional human-readable project name
        """
        project_path = str(Path(project_path).resolve())
        
        # Load existing recent projects
        recent = self._load_recent()
        
        # Remove if already exists (we'll re-add at top)
        recent = [p for p in recent if p.get('path') != project_path]
        
        # Add to front
        project_entry = {
            'path': project_path,
            'name': project_name or Path(project_path).name,
            'last_accessed': datetime.now().isoformat()
        }
        recent.insert(0, project_entry)
        
        # Trim to max_recent
        recent = recent[:self.max_recent]
        
        # Save
        self._save_recent(recent)
    
    def get_recent(self, limit: Optional[int] = None) -> List[Dict]:
        """Get list of recent projects.
        
        Args:
            limit: Optional limit on number of projects to return
        
        Returns:
            List of recent project dictionaries
        """
        recent = self._load_recent()
        
        # Filter out projects that no longer exist
        valid_recent = []
        for project in recent:
            project_path = Path(project['path'])
            if project_path.exists() and (project_path / 'state.json').exists():
                valid_recent.append(project)
        
        # Save cleaned list if anything was removed
        if len(valid_recent) != len(recent):
            self._save_recent(valid_recent)
        
        if limit:
            return valid_recent[:limit]
        return valid_recent
    
    def get_most_recent(self) -> Optional[str]:
        """Get path to most recently accessed project.
        
        Returns:
            Path to most recent project, or None if no recent projects
        """
        recent = self.get_recent(limit=1)
        if recent:
            return recent[0]['path']
        return None
    
    def clear(self):
        """Clear all recent projects."""
        self._save_recent([])
