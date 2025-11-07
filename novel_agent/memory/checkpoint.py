"""Checkpoint system for project state snapshots."""
import json
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class CheckpointManifest:
    """Metadata for a checkpoint."""
    checkpoint_id: str
    tick: int
    timestamp: str
    scenes_count: int
    characters_count: int
    locations_count: int
    size_bytes: int
    created_by: str
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointManifest":
        return cls(**data)


def get_checkpoint_dir(project_dir: Path) -> Path:
    """Get checkpoints directory path.
    
    Args:
        project_dir: Path to project directory
        
    Returns:
        Path to checkpoints directory
    """
    return project_dir / "checkpoints"


def get_checkpoint_id(tick: int) -> str:
    """Generate checkpoint ID from tick number.
    
    Args:
        tick: Tick number
        
    Returns:
        Checkpoint ID string
    """
    return f"checkpoint_tick_{tick:03d}"


def get_directory_size(path: Path) -> int:
    """Calculate total size of directory in bytes.
    
    Args:
        path: Directory path
        
    Returns:
        Size in bytes
    """
    total = 0
    for item in path.rglob('*'):
        if item.is_file():
            total += item.stat().st_size
    return total


def count_files_in_dir(directory: Path, pattern: str = "*.json") -> int:
    """Count files matching pattern in directory.
    
    Args:
        directory: Directory to search
        pattern: Glob pattern
        
    Returns:
        File count
    """
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def create_checkpoint(project_dir: Path, tick: int, created_by: str = "manual") -> Path:
    """Create a checkpoint of the current project state.
    
    Args:
        project_dir: Path to project directory
        tick: Current tick number
        created_by: Description of what created the checkpoint
        
    Returns:
        Path to created checkpoint directory
        
    Raises:
        IOError: If checkpoint cannot be created
    """
    checkpoint_id = get_checkpoint_id(tick)
    checkpoints_dir = get_checkpoint_dir(project_dir)
    checkpoint_path = checkpoints_dir / checkpoint_id
    
    # Create checkpoints directory if needed
    checkpoints_dir.mkdir(exist_ok=True)
    
    # Check if checkpoint already exists
    if checkpoint_path.exists():
        raise IOError(f"Checkpoint already exists: {checkpoint_id}")
    
    try:
        # Create checkpoint directory
        checkpoint_path.mkdir()
        
        # Copy directories
        dirs_to_copy = ['memory', 'scenes', 'plans']
        for dir_name in dirs_to_copy:
            src = project_dir / dir_name
            if src.exists():
                dst = checkpoint_path / dir_name
                shutil.copytree(src, dst)
        
        # Copy files
        files_to_copy = ['state.json', 'config.yaml']
        for file_name in files_to_copy:
            src = project_dir / file_name
            if src.exists():
                dst = checkpoint_path / file_name
                shutil.copy2(src, dst)
        
        # Count entities
        memory_dir = checkpoint_path / "memory"
        scenes_count = count_files_in_dir(checkpoint_path / "scenes", "*.md")
        chars_count = count_files_in_dir(memory_dir / "characters")
        locs_count = count_files_in_dir(memory_dir / "locations")
        
        # Calculate size
        size_bytes = get_directory_size(checkpoint_path)
        
        # Create manifest
        manifest = CheckpointManifest(
            checkpoint_id=checkpoint_id,
            tick=tick,
            timestamp=datetime.now().isoformat(),
            scenes_count=scenes_count,
            characters_count=chars_count,
            locations_count=locs_count,
            size_bytes=size_bytes,
            created_by=created_by
        )
        
        # Save manifest
        manifest_path = checkpoint_path / "manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest.to_dict(), f, indent=2)
        
        return checkpoint_path
        
    except Exception as e:
        # Clean up on error
        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)
        raise IOError(f"Error creating checkpoint: {e}")


def list_checkpoints(project_dir: Path) -> List[CheckpointManifest]:
    """List all available checkpoints.
    
    Args:
        project_dir: Path to project directory
        
    Returns:
        List of checkpoint manifests, sorted by tick
    """
    checkpoints_dir = get_checkpoint_dir(project_dir)
    
    if not checkpoints_dir.exists():
        return []
    
    manifests = []
    for checkpoint_dir in checkpoints_dir.iterdir():
        if not checkpoint_dir.is_dir():
            continue
        
        manifest_file = checkpoint_dir / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    manifests.append(CheckpointManifest.from_dict(data))
            except Exception:
                # Skip invalid manifests
                continue
    
    # Sort by tick
    return sorted(manifests, key=lambda m: m.tick)


def restore_checkpoint(project_dir: Path, checkpoint_id: str, backup_current: bool = True) -> None:
    """Restore project state from a checkpoint.
    
    Args:
        project_dir: Path to project directory
        checkpoint_id: Checkpoint ID to restore
        backup_current: Create backup of current state before restoring
        
    Raises:
        ValueError: If checkpoint not found
        IOError: If restore fails
    """
    checkpoints_dir = get_checkpoint_dir(project_dir)
    checkpoint_path = checkpoints_dir / checkpoint_id
    
    if not checkpoint_path.exists():
        raise ValueError(f"Checkpoint not found: {checkpoint_id}")
    
    # Backup current state if requested
    if backup_current:
        try:
            # Load current tick
            state_file = project_dir / "state.json"
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    current_tick = state.get('current_tick', 0)
                
                # Create backup checkpoint
                backup_id = f"backup_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                backup_path = checkpoints_dir / backup_id
                
                # Copy current state
                backup_path.mkdir(exist_ok=True)
                for dir_name in ['memory', 'scenes', 'plans']:
                    src = project_dir / dir_name
                    if src.exists():
                        dst = backup_path / dir_name
                        shutil.copytree(src, dst)
                
                for file_name in ['state.json', 'config.yaml']:
                    src = project_dir / file_name
                    if src.exists():
                        dst = backup_path / file_name
                        shutil.copy2(src, dst)
        except Exception as e:
            print(f"Warning: Could not create backup: {e}")
    
    try:
        # Restore directories
        dirs_to_restore = ['memory', 'scenes', 'plans']
        for dir_name in dirs_to_restore:
            src = checkpoint_path / dir_name
            dst = project_dir / dir_name
            
            # Remove existing
            if dst.exists():
                shutil.rmtree(dst)
            
            # Copy from checkpoint
            if src.exists():
                shutil.copytree(src, dst)
        
        # Restore files
        files_to_restore = ['state.json', 'config.yaml']
        for file_name in files_to_restore:
            src = checkpoint_path / file_name
            dst = project_dir / file_name
            
            if src.exists():
                shutil.copy2(src, dst)
        
    except Exception as e:
        raise IOError(f"Error restoring checkpoint: {e}")


def delete_checkpoint(project_dir: Path, checkpoint_id: str) -> None:
    """Delete a checkpoint.
    
    Args:
        project_dir: Path to project directory
        checkpoint_id: Checkpoint ID to delete
        
    Raises:
        ValueError: If checkpoint not found
        IOError: If deletion fails
    """
    checkpoints_dir = get_checkpoint_dir(project_dir)
    checkpoint_path = checkpoints_dir / checkpoint_id
    
    if not checkpoint_path.exists():
        raise ValueError(f"Checkpoint not found: {checkpoint_id}")
    
    try:
        shutil.rmtree(checkpoint_path)
    except Exception as e:
        raise IOError(f"Error deleting checkpoint: {e}")


def cleanup_old_checkpoints(project_dir: Path, keep_last: int = 5) -> List[str]:
    """Remove old checkpoints, keeping only the most recent N.
    
    Args:
        project_dir: Path to project directory
        keep_last: Number of checkpoints to keep
        
    Returns:
        List of deleted checkpoint IDs
    """
    manifests = list_checkpoints(project_dir)
    
    if len(manifests) <= keep_last:
        return []
    
    # Sort by tick (oldest first)
    manifests.sort(key=lambda m: m.tick)
    
    # Delete oldest checkpoints
    to_delete = manifests[:-keep_last]
    deleted = []
    
    for manifest in to_delete:
        try:
            delete_checkpoint(project_dir, manifest.checkpoint_id)
            deleted.append(manifest.checkpoint_id)
        except Exception:
            # Continue even if one fails
            continue
    
    return deleted


def should_create_checkpoint(current_tick: int, checkpoint_interval: int, 
                            last_checkpoint_tick: Optional[int] = None) -> bool:
    """Determine if a checkpoint should be created.
    
    Args:
        current_tick: Current tick number
        checkpoint_interval: Interval between checkpoints
        last_checkpoint_tick: Tick of last checkpoint (if any)
        
    Returns:
        True if checkpoint should be created
    """
    if checkpoint_interval <= 0:
        return False
    
    if last_checkpoint_tick is None:
        # First checkpoint
        return current_tick > 0 and current_tick % checkpoint_interval == 0
    
    return current_tick - last_checkpoint_tick >= checkpoint_interval
