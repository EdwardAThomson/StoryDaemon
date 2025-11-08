# Project Safety & Quality Improvements

**Date:** November 8, 2025  
**Status:** Implemented  

---

## 1. UUID-Based Project Names

### Problem
User-provided project names could accidentally overwrite existing projects:
```bash
novel new test-story  # Creates test-story/
novel new test-story  # ERROR: Already exists!
```

This is especially risky when LLMs suggest project names, as they may reuse common names.

### Solution
Append 8-character UUID to project directory names:
```bash
novel new test-story  # Creates test-story_f9f163a7/
novel new test-story  # Creates test-story_d230e6be/  ✅ No collision!
```

### Implementation

**File:** `novel_agent/cli/project.py`

```python
import uuid

# Generate unique project ID to prevent overwrites
project_id = str(uuid.uuid4())[:8]  # Use first 8 chars for readability
project_dirname = f"{name}_{project_id}"
project_dir = os.path.join(base_dir, project_dirname)
```

**State file includes both:**
```json
{
  "novel_name": "test-story",
  "project_id": "f9f163a7",
  "created_at": "2025-11-08T19:10:43.038468"
}
```

### Benefits
✅ **No overwrites** - Each project gets unique directory  
✅ **Readable** - Still shows human-friendly name  
✅ **Traceable** - UUID stored in state.json  
✅ **LLM-safe** - Even if LLM reuses names, no collision  

### Examples

```bash
# Multiple projects with same base name
work/novels/
├── test-story_f9f163a7/
├── test-story_d230e6be/
├── sci-fi-adventure_a1b2c3d4/
└── sci-fi-adventure_e5f6g7h8/
```

---

## 2. Improved Scene Title Generation

### Problem
Scene titles were truncated at exactly 5 words, causing awkward cuts:
```markdown
# Introduce the protagonist as she
```

The word "she" is cut off mid-thought, making titles look unfinished.

### Solution
Smart truncation at word boundaries up to 60 characters:

**Before (5 words max):**
```markdown
# Introduce the protagonist as she  ❌ Awkward
```

**After (60 chars, word boundary):**
```markdown
# Have the newly introduced protagonist discover a puzzling  ✅ Natural
```

### Implementation

**File:** `novel_agent/agent/writer.py`

```python
# Generate from scene intention
intention = context.get('scene_intention', '')
if intention:
    # Use full intention if it's short enough, otherwise truncate smartly
    if len(intention) <= 60:
        title = intention
    else:
        # Truncate at word boundary near 60 chars
        words = intention.split()
        title = ''
        for word in words:
            if len(title) + len(word) + 1 <= 60:
                title += (' ' if title else '') + word
            else:
                break
    
    # Capitalize first letter and ensure no trailing punctuation
    if title:
        title = title.rstrip('.,;:!?')
        return title[0].upper() + title[1:]
```

### Benefits
✅ **Natural truncation** - Stops at word boundaries  
✅ **More context** - Uses up to 60 chars instead of 5 words  
✅ **Clean formatting** - Removes trailing punctuation  
✅ **Readable** - Titles make sense at a glance  

### Examples

| Scene Intention | Old Title (5 words) | New Title (60 chars) |
|----------------|---------------------|----------------------|
| "Introduce the protagonist as she arrives at the mysterious facility" | "Introduce the protagonist as she" ❌ | "Introduce the protagonist as she arrives at the mysterious" ✅ |
| "Have the newly introduced protagonist discover a puzzling artifact in a remote locale" | "Have the newly introduced protagonist" ❌ | "Have the newly introduced protagonist discover a puzzling" ✅ |
| "Continue the investigation" | "Continue the investigation" ✅ | "Continue the investigation" ✅ |

---

## Testing

### UUID Testing
```bash
# Create multiple projects with same name
./venv/bin/novel new test-story --dir work/novels
# → test-story_f9f163a7

./venv/bin/novel new test-story --dir work/novels
# → test-story_d230e6be

# No collision! ✅
```

### Title Testing
```bash
# Generate scene with long intention
./venv/bin/novel tick --project work/novels/test-story_f9f163a7

# Check title
head -1 work/novels/test-story_f9f163a7/scenes/scene_000.md
# → "Have the newly introduced protagonist discover a puzzling"
# Clean, natural truncation ✅
```

---

## Configuration

Both features are automatic and require no configuration:
- UUID generation happens on every `novel new` command
- Title truncation happens during scene writing

---

## Future Enhancements

### UUID Display
Could add command to show all projects with same base name:
```bash
novel list --name test-story
# test-story_f9f163a7 (created 2025-11-08, 3 scenes)
# test-story_d230e6be (created 2025-11-08, 0 scenes)
```

### Title Customization
Could make title length configurable:
```yaml
# config.yaml
generation:
  scene_title_max_length: 60  # Default
```

---

## Conclusion

Both improvements enhance safety and quality:
1. **UUID suffixes** prevent accidental overwrites
2. **Smart title truncation** creates readable scene headers

These changes make the system more robust for both human and LLM usage.
