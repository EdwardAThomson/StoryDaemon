"""Shape and hygiene checks for the name-bank data files."""
import json
import re
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "novel_agent" / "data" / "names"

DRAWN_BANKS = ["modern", "historical", "western", "gothic", "fantasy",
               "victorian"]

REGISTER_BANKS = {"victorian": {"common", "gentry"}}

FORBIDDEN_IN_NAMES = {
    "Agent", "Admiral", "Captain", "Chief", "Colonel", "Commander",
    "Constable", "Deputy", "Detective", "Director", "Doc", "Doctor",
    "General", "Inspector", "Judge", "Lieutenant", "Major", "Marshal",
    "Officer", "Preacher", "Private", "Professor", "Reverend", "Sergeant",
    "Sheriff",
}

def load(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))

@pytest.fixture(scope="module")
def banks():
    return {n: load(f"{n}_names.json") for n in DRAWN_BANKS}

def test_all_data_files_are_valid_json():
    files = sorted(DATA_DIR.glob("*.json"))
    assert files, f"no name data found in {DATA_DIR}"
    for path in files:
        json.loads(path.read_text(encoding="utf-8"))

@pytest.mark.parametrize("bank_name", DRAWN_BANKS)
def test_drawn_bank_shape(bank_name, banks):
    bank = banks[bank_name]
    assert bank["mode"] == "drawn"
    assert set(bank["first_name"]) == {"male", "female"}
    usable = bank.get("usable", True)
    for gender in ("male", "female"):
        names = bank["first_name"][gender]
        assert isinstance(names, list)
        assert names or not usable, f"{bank_name}/{gender} empty"
        assert all(isinstance(n, str) and n.strip() for n in names)
    assert isinstance(bank["last_name"], list)

@pytest.mark.parametrize("bank_name", DRAWN_BANKS)
def test_no_ranks_in_name_lists(bank_name, banks):
    """No rank vocabulary appears in any name list."""
    bank = banks[bank_name]
    lists = [bank["first_name"]["male"], bank["first_name"]["female"],
             bank["last_name"]]
    for names in lists:
        leaked = FORBIDDEN_IN_NAMES.intersection(names)
        assert not leaked, f"{bank_name}: ranks leaked into a name list: {sorted(leaked)}"

@pytest.mark.parametrize("bank_name", DRAWN_BANKS)
def test_no_duplicates_within_a_list(bank_name, banks):
    bank = banks[bank_name]
    for label, names in [
        ("first_name.male", bank["first_name"]["male"]),
        ("first_name.female", bank["first_name"]["female"]),
        ("last_name", bank["last_name"]),
    ]:
        dupes = {n for n in names if names.count(n) > 1}
        assert not dupes, f"{bank_name}/{label} has duplicates: {sorted(dupes)}"

def test_fantasy_surnames_are_coined_not_missing(banks):
    """Fantasy last_name is empty and the coined companion bank exists."""
    assert banks["fantasy"]["last_name"] == []
    syl = load("fantasy_syllables.json")
    assert syl["mode"] == "coined"
    for part in ("start", "end"):
        assert syl["last_name"][part], f"fantasy coined last_name.{part} empty"

def test_fantasy_syllables_declare_ungendered_first_names():
    """Fantasy syllables declare ungendered first names under 'neutral'."""
    syl = load("fantasy_syllables.json")
    assert syl["gendered_first_names"] is False
    assert set(syl["first_name"]) == {"neutral"}
    assert syl["first_name"]["neutral"]["start"]

def test_titles_are_separate_and_complete():
    titles = load("titles_by_genre.json")
    genres = [g for g in titles if not g.startswith("_")]
    assert set(genres) >= {"historical", "modern", "scifi", "fantasy",
                           "western", "gothic"}
    for genre in genres:
        block = titles[genre]
        assert "tiers" in block or "roles" in block, f"{genre} has neither shape"
        for category, tiers in block.get("tiers", {}).items():
            assert set(tiers) <= {"high", "mid", "low"}, f"{genre}/{category}"
        for category, entries in block.get("roles", {}).items():
            assert isinstance(entries, list) and entries, f"{genre}/{category}"

def test_stripped_ranks_are_recorded_where_they_landed():
    """Ranks recorded as stripped are known rank vocabulary."""
    titles = load("titles_by_genre.json")
    for genre in ("western", "modern"):
        stripped = titles[genre]["stripped_from_names"]
        assert stripped, f"{genre} records no stripped ranks"
        assert not set(stripped) - FORBIDDEN_IN_NAMES, (
            f"{genre} claims to have stripped something that is not a known rank"
        )

@pytest.mark.parametrize("bank_name,expected", sorted(REGISTER_BANKS.items()))
def test_registers_stay_in_sync_with_last_name(bank_name, expected):
    """A split bank's last_name is exactly its registers, with no overlap."""
    bank = load(f"{bank_name}_names.json")
    registers = bank["registers"]
    assert set(registers) == expected
    pools = [registers[r] for r in sorted(registers)]
    assert sorted(bank["last_name"]) == sorted(sum(pools, []))
    assert not set(pools[0]) & set(pools[1]), (
        "a surname cannot be in both registers"
    )

def test_existing_scifi_bank_is_untouched():
    """The scifi syllable bank still loads."""
    scifi = load("scifi_syllables.json")
    assert set(scifi["first_name"]) == {"male", "female"}
    assert scifi["first_name"]["male"]["start"]
    assert scifi["last_name"]["start"]

from novel_agent.tools.name_generator import NameGenerator  # noqa: E402

@pytest.fixture
def gen():
    return NameGenerator(DATA_DIR)

@pytest.mark.parametrize("genre,expected", [
    ("historical adventure", "historical"),
    ("Victorian mystery", "victorian"),
    ("epic fantasy", "fantasy"),
    ("medieval fantasy", "fantasy"),       # order matters: fantasy beats historical
    ("medieval", "historical"),
    ("science fiction", "scifi"),
    ("gothic horror", "gothic"),
    ("crime thriller", "modern"),
    ("weird western", "western"),
    ("", "modern"),
    (None, "modern"),
    ("something nobody listed", "modern"),  # the old default branch gave scifi
])
def test_genre_routing(gen, genre, expected):
    assert gen._normalize_genre(genre) == expected

@pytest.mark.parametrize("genre,expected", [
    ("historical adventure set in 1871", "victorian"),
    ("1871 naval survey", "victorian"),
    ("a fantasy epic set in 1871", "fantasy"),   # a specific genre still wins
    ("science fiction, 2431", "scifi"),
])
def test_year_in_genre_sharpens_period(gen, genre, expected):
    assert gen._normalize_genre(genre) == expected

def test_drawn_bank_returns_whole_names(gen):
    """A drawn bank returns whole names drawn from its own lists."""
    bank = json.loads((DATA_DIR / "historical_names.json").read_text())
    result = gen.generate_name(gender="male", genre="historical adventure")
    assert result["first_name"] in bank["first_name"]["male"]
    assert result["last_name"] in bank["last_name"]

def test_unmatched_genre_no_longer_reaches_the_scifi_bank(gen):
    """An unmatched genre does not resolve to the scifi bank.

    Asserted on the resolved bank and the drawn name, not on syllable
    prefixes: three real historical surnames (Ashford, Ashby, Brandon) begin
    with a scifi start syllable, so a prefix check failed ~4% of runs on names
    that came from the right bank all along.
    """
    bank = json.loads((DATA_DIR / "historical_names.json").read_text())
    assert gen.resolve_person_bank("historical adventure") == "historical"
    result = gen.generate_name(gender="male", genre="historical adventure")
    assert result["last_name"] in bank["last_name"]

def test_register_selects_the_right_surname_pool(gen):
    bank = json.loads((DATA_DIR / "victorian_names.json").read_text())
    for register in ("gentry", "common"):
        result = gen.generate_name(gender="male", genre="victorian",
                                   register=register)
        assert result["last_name"] in bank["registers"][register]

def test_fantasy_coins_surnames_from_the_companion_bank(gen):
    """Fantasy surnames are coined from the syllable bank."""
    syl = json.loads((DATA_DIR / "fantasy_syllables.json").read_text())
    drawn = json.loads((DATA_DIR / "fantasy_names.json").read_text())
    result = gen.generate_name(gender="female", genre="epic fantasy")
    assert result["first_name"] in drawn["first_name"]["female"]
    assert any(result["last_name"].startswith(s)
               for s in syl["last_name"]["start"])

def test_given_names_are_preferred_unused_then_reused(gen):
    """Given names stay distinct until the pool is spent, then reuse."""
    bank = json.loads((DATA_DIR / "historical_names.json").read_text())
    pool = len(bank["first_name"]["male"])
    firsts = [gen.generate_name(gender="male", genre="historical")["first_name"]
              for _ in range(pool)]
    assert len(set(firsts)) == pool, "should exhaust the pool before repeating"
    assert gen.generate_name(gender="male", genre="historical")["first_name"]

def test_small_bank_does_not_raise_before_it_is_actually_full(gen):
    """A partly-used bank still yields every remaining combination."""
    bank = json.loads((DATA_DIR / "historical_names.json").read_text())
    total = len(bank["first_name"]["male"]) * len(bank["last_name"])
    names = [gen.generate_name(gender="male", genre="historical")["full_name"]
             for _ in range(total)]
    assert len(set(names)) == total

def test_a_genuinely_full_bank_raises(gen):
    bank = json.loads((DATA_DIR / "historical_names.json").read_text())
    total = len(bank["first_name"]["male"]) * len(bank["last_name"])
    for _ in range(total):
        gen.generate_name(gender="male", genre="historical")
    with pytest.raises(ValueError, match="exhausted"):
        gen.generate_name(gender="male", genre="historical")

def test_register_used_name_strips_a_leading_title(gen):
    """register_used_name strips a leading title."""
    gen.register_used_name("Captain Edward Gale")
    assert gen.used_first_names == {"Edward"}
    assert "Edward Gale" in gen.used_names

def test_drawn_banks_can_be_switched_off():
    """use_drawn_banks=False loads only the scifi bank."""
    old = NameGenerator(DATA_DIR, use_drawn_banks=False)
    assert set(old.banks) == {"scifi"}
    scifi = json.loads((DATA_DIR / "scifi_syllables.json").read_text())
    result = old.generate_name(gender="male", genre="historical adventure")
    assert any(result["last_name"].startswith(s)
               for s in scifi["last_name"]["start"])

def test_coined_scifi_path_is_unchanged(gen):
    scifi = json.loads((DATA_DIR / "scifi_syllables.json").read_text())
    result = gen.generate_name(gender="male", genre="science fiction")
    assert any(result["first_name"].startswith(s)
               for s in scifi["first_name"]["male"]["start"])

def test_title_is_prepended_and_gender_corrected(gen):
    result = gen.generate_name(gender="female", genre="victorian", title="Lord")
    assert result["title"] == "Lady"
    assert result["full_name"].startswith("Lady ")

PLACE_GENRES = ["victorian", "historical", "western", "gothic", "modern",
                "scifi", "fantasy"]

@pytest.mark.parametrize("genre", PLACE_GENRES)
def test_place_bank_shape(genre):
    bank = load("places_by_genre.json")[genre]
    assert bank["start"] and bank["end"] and bank["patterns"]
    assert all("{root}" in p for p in bank["patterns"])

@pytest.mark.parametrize("genre", PLACE_GENRES)
def test_places_come_from_the_genres_own_bank(gen, genre):
    """Place roots come from the genre's own place bank."""
    bank = load("places_by_genre.json")[genre]
    join = bank.get("join", "")
    for _ in range(40):
        root = gen.generate_place_name(genre=genre)["root"]
        stripped = root[0].lower() + root[1:]
        assert any(
            stripped.startswith(s.lower()) or stripped.startswith(s)
            for s in bank["start"]
        ), f"{root!r} did not come from the {genre} bank"
        if join:
            assert join in root

def test_victorian_and_scifi_places_do_not_overlap(gen):
    vic = {gen.generate_place_name(genre="victorian")["root"] for _ in range(200)}
    gen.reset_used_names()
    sci = {gen.generate_place_name(genre="science fiction")["root"] for _ in range(200)}
    assert not (vic & sci)

def test_place_root_never_doubles_an_element(gen):
    """A place root never repeats an element."""
    for genre in PLACE_GENRES:
        gen.reset_used_names()
        for _ in range(150):
            root = gen.generate_place_name(genre=genre)["root"]
            words = root.replace("-", " ").split()
            assert len(set(w.lower() for w in words)) == len(words), root
            assert not re.search(r"(?i)\b(\w{3,})\1\b", root), root

def test_descriptor_still_appends(gen):
    result = gen.generate_place_name(descriptor="Harbour", genre="victorian")
    assert result["full_name"].endswith(" Harbour")

def test_widened_banks_cleared_the_thin_threshold():
    for bank_name in ("historical", "western", "gothic"):
        bank = load(f"{bank_name}_names.json")
        assert len(bank["last_name"]) >= 60, bank_name


# --------------------------------------------------------------------------
# The author configures the banks; the LLM never chooses one.

def test_more_specific_genres_still_win(gen):
    """The new entries do not steal from the banks listed above them."""
    assert gen._normalize_genre("weird western") == "western"
    assert gen._normalize_genre("napoleonic campaign") == "historical"

@pytest.mark.parametrize("genre,expected", [
    ("romance", "modern"),          # "roman" used to swallow this
    ("romantic comedy", "modern"),
    ("roman britain", "historical"),
    ("ancient rome", "historical"),
])
def test_roman_no_longer_swallows_romance(gen, genre, expected):
    assert gen._normalize_genre(genre) == expected

def test_pinned_person_bank_beats_genre_routing():
    """names.person_bank overrides the genre for people, and only for people."""
    gen = NameGenerator(DATA_DIR, person_bank="victorian")
    victorian = load("victorian_names.json")
    result = gen.generate_name(gender="male", genre="space opera")
    assert result["first_name"] in victorian["first_name"]["male"]
    assert result["last_name"] in victorian["last_name"]
    # places still follow the story's genre, which is the point of the split
    assert gen.resolve_place_bank("space opera") == "scifi"

def test_pinned_place_and_title_banks_resolve_independently():
    gen = NameGenerator(DATA_DIR, place_bank="victorian", title_bank="western")
    assert gen.resolve_place_bank("space opera") == "victorian"
    assert gen.resolve_title_bank("space opera") == "western"
    assert gen.resolve_person_bank("space opera") == "scifi"

def test_auto_and_blank_mean_genre_routing():
    for value in ("auto", "AUTO", "", None):
        gen = NameGenerator(DATA_DIR, person_bank=value)
        assert gen.person_bank is None
        assert gen.resolve_person_bank("victorian mystery") == "victorian"

def test_an_unknown_bank_raises_and_names_the_valid_ones():
    with pytest.raises(ValueError) as excinfo:
        NameGenerator(DATA_DIR, person_bank="klingon")
    message = str(excinfo.value)
    assert "names.person_bank" in message
    for bank_name in ("victorian", "historical", "scifi"):
        assert bank_name in message

def test_pinning_a_drawn_bank_with_drawn_banks_off_raises():
    with pytest.raises(ValueError, match="use_drawn_banks"):
        NameGenerator(DATA_DIR, use_drawn_banks=False, person_bank="victorian")

def test_a_place_name_never_says_the_same_word_twice(gen):
    """A pattern prefix can repeat the root's own noun."""
    for genre in PLACE_GENRES:
        gen.reset_used_names()
        for _ in range(300):
            name = gen.generate_place_name(genre=genre)["full_name"]
            words = [w.lower() for w in name.replace("-", " ").split()]
            assert len(set(words)) == len(words), name

def test_config_block_maps_auto_to_the_generator(tmp_path):
    """bank_settings_from_config reads names.*, project file over global."""
    from novel_agent.configs.config import Config
    from novel_agent.tools.name_generator import bank_settings_from_config

    assert bank_settings_from_config(Config())["person_bank"] == "auto"

    config_path = tmp_path / "config.yaml"
    config_path.write_text("names:\n  person_bank: victorian\n", encoding="utf-8")
    settings = bank_settings_from_config(Config(str(config_path)))
    assert settings["person_bank"] == "victorian"
    assert settings["place_bank"] == "auto"
    assert NameGenerator(DATA_DIR, **settings).person_bank == "victorian"

# --------------------------------------------------------------------------
# name.generate no longer advertises a genre, so the model cannot pick a bank.

from novel_agent.tools.name_generator import NameGeneratorTool  # noqa: E402

def test_the_tool_does_not_offer_a_genre_parameter():
    tool = NameGeneratorTool(DATA_DIR, genre="victorian mystery")
    assert "genre" not in tool.parameters
    assert set(tool.parameters) == {"gender", "register", "title"}

def test_a_genre_argument_from_the_model_is_ignored():
    tool = NameGeneratorTool(DATA_DIR, genre="victorian mystery")
    victorian = load("victorian_names.json")
    result = tool.execute(gender="male", genre="epic fantasy")
    assert result["success"]
    assert result["last_name"] in victorian["last_name"]

def test_the_tool_describes_the_story_own_registers_and_titles():
    tool = NameGeneratorTool(DATA_DIR, genre="victorian mystery")
    assert "gentry" in tool.parameters["register"]["description"]
    assert "Roster" in tool.parameters["title"]["description"]

# --------------------------------------------------------------------------
# Titles: a roster to select from, not free text.

@pytest.mark.parametrize("genre", ["historical", "modern", "scifi", "fantasy",
                                   "western", "gothic", "victorian"])
def test_every_bank_genre_has_a_title_roster(gen, genre):
    roster = gen.titles_for_genre(genre)
    assert roster and all(titles for titles in roster.values())

def test_a_genre_with_no_title_block_borrows_the_historical_one(gen):
    assert gen.resolve_title_bank("victorian mystery") == "historical"
    assert gen.resolve_title_bank("space opera") == "scifi"

def test_a_title_outside_the_roster_is_dropped(gen):
    result = gen.generate_name(gender="male", genre="victorian",
                               title="Grand Zorblax")
    assert result["title"] == ""
    assert result["full_name"] == f"{result['first_name']} {result['last_name']}"

def test_a_near_miss_title_is_normalised(gen):
    result = gen.generate_name(gender="male", genre="victorian", title="Captian")
    assert result["title"] == "Captain"

def test_a_wrong_gender_title_with_no_pair_falls_back_to_neutral(gen):
    """Emperor has no map entry, so the tier's neutral rank is used."""
    result = gen.generate_name(gender="female", genre="historical",
                               title="Emperor")
    neutral = load("titles_by_genre.json")["historical"]["tiers"]["noble"]["high"]["neutral"]
    assert result["title"] in neutral

def test_a_genre_rank_is_stripped_from_a_recorded_name(gen):
    gen.register_used_name("Sheriff Tom Blake")
    assert gen.used_first_names == {"Tom"}
    assert "Tom Blake" in gen.used_names

def test_a_configured_register_is_the_default_for_every_name():
    gen = NameGenerator(DATA_DIR, person_bank="victorian", register="gentry")
    gentry = load("victorian_names.json")["registers"]["gentry"]
    for _ in range(10):
        assert gen.generate_name(gender="male", genre="victorian")["last_name"] in gentry

def test_an_unknown_register_falls_back_instead_of_failing(gen):
    bank = load("victorian_names.json")
    result = gen.generate_name(gender="male", genre="victorian", register="nonsense")
    assert result["last_name"] in bank["last_name"]
