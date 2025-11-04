# Phase 2 — Memory and Data Structures (Detailed Design)

**Goal:** Add persistent structured memory for entities and scenes with semantic search capabilities.

---

## 1. Overview

Phase 2 establishes the memory layer that allows the agent to:
- Store and retrieve structured entity data (characters, locations, scenes, open loops)
- Perform semantic search across stored memories
- Maintain consistent entity IDs and relationships
- Track entity evolution over time

**Key Principle:** All entity data is stored as JSON files with a vector index for semantic retrieval.

---

## 2. Entity Schemas

### 2.1 Character Schema

**File location:** `~/novels/<novel-name>/memory/characters/<id>.json`

```json
{
  "id": "C0",
  "type": "character",
  "created_at": "2024-11-04T18:50:00Z",
  "updated_at": "2024-11-04T18:50:00Z",
  "name": "Elena Thorne",
  "aliases": ["The Cartographer", "Elle"],
  "role": "protagonist",
  "description": "A 32-year-old mapmaker with an obsessive attention to detail",
  "physical_traits": {
    "age": 32,
    "appearance": "Tall, angular features, ink-stained fingers",
    "distinctive_features": ["Scar above left eyebrow", "Always wears leather satchel"]
  },
  "personality": {
    "core_traits": ["meticulous", "curious", "guarded"],
    "fears": ["losing control", "being forgotten"],
    "desires": ["discover the truth about her father's disappearance"],
    "flaws": ["perfectionism", "difficulty trusting others"]
  },
  "relationships": [
    {
      "character_id": "C1",
      "relationship_type": "mentor",
      "status": "strained",
      "description": "Former teacher who now seems to be hiding something"
    }
  ],
  "current_state": {
    "location_id": "L0",
    "emotional_state": "anxious",
    "physical_state": "exhausted",
    "inventory": ["map fragment", "compass", "journal"],
    "goals": ["Decode the map fragment", "Confront her mentor"]
  },
  "backstory": "Raised in the Cartographers' Guild after her father vanished...",
  "history": [
    {
      "tick": 1,
      "scene_id": "S001",
      "changes": {"emotional_state": "anxious", "inventory": ["map fragment"]},
      "summary": "Discovered mysterious map fragment in father's old desk"
    }
  ],
  "metadata": {
    "pov_count": 3,
    "last_appeared": "S003",
    "importance": "primary"
  }
}
```

**Python Dataclass:**

```python
@dataclass
class PhysicalTraits:
    age: Optional[int] = None
    appearance: str = ""
    distinctive_features: List[str] = field(default_factory=list)

@dataclass
class Personality:
    core_traits: List[str] = field(default_factory=list)
    fears: List[str] = field(default_factory=list)
    desires: List[str] = field(default_factory=list)
    flaws: List[str] = field(default_factory=list)

@dataclass
class Relationship:
    character_id: str
    relationship_type: str  # mentor, friend, rival, enemy, family, etc.
    status: str  # close, strained, hostile, unknown, etc.
    description: str

@dataclass
class CurrentState:
    location_id: Optional[str] = None
    emotional_state: str = ""
    physical_state: str = ""
    inventory: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)

@dataclass
class HistoryEntry:
    tick: int
    scene_id: str
    changes: Dict[str, Any]
    summary: str

@dataclass
class Character:
    id: str
    type: str = "character"
    created_at: str = ""
    updated_at: str = ""
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    role: str = ""  # protagonist, antagonist, supporting, minor
    description: str = ""
    physical_traits: PhysicalTraits = field(default_factory=PhysicalTraits)
    personality: Personality = field(default_factory=Personality)
    relationships: List[Relationship] = field(default_factory=list)
    current_state: CurrentState = field(default_factory=CurrentState)
    backstory: str = ""
    history: List[HistoryEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

### 2.2 Location Schema

**File location:** `~/novels/<novel-name>/memory/locations/<id>.json`

```json
{
  "id": "L0",
  "type": "location",
  "created_at": "2024-11-04T18:50:00Z",
  "updated_at": "2024-11-04T18:50:00Z",
  "name": "The Archive of Lost Maps",
  "aliases": ["The Archive", "The Vault"],
  "description": "A vast underground library filled with ancient cartographic records",
  "atmosphere": "musty, dimly lit, oppressively silent",
  "sensory_details": {
    "visual": "Towering shelves disappearing into darkness, dust motes in lamplight",
    "auditory": "Distant dripping water, creaking floorboards",
    "olfactory": "Old paper, mildew, lamp oil",
    "tactile": "Cold stone floors, rough wooden shelves"
  },
  "features": [
    "Locked vault in the back room",
    "Spiral staircase leading down",
    "Reading desk with magnifying glass"
  ],
  "connections": [
    {
      "location_id": "L1",
      "connection_type": "adjacent",
      "description": "Hidden door behind the map cabinet leads to the tunnels"
    }
  ],
  "current_state": {
    "tension_level": 4,
    "time_of_day": "night",
    "weather": "n/a",
    "occupants": ["C0", "C1"],
    "notable_objects": ["map fragment", "ancient tome"]
  },
  "significance": "Where Elena's father worked before his disappearance",
  "history": [
    {
      "tick": 1,
      "scene_id": "S001",
      "changes": {"tension_level": 4, "notable_objects": ["map fragment"]},
      "summary": "Elena broke into the archive after hours"
    }
  ],
  "metadata": {
    "scene_count": 2,
    "last_used": "S003"
  }
}
```

**Python Dataclass:**

```python
@dataclass
class SensoryDetails:
    visual: str = ""
    auditory: str = ""
    olfactory: str = ""
    tactile: str = ""

@dataclass
class LocationConnection:
    location_id: str
    connection_type: str  # adjacent, distant, portal, hidden, etc.
    description: str

@dataclass
class LocationState:
    tension_level: int = 0  # 0-10 scale
    time_of_day: str = ""
    weather: str = ""
    occupants: List[str] = field(default_factory=list)  # Character IDs
    notable_objects: List[str] = field(default_factory=list)

@dataclass
class Location:
    id: str
    type: str = "location"
    created_at: str = ""
    updated_at: str = ""
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    atmosphere: str = ""
    sensory_details: SensoryDetails = field(default_factory=SensoryDetails)
    features: List[str] = field(default_factory=list)
    connections: List[LocationConnection] = field(default_factory=list)
    current_state: LocationState = field(default_factory=LocationState)
    significance: str = ""
    history: List[HistoryEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

### 2.3 Scene Schema

**File location:** `~/novels/<novel-name>/memory/scenes/<id>.json`

```json
{
  "id": "S001",
  "type": "scene",
  "created_at": "2024-11-04T18:50:00Z",
  "tick": 1,
  "title": "The Hidden Fragment",
  "pov_character_id": "C0",
  "location_id": "L0",
  "markdown_file": "scene_001.md",
  "word_count": 1247,
  "summary": [
    "Elena breaks into the Archive after hours to search her father's old desk",
    "She discovers a mysterious map fragment hidden in a false bottom",
    "Her mentor appears unexpectedly, creating tension"
  ],
  "characters_present": ["C0", "C1"],
  "key_events": [
    "Discovery of map fragment",
    "Confrontation with mentor"
  ],
  "emotional_beats": ["curiosity", "discovery", "fear", "suspicion"],
  "entities_created": ["C0", "C1", "L0"],
  "entities_updated": ["C0"],
  "open_loops_created": ["OL0", "OL1"],
  "open_loops_resolved": [],
  "metadata": {
    "plan_id": "P001",
    "revision_count": 0,
    "evaluation_passed": true
  }
}
```

**Python Dataclass:**

```python
@dataclass
class Scene:
    id: str
    type: str = "scene"
    created_at: str = ""
    tick: int = 0
    title: str = ""
    pov_character_id: str = ""
    location_id: str = ""
    markdown_file: str = ""
    word_count: int = 0
    summary: List[str] = field(default_factory=list)
    characters_present: List[str] = field(default_factory=list)
    key_events: List[str] = field(default_factory=list)
    emotional_beats: List[str] = field(default_factory=list)
    entities_created: List[str] = field(default_factory=list)
    entities_updated: List[str] = field(default_factory=list)
    open_loops_created: List[str] = field(default_factory=list)
    open_loops_resolved: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

### 2.4 OpenLoop Schema

**File location:** `~/novels/<novel-name>/memory/open_loops.json`

```json
{
  "loops": [
    {
      "id": "OL0",
      "type": "open_loop",
      "created_at": "2024-11-04T18:50:00Z",
      "created_in_scene": "S001",
      "status": "open",
      "category": "mystery",
      "description": "What does the map fragment lead to?",
      "importance": "high",
      "related_characters": ["C0"],
      "related_locations": ["L0"],
      "notes": "Fragment appears to be part of a larger map",
      "resolved_in_scene": null,
      "resolution_summary": null
    },
    {
      "id": "OL1",
      "type": "open_loop",
      "created_at": "2024-11-04T18:50:00Z",
      "created_in_scene": "S001",
      "status": "open",
      "category": "relationship",
      "description": "Why is Elena's mentor acting suspicious?",
      "importance": "medium",
      "related_characters": ["C0", "C1"],
      "related_locations": ["L0"],
      "notes": "Mentor seemed nervous when Elena found the fragment",
      "resolved_in_scene": null,
      "resolution_summary": null
    }
  ]
}
```

**Python Dataclass:**

```python
@dataclass
class OpenLoop:
    id: str
    type: str = "open_loop"
    created_at: str = ""
    created_in_scene: str = ""
    status: str = "open"  # open, resolved, abandoned
    category: str = ""  # mystery, relationship, goal, threat, etc.
    description: str = ""
    importance: str = "medium"  # low, medium, high, critical
    related_characters: List[str] = field(default_factory=list)
    related_locations: List[str] = field(default_factory=list)
    notes: str = ""
    resolved_in_scene: Optional[str] = None
    resolution_summary: Optional[str] = None
```

---

### 2.5 Relationship Graph Schema

**File location:** `~/novels/<novel-name>/memory/relationships.json`

```json
{
  "relationships": [
    {
      "id": "R0",
      "type": "relationship",
      "created_at": "2024-11-04T18:50:00Z",
      "updated_at": "2024-11-04T18:50:00Z",
      "character_a": "C0",
      "character_b": "C1",
      "relationship_type": "mentor-student",
      "status": "strained",
      "perspective_a": "Former teacher who now seems to be hiding something",
      "perspective_b": "Brilliant but reckless student who asks too many questions",
      "intensity": 7,
      "history": [
        {
          "tick": 1,
          "scene_id": "S001",
          "event": "Tense confrontation in the archive",
          "status_change": "close -> strained"
        }
      ],
      "metadata": {
        "last_interaction": "S001",
        "interaction_count": 3
      }
    }
  ]
}
```

**Python Dataclass:**

```python
@dataclass
class RelationshipHistoryEntry:
    tick: int
    scene_id: str
    event: str
    status_change: Optional[str] = None

@dataclass
class Relationship:
    id: str
    type: str = "relationship"
    created_at: str = ""
    updated_at: str = ""
    character_a: str = ""
    character_b: str = ""
    relationship_type: str = ""  # mentor-student, friends, rivals, enemies, family, romantic, etc.
    status: str = "neutral"  # close, strained, hostile, unknown, complicated, etc.
    perspective_a: str = ""  # How character_a views character_b
    perspective_b: str = ""  # How character_b views character_a
    intensity: int = 5  # 0-10 scale, how important this relationship is
    history: List[RelationshipHistoryEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**Benefits:**

1. **Bidirectional Consistency:** Both characters' perspectives stored in one place
2. **Relationship Evolution:** Track how relationships change over time
3. **Query Support:** Easy to find all relationships for a character or between characters
4. **Conflict Detection:** Validate relationship consistency across scenes
5. **Prompt Context:** Include relevant relationship dynamics in writer prompts

**Usage in Prompts:**

```
POV: Elena (C0)
Active Relationships:
- Marcus (C1): mentor-student → strained (intensity: 7)
  Your view: "Former teacher who now seems to be hiding something"
  Recent: Tense confrontation in the archive (S001)
```

---

## 3. Memory Manager Implementation

### 3.1 Core Memory Manager Class

**File:** `novel_agent/memory/manager.py`

```python
class MemoryManager:
    """Manages persistent storage and retrieval of entities."""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.memory_path = project_path / "memory"
        self.characters_path = self.memory_path / "characters"
        self.locations_path = self.memory_path / "locations"
        self.scenes_path = self.memory_path / "scenes"
        self.open_loops_file = self.memory_path / "open_loops.json"
        self.relationships_file = self.memory_path / "relationships.json"
        
        # ID counters
        self.counters_file = self.memory_path / "counters.json"
        self._ensure_directories()
        self._load_counters()
    
    # CRUD Operations
    def load_entity(self, entity_id: str) -> Optional[Union[Character, Location, Scene]]:
        """Load an entity by ID."""
        
    def save_entity(self, entity: Union[Character, Location, Scene]) -> None:
        """Save an entity to disk."""
        
    def update_entity(self, entity_id: str, changes: Dict[str, Any]) -> None:
        """Update specific fields of an entity."""
        
    def delete_entity(self, entity_id: str) -> None:
        """Delete an entity (rarely used)."""
        
    def list_entities(self, entity_type: str) -> List[str]:
        """List all entity IDs of a given type."""
        
    # ID Management
    def generate_id(self, entity_type: str) -> str:
        """Generate next ID for entity type (C0, L0, S001, OL0)."""
        
    # Open Loops
    def load_open_loops(self) -> List[OpenLoop]:
        """Load all open loops."""
        
    def save_open_loops(self, loops: List[OpenLoop]) -> None:
        """Save open loops to disk."""
        
    def add_open_loop(self, loop: OpenLoop) -> None:
        """Add a new open loop."""
        
    def resolve_open_loop(self, loop_id: str, scene_id: str, summary: str) -> None:
        """Mark an open loop as resolved."""
    
    # Relationships
    def load_relationships(self) -> List[Relationship]:
        """Load all relationships."""
        
    def save_relationships(self, relationships: List[Relationship]) -> None:
        """Save relationships to disk."""
        
    def add_relationship(self, relationship: Relationship) -> None:
        """Add a new relationship."""
        
    def update_relationship(self, relationship_id: str, changes: Dict[str, Any]) -> None:
        """Update a relationship."""
        
    def get_character_relationships(self, character_id: str) -> List[Relationship]:
        """Get all relationships involving a character."""
        
    def get_relationship_between(self, char_a: str, char_b: str) -> Optional[Relationship]:
        """Get relationship between two characters (order-independent)."""
```

### 3.2 ID Assignment Logic

- **Characters:** `C0`, `C1`, `C2`, ...
- **Locations:** `L0`, `L1`, `L2`, ...
- **Scenes:** `S001`, `S002`, `S003`, ... (zero-padded to 3 digits)
- **Open Loops:** `OL0`, `OL1`, `OL2`, ...
- **Relationships:** `R0`, `R1`, `R2`, ...

**Counter storage:** `~/novels/<novel-name>/memory/counters.json`

```json
{
  "character": 2,
  "location": 1,
  "scene": 3,
  "open_loop": 2,
  "relationship": 1
}
```

---

## 4. Vector Store Integration

### 4.1 Vector Store Setup

**Library:** ChromaDB (lightweight, embeddable, no server required)

**Storage location:** `~/novels/<novel-name>/memory/index/`

**Collections:**
- `characters` — indexed character data
- `locations` — indexed location data
- `scenes` — indexed scene summaries

### 4.2 Indexing Strategy

**What to index:**

1. **Characters:**
   - Name, aliases, description
   - Personality traits, fears, desires
   - Backstory
   - Current goals

2. **Locations:**
   - Name, aliases, description
   - Atmosphere, sensory details
   - Significance

3. **Scenes:**
   - Summary bullets
   - Key events
   - Emotional beats

**Metadata stored with vectors:**
- Entity ID
- Entity type
- Last updated timestamp
- Importance/relevance score

### 4.3 Vector Store Manager

**File:** `novel_agent/memory/vector_store.py`

```python
class VectorStore:
    """Manages semantic search using ChromaDB."""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.index_path = project_path / "memory" / "index"
        self.client = chromadb.PersistentClient(path=str(self.index_path))
        
        # Initialize collections
        self.characters_collection = self.client.get_or_create_collection("characters")
        self.locations_collection = self.client.get_or_create_collection("locations")
        self.scenes_collection = self.client.get_or_create_collection("scenes")
    
    def index_character(self, character: Character) -> None:
        """Add or update character in vector index."""
        
    def index_location(self, location: Location) -> None:
        """Add or update location in vector index."""
        
    def index_scene(self, scene: Scene) -> None:
        """Add or update scene in vector index."""
        
    def search(self, query: str, collection: str = "all", limit: int = 5) -> List[Dict]:
        """Semantic search across collections."""
        
    def search_characters(self, query: str, limit: int = 5) -> List[Character]:
        """Search for relevant characters."""
        
    def search_locations(self, query: str, limit: int = 5) -> List[Location]:
        """Search for relevant locations."""
        
    def search_scenes(self, query: str, limit: int = 5) -> List[Scene]:
        """Search for relevant scenes."""
```

---

## 5. Memory Tools

### 5.1 Tool: `memory.search`

**Purpose:** Semantic search across all stored entities.

**Arguments:**
- `query` (str): Natural language search query
- `entity_types` (List[str], optional): Filter by entity types (character, location, scene)
- `limit` (int, default=5): Max results to return

**Returns:**
```json
{
  "results": [
    {
      "entity_id": "C0",
      "entity_type": "character",
      "name": "Elena Thorne",
      "relevance_score": 0.89,
      "snippet": "A 32-year-old mapmaker with an obsessive attention to detail..."
    }
  ]
}
```

**Implementation:** `novel_agent/tools/memory_tools.py`

---

### 5.2 Tool: `memory.upsert`

**Purpose:** Insert or update a memory entry (used internally, not exposed to LLM planner).

**Arguments:**
- `entity_id` (str): Entity to update
- `changes` (Dict): Fields to update

**Returns:**
```json
{
  "success": true,
  "entity_id": "C0",
  "updated_fields": ["emotional_state", "inventory"]
}
```

---

### 5.3 Tool: `character.generate`

**Purpose:** Create a new character with initial attributes.

**Arguments:**
- `name` (str): Character name
- `role` (str): protagonist, antagonist, supporting, minor
- `description` (str): Brief character description
- `traits` (List[str], optional): Core personality traits
- `goals` (List[str], optional): Initial goals

**Returns:**
```json
{
  "success": true,
  "character_id": "C2",
  "name": "Marcus Vale"
}
```

**Implementation:**
1. Generate new character ID
2. Create Character dataclass with provided data
3. Save to `memory/characters/<id>.json`
4. Index in vector store
5. Return character ID

---

### 5.4 Tool: `location.generate`

**Purpose:** Create a new location with initial attributes.

**Arguments:**
- `name` (str): Location name
- `description` (str): Brief location description
- `atmosphere` (str, optional): Mood/feeling of the location
- `features` (List[str], optional): Notable features

**Returns:**
```json
{
  "success": true,
  "location_id": "L3",
  "name": "The Forgotten Lighthouse"
}
```

**Implementation:**
1. Generate new location ID
2. Create Location dataclass with provided data
3. Save to `memory/locations/<id>.json`
4. Index in vector store
5. Return location ID

---

### 5.5 Tool: `relationship.create`

**Purpose:** Create a new relationship between two characters.

**Arguments:**
- `character_a` (str): First character ID
- `character_b` (str): Second character ID
- `relationship_type` (str): Type of relationship (mentor-student, friends, rivals, etc.)
- `perspective_a` (str): How character_a views character_b
- `perspective_b` (str): How character_b views character_a
- `status` (str, optional): Relationship status (default: "neutral")
- `intensity` (int, optional): Importance 0-10 (default: 5)

**Returns:**
```json
{
  "success": true,
  "relationship_id": "R0"
}
```

**Implementation:**
1. Generate new relationship ID
2. Create Relationship dataclass with provided data
3. Save to `memory/relationships.json`
4. Return relationship ID

---

### 5.6 Tool: `relationship.update`

**Purpose:** Update an existing relationship (status change, new interaction, etc.).

**Arguments:**
- `character_a` (str): First character ID
- `character_b` (str): Second character ID
- `status` (str, optional): New status
- `event` (str, optional): Description of what happened
- `scene_id` (str, optional): Scene where this occurred
- `intensity` (int, optional): New intensity level

**Returns:**
```json
{
  "success": true,
  "relationship_id": "R0",
  "updated": true
}
```

**Implementation:**
1. Find relationship between characters (order-independent)
2. Update specified fields
3. Add history entry if event provided
4. Save to `memory/relationships.json`

---

### 5.7 Tool: `relationship.query`

**Purpose:** Query relationships for a character (used by planner to understand social dynamics).

**Arguments:**
- `character_id` (str): Character to query relationships for
- `status_filter` (str, optional): Filter by status (e.g., "strained", "hostile")

**Returns:**
```json
{
  "relationships": [
    {
      "character_id": "C1",
      "character_name": "Marcus Vale",
      "relationship_type": "mentor-student",
      "status": "strained",
      "your_view": "Former teacher who now seems to be hiding something",
      "intensity": 7
    }
  ]
}
```

**Implementation:**
1. Load all relationships
2. Filter for those involving character_id
3. Format from character's perspective
4. Return list

---

## 6. Summarization Helper

### 6.1 Scene Summarization

**Purpose:** Generate 3-5 bullet point summary of a scene after it's written.

**Function:** `summarize_scene(scene_text: str) -> List[str]`

**Implementation:**
1. Call LLM with specialized prompt:
   ```
   Read the following scene and generate 3-5 concise bullet points summarizing:
   - Key events that occurred
   - Important character actions or decisions
   - New information revealed
   
   Scene:
   {scene_text}
   
   Return only the bullet points, one per line.
   ```

2. Parse response into list of strings
3. Store in Scene entity's `summary` field

**File:** `novel_agent/memory/summarizer.py`

---

## 7. File Structure

```
~/novels/<novel-name>/
  memory/
    characters/
      C0.json
      C1.json
      ...
    locations/
      L0.json
      L1.json
      ...
    scenes/
      S001.json
      S002.json
      ...
    open_loops.json
    relationships.json
    counters.json
    index/              # ChromaDB files
      chroma.sqlite3
      ...
```

---

## 8. Implementation Order

1. **Entity dataclasses** (`novel_agent/memory/entities.py`)
   - Define all dataclasses with proper type hints (Character, Location, Scene, OpenLoop, Relationship)
   - Add `to_dict()` and `from_dict()` methods
   - Add validation logic

2. **Memory Manager** (`novel_agent/memory/manager.py`)
   - Implement CRUD operations for entities
   - Implement ID generation
   - Add open loops management
   - Add relationship management (load, save, query)

3. **Vector Store** (`novel_agent/memory/vector_store.py`)
   - Set up ChromaDB integration
   - Implement indexing methods
   - Implement search methods

4. **Memory Tools** (`novel_agent/tools/memory_tools.py`)
   - Implement `memory.search` tool
   - Implement `character.generate` tool
   - Implement `location.generate` tool
   - Implement `relationship.create` tool
   - Implement `relationship.update` tool
   - Implement `relationship.query` tool
   - Register tools with tool registry

5. **Summarization** (`novel_agent/memory/summarizer.py`)
   - Implement scene summarization function
   - Integrate with LLM interface

6. **Integration**
   - Update `novel new` command to initialize memory directories
   - Add memory manager to agent runtime
   - Test end-to-end flow

---

## 9. Testing Strategy

### Unit Tests

- **Entity serialization:** Test `to_dict()` and `from_dict()` for all entities
- **ID generation:** Verify correct format and incrementing
- **CRUD operations:** Test save, load, update, delete
- **Vector indexing:** Test indexing and search accuracy
- **Relationship queries:** Test bidirectional lookup and filtering

### Integration Tests

- **Full workflow:** Create character → save → index → search → retrieve
- **Open loops:** Create → list → resolve
- **Relationships:** Create → update → query → retrieve
- **Scene summarization:** Generate summary from sample text

### Test Files

```
tests/
  test_entities.py
  test_memory_manager.py
  test_vector_store.py
  test_memory_tools.py
  test_relationship_tools.py
  test_summarizer.py
```

---

## 10. Dependencies

Add to `requirements.txt`:

```
chromadb>=0.4.0
pydantic>=2.0.0  # For data validation (optional, can use dataclasses)
```

---

## 11. Configuration

Add to `config.yaml`:

```yaml
memory:
  vector_store:
    provider: "chromadb"
    embedding_model: "default"  # ChromaDB default embedding
  summarization:
    max_bullets: 5
    model: "gpt-5"
```

---

## 12. Open Questions / Design Decisions

1. **Entity versioning:** Should we keep full history snapshots or just change deltas?
   - **Recommendation:** Change deltas (current approach) for efficiency

2. **Vector embedding model:** Use ChromaDB default or custom embeddings?
   - **Recommendation:** Start with default, can upgrade later

3. **Search relevance threshold:** What minimum score should we use?
   - **Recommendation:** 0.5 for initial implementation, tune based on results

4. **Entity relationships:** Should relationships be bidirectional?
   - **Decision:** Yes, using separate relationship graph (implemented in Phase 2)

5. **Memory pruning:** Should old/irrelevant memories be archived?
   - **Recommendation:** Not in Phase 2, defer to Phase 7

---

## 13. Success Criteria

Phase 2 is complete when:

- ✅ All entity dataclasses defined and tested (Character, Location, Scene, OpenLoop, Relationship)
- ✅ Memory manager can save/load/update all entity types
- ✅ Relationship graph management works (create, update, query)
- ✅ Vector store indexes and searches entities correctly
- ✅ `character.generate` and `location.generate` tools work
- ✅ `relationship.create`, `relationship.update`, and `relationship.query` tools work
- ✅ `memory.search` returns relevant results
- ✅ Scene summarization generates quality bullet points
- ✅ `novel new` command initializes memory structure (including relationships.json)
- ✅ Integration tests pass for full memory workflow

---

## 14. Next Steps (Phase 3 Preview)

Once Phase 2 is complete, Phase 3 will:
- Use memory tools in planner prompts
- Execute tool calls to create/update entities
- Build the agent execution loop
- Store plans in `/plans/` directory
