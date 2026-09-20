"""Name generation tool for creating unique character names."""

import difflib
import random
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from .base import Tool

logger = logging.getLogger(__name__)

AUTO = "auto"


def bank_settings_from_config(config) -> Dict[str, Any]:
    """Read the names.* config block into NameGenerator keyword arguments.

    One place resolves the author's settings, so the CLI, the project wizard
    and the protagonist minting at project creation cannot drift apart.
    """
    return {
        "use_drawn_banks": config.get("names.use_drawn_banks", True),
        "person_bank": config.get("names.person_bank"),
        "place_bank": config.get("names.place_bank"),
        "title_bank": config.get("names.title_bank"),
        "register": config.get("names.register"),
    }

class NameGenerator:
    """Generate unique character names from per-genre banks."""

    # Keywords are matched at a word boundary. A plain entry matches as a
    # prefix, because several are deliberately stemmed ("futur" covers
    # futurism and futuristic); a trailing "$" means whole word. "roman$" is
    # whole-word for a reason: as a bare substring it swallowed every
    # "romance", routing love stories to the Roman bank.
    # Order decides ties, so the more specific bank comes first.
    GENRE_KEYWORDS = [
        ("western", ["western", "cowboy", "frontier", "wild west",
                     "gunslinger", "outlaw"]),
        ("gothic", ["gothic", "horror", "haunt", "vampire", "ghost",
                    "occult", "supernatural", "macabre"]),
        ("victorian", ["victorian", "regency", "dickens", "gaslight",
                       "steampunk"]),
        ("fantasy", ["fantasy", "myth", "sword", "magic", "dragon",
                     "elves", "elven", "wizard"]),
        ("historical", ["historic", "period drama", "ancient", "roman$",
                        "medieval", "renaissance", "napoleonic", "tudor",
                        "samurai"]),
        ("scifi", ["sci-fi", "scifi", "science fiction", "space", "cyber",
                   "futur", "dystopi", "galac", "starship", "mars", "alien",
                   "robot"]),
        ("modern", ["modern", "contemp", "thriller", "noir", "realis",
                    "crime", "detective", "spy", "urban", "domestic",
                    "romance", "romantic"]),
    ]

    DEFAULT_GENRE = "modern"

    BANK_FILES = {
        "scifi": "scifi_syllables.json",
        "modern": "modern_names.json",
        "historical": "historical_names.json",
        "victorian": "victorian_names.json",
        "western": "western_names.json",
        "gothic": "gothic_names.json",
        "fantasy": "fantasy_names.json",
    }

    COINED_COMPANIONS = {"fantasy": "fantasy_syllables.json"}

    TITLE_BANK_FILE = "titles_by_genre.json"

    # Banks with no title block of their own (victorian) borrow this one.
    DEFAULT_TITLE_GENRE = "historical"

    @classmethod
    def available_banks(cls) -> List[str]:
        """Every valid name-bank key, for config validation and the wizard."""
        return sorted(cls.BANK_FILES)

    def __init__(self, data_dir: Path, use_drawn_banks: bool = True,
                 person_bank: Optional[str] = None,
                 place_bank: Optional[str] = None,
                 title_bank: Optional[str] = None,
                 register: Optional[str] = None):
        """Initialize name generator with data files.

        The three bank arguments are the author's settings (config, the
        --name-bank flag, the wizard). Each is a bank key or None/"auto",
        which routes from the story's genre exactly as before. They are
        independent, so Victorian character names can sit in a novel whose
        places are still science fiction.
        """
        self.data_dir = Path(data_dir)
        self.scifi_data = self._load_json("scifi_syllables.json")
        self.titles_data = self._load_json("titles.json")
        self.title_banks = self._load_json(self.TITLE_BANK_FILE, required=False) or {}
        self.place_data = self._load_json("place_syllables.json")
        self.place_banks = self._load_json("places_by_genre.json", required=False) or {}

        self.use_drawn_banks = use_drawn_banks
        self.banks = {"scifi": self.scifi_data}
        self.coined_companions = {}
        if use_drawn_banks:
            for key, filename in self.BANK_FILES.items():
                if key == "scifi":
                    continue
                bank = self._load_json(filename, required=False)
                if bank:
                    self.banks[key] = bank
            for key, filename in self.COINED_COMPANIONS.items():
                companion = self._load_json(filename, required=False)
                if companion:
                    self.coined_companions[key] = companion
        for key, bank in self.banks.items():
            bank["_key"] = key

        # Validated eagerly: a typo in config.yaml should stop the run here,
        # not misname a whole novel. Silent fallback is for "auto" only,
        # where the author has stated no intent.
        self.person_bank = self._validated_pin("person_bank", person_bank)
        self.place_bank = self._validated_pin("place_bank", place_bank)
        self.title_bank = self._validated_pin("title_bank", title_bank)
        self.register = self._normalize_pin(register)

        self.used_names = set()        # Full person names used this process
        self.used_first_names = set()  # Given names only -- see _draw()
        self.used_places = set()       # Place names used this process
        self._title_words = self._collect_title_words()
        self.vowels = set('aeiou')
        self.consonants = set('bcdfghjklmnpqrstvwxyz')

    @staticmethod
    def _normalize_pin(value: Optional[str]) -> Optional[str]:
        """A configured slot: None for unset or "auto", else a bank key."""
        key = (value or "").strip().lower()
        return None if key in ("", AUTO) else key

    def _validated_pin(self, slot: str, value: Optional[str]) -> Optional[str]:
        """Validate one configured bank slot, raising on anything unusable."""
        key = self._normalize_pin(value)
        if key is None:
            return None
        if key not in self.BANK_FILES:
            raise ValueError(
                f"names.{slot} is {key!r}, which is not a name bank. "
                f"Available: {', '.join(self.available_banks())}, or 'auto'."
            )
        if key not in self.banks:
            if not self.use_drawn_banks:
                raise ValueError(
                    f"names.{slot} is {key!r} but names.use_drawn_banks is "
                    f"false, so only the scifi bank is loaded."
                )
            raise ValueError(
                f"names.{slot} is {key!r} but its data file "
                f"{self.BANK_FILES[key]} is missing from {self.data_dir}."
            )
        bank = self.banks[key]
        if bank.get("usable") is False:
            firsts = bank.get("first_name") or {}
            raise ValueError(
                f"names.{slot} is {key!r}, a bank that is not usable yet "
                f"({len(firsts.get('male', [])) + len(firsts.get('female', []))} "
                f"given names, {len(bank.get('last_name') or [])} surnames). "
                f"Choose another bank or leave it on 'auto'."
            )
        return key

    @staticmethod
    def _flatten_strings(node, into: Optional[set] = None) -> set:
        """Every string anywhere in a nested title structure."""
        words = set() if into is None else into
        if isinstance(node, dict):
            for value in node.values():
                NameGenerator._flatten_strings(value, words)
        elif isinstance(node, list):
            for item in node:
                NameGenerator._flatten_strings(item, words)
        elif isinstance(node, str):
            words.add(node)
        return words

    def _collect_title_words(self) -> set:
        """Every known title, so a recorded name can have one stripped off.

        Includes the per-genre blocks and their stripped_from_names lists, so
        "Sheriff Tom Blake" records Tom rather than Sheriff.
        """
        words = self._flatten_strings(self.titles_data)
        return self._flatten_strings(self.title_banks, words)

    @staticmethod
    def _keyword_matches(keyword: str, text: str) -> bool:
        """Match a keyword at a word boundary; a trailing "$" means whole word."""
        if keyword.endswith("$"):
            return re.search(rf"\b{re.escape(keyword[:-1])}\b", text) is not None
        return re.search(rf"\b{re.escape(keyword)}", text) is not None

    def _normalize_genre(self, genre: Optional[str]) -> str:
        """Map a free-text story genre to an available name bank key."""
        if not genre:
            return self.DEFAULT_GENRE
        g = genre.lower()
        matched = None
        for key, keywords in self.GENRE_KEYWORDS:
            if any(self._keyword_matches(k, g) for k in keywords):
                matched = key
                break
        if matched in (None, "historical") and any(
            1800 <= int(y) <= 1901 for y in re.findall(r"\b(1[89]\d{2})\b", g)
        ):
            return "victorian"
        return matched or self.DEFAULT_GENRE

    def _routed_bank(self, genre: Optional[str]) -> str:
        """Which bank a genre routes to, ignoring the author's settings."""
        key = self._normalize_genre(genre)
        bank = self.banks.get(key)
        if bank is not None and bank.get("usable") is False:
            firsts = bank.get("first_name") or {}
            logger.warning(
                "name bank %r is not usable yet (%d given names, %d surnames); "
                "falling back to %s",
                key, len(firsts.get("male", [])) + len(firsts.get("female", [])),
                len(bank.get("last_name") or []), self.DEFAULT_GENRE,
            )
            key = self.DEFAULT_GENRE
        if key not in self.banks:
            key = self.DEFAULT_GENRE if self.DEFAULT_GENRE in self.banks else "scifi"
        return key

    def resolve_person_bank(self, genre: Optional[str]) -> str:
        """The bank character names come from: the author's pin, else the genre."""
        return self.person_bank or self._routed_bank(genre)

    def resolve_place_bank(self, genre: Optional[str]) -> str:
        """The bank place names come from.

        Unpinned, this follows the *genre* rather than the person bank, which
        is what makes "Victorian names in a space opera" mean Victorian-named
        people on science-fiction worlds instead of dragging the planets to
        London.
        """
        return self.place_bank or self._routed_bank(genre)

    def resolve_title_bank(self, genre: Optional[str]) -> str:
        """The bank the rank/honorific roster comes from."""
        key = self.title_bank or self._routed_bank(genre)
        if key not in self.title_banks:
            key = self.DEFAULT_TITLE_GENRE
        return key

    def _bank_for_genre(self, genre: Optional[str]) -> dict:
        """Resolve a genre to a loaded bank, falling back to science fiction."""
        return self.banks.get(self.resolve_person_bank(genre), self.scifi_data)

    def _place_bank_for_genre(self, genre: Optional[str]) -> dict:
        """Resolve a genre to a place bank."""
        bank = self.place_banks.get(self.resolve_place_bank(genre))
        return bank if bank else self.place_data

    def register_used_name(self, full_name: Optional[str]) -> None:
        """Mark a person name as taken so it won't be regenerated."""
        if not full_name:
            return
        name = str(full_name).strip()
        if not name:
            return
        self.used_names.add(name)

        parts = name.split()
        while parts and (parts[0] in self._title_words or parts[0].endswith(".")):
            parts.pop(0)
        if parts:
            self.used_first_names.add(parts[0])
            self.used_names.add(" ".join(parts))

    def register_used_place(self, name: Optional[str]) -> None:
        """Mark a place name as taken so it won't be regenerated."""
        if name:
            self.used_places.add(name)

    def _load_json(self, filename: str, required: bool = True):
        """Load a JSON data file."""
        file_path = self.data_dir / filename
        if not required and not file_path.exists():
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _firsts(self, bank: dict, gender: str) -> List[str]:
        names = bank["first_name"]
        return names.get(gender) or names.get("male") or []

    def _lasts(self, bank: dict, register: Optional[str]) -> List[str]:
        """Surnames for a bank, honouring an optional register."""
        registers = bank.get("registers") or {}
        if register and register in registers:
            return registers[register]
        return bank.get("last_name") or []

    def _draw(self, bank: dict, gender: str, register: Optional[str]):
        """Select a whole first and last name from a drawn bank."""
        firsts = self._firsts(bank, gender)
        if not firsts:
            raise ValueError(f"bank {bank.get('_key')!r} has no {gender} given names")
        unused = [n for n in firsts if n not in self.used_first_names]
        first = random.choice(unused or firsts)

        lasts = self._lasts(bank, register)
        if lasts:
            return first, random.choice(lasts)
        companion = self.coined_companions.get(bank.get("_key"))
        if not companion:
            raise ValueError(
                f"bank {bank.get('_key')!r} has no surnames and no coined companion"
            )
        return first, self._generate_syllable_name(companion["last_name"], "neutral")

    def _mint(self, bank: dict, gender: str, register: Optional[str]):
        if bank.get("mode") == "drawn":
            return self._draw(bank, gender, register)
        first = self._generate_syllable_name(bank["first_name"], gender)
        last = self._generate_syllable_name(bank["last_name"], "neutral")
        return first, last

    def _scan_for_unused(self, bank: dict, gender: str, register: Optional[str]):
        """Search the remaining combinations for an unused pair."""
        if bank.get("mode") != "drawn":
            return None
        firsts, lasts = list(self._firsts(bank, gender)), list(self._lasts(bank, register))
        if not firsts or not lasts:
            return None
        random.shuffle(firsts)
        random.shuffle(lasts)
        for first in firsts:
            for last in lasts:
                if f"{first} {last}" not in self.used_names:
                    return first, last
        return None

    def _title_block(self, genre: Optional[str]) -> dict:
        """The raw title block for a story, after slot and fallback resolution."""
        return self.title_banks.get(self.resolve_title_bank(genre)) or {}

    def titles_for_genre(self, genre: Optional[str] = None,
                         gender: Optional[str] = None) -> Dict[str, List[str]]:
        """The rank/honorific roster for a story, as category -> titles.

        Handles both shapes in titles_by_genre.json: tiered and gendered
        (historical, modern, scifi, fantasy) and flat ungendered roles
        (western, gothic). Gendered lists always keep the neutral ranks, which
        is what a title with no counterpart falls back to.
        """
        roster: Dict[str, List[str]] = {}

        def add(category: str, names: List[str]) -> None:
            seen = roster.setdefault(category, [])
            for name in names:
                if name not in seen:
                    seen.append(name)

        block = self._title_block(genre)
        for category, tiers in (block.get("tiers") or {}).items():
            for tier in ("high", "mid", "low"):
                by_gender = tiers.get(tier) or {}
                genders = (gender, "neutral") if gender else ("male", "female", "neutral")
                for key in genders:
                    add(category, by_gender.get(key) or [])
        for category, entries in (block.get("roles") or {}).items():
            add(category, list(entries))
        return {c: names for c, names in roster.items() if names}

    def _title_roster(self, genre: Optional[str]) -> List[str]:
        """Every acceptable title for a story: the genre block plus the
        genre-neutral set, so a common rank is never rejected because one
        block happens not to list it."""
        roster = [t for names in self.titles_for_genre(genre).values() for t in names]
        neutral = self._flatten_strings(self.titles_data)
        return roster + [t for t in sorted(neutral) if t not in roster]

    def _sanitize_title(self, title: str, genre: Optional[str]) -> str:
        """Hold a supplied title to the story's roster.

        The model selects a rank, it does not invent one, which is the same
        sanitize-not-trust rule entity references and thread ids follow. A
        near miss is normalised ("Captian"); anything else is dropped.
        """
        roster = self._title_roster(genre)
        if not roster:
            return title
        by_lower = {t.lower(): t for t in roster}
        if title.lower() in by_lower:
            return by_lower[title.lower()]
        close = difflib.get_close_matches(title.lower(), list(by_lower), n=1, cutoff=0.8)
        if close:
            logger.info("title %r normalised to %r", title, by_lower[close[0]])
            return by_lower[close[0]]
        logger.warning(
            "title %r is not in the %r title roster; dropping it",
            title, self.resolve_title_bank(genre),
        )
        return ""

    def _resolve_register(self, bank: dict, register: Optional[str]) -> Optional[str]:
        """The surname register to draw from: the caller's, else the config default."""
        registers = bank.get("registers") or {}
        for candidate in (self._normalize_pin(register), self.register):
            if not candidate:
                continue
            if candidate in registers:
                return candidate
            if registers:
                logger.warning(
                    "register %r is not one of %s for the %r bank; ignoring it",
                    candidate, sorted(registers), bank.get("_key"),
                )
            else:
                logger.debug("the %r bank has no registers; ignoring %r",
                             bank.get("_key"), candidate)
        return None

    def generate_name(
        self,
        gender: str = "male",
        genre: str = "scifi",
        title: Optional[str] = None,
        register: Optional[str] = None,
        max_attempts: int = 50
    ) -> Dict[str, str]:
        """Generate a unique character name."""
        # Validate and correct gender-specific titles, then hold the result to
        # the story's roster.
        if title:
            title = self._validate_title_gender(title, gender, genre)
            title = self._sanitize_title(title, genre) if title else title

        bank = self._bank_for_genre(genre)
        register = self._resolve_register(bank, register)

        first_name = last_name = None
        for _ in range(max_attempts):
            first_name, last_name = self._mint(bank, gender, register)
            if f"{first_name} {last_name}" not in self.used_names:
                break
        else:
            pair = self._scan_for_unused(bank, gender, register)
            if pair is None:
                raise ValueError(
                    f"Name bank {bank.get('_key')!r} is exhausted "
                    f"({len(self.used_names)} names already used)."
                )
            first_name, last_name = pair

        full_name = f"{first_name} {last_name}"
        self.used_names.add(full_name)
        self.used_first_names.add(first_name)

        return {
            "full_name": f"{title} {full_name}" if title else full_name,
            "first_name": first_name,
            "last_name": last_name,
            "title": title or ""
        }

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
    
    def _validate_title_gender(self, title: str, gender: str,
                               genre: Optional[str] = None) -> str:
        """Validate and correct gender-specific titles.
        
        Args:
            title: The title to validate
            gender: The character's gender ("male" or "female")
            genre: Story genre, used to find the roster's neutral counterpart
        
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
        
        # The map covers the classic pairs. Beyond it the roster is the
        # authority: a title listed only under the other gender has no
        # counterpart to swap to, so take that tier's neutral rank rather
        # than leaving a Duke on a woman.
        neutral = self._neutral_counterpart(title, gender, genre)
        if neutral:
            return neutral

        # Title is gender-neutral or already correct
        return title

    def _neutral_counterpart(self, title: str, gender: str,
                             genre: Optional[str]) -> Optional[str]:
        """A neutral rank from the tier a wrong-gender title was found in."""
        other = "female" if gender == "male" else "male"
        for tiers in (self._title_block(genre).get("tiers") or {}).values():
            for tier in tiers.values():
                if title in (tier.get(other) or []) and title not in (tier.get(gender) or []):
                    candidates = tier.get("neutral") or []
                    if candidates:
                        return candidates[0]
        return None
    
    def generate_place_name(
        self,
        descriptor: Optional[str] = None,
        genre: str = "scifi",
        max_attempts: int = 50,
    ) -> Dict[str, str]:
        """Coin a unique place name."""
        descriptor = (descriptor or "").strip()
        bank = self._place_bank_for_genre(genre)
        join = bank.get("join", "")
        for _ in range(max_attempts):
            root = self._coin_place_root(bank, join)
            root = root[:1].upper() + root[1:]

            pattern = random.choice(bank.get("patterns", ["{root}"]))
            base = pattern.format(
                root=root,
                prefix=random.choice(bank.get("prefixes", ["New"])),
            )

            if self._repeats_a_word(base):
                continue

            full_name = f"{base} {descriptor}".strip() if descriptor else base
            if full_name not in self.used_places:
                self.used_places.add(full_name)
                return {"full_name": full_name, "root": root}

        raise ValueError(
            f"Could not generate unique place name after {max_attempts} attempts. "
            f"Used places: {len(self.used_places)}"
        )

    @staticmethod
    def _repeats_a_word(name: str) -> bool:
        """True when a place name says the same word twice.

        A pattern's prefix can repeat the root's own noun, which is how
        "Villa de Villa Nueva" happens.
        """
        words = [w.lower() for w in name.replace("-", " ").split()]
        return len(set(words)) != len(words)

    def _coin_place_root(self, bank: dict, join: str, tries: int = 20) -> str:
        """Coin one place root from a place bank."""
        for _ in range(tries):
            start = random.choice(bank["start"])
            end = random.choice(bank["end"])
            if start.strip().lower() == end.strip().lower():
                continue
            if join or self._is_phonetically_compatible(start, end):
                return start + join + end
        return start + join + end

    def reset_used_names(self):
        """Reset the set of used names. Useful for testing or new projects."""
        self.used_names.clear()
        self.used_first_names.clear()
        self.used_places.clear()

class NameGeneratorTool(Tool):
    """Tool for generating unique character names.

    The bank is settled in Python before the tool is built, from the author's
    config and the story's genre, and is deliberately not a parameter: the
    model selects from what Python mints and never chooses the source.
    """

    TITLES_SHOWN_PER_CATEGORY = 6

    def __init__(self, data_dir: Path, genre: str = "scifi",
                 use_drawn_banks: bool = True,
                 person_bank: Optional[str] = None,
                 place_bank: Optional[str] = None,
                 title_bank: Optional[str] = None,
                 register: Optional[str] = None):
        """Initialize name generator tool."""
        generator = NameGenerator(
            data_dir, use_drawn_banks=use_drawn_banks, person_bank=person_bank,
            place_bank=place_bank, title_bank=title_bank, register=register,
        )
        self.genre = genre or "scifi"
        bank = generator.resolve_person_bank(self.genre)
        super().__init__(
            name="name.generate",
            description=(
                f"Generate a unique character name from the story's {bank} name bank"
            ),
            parameters={
                "gender": {
                    "type": "string",
                    "enum": ["male", "female"],
                    "description": "Character gender for name generation"
                },
                "register": self._register_parameter(generator, bank),
                "title": self._title_parameter(generator, self.genre),
            }
        )
        self.generator = generator
        self._warned_about_genre = False

    @classmethod
    def from_config(cls, data_dir: Path, config, genre: str) -> "NameGeneratorTool":
        """Build the tool from the names.* config block and the story's genre."""
        return cls(data_dir, genre=genre, **bank_settings_from_config(config))

    @staticmethod
    def _register_parameter(generator: NameGenerator, bank: str) -> Dict[str, Any]:
        """Describe the surname registers this story's bank actually offers."""
        registers = sorted((generator.banks.get(bank) or {}).get("registers") or {})
        if not registers:
            description = (
                "Not used by this story's name bank, which has a single "
                "surname pool. Leave it out."
            )
        else:
            description = (
                "Optional surname register for this character: "
                + ", ".join(f"'{r}'" for r in registers)
                + ". Anything else is ignored."
            )
        return {"type": "string", "description": description, "optional": True}

    @classmethod
    def _sample(cls, names: List[str]) -> List[str]:
        """A spread of a category's titles rather than its head.

        The roster is ordered high to low and male before female, so the first
        few entries are all senior and all male; a stride shows the range.
        """
        stride = max(1, len(names) // cls.TITLES_SHOWN_PER_CATEGORY)
        return names[::stride][:cls.TITLES_SHOWN_PER_CATEGORY]

    @classmethod
    def _title_parameter(cls, generator: NameGenerator, genre: str) -> Dict[str, Any]:
        """Offer the story's rank roster, capped so the prompt stays small."""
        roster = generator.titles_for_genre(genre)
        shown = "; ".join(
            f"{category}: " + ", ".join(cls._sample(names))
            for category, names in roster.items()
        )
        description = "Optional rank or honorific."
        if shown:
            description += (
                " Choose one that fits the character's role; a title outside "
                f"the story's roster is dropped. Roster ({shown})."
            )
        return {"type": "string", "description": description, "optional": True}

    def execute(
        self,
        gender: str,
        title: Optional[str] = None,
        register: Optional[str] = None,
        genre: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute name generation.

        ``genre`` is accepted and ignored so a plan saved before the bank
        became an author setting still replays; the bank comes from config.
        """
        if genre is not None and not self._warned_about_genre:
            logger.info(
                "name.generate was called with genre=%r; the name bank is "
                "settled from config, so the argument is ignored.", genre,
            )
            self._warned_about_genre = True
        try:
            result = self.generator.generate_name(gender, self.genre, title, register)
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
