"""Name generation tool for creating unique character names."""

import random
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from .base import Tool


class NameGenerator:
    """Generate unique character names using syllable combinations."""
    
    def __init__(self, data_dir: Path):
        """Initialize name generator with data files.
        
        Args:
            data_dir: Path to directory containing name data JSON files
        """
        self.data_dir = Path(data_dir)
        self.scifi_data = self._load_json("scifi_syllables.json")
        self.titles_data = self._load_json("titles.json")
        self.place_data = self._load_json("place_syllables.json")
        # Only scifi person-name banks exist today; fantasy/modern fall back to it.
        self.banks = {"scifi": self.scifi_data}
        self.used_names = set()   # Person names used this process
        self.used_places = set()  # Place names used this process
        self.vowels = set('aeiou')
        self.consonants = set('bcdfghjklmnpqrstvwxyz')

    def _normalize_genre(self, genre: Optional[str]) -> str:
        """Map a free-text story genre to an available name bank key."""
        if not genre:
            return "scifi"
        g = genre.lower()
        if any(k in g for k in ["fantasy", "myth", "medieval", "sword"]):
            return "fantasy"
        if any(k in g for k in ["modern", "contemp", "thriller", "noir", "realis", "crime"]):
            return "modern"
        return "scifi"

    def _bank_for_genre(self, genre: Optional[str]) -> dict:
        return self.banks.get(self._normalize_genre(genre), self.scifi_data)

    def register_used_name(self, full_name: Optional[str]) -> None:
        """Mark a person name as taken so it won't be regenerated."""
        if full_name and full_name.strip():
            self.used_names.add(full_name.strip())

    def register_used_place(self, name: Optional[str]) -> None:
        """Mark a place name as taken so it won't be regenerated."""
        if name and name.strip():
            self.used_places.add(name.strip())
    
    def _load_json(self, filename: str) -> dict:
        """Load name data from JSON file.
        
        Args:
            filename: Name of JSON file to load
        
        Returns:
            Parsed JSON data
        """
        file_path = self.data_dir / filename
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def generate_name(
        self,
        gender: str = "male",
        genre: str = "scifi",
        title: Optional[str] = None,
        max_attempts: int = 50
    ) -> Dict[str, str]:
        """Generate a unique character name.
        
        Args:
            gender: "male" or "female"
            genre: "scifi" (more genres can be added later)
            title: Optional title (e.g., "Dr.", "Captain")
            max_attempts: Maximum attempts to generate unique name
        
        Returns:
            Dictionary with full_name, first_name, last_name, title
        
        Raises:
            ValueError: If unable to generate unique name after max_attempts
        """
        # Validate and correct gender-specific titles
        if title:
            title = self._validate_title_gender(title, gender)
        
        data = self._bank_for_genre(genre)
        for attempt in range(max_attempts):
            first_name = self._generate_syllable_name(
                data["first_name"],
                gender
            )
            last_name = self._generate_syllable_name(
                data["last_name"],
                "neutral"  # Last names are gender-neutral
            )
            
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
        
        # Fallback if all attempts failed (very unlikely with 864k+ combinations)
        raise ValueError(
            f"Could not generate unique name after {max_attempts} attempts. "
            f"Used names: {len(self.used_names)}"
        )
    
    def _generate_syllable_name(
        self,
        syllable_data: dict,
        gender: str,
        max_attempts: int = 20
    ) -> str:
        """Generate name from syllables with phonetic compatibility.
        
        Args:
            syllable_data: Dictionary with gender-specific syllable lists
            gender: Gender key to use
            max_attempts: Maximum attempts to find compatible syllables
        
        Returns:
            Generated name string
        """
        # Get gender-specific data, fallback to neutral if not found
        # Handle both gendered (first_name) and non-gendered (last_name) data
        if gender in syllable_data:
            gender_data = syllable_data[gender]
        elif "neutral" in syllable_data:
            gender_data = syllable_data["neutral"]
        elif "male" in syllable_data:
            gender_data = syllable_data["male"]
        else:
            # Direct syllable data (for last names)
            gender_data = syllable_data
        
        for _ in range(max_attempts):
            start = random.choice(gender_data["start"])
            end = random.choice(gender_data["end"])
            
            # Check phonetic compatibility
            if self._is_phonetically_compatible(start, end):
                return start + end
        
        # Fallback: just concatenate without checking
        return random.choice(gender_data["start"]) + random.choice(gender_data["end"])
    
    def _is_phonetically_compatible(self, syllable1: str, syllable2: str) -> bool:
        """Check if two syllables flow well together phonetically.
        
        Args:
            syllable1: First syllable
            syllable2: Second syllable
        
        Returns:
            True if syllables are compatible, False otherwise
        """
        if not syllable1 or not syllable2:
            return True
        
        end_char = syllable1[-1].lower()
        start_char = syllable2[0].lower()
        
        # Avoid double vowels (except specific good combinations)
        if end_char in self.vowels and start_char in self.vowels:
            good_vowel_combos = [
                'ae', 'ai', 'ao', 'ea', 'ei', 'eo', 'ia', 'ie', 'io',
                'oa', 'oe', 'oi', 'ua', 'ue', 'ui'
            ]
            if end_char + start_char in good_vowel_combos:
                return True
            return False
        
        # Avoid harsh consonant clusters
        if end_char in self.consonants and start_char in self.consonants:
            harsh_clusters = [
                'ck', 'gk', 'pk', 'tk', 'xk', 'zk', 'qx', 'xq',
                'zx', 'xz', 'qq', 'xx', 'zz'
            ]
            if end_char + start_char in harsh_clusters:
                return False
        
        return True
    
    def _validate_title_gender(self, title: str, gender: str) -> str:
        """Validate and correct gender-specific titles.
        
        Args:
            title: The title to validate
            gender: The character's gender ("male" or "female")
        
        Returns:
            Corrected title if needed, original title otherwise
        """
        # Gender-specific title mappings
        male_to_female = {
            "Lord": "Lady",
            "Duke": "Duchess",
            "Baron": "Baroness",
            "Count": "Countess",
            "Knight": "Dame",
            "Sir": "Dame",
            "Viscount": "Viscountess"
        }
        
        female_to_male = {v: k for k, v in male_to_female.items()}
        
        # If title is gender-specific, correct it
        if gender == "female" and title in male_to_female:
            return male_to_female[title]
        elif gender == "male" and title in female_to_male:
            return female_to_male[title]
        
        # Title is gender-neutral or already correct
        return title
    
    def generate_place_name(
        self,
        descriptor: Optional[str] = None,
        genre: str = "scifi",
        max_attempts: int = 50,
    ) -> Dict[str, str]:
        """Coin a unique place name.

        Python owns the proper-noun root (e.g. "Vernholt"); the optional
        ``descriptor`` is an LLM-supplied common noun (e.g. "Town Hall") that is
        appended, giving "Vernholt Town Hall". With no descriptor a standalone
        toponym is returned.

        Returns a dict with ``full_name`` and ``root``.
        """
        descriptor = (descriptor or "").strip()
        for _ in range(max_attempts):
            root = self._generate_syllable_name(self.place_data, "neutral")
            root = root[:1].upper() + root[1:]

            pattern = random.choice(self.place_data.get("patterns", ["{root}"]))
            base = pattern.format(
                root=root,
                prefix=random.choice(self.place_data.get("prefixes", ["New"])),
            )

            full_name = f"{base} {descriptor}".strip() if descriptor else base
            if full_name not in self.used_places:
                self.used_places.add(full_name)
                return {"full_name": full_name, "root": root}

        raise ValueError(
            f"Could not generate unique place name after {max_attempts} attempts. "
            f"Used places: {len(self.used_places)}"
        )

    def reset_used_names(self):
        """Reset the set of used names. Useful for testing or new projects."""
        self.used_names.clear()
        self.used_places.clear()


class NameGeneratorTool(Tool):
    """Tool for generating unique character names."""
    
    def __init__(self, data_dir: Path):
        """Initialize name generator tool.
        
        Args:
            data_dir: Path to directory containing name data files
        """
        super().__init__(
            name="name.generate",
            description="Generate a unique character name using phonetic syllables to avoid repetition",
            parameters={
                "gender": {
                    "type": "string",
                    "enum": ["male", "female"],
                    "description": "Character gender for name generation"
                },
                "genre": {
                    "type": "string",
                    "enum": ["scifi"],
                    "description": "Genre style for name generation (default: scifi)",
                    "optional": True
                },
                "title": {
                    "type": "string",
                    "description": "Optional title (Dr., Captain, Admiral, etc.)",
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
    ) -> Dict[str, Any]:
        """Execute name generation.
        
        Args:
            gender: Character gender ("male" or "female")
            genre: Name genre/style (currently only "scifi")
            title: Optional title to prepend to name
        
        Returns:
            Dictionary with success status and generated name components
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
                "error": str(e),
                "full_name": "",
                "first_name": "",
                "last_name": "",
                "title": ""
            }
