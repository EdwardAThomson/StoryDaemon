"""Character detection and auto-creation for mentioned characters."""

import re
from typing import List, Dict, Any, Set, Optional
from pathlib import Path


class CharacterDetector:
    """Detects new character names in scene prose and prompts for entity creation."""
    
    def __init__(self, memory_manager, config: Dict[str, Any]):
        """Initialize character detector.
        
        Args:
            memory_manager: MemoryManager instance
            config: Project configuration
        """
        self.memory = memory_manager
        self.config = config
        
        # Common titles and honorifics to help identify names
        self.titles = {
            'Mr', 'Mrs', 'Ms', 'Miss', 'Dr', 'Doctor', 'Professor', 'Prof',
            'Captain', 'Lieutenant', 'Sergeant', 'Major', 'Colonel', 'General',
            'Lord', 'Lady', 'Sir', 'Dame', 'Agent', 'Detective', 'Officer'
        }
        
        # Words that are often capitalized but aren't names
        self.common_false_positives = {
            'I', 'The', 'A', 'An', 'And', 'But', 'Or', 'So', 'Yet', 'For',
            'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
            'January', 'February', 'March', 'April', 'May', 'June', 'July',
            'August', 'September', 'October', 'November', 'December',
            'Earth', 'Mars', 'Moon', 'Sun', 'God', 'Gods'
        }
    
    def detect_character_names(self, scene_text: str) -> List[str]:
        """Detect potential character names in scene text.
        
        Uses heuristics to find capitalized words that look like names:
        - Preceded by titles (Dr., Mr., etc.)
        - Multiple capitalized words in sequence
        - Capitalized words in dialogue attribution
        
        Args:
            scene_text: The scene prose text
        
        Returns:
            List of potential character names
        """
        potential_names = set()
        
        # Pattern 1: Title + Name (e.g., "Dr. Chen", "Agent Rodriguez")
        title_pattern = r'\b(' + '|'.join(self.titles) + r')\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
        for match in re.finditer(title_pattern, scene_text):
            name = match.group(2).strip()
            potential_names.add(name)
        
        # Pattern 2: Dialogue attribution (e.g., "said Marcus", "Chen replied")
        dialogue_pattern = r'(?:said|asked|replied|shouted|whispered|muttered|called|yelled)\s+([A-Z][a-z]+)'
        for match in re.finditer(dialogue_pattern, scene_text):
            name = match.group(1).strip()
            if name not in self.common_false_positives:
                potential_names.add(name)
        
        # Pattern 3: Multiple capitalized words (likely full names)
        full_name_pattern = r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b'
        for match in re.finditer(full_name_pattern, scene_text):
            name = match.group(1).strip()
            # Check if it's not a false positive
            words = name.split()
            if not any(w in self.common_false_positives for w in words):
                potential_names.add(name)
        
        # Pattern 4: Possessive names (e.g., "Chen's", "Marcus's")
        possessive_pattern = r"\b([A-Z][a-z]+)'s\b"
        for match in re.finditer(possessive_pattern, scene_text):
            name = match.group(1).strip()
            if name not in self.common_false_positives:
                potential_names.add(name)
        
        return sorted(list(potential_names))
    
    def get_existing_character_names(self) -> Set[str]:
        """Get all existing character names from memory.
        
        Returns:
            Set of character names (first names, family names, and full names)
        """
        existing_names = set()
        
        # Get all character IDs
        char_ids = self.memory.list_characters()
        
        for char_id in char_ids:
            char = self.memory.load_character(char_id)
            if char:
                # Add first name
                if char.first_name:
                    existing_names.add(char.first_name)
                
                # Add family name
                if char.family_name:
                    existing_names.add(char.family_name)
                
                # Add full name
                if char.first_name and char.family_name:
                    existing_names.add(f"{char.first_name} {char.family_name}")
                
                # Add nicknames
                for nickname in char.nicknames:
                    existing_names.add(nickname)
        
        return existing_names
    
    def find_new_characters(self, scene_text: str) -> List[str]:
        """Find character names in scene that don't have entities yet.
        
        Args:
            scene_text: The scene prose text
        
        Returns:
            List of new character names not in the character registry
        """
        detected_names = self.detect_character_names(scene_text)
        existing_names = self.get_existing_character_names()
        
        new_characters = []
        for name in detected_names:
            # Check if this name or any part of it exists
            name_parts = name.split()
            is_new = True
            
            # Check full name
            if name in existing_names:
                is_new = False
            # Check if any part matches (e.g., "Chen" matches "Dr. Chen")
            elif any(part in existing_names for part in name_parts):
                is_new = False
            # Check if any existing name contains this name
            elif any(name in existing for existing in existing_names):
                is_new = False
            
            if is_new:
                new_characters.append(name)
        
        return new_characters
    
    def create_character_stub(self, name: str, role: str = "Minor Character") -> str:
        """Create a minimal character entity stub.
        
        Args:
            name: Character name (can be full name or single name)
            role: Character role (default: "Minor Character")
        
        Returns:
            Character ID of created entity
        """
        # Split name into first and family name
        name_parts = name.split()
        if len(name_parts) >= 2:
            first_name = name_parts[0]
            family_name = ' '.join(name_parts[1:])
        else:
            first_name = name
            family_name = ""
        
        # Generate character ID
        char_id = self.memory.generate_id("character")
        
        # Create minimal character entity
        from ..memory.entities import Character
        
        character = Character(
            id=char_id,
            first_name=first_name,
            family_name=family_name,
            role=role,
            description=f"Auto-detected character from scene prose. Details to be filled in.",
            personality={"core_traits": []},
            relationships=[],
            current_state={
                "location_id": None,
                "emotional_state": "",
                "physical_state": "",
                "inventory": [],
                "goals": [],
                "beliefs": []
            }
        )
        
        # Save to memory
        self.memory.save_character(character)
        
        return char_id
