# Resume Workflow

**Date:** November 8, 2025  
**Status:** Implemented  
**Related:** UUID Project Names

---

## Problem

With UUID-based project names, it's difficult to remember and type full paths:
```bash
# Hard to remember and type
novel tick --project work/novels/test-story_f9f163a7
novel run --n 5 --project work/novels/sci-fi-adventure_a1b2c3d4
```

Users need an easy way to:
1. See which projects they've been working on
2. Continue working on recent projects without typing full paths
3. Switch between multiple active projects

---

## Solution

**Recent Projects Tracking** with `recent` and `resume` commands.

### Features

1. **Automatic Tracking** - Projects are tracked when you run `tick` or `run`
2. **Recent List** - View your 10 most recent projects with `novel recent`
3. **Quick Resume** - Continue most recent project with `novel resume`
4. **Persistent** - Stored in `~/.config/storydaemon/recent_projects.json`

---

## Commands

### `novel recent`

Show recently accessed projects:

```bash
$ novel recent

📚 Recent Projects (last 2):

  1. final-test
     Path: /home/edward/Projects/StoryDaemon/work/novels/final-test
     Scenes: 2 scenes
     Last accessed: 2025-11-08T19:27:43

  2. test-story
     Path: /home/edward/Projects/StoryDaemon/work/novels/test-story_f9f163a7
     Scenes: 3 scenes
     Last accessed: 2025-11-08T19:27:02

💡 Tip: Use 'novel resume' to continue the most recent project
```

**Options:**
- `--limit N` / `-n N` - Show N most recent projects (default: 10)

**Examples:**
```bash
novel recent              # Show last 10 projects
novel recent --limit 5    # Show last 5 projects
novel recent -n 3         # Show last 3 projects
```

---

### `novel resume`

Continue working on the most recent project:

```bash
$ novel resume

📖 Resuming: test-story
   Path: /home/edward/Projects/StoryDaemon/work/novels/test-story_f9f163a7
   Current progress: 3 scenes

📖 Running tick for project: ...
✅ Tick 3 completed successfully!
```

**Options:**
- `--n N` / `-n N` - Number of ticks to run (default: 1)

**Examples:**
```bash
novel resume          # Run 1 tick on most recent project
novel resume --n 5    # Run 5 ticks on most recent project
novel resume -n 10    # Run 10 ticks on most recent project
```

---

## Workflow Examples

### Starting a New Project

```bash
# Create new project (gets UUID automatically)
novel new my-story --dir work/novels
# → Creates: work/novels/my-story_f9f163a7/

# Run first tick
cd work/novels/my-story_f9f163a7
novel tick

# Project is now tracked!
```

### Working on Multiple Projects

```bash
# Work on project A
novel tick --project work/novels/project-a_abc123

# Work on project B
novel tick --project work/novels/project-b_def456

# See both in recent list
novel recent
# 1. project-b (most recent)
# 2. project-a

# Resume most recent (project-b)
novel resume

# Or explicitly work on project-a again
novel tick --project work/novels/project-a_abc123
```

### Daily Workflow

```bash
# Morning: Check what you were working on
novel recent

# Continue where you left off
novel resume --n 5

# Later: Quick check on progress
novel status

# End of day: Generate more scenes
novel resume --n 10
```

---

## Implementation

### Recent Projects Tracker

**File:** `novel_agent/cli/recent_projects.py`

```python
class RecentProjects:
    """Manage list of recently accessed projects."""
    
    def __init__(self, max_recent: int = 10):
        self.config_dir = Path.home() / ".config" / "storydaemon"
        self.recent_file = self.config_dir / "recent_projects.json"
    
    def add_project(self, project_path: str, project_name: Optional[str] = None):
        """Add or update a project in recent list."""
        # Loads recent, removes duplicates, adds to front, saves
    
    def get_recent(self, limit: Optional[int] = None) -> List[Dict]:
        """Get list of recent projects."""
        # Returns valid projects (filters out deleted ones)
    
    def get_most_recent(self) -> Optional[str]:
        """Get path to most recently accessed project."""
```

### Storage Format

**File:** `work/recent_projects.json` (in project root)

```json
[
  {
    "path": "/home/user/work/novels/test-story_f9f163a7",
    "name": "test-story",
    "last_accessed": "2025-11-08T19:27:43.123456"
  },
  {
    "path": "/home/user/work/novels/final-test",
    "name": "final-test",
    "last_accessed": "2025-11-08T19:27:02.654321"
  }
]
```

### Auto-Tracking

Projects are automatically tracked when you run:
- `novel tick --project <path>`
- `novel run --n N --project <path>`

**Code:**
```python
# In tick() and run() commands
recent = RecentProjects()
state = load_project_state(project_dir)
recent.add_project(str(project_dir), state.get('novel_name'))
```

---

## Benefits

✅ **No typing UUIDs** - Just use `novel resume`  
✅ **Easy project switching** - See all recent projects with `novel recent`  
✅ **Persistent tracking** - Survives terminal restarts  
✅ **Automatic cleanup** - Removes deleted projects from list  
✅ **Works with UUIDs** - Complements UUID safety feature  

---

## Configuration

### Max Recent Projects

Default: 10 most recent projects

Can be changed by modifying `RecentProjects` initialization:
```python
recent = RecentProjects(max_recent=20)  # Track 20 projects
```

### Storage Location

Default: `work/recent_projects.json` (in project root)

This keeps all development work in one place:
```
StoryDaemon/
├── work/
│   ├── recent_projects.json    # Recent projects tracker
│   ├── novels/                 # Test novels
│   ├── experiments/            # Experiments
│   └── scratch/                # Temp files
```

Benefits:
- ✅ Everything in one place
- ✅ Easy to find and inspect
- ✅ Can be gitignored (already configured)
- ✅ No hidden files in home directory

---

## Edge Cases

### Deleted Projects

If a project is deleted, it's automatically removed from the recent list:
```python
# Filter out projects that no longer exist
valid_recent = []
for project in recent:
    project_path = Path(project['path'])
    if project_path.exists() and (project_path / 'state.json').exists():
        valid_recent.append(project)
```

### No Recent Projects

```bash
$ novel resume
❌ No recent projects found

💡 Tip: Create a project with 'novel new <name>'
```

### Concurrent Access

The tracker uses simple file-based storage. If multiple terminals access it simultaneously, the last write wins. This is acceptable for a single-user tool.

---

## Future Enhancements

### Project Aliases

Allow naming projects for easier access:
```bash
novel alias my-story work/novels/test-story_f9f163a7
novel resume my-story  # Resume by alias
```

### Project Selection

Interactive selection from recent list:
```bash
novel resume --select
# 1. test-story (3 scenes)
# 2. final-test (2 scenes)
# Choose project [1-2]: 1
```

### Project Tags

Tag projects for organization:
```bash
novel tag add work/novels/test-story_f9f163a7 "sci-fi" "draft"
novel recent --tag "sci-fi"  # Show only sci-fi projects
```

---

## Testing

### Test Recent Tracking

```bash
# Create and work on projects
novel new project-a --dir work/novels
novel tick --project work/novels/project-a_*

novel new project-b --dir work/novels
novel tick --project work/novels/project-b_*

# Check recent list
novel recent
# Should show both projects, project-b first
```

### Test Resume

```bash
# Resume should pick most recent
novel resume
# Should resume project-b

# Work on project-a
novel tick --project work/novels/project-a_*

# Resume should now pick project-a
novel resume
# Should resume project-a
```

### Test Cleanup

```bash
# Delete a project
rm -rf work/novels/project-b_*

# Recent should auto-clean
novel recent
# Should only show project-a (project-b removed)
```

---

## Conclusion

The resume workflow makes it easy to work on multiple projects with UUID-based names. Users can:
1. See their recent work with `novel recent`
2. Continue instantly with `novel resume`
3. Never type UUID paths manually

This complements the UUID safety feature by making the longer names manageable.
