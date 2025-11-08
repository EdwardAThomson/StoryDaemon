# Name Generator Implementation Plan

**Date:** November 8, 2025  
**Status:** Proposed Enhancement  
**Priority:** High - Fixes AI name repetition issue

---

## Problem Statement

**AI-generated names are repetitive:**
- "Mara" appeared in multiple test stories
- "Dr. Mara Kess", "Mara Ivers", "Dr. Mara Ellion"
- Pure LLM generation lacks diversity
- No control over name uniqueness

**Solution:** Implement a local name generator tool that the agent can call, similar to NovelWriter's approach.

---

## Reference: NovelWriter's Approach

From `/reference/NovelWriter/SciFiGenerator.py` and `SciFiCharacterGenerator.py`:

### Key Features:
1. **Syllable-based generation** - Phonetically pleasing combinations
2. **Large name lists** - Hundreds of syllables for variety
3. **Gender-specific names** - Different pools for male/female
4. **Phonetic compatibility rules** - Avoid awkward combinations
5. **Configurable length** - Min/max character limits
6. **Genre-specific** - Sci-fi vs fantasy vs modern names

### Example Structure:
```python
CHAR_FIRST_SYLLABLES = {
    "start": ["Ar", "Bel", "Cael", "Dar", "El", "Fen", ...],  # 40+ options
    "end": ["a", "an", "ar", "as", "en", "er", ...]  # 24+ options
}

CHAR_LAST_SYLLABLES = {
    "start": ["Zar", "Vex", "Kyr", "Nyx", ...],  # 30+ options
    "end": ["an", "ar", "as", "ax", ...]  # 30+ options
}
```

**Result:** 40 × 24 × 30 × 30 = **864,000 possible unique names**

---

## Proposed Implementation for StoryDaemon

### Architecture

```
novel_agent/
├── tools/
│   └── name_generator.py        # New tool
├── data/
│   └── names/
│       ├── scifi_syllables.json
│       ├── fantasy_syllables.json
│       ├── modern_names.json
│       └── titles.json
```

### New Tool: `name.generate`

**Tool Definition:**
```python
class NameGeneratorTool(Tool):
    def __init__(self):
        super().__init__(
            name="name.generate",
            description="Generate a unique character name using phonetic syllables",
            parameters={
                "gender": {
                    "type": "string",
                    "enum": ["male", "female"],
                    "description": "Character gender for name generation"
                },
                "genre": {
                    "type": "string",
                    "enum": ["scifi", "fantasy", "modern", "historical"],
                    "description": "Genre style for name generation",
                    "optional": True
                },
                "title": {
                    "type": "string",
                    "description": "Optional title (Dr., Captain, Lord, etc.)",
                    "optional": True
                }
            }
        )
```

**Usage by Agent:**
```json
{
  "tool": "name.generate",
  "args": {
    "gender": "female",
    "genre": "scifi",
    "title": "Dr."
  },
  "reason": "Generate unique name for protagonist scientist"
}
```

**Returns:**
```json
{
  "success": true,
  "full_name": "Dr. Kira Vexan",
  "first_name": "Kira",
  "last_name": "Vexan",
  "title": "Dr."
}
```

---

## Integration with Character Generation

### Current Flow (Problematic):
```
Planner decides:
  "I need a character named 'Dr. Mara Kess'"
  ↓
character.generate(name="Dr. Mara Kess", ...)
  ↓
Character created with AI-chosen name
```

### Proposed Flow (Fixed):
```
Planner decides:
  "I need a female scientist character"
  ↓
name.generate(gender="female", genre="scifi", title="Dr.")
  ↓
Returns: "Dr. Kira Vexan"
  ↓
character.generate(name="Dr. Kira Vexan", ...)
  ↓
Character created with unique generated name
```

---

## Name Data Structure

### Sci-Fi Names

**File:** `novel_agent/data/names/scifi_syllables.json`

```json
{
  "first_name": {
    "male": {
      "start": ["Ar", "Bel", "Cael", "Dar", "El", "Fen", "Gal", "Hal", ...],
      "end": ["an", "ar", "en", "er", "on", "or", "us", "yn", ...]
    },
    "female": {
      "start": ["Ar", "Bel", "Cael", "El", "Ir", "Lir", "Syl", "Vel", ...],
      "end": ["a", "ia", "is", "yn", "el", "il", "ex", "ix", ...]
    },
  },
  "last_name": {
    "start": ["Zar", "Vex", "Kyr", "Nyx", "Rax", "Dex", "Lyx", "Myr", ...],
    "end": ["an", "ar", "as", "ax", "en", "er", "es", "ex", ...]
  }
}
```

### Fantasy Names

**File:** `novel_agent/data/names/fantasy_syllables.json`

```json
{
  "first_name": {
    "male": {
      "start": ["Ael", "Bran", "Cor", "Dun", "Eld", "Finn", "Gar", ...],
      "end": ["ric", "wyn", "dor", "mir", "thor", "dan", ...]
    },
    "female": {
      "start": ["Ael", "Bri", "Cel", "Ela", "Gwen", "Isa", "Lys", ...],
      "end": ["wen", "lyn", "ara", "iel", "eth", "ith", ...]
    }
  },
  "last_name": {
    "start": ["Ash", "Black", "Bright", "Dark", "Fair", "Gold", ...],
    "end": ["wood", "stone", "water", "fire", "wind", "heart", ...]
  }
}
```

### Modern Names

**File:** `novel_agent/data/names/modern_names.json`

```json
{
  "first_name": {
    "male": ["James", "Michael", "Robert", "John", "David", "William", ...],
    "female": ["Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", ...],
  },
  "last_name": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", ...]
}
```

### Titles

**File:** `novel_agent/data/names/titles.json`

```json
{
  "military": {
    "high": ["Admiral", "General", "Commander", "Captain", "Colonel"],
    "mid": ["Lieutenant", "Sergeant", "Major", "Ensign"],
    "low": ["Private", "Corporal", "Cadet"]
  },
  "civilian": {
    "high": ["Dr.", "Professor", "Director", "Chancellor"],
    "mid": ["Senior", "Manager", "Supervisor"],
    "low": ["Junior", "Assistant", "Technician"]
  },
  "noble": {
    "high": ["Lord", "Lady", "Duke", "Duchess", "Baron", "Baroness"],
    "mid": ["Knight", "Dame", "Sir"],
    "low": ["Squire", "Page"]
  }
}
```

---

## Implementation Details

### 1. Name Generator Module

**File:** `novel_agent/tools/name_generator.py`

```python
import random
import json
from pathlib import Path
from typing import Dict, List, Optional
from .base import Tool

class NameGenerator:
    """Generate unique character names using syllable combinations."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.scifi_data = self._load_json("scifi_syllables.json")
        self.fantasy_data = self._load_json("fantasy_syllables.json")
        self.modern_data = self._load_json("modern_names.json")
        self.titles_data = self._load_json("titles.json")
        self.used_names = set()  # Track used names for uniqueness
    
    def _load_json(self, filename: str) -> dict:
        """Load name data from JSON file."""
        file_path = self.data_dir / filename
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def generate_name(
        self,
        gender: str = "",
        genre: str = "scifi",
        title: Optional[str] = None,
        max_attempts: int = 50
    ) -> Dict[str, str]:
        """Generate a unique character name.
        
        Args:
            gender: "male", "female"
            genre: "scifi", "fantasy", "modern", or "historical"
            title: Optional title (e.g., "Dr.", "Captain")
            max_attempts: Maximum attempts to generate unique name
        
        Returns:
            Dictionary with full_name, first_name, last_name, title
        """
        for _ in range(max_attempts):
            if genre == "modern":
                first_name = self._generate_modern_name(gender, "first_name")
                last_name = self._generate_modern_name(gender, "last_name")
            else:
                # Syllable-based generation for scifi/fantasy
                data = self.scifi_data if genre == "scifi" else self.fantasy_data
                first_name = self._generate_syllable_name(data["first_name"], gender)
                last_name = self._generate_syllable_name(data["last_name"], gender)
            
            full_name = f"{first_name} {last_name}"
            
            # Check uniqueness
            if full_name not in self.used_names:
                self.used_names.add(full_name)
                
                if title:
                    full_name_with_title = f"{title} {full_name}"
                else:
                    full_name_with_title = full_name
                
                return {
                    "full_name": full_name_with_title,
                    "first_name": first_name,
                    "last_name": last_name,
                    "title": title or ""
                }
        
        # Fallback if all attempts failed (very unlikely)
        raise ValueError(f"Could not generate unique name after {max_attempts} attempts")
    
    def _generate_syllable_name(self, syllable_data: dict, gender: str) -> str:
        """Generate name from syllables."""
        gender_data = syllable_data.get(gender, syllable_data.get("male"))
        
        start = random.choice(gender_data["start"])
        end = random.choice(gender_data["end"])
        
        # Check phonetic compatibility
        if self._is_compatible(start, end):
            return start + end
        else:
            # Try again with different combination
            return self._generate_syllable_name(syllable_data, gender)
    
    def _generate_modern_name(self, gender: str, name_type: str) -> str:
        """Generate modern name from list."""
        names = self.modern_data[name_type].get(gender, self.modern_data[name_type]["male"])
        return random.choice(names)
    
    def _is_compatible(self, syllable1: str, syllable2: str) -> bool:
        """Check if syllables flow well together."""
        if not syllable1 or not syllable2:
            return True
        
        vowels = set('aeiou')
        end_char = syllable1[-1].lower()
        start_char = syllable2[0].lower()
        
        # Avoid double vowels (except specific combinations)
        if end_char in vowels and start_char in vowels:
            good_combos = ['ae', 'ai', 'ao', 'ea', 'ei', 'eo', 'ia', 'ie', 'io']
            if end_char + start_char in good_combos:
                return True
            return False
        
        return True


class NameGeneratorTool(Tool):
    """Tool for generating unique character names."""
    
    def __init__(self, data_dir: Path):
        super().__init__(
            name="name.generate",
            description="Generate a unique character name using phonetic syllables",
            parameters={
                "gender": {
                    "type": "string",
                    "enum": ["male", "female"],
                    "description": "Character gender for name generation"
                },
                "genre": {
                    "type": "string",
                    "enum": ["scifi", "fantasy", "modern"],
                    "description": "Genre style for name generation (default: scifi)",
                    "optional": True
                },
                "title": {
                    "type": "string",
                    "description": "Optional title (Dr., Captain, Lord, etc.)",
                    "optional": True
                }
            }
        )
        self.generator = NameGenerator(data_dir)
    
    def execute(
        self,
        gender: str,
        genre: str = "scifi",
        title: Optional[str] = None
    ) -> Dict[str, any]:
        """Execute name generation.
        
        Args:
            gender: Character gender
            genre: Name genre/style
            title: Optional title
        
        Returns:
            Success status and generated name
        """
        try:
            result = self.generator.generate_name(gender, genre, title)
            return {
                "success": True,
                **result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
```

---

## Updated Planner Prompt

**File:** `novel_agent/agent/prompts.py`

Update guidelines to encourage name generation tool:

```python
## Guidelines

- Keep actions focused (2-4 tools maximum per plan)
- Use memory.search to recall relevant context
- **Use name.generate to create unique character names** (recommended)
- Use character.generate to create characters with generated names
- Use relationship.create when characters first interact significantly
- Use relationship.update to track relationship changes
- Scene intention should be specific and actionable
```

---

## Planner Workflow Example

### Old Way (AI chooses name):
```json
{
  "actions": [
    {
      "tool": "character.generate",
      "args": {
        "name": "Dr. Mara Kess",
        "role": "protagonist",
        ...
      }
    }
  ]
}
```

### New Way (Tool generates name):
```json
{
  "actions": [
    {
      "tool": "name.generate",
      "args": {
        "gender": "female",
        "genre": "scifi",
        "title": "Dr."
      },
      "reason": "Generate unique name for protagonist"
    },
    {
      "tool": "character.generate",
      "args": {
        "name": "{{name_from_previous_tool}}",
        "role": "protagonist",
        ...
      },
      "reason": "Create protagonist with generated name"
    }
  ]
}
```

**Note:** The planner would need to reference the result from the first tool. We may need to enhance the executor to support tool result chaining.

---

## Alternative: Simpler Integration

If tool chaining is complex, we can integrate name generation directly into `character.generate`:

```python
class CharacterGenerateTool(Tool):
    def execute(self, name: str = None, role: str, ...):
        # If no name provided, generate one
        if not name:
            # Infer gender from role
            gender = self._infer_gender(role)
            name_result = self.name_generator.generate_name(gender, "scifi")
            name = name_result["full_name"]
        
        # Continue with character creation...
```

**Planner just calls:**
```json
{
  "tool": "character.generate",
  "args": {
    "role": "protagonist",
    "description": "A brilliant scientist",
    // No name - will be auto-generated
  }
}
```

---

## Data Files to Create

### Priority 1 (Essential):
1. `scifi_syllables.json` - 100+ syllables per category
2. `titles.json` - Common titles

### Priority 2 (Nice to have):
3. `fantasy_syllables.json` - Fantasy names
4. `modern_names.json` - Contemporary names

### Priority 3 (Future):
5. `historical_names.json` - Period-specific names
6. `cultural_names.json` - Culture-specific patterns

---

## Benefits

✅ **Uniqueness** - 864,000+ possible combinations  
✅ **No repetition** - Tracks used names  
✅ **Phonetically pleasing** - Compatibility rules  
✅ **Genre-appropriate** - Sci-fi vs fantasy vs modern  
✅ **Controllable** - Not dependent on LLM whims  
✅ **Fast** - Local generation, no API calls  
✅ **Extensible** - Easy to add new syllables/patterns  

---

## Implementation Steps

### Phase 1: Core Name Generator (Week 1)
1. Create `novel_agent/data/names/` directory
2. Create `scifi_syllables.json` with 100+ syllables
3. Create `titles.json` with common titles
4. Implement `NameGenerator` class
5. Implement `NameGeneratorTool`
6. Register tool in tool registry
7. Test name generation standalone

### Phase 2: Integration (Week 1)
8. Update planner prompt to mention name.generate tool
9. Test with agent - verify tool is called
10. Verify names appear in character.generate
11. Test uniqueness tracking

### Phase 3: Enhancement (Week 2)
12. Add fantasy syllables
13. Add modern names
14. Add phonetic compatibility rules
15. Add name validation (no offensive combinations)
16. Add configuration options

### Phase 4: Polish (Week 2)
17. Comprehensive testing with 50+ characters
18. Verify no name repetition
19. Tune syllable lists for better names
20. Documentation and examples

---

## Testing Strategy

### Test 1: Uniqueness
- Generate 100 names
- Verify no duplicates
- Measure: 100% unique

### Test 2: Phonetic Quality
- Generate 50 names
- Manual review for pronounceability
- Measure: 90%+ sound natural

### Test 3: Integration
- Generate 10 stories with 3+ characters each
- Verify no "Mara" repetition
- Verify names are genre-appropriate

### Test 4: Performance
- Generate 1000 names
- Measure: <1ms per name
- Verify no memory leaks

---

## Configuration Options

```yaml
name_generation:
  enabled: true  # Enable/disable name generator tool
  default_genre: "scifi"  # Default genre if not specified
  track_uniqueness: true  # Prevent duplicate names
  min_name_length: 4  # Minimum characters
  max_name_length: 12  # Maximum characters
  allow_ai_names: false  # Fallback to AI if tool fails
```

---

## Success Metrics

✅ **No name repetition** across 20+ stories  
✅ **Phonetically pleasing** names (subjective review)  
✅ **Fast generation** (<1ms per name)  
✅ **High variety** (no common patterns)  
✅ **Genre-appropriate** (sci-fi names sound sci-fi)  

---

## Conclusion

Implementing a local name generator tool solves the "Mara problem" and gives us:
- Full control over name generation
- Guaranteed uniqueness
- Genre-appropriate names
- No dependency on LLM creativity
- Fast, deterministic results

This approach mirrors NovelWriter's successful system while integrating cleanly with StoryDaemon's agentic architecture.

**Recommendation:** Start with Phase 1 (core generator) and test thoroughly before expanding to other genres.
