"""Entity dataclasses for memory system."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime


# ============================================================================
# Helper Classes
# ============================================================================

@dataclass
class PhysicalTraits:
    """Physical characteristics of a character."""
    age: Optional[int] = None
    appearance: str = ""
    distinctive_features: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhysicalTraits":
        return cls(**data)


@dataclass
class Personality:
    """Personality traits and motivations."""
    core_traits: List[str] = field(default_factory=list)
    fears: List[str] = field(default_factory=list)
    desires: List[str] = field(default_factory=list)
    flaws: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Personality":
        return cls(**data)


@dataclass
class Relationship:
    """Relationship between a character and another character."""
    character_id: str
    relationship_type: str  # mentor, friend, rival, enemy, family, etc.
    status: str  # close, strained, hostile, unknown, etc.
    description: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relationship":
        return cls(**data)


@dataclass
class CurrentState:
    """Current state of a character."""
    location_id: Optional[str] = None
    emotional_state: str = ""
    physical_state: str = ""
    inventory: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    beliefs: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CurrentState":
        return cls(**data)


@dataclass
class HistoryEntry:
    """History entry for tracking entity changes over time."""
    tick: int
    scene_id: str
    changes: Dict[str, Any]
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEntry":
        return cls(**data)


@dataclass
class SensoryDetails:
    """Sensory details for a location."""
    visual: str = ""
    auditory: str = ""
    olfactory: str = ""
    tactile: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SensoryDetails":
        return cls(**data)


@dataclass
class LocationConnection:
    """Connection between locations."""
    location_id: str
    connection_type: str  # adjacent, distant, portal, hidden, etc.
    description: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LocationConnection":
        return cls(**data)


@dataclass
class LocationState:
    """Current state of a location."""
    tension_level: int = 0  # 0-10 scale
    time_of_day: str = ""
    weather: str = ""
    occupants: List[str] = field(default_factory=list)  # Character IDs
    notable_objects: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LocationState":
        return cls(**data)


@dataclass
class RelationshipHistoryEntry:
    """History entry for relationship changes."""
    tick: int
    scene_id: str
    event: str
    status_change: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipHistoryEntry":
        return cls(**data)


# ============================================================================
# Main Entity Classes
# ============================================================================

@dataclass
class Character:
    """Character entity with full attributes."""
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
    
    # NEW: Goal hierarchy (Phase 7A.2)
    immediate_goals: List[str] = field(default_factory=list)  # "Fix the antenna"
    arc_goal: Optional[str] = None  # "Overcome isolation and trust others"
    story_goal: Optional[str] = None  # "Make contact with alien intelligence"
    
    # NEW: Goal tracking
    goal_progress: Dict[str, float] = field(default_factory=dict)  # goal -> progress (0.0-1.0)
    goals_completed: List[str] = field(default_factory=list)
    goals_abandoned: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Set timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert nested objects
        if isinstance(self.physical_traits, PhysicalTraits):
            data['physical_traits'] = self.physical_traits.to_dict()
        if isinstance(self.personality, Personality):
            data['personality'] = self.personality.to_dict()
        if isinstance(self.current_state, CurrentState):
            data['current_state'] = self.current_state.to_dict()
        data['relationships'] = [r.to_dict() if isinstance(r, Relationship) else r for r in self.relationships]
        data['history'] = [h.to_dict() if isinstance(h, HistoryEntry) else h for h in self.history]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        """Create from dictionary."""
        # Convert nested objects
        if 'physical_traits' in data and isinstance(data['physical_traits'], dict):
            data['physical_traits'] = PhysicalTraits.from_dict(data['physical_traits'])
        if 'personality' in data and isinstance(data['personality'], dict):
            data['personality'] = Personality.from_dict(data['personality'])
        if 'current_state' in data and isinstance(data['current_state'], dict):
            data['current_state'] = CurrentState.from_dict(data['current_state'])
        if 'relationships' in data:
            data['relationships'] = [
                Relationship.from_dict(r) if isinstance(r, dict) else r 
                for r in data['relationships']
            ]
        if 'history' in data:
            data['history'] = [
                HistoryEntry.from_dict(h) if isinstance(h, dict) else h 
                for h in data['history']
            ]
        return cls(**data)


@dataclass
class Location:
    """Location entity with full attributes."""
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
    
    def __post_init__(self):
        """Set timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if isinstance(self.sensory_details, SensoryDetails):
            data['sensory_details'] = self.sensory_details.to_dict()
        if isinstance(self.current_state, LocationState):
            data['current_state'] = self.current_state.to_dict()
        data['connections'] = [c.to_dict() if isinstance(c, LocationConnection) else c for c in self.connections]
        data['history'] = [h.to_dict() if isinstance(h, HistoryEntry) else h for h in self.history]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Location":
        """Create from dictionary."""
        if 'sensory_details' in data and isinstance(data['sensory_details'], dict):
            data['sensory_details'] = SensoryDetails.from_dict(data['sensory_details'])
        if 'current_state' in data and isinstance(data['current_state'], dict):
            data['current_state'] = LocationState.from_dict(data['current_state'])
        if 'connections' in data:
            data['connections'] = [
                LocationConnection.from_dict(c) if isinstance(c, dict) else c 
                for c in data['connections']
            ]
        if 'history' in data:
            data['history'] = [
                HistoryEntry.from_dict(h) if isinstance(h, dict) else h 
                for h in data['history']
            ]
        return cls(**data)


@dataclass
class Scene:
    """Scene entity with metadata."""
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
    
    # NEW: Tension tracking (Phase 7A.3)
    tension_level: Optional[int] = None  # 0-10 scale
    tension_category: Optional[str] = None  # calm, rising, high, climactic
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scene":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class OpenLoop:
    """Open story loop (unresolved plot thread)."""
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
    
    # NEW: Tracking fields (Phase 7A.2)
    scenes_mentioned: int = 0  # How many scenes has this appeared in?
    last_mentioned_tick: Optional[int] = None
    is_story_goal: bool = False  # Promoted to main story goal?
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpenLoop":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RelationshipGraph:
    """Relationship between two characters (bidirectional)."""
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
    
    def __post_init__(self):
        """Set timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['history'] = [h.to_dict() if isinstance(h, RelationshipHistoryEntry) else h for h in self.history]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipGraph":
        """Create from dictionary."""
        if 'history' in data:
            data['history'] = [
                RelationshipHistoryEntry.from_dict(h) if isinstance(h, dict) else h 
                for h in data['history']
            ]
        return cls(**data)
    
    def involves_character(self, character_id: str) -> bool:
        """Check if this relationship involves the given character."""
        return character_id in (self.character_a, self.character_b)
    
    def get_other_character(self, character_id: str) -> Optional[str]:
        """Get the other character in the relationship."""
        if character_id == self.character_a:
            return self.character_b
        elif character_id == self.character_b:
            return self.character_a
        return None
    
    def get_perspective(self, character_id: str) -> Optional[str]:
        """Get the perspective from a specific character's viewpoint."""
        if character_id == self.character_a:
            return self.perspective_a
        elif character_id == self.character_b:
            return self.perspective_b
        return None


@dataclass
class Lore:
    """World rule or lore fact (Phase 7A.4).
    
    Tracks established world rules, constraints, and facts to maintain
    internal consistency across the emergent narrative.
    """
    id: str
    type: str = "lore"
    lore_type: str = ""  # "rule", "fact", "constraint", "capability", "limitation"
    content: str = ""  # The actual lore statement
    category: str = ""  # "magic", "technology", "society", "physics", "biology", etc.
    source_scene_id: str = ""  # Scene where this was established
    tick: int = 0
    importance: str = "normal"  # "critical", "important", "normal", "minor"
    tags: List[str] = field(default_factory=list)  # For categorization
    related_lore: List[str] = field(default_factory=list)  # IDs of related lore
    potential_contradictions: List[str] = field(default_factory=list)  # IDs of potentially conflicting lore
    created_at: str = ""
    
    def __post_init__(self):
        """Set created_at if not provided."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lore":
        """Create from dictionary."""
        return cls(**data)
