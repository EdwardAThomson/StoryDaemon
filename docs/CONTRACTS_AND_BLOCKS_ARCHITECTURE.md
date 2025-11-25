# Contracts and Blocks Architecture

**Status:** Design Proposal  
**Date:** 2025-11-25  
**Supersedes:** Initial DSL_and_contracts.md ideas

## Overview

This document formalizes the architecture for structured narrative generation using **contracts** (validation/requirements) and **blocks** (composition/structure). The key insight is that these are orthogonal concerns:

- **Contracts** define what must be true (validation hierarchy)
- **Blocks** define how the story is organized (composition hierarchy)

## Core Principles

### 1. Separation of Concerns

**Contracts answer:** "Did we accomplish what we needed to?"
- Preconditions: What must be true before execution
- Postconditions: What must be true after execution
- Resource requirements: What entities/state are needed

**Blocks answer:** "How do we tell this story?"
- Narrative structure: Opening → Action → Climax → Closing
- Content organization: Setting, dialogue, action, internal thoughts
- Composition: How sub-blocks combine into blocks, blocks into scenes

### 2. Linear Composition

> "Books proceed page-by-page. So the mechanical flow is linear, even if the prose is non-linear."

The execution model is fundamentally linear:
- No recursive blocks within blocks
- New sub-blocks can be appended to resolve situations
- Contracts proceed block-by-block in linear fashion
- State updates flow forward through the sequence

### 3. Strict Entity Management

All entities (characters, locations, items) must:
- Come from generators (no ad-hoc LLM creation)
- Be deduplicated (no duplicate names/IDs)
- Be tracked in inventory systems
- Satisfy consistency constraints

## Architecture

### Hierarchical Structure

```
┌─────────────────────────────────────────┐
│         Story Contract                  │  ← Global constraints
│  (No duplicates, consistency, etc.)     │
└─────────────────────────────────────────┘
                    │
                    ├─────────────────────────────┐
                    ▼                             ▼
        ┌───────────────────────┐    ┌───────────────────────┐
        │   Beat Contract 1     │    │   Beat Contract 2     │  ← Scene requirements
        │   (Pre/Postconditions)│    │   (Pre/Postconditions)│
        └───────────────────────┘    └───────────────────────┘
                    │                             │
        ┌───────────┼───────────┐                │
        ▼           ▼           ▼                ▼
    [Block A]   [Block B]   [Block C]       [Block D]          ← Narrative structure
        │           │           │                │
    [SubBlock]  [SubBlock]  [SubBlock]      [SubBlock]         ← Atomic units
```

**Two Orthogonal Dimensions:**
- **Vertical (Contracts):** Requirements flow down (story → beat → sub-beat)
- **Horizontal (Blocks):** Narrative flows forward (scene → block → sub-block)

### Book Structure

```python
Book = Sequence[Chapter]
Chapter = Sequence[Scene]
Scene = Sequence[Block | Transition]
Block = Sequence[SubBlock]
```

The book is composed of blocks, but **governed** by contracts.

## Contract System

### Story Contract

Top-level contract defining global constraints for the entire story.

```python
@dataclass
class StoryContract:
    """Global story-level contract."""
    foundation: StoryFoundation
    global_constraints: List[Constraint]
    beat_contracts: List[BeatContract]
    
    # Global constraints examples:
    # - NoCharacterDuplication()
    # - NoLocationDuplication()
    # - InventoryConsistency()
    # - TensionPacing(min=4, max=9)
    # - CharacterArcProgression()
```

### Beat Contract

Scene-level contract defining requirements for executing a plot beat.

```python
@dataclass
class BeatContract:
    """Contract for a single plot beat (typically one scene)."""
    beat_id: str
    description: str
    
    # Requirements
    required_characters: List[str]  # Character IDs that MUST appear
    required_location: str  # Location ID
    required_items: Dict[str, List[str]]  # char_id -> [item_ids] in inventory
    
    # Preconditions (must be true BEFORE execution)
    preconditions: List[Callable[[StoryState], bool]]
    
    # Postconditions (must be true AFTER execution)
    postconditions: List[Callable[[str, StoryState], bool]]
    
    # Story effects
    resolves_loops: List[str]  # Loop IDs this beat resolves
    creates_loops: List[str]  # New loops this beat creates
    tension_target: Optional[int]  # Target tension level (1-10)
    
    def validate_preconditions(self, state: StoryState) -> ValidationResult:
        """Check if all preconditions are met before generation."""
        errors = []
        for check in self.preconditions:
            if not check(state):
                errors.append(f"Precondition failed: {check.__name__}")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def validate_postconditions(self, prose: str, state: StoryState) -> ValidationResult:
        """Check if all postconditions are met after generation."""
        errors = []
        for check in self.postconditions:
            if not check(prose, state):
                errors.append(f"Postcondition failed: {check.__name__}")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

### Example Beat Contract

```python
# Beat: "Sylura triggers a power surge in The Glitch Pit, causing a blackout"
beat_contract = BeatContract(
    beat_id="PB001",
    description="Sylura triggers power surge in Glitch Pit, causes blackout",
    required_characters=["C0"],  # Sylura
    required_location="L1",  # The Glitch Pit
    required_items={
        "C0": ["data_slate", "hacking_tools"]  # Sylura must have these
    },
    preconditions=[
        lambda state: state.get_character("C0").location == "L1",
        lambda state: state.get_location("L1").power_status == "on",
        lambda state: state.get_character("C0").has_technical_skill(),
    ],
    postconditions=[
        lambda prose, state: "power" in prose.lower() and "surge" in prose.lower(),
        lambda prose, state: state.get_location("L1").power_status == "off",
        lambda prose, state: state.chaos_level >= 7,
        lambda prose, state: "blackout" in prose.lower() or "darkness" in prose.lower(),
    ],
    resolves_loops=[],
    creates_loops=["OL_escape_glitch_pit"],
    tension_target=8,
)
```

## Block System

### Prose Block

A prose block is a structural unit of narrative, typically 200-500 words.

```python
@dataclass
class ProseBlock:
    """Structural unit of narrative."""
    block_id: str
    type: BlockType  # SETUP | ACTION | CLIMAX | RESOLUTION
    sub_blocks: List[SubBlock]
    
    # Metadata (not requirements)
    purpose: str  # Human-readable description
    estimated_word_count: int = 300
```

### Sub-Block

Atomic narrative unit with a specific function.

```python
class SubBlockType(Enum):
    """Types of narrative sub-blocks."""
    OPENING = "opening"              # Chapter/scene start
    SETTING = "setting"              # Location description
    CHARACTER_INTRO = "character_intro"  # Character appearance/description
    TECH_DESCRIPTION = "tech_description"  # Technology/worldbuilding
    DIALOGUE = "dialogue"            # Character conversation
    ACTION = "action"                # Physical actions
    INTERNAL = "internal"            # Thoughts/feelings/monologue
    TENSION_BUILD = "tension_build"  # Cliffhanger/suspense
    CLOSING = "closing"              # Chapter/scene end

@dataclass
class SubBlock:
    """Atomic narrative unit."""
    type: SubBlockType
    purpose: str  # What this sub-block accomplishes
    max_tokens: int = 300
    
    # Content hints (not requirements)
    focus_character: Optional[str] = None
    focus_location: Optional[str] = None
    mood: Optional[str] = None
```

### Transition

Special block type for scene/location changes.

```python
@dataclass
class Transition:
    """Transition between prose blocks or scenes."""
    from_location: Optional[str]
    to_location: Optional[str]
    time_skip: Optional[str]  # "minutes", "hours", "days", "weeks"
    
    # Generation flags
    describe_journey: bool = False
    generate_new_location: bool = False
    describe_new_location: bool = True
    
    def validate(self) -> ValidationResult:
        """Validate transition is well-formed."""
        if self.generate_new_location and self.to_location:
            return ValidationResult(
                is_valid=False,
                errors=["Cannot both generate new location and specify existing one"]
            )
        return ValidationResult(is_valid=True, errors=[])
```

## Execution Flow

### High-Level Flow

```python
def execute_tick(beat_contract: BeatContract, story_state: StoryState) -> Scene:
    """Execute a single tick (beat) with contract validation."""
    
    # 1. Validate preconditions BEFORE generation
    validation = beat_contract.validate_preconditions(story_state)
    if not validation.is_valid:
        raise ContractViolation(f"Preconditions not met: {validation.errors}")
    
    # 2. Plan blocks to fulfill contract
    blocks = BlockPlanner.plan_blocks_for_beat(beat_contract, story_state)
    
    # 3. Execute blocks (generate prose)
    prose_results = []
    for block in blocks:
        prose = ProseGenerator.generate(block, story_state)
        prose_results.append(prose)
        story_state.update_from_prose(prose)  # Incremental state update
    
    # 4. Validate postconditions AFTER generation
    final_prose = "\n\n".join(prose_results)
    validation = beat_contract.validate_postconditions(final_prose, story_state)
    if not validation.is_valid:
        # Retry with feedback
        return retry_with_feedback(beat_contract, story_state, validation.errors)
    
    # 5. Return completed scene
    return Scene(
        scene_id=generate_scene_id(),
        beat_id=beat_contract.beat_id,
        prose=final_prose,
        blocks=blocks
    )
```

### Block Planning

```python
class BlockPlanner:
    """Plans block structure to fulfill beat contracts."""
    
    @staticmethod
    def plan_blocks_for_beat(beat: BeatContract, state: StoryState) -> List[ProseBlock]:
        """Generate block structure for a beat.
        
        Typical structure:
        1. SETUP block - Establish scene, characters, situation
        2. ACTION block(s) - Execute the beat's main action
        3. CLIMAX block - Peak moment of the beat
        4. RESOLUTION block - Immediate aftermath
        """
        blocks = []
        
        # Setup block
        blocks.append(ProseBlock(
            block_id=f"{beat.beat_id}_setup",
            type=BlockType.SETUP,
            sub_blocks=[
                SubBlock(type=SubBlockType.SETTING, purpose="Establish location"),
                SubBlock(type=SubBlockType.INTERNAL, purpose="Character state/plan"),
            ]
        ))
        
        # Action block
        blocks.append(ProseBlock(
            block_id=f"{beat.beat_id}_action",
            type=BlockType.ACTION,
            sub_blocks=[
                SubBlock(type=SubBlockType.ACTION, purpose="Main beat action"),
                SubBlock(type=SubBlockType.TECH_DESCRIPTION, purpose="Technical details"),
            ]
        ))
        
        # Climax block
        blocks.append(ProseBlock(
            block_id=f"{beat.beat_id}_climax",
            type=BlockType.CLIMAX,
            sub_blocks=[
                SubBlock(type=SubBlockType.ACTION, purpose="Beat culmination"),
                SubBlock(type=SubBlockType.TENSION_BUILD, purpose="Aftermath/consequences"),
            ]
        ))
        
        return blocks
```

### Prose Generation

```python
class ProseGenerator:
    """Generates prose for blocks."""
    
    @staticmethod
    def generate(block: ProseBlock, state: StoryState) -> str:
        """Generate prose for a single block."""
        sub_block_prose = []
        
        for sub_block in block.sub_blocks:
            # Generate prose for this sub-block
            prose = ProseGenerator._generate_sub_block(sub_block, state)
            sub_block_prose.append(prose)
            
            # Update state incrementally
            state.update_from_prose(prose)
        
        return "\n\n".join(sub_block_prose)
    
    @staticmethod
    def _generate_sub_block(sub_block: SubBlock, state: StoryState) -> str:
        """Generate prose for a single sub-block."""
        # Build context for this specific sub-block type
        context = SubBlockContextBuilder.build(sub_block, state)
        
        # Generate with LLM
        prompt = format_sub_block_prompt(sub_block, context)
        prose = llm.generate(prompt, max_tokens=sub_block.max_tokens)
        
        return prose
```

## Entity Management

### Character Inventory System

```python
@dataclass
class Character:
    """Character entity with inventory tracking."""
    id: str
    first_name: str
    family_name: str
    role: str
    
    # Inventory system
    inventory: List[Item] = field(default_factory=list)
    
    def has_item(self, item_id: str) -> bool:
        """Check if character has an item."""
        return any(i.id == item_id for i in self.inventory)
    
    def add_item(self, item: Item):
        """Add item to inventory with deduplication."""
        if self.has_item(item.id):
            raise DuplicateItemError(f"Character already has {item.id}")
        self.inventory.append(item)
    
    def remove_item(self, item_id: str):
        """Remove item from inventory."""
        self.inventory = [i for i in self.inventory if i.id != item_id]
    
    def transfer_item(self, item_id: str, to_character: 'Character'):
        """Transfer item to another character."""
        if not self.has_item(item_id):
            raise ItemNotFoundError(f"Character doesn't have {item_id}")
        item = next(i for i in self.inventory if i.id == item_id)
        self.remove_item(item_id)
        to_character.add_item(item)

@dataclass
class Item:
    """Inventory item."""
    id: str
    name: str
    description: str
    item_type: str  # weapon, tool, data, consumable, etc.
    properties: Dict[str, Any] = field(default_factory=dict)
```

### Entity Registry

Centralized registry preventing duplicate entity creation.

```python
class EntityRegistry:
    """Centralized registry for all story entities."""
    
    def __init__(self):
        self.characters: Dict[str, Character] = {}
        self.locations: Dict[str, Location] = {}
        self.items: Dict[str, Item] = {}
        self.factions: Dict[str, Faction] = {}
    
    def create_character(self, name: str, **kwargs) -> Character:
        """Create character with duplicate detection."""
        # Check for duplicates by name (fuzzy match)
        existing = self._find_similar_character_name(name, threshold=0.85)
        if existing:
            raise DuplicateEntityError(
                f"Character similar to '{name}' already exists: {existing.id}"
            )
        
        char = Character(
            id=self._generate_id("character"),
            first_name=self._parse_first_name(name),
            family_name=self._parse_family_name(name),
            **kwargs
        )
        self.characters[char.id] = char
        return char
    
    def create_location(self, name: str, **kwargs) -> Location:
        """Create location with duplicate detection."""
        # Check for duplicates
        existing = self._find_similar_location_name(name, threshold=0.90)
        if existing:
            raise DuplicateEntityError(
                f"Location similar to '{name}' already exists: {existing.id}"
            )
        
        loc = Location(
            id=self._generate_id("location"),
            name=name,
            **kwargs
        )
        self.locations[loc.id] = loc
        return loc
    
    def create_item(self, name: str, **kwargs) -> Item:
        """Create item with duplicate detection."""
        # Check for duplicates
        existing = self._find_similar_item_name(name, threshold=0.90)
        if existing:
            raise DuplicateEntityError(
                f"Item similar to '{name}' already exists: {existing.id}"
            )
        
        item = Item(
            id=self._generate_id("item"),
            name=name,
            **kwargs
        )
        self.items[item.id] = item
        return item
    
    def _find_similar_character_name(self, name: str, threshold: float) -> Optional[Character]:
        """Find character with similar name using fuzzy matching."""
        from difflib import SequenceMatcher
        
        name_lower = name.lower()
        for char in self.characters.values():
            full_name = f"{char.first_name} {char.family_name}".lower()
            similarity = SequenceMatcher(None, name_lower, full_name).ratio()
            if similarity >= threshold:
                return char
        return None
    
    # Similar methods for locations and items...
```

## Constraint System

### Global Constraints

```python
class Constraint(ABC):
    """Base class for story constraints."""
    
    @abstractmethod
    def validate(self, state: StoryState) -> ValidationResult:
        """Check if constraint is satisfied."""
        pass

class NoCharacterDuplication(Constraint):
    """Ensure no duplicate characters exist."""
    
    def validate(self, state: StoryState) -> ValidationResult:
        characters = state.registry.characters.values()
        names = [f"{c.first_name} {c.family_name}".lower() for c in characters]
        
        duplicates = [name for name in names if names.count(name) > 1]
        if duplicates:
            return ValidationResult(
                is_valid=False,
                errors=[f"Duplicate character names: {set(duplicates)}"]
            )
        return ValidationResult(is_valid=True, errors=[])

class InventoryConsistency(Constraint):
    """Ensure items don't appear/disappear without explanation."""
    
    def validate(self, state: StoryState) -> ValidationResult:
        # Track all item movements in recent scenes
        # Ensure items are only created/destroyed explicitly
        # Check that characters have items they're using
        pass

class TensionPacing(Constraint):
    """Ensure tension follows appropriate pacing."""
    
    def __init__(self, min_tension: int = 4, max_tension: int = 9):
        self.min_tension = min_tension
        self.max_tension = max_tension
    
    def validate(self, state: StoryState) -> ValidationResult:
        recent_tension = state.get_recent_tension_values(n=5)
        
        # Check for stagnation
        if len(set(recent_tension)) == 1:
            return ValidationResult(
                is_valid=False,
                errors=["Tension is stagnant - no variation in last 5 scenes"]
            )
        
        # Check bounds
        if any(t < self.min_tension or t > self.max_tension for t in recent_tension):
            return ValidationResult(
                is_valid=False,
                errors=[f"Tension out of bounds [{self.min_tension}, {self.max_tension}]"]
            )
        
        return ValidationResult(is_valid=True, errors=[])
```

## Implementation Phases

### Phase 1: Contract Foundation (Weeks 1-2)
- [ ] Implement `BeatContract` dataclass
- [ ] Implement `ValidationResult` and validation methods
- [ ] Add precondition/postcondition support
- [ ] Create `ContractValidator` class
- [ ] Update beat generation to create contracts

### Phase 2: Entity Registry (Weeks 2-3)
- [ ] Implement `EntityRegistry` with deduplication
- [ ] Add fuzzy name matching for characters/locations
- [ ] Implement `Character.inventory` system
- [ ] Add `Item` entity type
- [ ] Update all entity creation tools to use registry

### Phase 3: Block System (Weeks 3-4)
- [ ] Implement `ProseBlock` and `SubBlock` dataclasses
- [ ] Create `BlockPlanner` to generate block structures
- [ ] Implement `SubBlockType` enum and handlers
- [ ] Add `Transition` block type
- [ ] Update prose generation to use blocks

### Phase 4: Integration (Weeks 4-5)
- [ ] Integrate contracts into tick execution
- [ ] Add precondition validation before generation
- [ ] Add postcondition validation after generation
- [ ] Implement retry logic for failed contracts
- [ ] Add contract violation reporting

### Phase 5: Global Constraints (Weeks 5-6)
- [ ] Implement `StoryContract` with global constraints
- [ ] Add `NoCharacterDuplication` constraint
- [ ] Add `InventoryConsistency` constraint
- [ ] Add `TensionPacing` constraint
- [ ] Create constraint violation recovery strategies

## Example: Complete Flow

```python
# Story setup
story_contract = StoryContract(
    foundation=story_foundation,
    global_constraints=[
        NoCharacterDuplication(),
        NoLocationDuplication(),
        InventoryConsistency(),
        TensionPacing(min=4, max=9),
    ],
    beat_contracts=[]  # Will be populated as beats are generated
)

# Generate beat contract
beat_contract = BeatContract(
    beat_id="PB001",
    description="Sylura triggers power surge in Glitch Pit",
    required_characters=["C0"],
    required_location="L1",
    required_items={"C0": ["data_slate"]},
    preconditions=[
        lambda state: state.get_character("C0").location == "L1",
        lambda state: state.get_character("C0").has_item("data_slate"),
    ],
    postconditions=[
        lambda prose, state: state.get_location("L1").power_status == "off",
        lambda prose, state: state.chaos_level >= 7,
    ],
    tension_target=8,
)

# Add to story contract
story_contract.beat_contracts.append(beat_contract)

# Validate global constraints
validation = story_contract.validate_global_constraints(story_state)
if not validation.is_valid:
    raise ContractViolation(f"Global constraints violated: {validation.errors}")

# Execute beat
try:
    scene = execute_tick(beat_contract, story_state)
    print(f"✅ Beat {beat_contract.beat_id} completed successfully")
except ContractViolation as e:
    print(f"❌ Beat {beat_contract.beat_id} failed: {e}")
    # Retry or handle failure
```

## Benefits

### Reliability
- ✅ Beats are validated before and after execution
- ✅ Entity duplication is prevented at creation time
- ✅ Inventory consistency is enforced
- ✅ Failed contracts can be retried with feedback

### Emergence
- ✅ LLM still controls prose generation within blocks
- ✅ Block structure can adapt to story needs
- ✅ Sub-blocks can be added/removed dynamically
- ✅ Contracts define requirements, not implementation

### Maintainability
- ✅ Clear separation between validation and composition
- ✅ Contracts are testable independently
- ✅ Block structures are reusable
- ✅ Easy to add new constraint types

### Debuggability
- ✅ Contract violations are explicit and actionable
- ✅ Block structure is visible and inspectable
- ✅ State changes are tracked incrementally
- ✅ Failed validations include specific error messages

## Open Questions

1. **Contract Granularity:** Should sub-blocks have their own micro-contracts, or is beat-level sufficient?

2. **Dynamic Block Planning:** Should block structure be fixed per beat type, or dynamically planned by LLM?

3. **Constraint Recovery:** When a constraint is violated, should we:
   - Retry generation with feedback?
   - Rollback state and try different approach?
   - Relax constraint temporarily?

4. **Performance:** How much validation overhead is acceptable? Should we cache validation results?

5. **Contract Language:** Should contracts be:
   - Pure Python (current approach)?
   - YAML/JSON declarative format?
   - Custom DSL?

## References

- `DSL_and_contracts.md` - Original design ideas
- `ARCHITECTURE_PROPOSAL_EMERGENT_PLOTTING.md` - Plot-first architecture
- `IMPLEMENTATION_CHECKLIST_EMERGENT_PLOTTING.md` - Implementation phases

## Changelog

- **2025-11-25:** Initial formalization based on DSL discussions
