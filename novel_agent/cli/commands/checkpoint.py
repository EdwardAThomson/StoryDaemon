"""Checkpoint command - manage project checkpoints."""
import json
from pathlib import Path
from typing import Optional
from ...memory.checkpoint import (
    create_checkpoint,
    list_checkpoints,
    restore_checkpoint,
    delete_checkpoint
)


def create_checkpoint_cmd(project_dir: Path, message: Optional[str] = None):
    """Create a checkpoint command wrapper.
    
    Args:
        project_dir: Path to project directory
        message: Optional description message
    """
    # Load current tick
    state_file = project_dir / "state.json"
    if not state_file.exists():
        print("❌ state.json not found")
        return
    
    with open(state_file, 'r') as f:
        state = json.load(f)
        current_tick = state.get('current_tick', 0)
    
    created_by = message if message else "manual"
    
    try:
        checkpoint_path = create_checkpoint(project_dir, current_tick, created_by)
        print(f"✅ Created checkpoint: {checkpoint_path.name}")
        print(f"   Tick: {current_tick}")
        if message:
            print(f"   Message: {message}")
    except IOError as e:
        print(f"❌ Error creating checkpoint: {e}")


def list_checkpoints_cmd(project_dir: Path):
    """List checkpoints command wrapper.
    
    Args:
        project_dir: Path to project directory
    """
    manifests = list_checkpoints(project_dir)
    
    if not manifests:
        print("\n📦 No checkpoints found\n")
        return
    
    print(f"\n📦 Checkpoints ({len(manifests)} total)\n")
    
    for manifest in manifests:
        print(f"  {manifest.checkpoint_id}")
        print(f"    Tick: {manifest.tick}")
        print(f"    Created: {manifest.timestamp}")
        print(f"    Scenes: {manifest.scenes_count}")
        print(f"    Characters: {manifest.characters_count}")
        print(f"    Locations: {manifest.locations_count}")
        size_mb = manifest.size_bytes / (1024 * 1024)
        print(f"    Size: {size_mb:.2f} MB")
        print(f"    Created by: {manifest.created_by}")
        print()


def restore_checkpoint_cmd(project_dir: Path, checkpoint_id: str):
    """Restore checkpoint command wrapper.
    
    Args:
        project_dir: Path to project directory
        checkpoint_id: Checkpoint ID to restore
    """
    print(f"⚠️  This will restore project state to: {checkpoint_id}")
    print("   Current state will be backed up automatically.")
    
    # Confirm
    response = input("\nContinue? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    try:
        restore_checkpoint(project_dir, checkpoint_id, backup_current=True)
        print(f"✅ Restored checkpoint: {checkpoint_id}")
        print("   Current state backed up to checkpoints/backup_before_restore_*")
    except (ValueError, IOError) as e:
        print(f"❌ Error restoring checkpoint: {e}")


def delete_checkpoint_cmd(project_dir: Path, checkpoint_id: str):
    """Delete checkpoint command wrapper.
    
    Args:
        project_dir: Path to project directory
        checkpoint_id: Checkpoint ID to delete
    """
    print(f"⚠️  This will permanently delete: {checkpoint_id}")
    
    # Confirm
    response = input("\nContinue? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    try:
        delete_checkpoint(project_dir, checkpoint_id)
        print(f"✅ Deleted checkpoint: {checkpoint_id}")
    except (ValueError, IOError) as e:
        print(f"❌ Error deleting checkpoint: {e}")
