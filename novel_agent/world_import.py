"""Import a worldgen world file as StoryDaemon entities.

The sibling ``world-building`` generator writes a JSON world with a ``schema``
field of ``worldgen/sector@0.1`` (an SF star sector) or ``worldgen/region@0.1``
(a fantasy region). ``map_world`` turns one of those into the locations,
factions and lore items a novel should start with, plus a setting summary for
the story foundation. It is pure: no LLM calls, no I/O beyond ``load_world``,
and it never assigns ids. Ids come from ``MemoryManager.generate_id`` when
``persist_world`` writes the entities, so the counters stay the single source
of truth and an imported world cannot collide with what the ticks mint later.

Mapping decisions worth knowing:

- A realm or faction becomes a ``Faction``. Its magic or psionic tradition is
  folded into the summary rather than filed as separate lore, because a
  tradition is how that culture practises the one shared system, and the
  planner reads factions as a list of summaries.
- Settlements and worlds become ``Location`` records, which are the stages a
  scene can be set on. Cities always qualify; towns above a population floor,
  capped at a count, so a region with forty towns does not swamp the planner's
  location list.
- Named mountain ranges and rivers become *lore*, not locations. A
  ``Location`` is a scene stage (it has occupants, a time of day, a tension
  level); a 400 km river or a range of a hundred hexes is geography a scene
  refers to, not a place a scene is set in. As ``geography`` lore they reach
  the planner through semantic search and the lore list without displacing
  the settlements from the location roster.
- Story hooks become lore tagged ``hook`` so the planner can pick them up as
  pressure without any of them being promoted to the premise by code.
- Sector chokepoints are read from the lanes (which carry distance and travel
  time) and merged with the matching ``chokepoint`` hook (which says who holds
  the ends), so a chokepoint is one lore item, not two.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)

SECTOR_SCHEMA = "worldgen/sector@0.1"
REGION_SCHEMA = "worldgen/region@0.1"
SUPPORTED_SCHEMAS = (SECTOR_SCHEMA, REGION_SCHEMA)

# Defaults for the import knobs; the CLI reads the real values through
# Config.get('world.*', default) and passes them in.
DEFAULT_MAX_TOWNS = 12
DEFAULT_TOWN_POPULATION_MIN = 3000
DEFAULT_MAX_WORLDS = 24

WORLDGEN_TAG = "worldgen"


class UnknownWorldSchemaError(ValueError):
    """The file is not a worldgen world this importer understands."""


@dataclass
class WorldEntities:
    """What a world file maps to, before any id is assigned.

    Each entry in ``locations``/``factions``/``lore`` is the keyword dict for
    the matching entity dataclass minus ``id``. ``persist_world`` adds the id.
    """
    schema: str
    kind: str                      # "region" | "sector"
    genre: str                     # foundation genre text
    setting: str                   # foundation setting text
    locations: List[Dict[str, Any]] = field(default_factory=list)
    factions: List[Dict[str, Any]] = field(default_factory=list)
    lore: List[Dict[str, Any]] = field(default_factory=list)
    title: str = ""                # a short name for the world

    def counts(self) -> Dict[str, int]:
        return {
            "locations": len(self.locations),
            "factions": len(self.factions),
            "lore": len(self.lore),
        }


# ============================================================================
# Loading and dispatch
# ============================================================================

def load_world(path: str) -> Dict[str, Any]:
    """Read a worldgen JSON file and check it carries a known schema."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise UnknownWorldSchemaError(
            f"{path} is not a worldgen world: expected a JSON object")
    schema_of(data)  # raises on an unknown schema
    return data


def schema_of(data: Dict[str, Any]) -> str:
    """Return the world's schema string or raise UnknownWorldSchemaError."""
    schema = data.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        raise UnknownWorldSchemaError(
            f"Unknown world schema {schema!r}; expected one of "
            f"{', '.join(SUPPORTED_SCHEMAS)}")
    return schema


def map_world(
    data: Dict[str, Any],
    max_towns: int = DEFAULT_MAX_TOWNS,
    town_population_min: int = DEFAULT_TOWN_POPULATION_MIN,
    max_worlds: int = DEFAULT_MAX_WORLDS,
) -> WorldEntities:
    """Dispatch on the schema and return the entities to create."""
    schema = schema_of(data)
    if schema == REGION_SCHEMA:
        return map_region(data, max_towns=max_towns,
                          town_population_min=town_population_min)
    return map_sector(data, max_worlds=max_worlds)


# ============================================================================
# Shared helpers
# ============================================================================

def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _join(items: List[str], last: str = "and") -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {last} " + items[-1]


def _fmt_int(n: Any) -> str:
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return str(n)


def describe_magic(m: Dict[str, Any]) -> str:
    """Render a magic/psionics system as one paragraph.

    A Python counterpart of worldgen's ``describeMagic``: same axes, same
    order, not byte-identical. Every field is optional so a hand-edited or
    older world still renders.
    """
    name = _cap(m.get("name") or "the magic")
    source = m.get("source") or "an unknown source"
    source_phrase = _SOURCE_PHRASE.get(source, source)
    hardness = m.get("hardness")
    grammar = m.get("grammar") or {}
    kind = grammar.get("kind")
    if kind == "verb × noun" and grammar.get("verbs") and grammar.get("nouns"):
        what = (f"Its workings pair a verb ({', '.join(grammar['verbs'])}) "
                f"with a subject ({', '.join(grammar['nouns'])}).")
    elif kind == "elements" and grammar.get("nouns"):
        what = f"It works through {', '.join(grammar['nouns'])}."
    elif kind == "discrete powers" and grammar.get("powers"):
        what = f"Its powers: {', '.join(grammar['powers'])}."
    elif grammar.get("domain"):
        what = f"It works on anything touching {grammar['domain']}."
    else:
        what = ""

    parts = [f"{name} draws on {source_phrase}" + (f" ({hardness})." if hardness else ".")]
    if m.get("whoCanUse"):
        clause = f"{_cap(m['whoCanUse'])} can use it"
        if m.get("rarity"):
            clause += f"; users are {m['rarity']}"
        if m.get("learning"):
            clause += f", and learn through {m['learning']}"
        parts.append(clause + ".")
    if m.get("mechanism"):
        parts.append(f"It works by {m['mechanism']}.")
    if what:
        parts.append(what)
    cannot = m.get("cannotDo") or []
    if cannot:
        parts.append(f"It cannot {' or '.join(cannot)}.")
    cost = (m.get("cost") or {}).get("description")
    if cost:
        parts.append(f"It {cost}.")
    if m.get("backfire"):
        parts.append(f"When it goes wrong: {m['backfire']}.")
    if m.get("castingTime") or m.get("duration"):
        timing = []
        if m.get("castingTime"):
            timing.append(f"a working takes {m['castingTime']}")
        if m.get("duration"):
            timing.append(f"lasts {m['duration']}")
        parts.append(_cap(_join(timing)) + ".")
    if m.get("socialStatus"):
        parts.append(f"Society: {m['socialStatus']}.")
    balance = m.get("balance") or []
    if balance:
        parts.append(f"Why users don't rule: {'; '.join(balance)}.")
    spells = [s.get("name") for s in (m.get("spells") or []) if s.get("name")]
    if spells:
        parts.append(f"Known workings include {_join(spells[:5])}.")
    return " ".join(parts)


_SOURCE_PHRASE = {
    "life energy": "the user's own life energy",
    "ambient field": "an ambient field that runs through the world",
    "patron": "a patron who grants it",
    "consumable substance": "a substance the user consumes",
    "belief": "belief, which bends reality",
    "emotion": "strong emotion",
    "true names": "the true names of things",
    "the heavens": "the heavens",
    "artifacts": "artifacts",
    "mutation": "a mutation",
    "precursor technology": "precursor technology",
    "exotic matter": "exotic matter",
}


def _tradition_sentence(magic: Dict[str, Any], culture_id: str,
                        system_word: str) -> str:
    """How one culture practises the shared magic, as a sentence or ''."""
    for t in magic.get("traditions") or []:
        if t.get("cultureId") == culture_id:
            name = t.get("name") or "its own way"
            bits = []
            if t.get("mechanism"):
                bits.append(f"worked through {t['mechanism']}")
            if t.get("socialStatus"):
                bits.append(t["socialStatus"])
            if t.get("organisation"):
                bits.append(f"organised as {t['organisation']}")
            detail = f" ({'; '.join(bits)})" if bits else ""
            return f"Practises {system_word} as {name}{detail}."
    return ""


def _lore(content: str, category: str, lore_type: str = "fact",
          importance: str = "normal", tags: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "lore_type": lore_type,
        "content": content,
        "category": category,
        "source_scene_id": "",
        "tick": 0,
        "importance": importance,
        "tags": [WORLDGEN_TAG] + [t for t in (tags or []) if t],
    }


def _hook_lore(hook: Dict[str, Any], extra_tags: Optional[List[str]] = None) -> Dict[str, Any]:
    kind = hook.get("kind") or "hook"
    return _lore(
        hook.get("summary") or "",
        category="story_hook",
        lore_type="fact",
        importance="important",
        tags=["hook", kind] + (extra_tags or []),
    )


# ============================================================================
# Region (fantasy)
# ============================================================================

def map_region(
    data: Dict[str, Any],
    max_towns: int = DEFAULT_MAX_TOWNS,
    town_population_min: int = DEFAULT_TOWN_POPULATION_MIN,
) -> WorldEntities:
    """Map a ``worldgen/region@0.1`` world."""
    realms = data.get("realms") or []
    settlements = data.get("settlements") or []
    rivers = data.get("rivers") or []
    ranges = data.get("ranges") or []
    magic = data.get("magic") or {}
    calendar = data.get("calendar") or {}
    cells = data.get("cells") or {}
    grid = data.get("grid") or {}
    cell_km = float(grid.get("cellKm") or (data.get("params") or {}).get("cellKm") or 0)
    biomes = cells.get("biome") or []
    river_flow = cells.get("river") or []
    realm_of_cell = cells.get("realm") or []

    realm_by_id = {r.get("id"): r for r in realms}
    realm_name = {rid: _realm_full_name(r) for rid, r in realm_by_id.items()}
    realm_by_index = {i: r for i, r in enumerate(realms)}
    settlement_by_id = {s.get("id"): s for s in settlements}

    def biome_at(cell: Any) -> str:
        try:
            return biomes[int(cell)]
        except (TypeError, ValueError, IndexError):
            return ""

    def realm_at(cell: Any) -> Optional[Dict[str, Any]]:
        try:
            idx = int(realm_of_cell[int(cell)])
        except (TypeError, ValueError, IndexError):
            return None
        return realm_by_index.get(idx)

    # ---- factions: one per realm ----
    factions: List[Dict[str, Any]] = []
    for realm in realms:
        gov = realm.get("government") or {}
        full = _realm_full_name(realm)
        ruler = realm.get("ruler") or {}
        capital = settlement_by_id.get(realm.get("capitalSettlementId")) or {}
        sentences = []
        form = gov.get("form") or "realm"
        family = gov.get("family")
        head = f"{full}, a {form.lower()}"
        if family and family.lower() != form.lower():
            head += f" ({family.lower()})"
        if capital.get("name"):
            head += f" ruled from {capital['name']}"
        sentences.append(head + ".")
        if ruler.get("name"):
            sentences.append(
                f"Its ruler is {ruler.get('title') or gov.get('rulerTitle') or 'the ruler'} "
                f"{ruler['name']}.")
        if gov.get("succession") or gov.get("genderLaw"):
            law = f"Succession: {gov['succession']}" if gov.get("succession") else "Succession"
            if gov.get("genderLaw"):
                law += f"; the throne is {gov['genderLaw']}"
            sentences.append(law + ".")
        size = []
        if realm.get("population"):
            size.append(f"{_fmt_int(realm['population'])} people")
        if realm.get("areaKm2"):
            size.append(f"about {_fmt_int(realm['areaKm2'])} km²")
        if size:
            coast = ", with a coast" if realm.get("coastal") else ", landlocked"
            sentences.append(_cap(_join(size)) + coast + ".")
        trad = _tradition_sentence(magic, realm.get("id"), "magic")
        if trad:
            sentences.append(trad)
        factions.append({
            "name": full,
            "org_type": "government",
            "summary": " ".join(sentences),
            "mandate_objectives": [],
            "influence_domains": [s for s in [capital.get("name")] if s],
            "assets_resources": [],
            "methods_tactics": [],
            "importance": "high",
            "tags": [WORLDGEN_TAG, "realm", (family or "").lower()],
            "metadata": {"worldgen": {
                "id": realm.get("id"),
                "name": realm.get("name"),
                "government": gov,
                "ruler": ruler,
                "capital_settlement_id": realm.get("capitalSettlementId"),
                "language_sample": (realm.get("language") or {}).get("sample", []),
            }},
        })

    # ---- locations: cities, and the largest towns above the floor ----
    cities = [s for s in settlements if s.get("kind") == "city"]
    towns = sorted(
        (s for s in settlements
         if s.get("kind") == "town" and (s.get("population") or 0) >= town_population_min),
        key=lambda s: -(s.get("population") or 0),
    )[:max(0, int(max_towns))]
    locations: List[Dict[str, Any]] = []
    for s in sorted(cities, key=lambda s: -(s.get("population") or 0)) + towns:
        site = list(s.get("site") or [])
        realm = realm_by_id.get(s.get("realmId"))
        biome = biome_at(s.get("cell"))
        on_river = "river" in site or _flow_at(river_flow, s.get("cell")) > 0
        on_coast = "coast" in site
        kind = s.get("kind") or "settlement"
        pop = s.get("population")
        head = f"{s.get('name')}, a {kind}"
        if pop:
            head += f" of {_fmt_int(pop)} people"
        if realm:
            head += (" and capital of " if s.get("capital") else " in ") + _realm_full_name(realm)
        else:
            head += " in land no realm holds"
        head += "."
        place = []
        if biome:
            place.append(f"it lies on {biome}")
        if "river mouth" in site:
            place.append("at a river mouth")
        elif on_river:
            place.append("on a river")
        if on_coast:
            place.append("on the coast")
        if "lake shore" in site:
            place.append("on a lake shore")
        if "confluence" in site:
            place.append("at a confluence")
        desc = head + (" " + _cap(_join(place)) + "." if place else "")
        features = [f for f in site if f not in ("river", "coast")]
        features = site if not features else features
        locations.append({
            "name": s.get("name") or s.get("id") or "Unnamed settlement",
            "description": desc,
            "atmosphere": "",
            "features": list(dict.fromkeys(features)),
            "significance": (f"Capital of {_realm_full_name(realm)}" if realm and s.get("capital")
                             else (f"{_cap(kind)} of {_realm_full_name(realm)}" if realm
                                   else f"Unclaimed {kind}")),
            "metadata": {"worldgen": {
                "id": s.get("id"),
                "kind": kind,
                "population": pop,
                "realm_id": s.get("realmId"),
                "realm_name": realm_name.get(s.get("realmId")),
                "capital": bool(s.get("capital")),
                "biome": biome,
                "river": on_river,
                "coast": on_coast,
                "cell": s.get("cell"),
            }},
        })

    # ---- lore ----
    lore: List[Dict[str, Any]] = []
    if magic:
        lore.append(_lore(describe_magic(magic), category="magic", lore_type="rule",
                          importance="critical", tags=["magic"]))
    cal = _calendar_sentence(calendar)
    if cal:
        lore.append(_lore(cal, category="calendar", tags=["calendar"]))

    for rng in ranges:
        rcells = rng.get("cells") or []
        bits = [f"The {rng.get('name')} is a mountain range"]
        if rng.get("peakM"):
            bits[0] += f" rising to {_fmt_int(rng['peakM'])} m"
        if rcells and cell_km:
            bits[0] += f", covering about {_fmt_int(len(rcells) * cell_km * cell_km)} km²"
        bits[0] += "."
        borders = _realm_names_at(rcells, realm_at)
        if borders:
            bits.append(f"It touches {_join(borders)}.")
        lore.append(_lore(" ".join(bits), category="geography", tags=["range", rng.get("id") or ""]))

    for river in rivers:
        rcells = river.get("cells") or []
        head = f"The {river.get('name')} is a river"
        if rcells and cell_km:
            head += f" of about {_fmt_int(len(rcells) * cell_km)} km"
        mouth_biome = biome_at(river.get("mouthCell"))
        if mouth_biome in ("deep ocean", "shallow sea"):
            head += " running to the sea"
        elif mouth_biome == "lake":
            head += " running to a lake"
        if river.get("dischargeM3s"):
            head += f", {_fmt_int(river['dischargeM3s'])} m³/s at its mouth"
        head += "."
        bits = [head]
        through = _realm_names_at(rcells, realm_at)
        if through:
            bits.append(f"It flows through {_join(through)}.")
        cell_set = set(int(c) for c in rcells if isinstance(c, (int, float)))
        towns_on = [s.get("name") for s in settlements if s.get("cell") in cell_set and s.get("name")]
        if towns_on:
            bits.append(f"{_join(towns_on)} stand{'s' if len(towns_on) == 1 else ''} on its banks.")
        lore.append(_lore(" ".join(bits), category="geography", tags=["river", river.get("id") or ""]))

    for hook in data.get("hooks") or []:
        lore.append(_hook_lore(hook))

    # ---- setting summary ----
    width = grid.get("width") or 0
    height = grid.get("height") or 0
    stats = data.get("stats") or {}
    realm_list = _join([realm_name[r.get("id")] for r in realms])
    sentences = []
    span = ""
    if width and height and cell_km:
        span = f" about {_fmt_int(width * cell_km)} by {_fmt_int(height * cell_km)} km"
    world_type = (data.get("params") or {}).get("worldType")
    shape = f" ({world_type})" if world_type else ""
    sentences.append(f"A fantasy region{span}{shape} with {len(realms)} realm{'s' if len(realms) != 1 else ''}"
                     + (f": {realm_list}." if realm_list else "."))
    n_cities = stats.get("cities", len(cities))
    n_towns = stats.get("towns", sum(1 for s in settlements if s.get("kind") == "town"))
    pop = stats.get("population")
    sentences.append(f"{n_cities} cities and {n_towns} towns"
                     + (f", {_fmt_int(pop)} people in all" if pop else "") + ".")
    if magic.get("name"):
        sentences.append(f"Magic is {magic['name']}"
                         + (f", {magic['hardness']}" if magic.get("hardness") else "")
                         + (f", drawn from {_SOURCE_PHRASE.get(magic['source'], magic['source'])}"
                            if magic.get("source") else "") + ".")
    if cal:
        sentences.append(cal)
    names = [r.get("name") for r in realms if r.get("name")]
    title = f"The realms of {_join(names[:3])}" if names else "A fantasy region"
    return WorldEntities(
        schema=REGION_SCHEMA, kind="region", genre="fantasy",
        setting=" ".join(sentences), locations=locations, factions=factions,
        lore=lore, title=title,
    )


def _realm_full_name(realm: Dict[str, Any]) -> str:
    gov = realm.get("government") or {}
    return gov.get("fullName") or realm.get("name") or realm.get("id") or "Unnamed realm"


def _flow_at(river_flow: List[Any], cell: Any) -> float:
    try:
        return float(river_flow[int(cell)])
    except (TypeError, ValueError, IndexError):
        return 0.0


def _realm_names_at(cells: List[Any], realm_at) -> List[str]:
    seen: Dict[str, str] = {}
    for c in cells:
        realm = realm_at(c)
        if realm and realm.get("id") not in seen:
            seen[realm.get("id")] = _realm_full_name(realm)
    return list(seen.values())


def _calendar_sentence(calendar: Dict[str, Any]) -> str:
    if not calendar:
        return ""
    bits = []
    if calendar.get("leapRuleText"):
        # The rule text already states the day count ("345 days; drop a day
        # every 161 years"), so it is the whole sentence.
        bits.append(f"A year is {calendar['leapRuleText']}.")
    elif calendar.get("yearDays"):
        bits.append(f"A year is {_fmt_int(calendar['yearDays'])} days.")
    moons = calendar.get("moons") or []
    if moons:
        descs = [f"{m.get('name')} ({_fmt_int(m.get('synodicDays'))} days)" if m.get("synodicDays")
                 else str(m.get("name")) for m in moons]
        n = len(moons)
        bits.append(f"There {'is one moon' if n == 1 else f'are {n} moons'}: {_join(descs)}.")
    if calendar.get("monthsPerYear"):
        bits.append(f"About {calendar['monthsPerYear']:.0f} months to the year.")
    if calendar.get("moonAlignmentDays"):
        bits.append(f"The moons align every {_fmt_int(calendar['moonAlignmentDays'])} days.")
    return " ".join(bits)


# ============================================================================
# Sector (science fiction)
# ============================================================================

_ORG_TYPE_KEYWORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("consortium", ("trade", "exchange", "merchant", "mercantile", "consortium", "cartel")),
    ("corporate", ("corporate", "corporation", "company", "conglomerate")),
    ("cult", ("sect", "cult", "church", "spiritual", "covenant", "theocra", "order")),
    ("ai_collective", ("hive", "collective", "machine", "ai ", "synthetic", "unity")),
    ("criminal", ("syndicate", "pirate", "criminal", "raider")),
    ("guild", ("guild",)),
]


def faction_org_type(faction_type: str) -> str:
    """Map a worldgen faction type to StoryDaemon's org_type vocabulary."""
    t = (faction_type or "").lower() + " "
    for org_type, keys in _ORG_TYPE_KEYWORDS:
        if any(k in t for k in keys):
            return org_type
    return "government"


def map_sector(data: Dict[str, Any], max_worlds: int = DEFAULT_MAX_WORLDS) -> WorldEntities:
    """Map a ``worldgen/sector@0.1`` world."""
    systems = data.get("systems") or []
    lanes = data.get("lanes") or []
    factions_in = data.get("factions") or []
    fleets = data.get("fleets") or []
    psionics = data.get("psionics") or {}
    hooks = data.get("hooks") or []

    system_by_id = {s.get("id"): s for s in systems}
    faction_by_id = {f.get("id"): f for f in factions_in}
    faction_name = {fid: f.get("name") or fid for fid, f in faction_by_id.items()}

    def system_name(sid: Any) -> str:
        s = system_by_id.get(sid)
        return (s.get("name") if s else None) or str(sid)

    # ---- factions ----
    factions: List[Dict[str, Any]] = []
    for f in factions_in:
        military = f.get("military") or {}
        capital = system_by_id.get(f.get("capitalSystemId")) or {}
        homeworld = _planet_by_id(capital, f.get("homeworldId"))
        main_world = homeworld or _main_world(capital)
        own_fleets = [fl for fl in fleets if fl.get("factionId") == f.get("id")]
        sentences = [f"{f.get('name')}, a {(f.get('type') or 'power').lower()}"
                     + (f" ({_join(list(f.get('traits') or []))})" if f.get("traits") else "") + "."]
        if military.get("techLevelName"):
            sentences.append(f"Tech level: {military['techLevelName']}.")
        if capital.get("name"):
            cap = f"Capital: the {capital['name']} system"
            if homeworld:
                cap += f", homeworld {_world_name(homeworld)}"
            elif main_world:
                cap += f", main world {_world_name(main_world)}"
            sentences.append(cap + ".")
        size = []
        if military.get("populationMillions"):
            size.append(f"{_fmt_int(military['populationMillions'])} million people")
        n_sys = len(f.get("systemIds") or [])
        if n_sys:
            size.append(f"{n_sys} system{'s' if n_sys != 1 else ''}")
        if size:
            sentences.append(_cap(_join(size, "across")) + ".")
        ships = military.get("ships") or {}
        total = sum(int(v) for v in ships.values() if isinstance(v, (int, float)))
        if total or own_fleets:
            fleet = f"Fleet: {total} ships"
            if ships:
                fleet += " (" + ", ".join(f"{int(v)} {k}" for k, v in ships.items()) + ")"
            if own_fleets:
                stations = [f"{fl.get('name')} ({fl.get('role')}) at {system_name(fl.get('stationSystemId'))}"
                            for fl in own_fleets]
                fleet += f" in {len(own_fleets)} fleet{'s' if len(own_fleets) != 1 else ''}: {_join(stations)}"
            sentences.append(fleet + ".")
        trad = _tradition_sentence(psionics, f.get("id"), "psionics")
        if trad:
            sentences.append(trad)
        factions.append({
            "name": f.get("name") or f.get("id") or "Unnamed faction",
            "org_type": faction_org_type(f.get("type") or ""),
            "summary": " ".join(sentences),
            "mandate_objectives": [],
            "influence_domains": [s for s in [capital.get("name")] if s],
            "assets_resources": [fl.get("name") for fl in own_fleets if fl.get("name")],
            "methods_tactics": [],
            "importance": "high",
            "tags": [WORLDGEN_TAG, "faction", (f.get("type") or "").lower()] + [t for t in (f.get("traits") or [])],
            "metadata": {"worldgen": {
                "id": f.get("id"),
                "type": f.get("type"),
                "traits": list(f.get("traits") or []),
                "capital_system_id": f.get("capitalSystemId"),
                "homeworld_id": f.get("homeworldId"),
                "tech_level": military.get("techLevel"),
                "tech_level_name": military.get("techLevelName"),
                "system_count": n_sys,
                "language_sample": (f.get("language") or {}).get("sample", []),
            }},
        })

    # ---- locations: capital main worlds and every temperate world ----
    chosen: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for f in factions_in:
        capital = system_by_id.get(f.get("capitalSystemId"))
        if not capital:
            continue
        world = _planet_by_id(capital, f.get("homeworldId")) or _main_world(capital)
        if world and world.get("id"):
            chosen[world["id"]] = (capital, world)
    for s in systems:
        for p in s.get("planets") or []:
            if p.get("habitability") == "temperate" and p.get("id"):
                chosen.setdefault(p["id"], (s, p))

    def rank(item: Tuple[Dict[str, Any], Dict[str, Any]]) -> Tuple[int, float]:
        _, p = item
        colony = p.get("colony") or {}
        is_home = 0 if colony.get("kind") == "homeworld" else 1
        return (is_home, -float(colony.get("populationMillions") or 0))

    locations: List[Dict[str, Any]] = []
    for system, planet in sorted(chosen.values(), key=rank)[:max(0, int(max_worlds))]:
        locations.append(_world_location(system, planet, faction_name))

    # ---- lore ----
    lore: List[Dict[str, Any]] = []
    if psionics:
        lore.append(_lore(describe_magic(psionics), category="psionics", lore_type="rule",
                          importance="critical", tags=["psionics"]))
    ftl = (data.get("params") or {}).get("ftl") or {}
    if ftl:
        lore.append(_lore(_ftl_sentence(ftl), category="technology", lore_type="rule",
                          importance="important", tags=["ftl", "travel"]))

    hook_by_lane: Dict[str, Dict[str, Any]] = {}
    for h in hooks:
        if h.get("kind") == "chokepoint":
            for eid in h.get("entityIds") or []:
                if isinstance(eid, str) and eid.startswith("L"):
                    hook_by_lane.setdefault(eid, h)
    merged_hooks = set()
    for lane in lanes:
        if not lane.get("chokepoint"):
            continue
        a, b = system_name(lane.get("a")), system_name(lane.get("b"))
        hook = hook_by_lane.get(lane.get("id"))
        if hook:
            merged_hooks.add(id(hook))
            head = hook.get("summary") or f"The {a}–{b} lane is a chokepoint."
        else:
            head = f"The {a}–{b} lane is a chokepoint: losing it would split the lane network."
        detail = []
        if lane.get("distanceLy"):
            detail.append(f"{float(lane['distanceLy']):.1f} ly")
        if lane.get("travelDays"):
            detail.append(f"{_fmt_int(lane['travelDays'])} days' travel")
        content = head + (f" The jump is {_join(detail)}." if detail else "")
        lore.append(_lore(content, category="starlanes", importance="important",
                          tags=["chokepoint", "hook", lane.get("id") or ""]))
    for h in hooks:
        if id(h) in merged_hooks:
            continue
        lore.append(_hook_lore(h))

    # ---- setting summary ----
    stats = data.get("stats") or {}
    n_systems = stats.get("systems", len(systems))
    names = [faction_name[f.get("id")] for f in factions_in]
    sentences = [f"A sector of {n_systems} star systems linked by {_ftl_phrase(ftl)}, "
                 f"held by {len(factions_in)} faction{'s' if len(factions_in) != 1 else ''}"
                 + (f": {_join(names)}." if names else ".")]
    temperate = stats.get("temperateWorlds", sum(
        1 for s in systems for p in s.get("planets") or [] if p.get("habitability") == "temperate"))
    chokepoints = stats.get("chokepoints", sum(1 for l in lanes if l.get("chokepoint")))
    unclaimed = stats.get("unclaimedSystems")
    bits = [f"{temperate} temperate world{'s' if temperate != 1 else ''}",
            f"{chokepoints} chokepoint lane{'s' if chokepoints != 1 else ''}"]
    if unclaimed is not None:
        bits.append(f"{unclaimed} unclaimed system{'s' if unclaimed != 1 else ''}")
    sentences.append(_cap(_join(bits)) + ".")
    if psionics.get("name"):
        sentences.append(f"Psionics, {psionics['name']}, "
                         + (f"{psionics['hardness']}, " if psionics.get("hardness") else "")
                         + f"drawn from {_SOURCE_PHRASE.get(psionics.get('source'), psionics.get('source') or 'an unknown source')}.")
    title = f"The {_join(names[:3])} sector" if names else "A star sector"
    return WorldEntities(
        schema=SECTOR_SCHEMA, kind="sector", genre="science fiction",
        setting=" ".join(sentences), locations=locations, factions=factions,
        lore=lore, title=title,
    )


def _planet_by_id(system: Dict[str, Any], planet_id: Any) -> Optional[Dict[str, Any]]:
    if not planet_id:
        return None
    for p in system.get("planets") or []:
        if p.get("id") == planet_id:
            return p
    return None


_HABITABILITY_RANK = {"temperate": 0, "marginal": 1, "hostile": 2}


def _main_world(system: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The capital's main world when no homeworld is named: the most
    habitable, then the most populous, planet in the system."""
    planets = list(system.get("planets") or [])
    if not planets:
        return None
    return sorted(planets, key=lambda p: (
        _HABITABILITY_RANK.get(p.get("habitability"), 3),
        -float((p.get("colony") or {}).get("populationMillions") or 0),
    ))[0]


def _world_name(planet: Dict[str, Any]) -> str:
    return planet.get("localName") or planet.get("designation") or planet.get("id") or "Unnamed world"


def _world_location(system: Dict[str, Any], planet: Dict[str, Any],
                    faction_name: Dict[str, str]) -> Dict[str, Any]:
    star = system.get("star") or {}
    name = _world_name(planet)
    colony = planet.get("colony") or {}
    owner = faction_name.get(system.get("ownerFactionId") or colony.get("factionId"))
    designation = planet.get("designation")
    head = name
    if designation and designation != name:
        head += f" ({designation})"
    head += f", a {planet.get('habitability') or ''} {planet.get('kind') or 'world'} world".replace("  ", " ")
    if system.get("name"):
        head += f" of the {system['name']} system"
        if star.get("spectralType"):
            head += f", a {star['spectralType']} star"
    sentences = [head + "."]
    phys = []
    if planet.get("gravityG") is not None:
        phys.append(f"gravity {float(planet['gravityG']):.2f} g")
    if planet.get("surfaceK") is not None:
        phys.append(f"mean surface {float(planet['surfaceK']) - 273.15:.0f} °C")
    if planet.get("atmosphere"):
        phys.append(f"a {planet['atmosphere']} atmosphere")
    if phys:
        sentences.append(_cap(_join(phys)) + ".")
    if planet.get("tidallyLocked"):
        sentences.append("It is tidally locked, one face always to its star.")
    elif planet.get("rotationHours"):
        sentences.append(f"The day is {float(planet['rotationHours']):.1f} hours.")
    if planet.get("yearEarthDays"):
        year = f"The year is {float(planet['yearEarthDays']):.0f} Earth days"
        leap = (planet.get("calendar") or {}).get("leapRuleText") or ""
        # worldgen writes "165 days; drop a day every 5 years": the count is
        # in local days, which is not the Earth-day figure.
        local, _, rule = leap.partition("; ")
        if local and rule:
            year += f" ({local} local; {rule})"
        elif leap:
            year += f" ({leap} local)"
        sentences.append(year + ".")
    if planet.get("plantColour"):
        sentences.append(f"Its plants are {planet['plantColour']}.")
    if colony:
        kind = colony.get("kind") or "colony"
        hold = f"{_cap(kind)} of {owner or 'an unknown faction'}"
        if colony.get("populationMillions"):
            hold += f", {_fmt_int(colony['populationMillions'])} million people"
        gov = colony.get("governor") or {}
        if gov.get("name"):
            hold += f", governed by {gov.get('title') or 'Governor'} {gov['name']}"
        if colony.get("resources"):
            hold += f"; resources {colony['resources'].lower()}"
        if colony.get("stability") is not None:
            hold += f", stability {_fmt_int(colony['stability'])}/100"
        sentences.append(hold + ".")
    elif owner:
        sentences.append(f"In {owner} space, unsettled.")
    else:
        sentences.append("Claimed by no faction.")

    if colony.get("kind") == "homeworld":
        significance = f"Homeworld and capital of {owner}" if owner else "A homeworld"
    elif colony:
        significance = f"{_cap(colony.get('kind') or 'colony')} of {owner}" if owner else "A settled world"
    else:
        significance = "An unclaimed temperate world"
    features = []
    if planet.get("tidallyLocked"):
        features.append("tidally locked")
    if planet.get("plantColour"):
        features.append(f"{planet['plantColour']} plants")
    moons = planet.get("moons") or []
    if moons:
        features.append(f"{len(moons)} moon{'s' if len(moons) != 1 else ''}")
    return {
        "name": name,
        "aliases": [designation] if designation and designation != name else [],
        "description": " ".join(sentences),
        "atmosphere": "",
        "features": features,
        "significance": significance,
        "metadata": {"worldgen": {
            "id": planet.get("id"),
            "designation": designation,
            "system_id": system.get("id"),
            "system_name": system.get("name"),
            "star": star.get("spectralType"),
            "owner_faction_id": system.get("ownerFactionId"),
            "owner_faction_name": owner,
            "habitability": planet.get("habitability"),
            "kind": planet.get("kind"),
            "colony_kind": colony.get("kind"),
            "population_millions": colony.get("populationMillions"),
            "gravity_g": planet.get("gravityG"),
            "surface_k": planet.get("surfaceK"),
            "tidally_locked": planet.get("tidallyLocked"),
            "plant_colour": planet.get("plantColour"),
        }},
    }


def _ftl_phrase(ftl: Dict[str, Any]) -> str:
    kind = ftl.get("kind") or "FTL"
    if kind == "jump":
        bits = []
        if ftl.get("maxJumpLy"):
            bits.append(f"up to {ftl['maxJumpLy']} ly")
        if ftl.get("daysPerJump"):
            bits.append(f"{ftl['daysPerJump']} days per jump")
        return "jump lanes" + (f" ({', '.join(bits)})" if bits else "")
    return f"{kind} lanes"


def _ftl_sentence(ftl: Dict[str, Any]) -> str:
    s = f"Faster-than-light travel is by {_ftl_phrase(ftl)}: ships move only along the lanes between neighbouring stars"
    if ftl.get("maxJumpLy"):
        s += f", never more than {ftl['maxJumpLy']} light-years in one jump"
    s += "."
    if ftl.get("daysPerJump"):
        s += f" Each jump takes {ftl['daysPerJump']} days."
    return s


# ============================================================================
# Persistence
# ============================================================================

def persist_world(memory, entities: WorldEntities, vector_store=None) -> Dict[str, Any]:
    """Write the mapped entities through a MemoryManager and index them.

    Ids come from ``memory.generate_id``/``generate_lore_id``. A location
    whose name already exists (case-insensitive) is skipped rather than
    duplicated, the same rule ``location.generate`` applies. Indexing is
    best-effort: a vector-store failure is logged and the entity stays on
    disk, where the next tick's re-index picks it up.
    """
    from .memory.entities import Faction, Location, Lore

    created = {"locations": [], "factions": [], "lore": [], "skipped_locations": []}

    existing_names = set()
    try:
        for lid in memory.list_locations():
            loc = memory.load_location(lid)
            if loc and loc.name:
                existing_names.add(loc.name.strip().lower())
    except Exception as e:  # a fresh project has none; never fatal
        logger.debug(f"Could not list existing locations: {e}")

    for spec in entities.locations:
        key = (spec.get("name") or "").strip().lower()
        if key and key in existing_names:
            created["skipped_locations"].append(spec.get("name"))
            continue
        existing_names.add(key)
        location = Location(id=memory.generate_id("location"), **spec)
        memory.save_location(location)
        _index(vector_store, "index_location", location)
        created["locations"].append(location.id)

    for spec in entities.factions:
        faction = Faction(id=memory.generate_id("faction"), **spec)
        memory.save_faction(faction)
        _index(vector_store, "index_faction", faction)
        created["factions"].append(faction.id)

    for spec in entities.lore:
        lore = Lore(id=memory.generate_lore_id(), **spec)
        memory.save_lore(lore)
        _index(vector_store, "index_lore", lore)
        created["lore"].append(lore.id)

    return created


def _index(vector_store, method: str, entity) -> None:
    if vector_store is None:
        return
    try:
        getattr(vector_store, method)(entity)
    except Exception as e:
        logger.warning(f"Could not index {getattr(entity, 'id', '?')} ({method}): {e}")


def world_state_record(path: str, entities: WorldEntities,
                       created: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The ``world`` block written to state.json."""
    record = {
        "source": os.path.abspath(path),
        "schema": entities.schema,
        "kind": entities.kind,
        "title": entities.title,
        "imported_at": datetime.now().isoformat(),
        "counts": entities.counts(),
    }
    if created:
        record["entity_ids"] = {
            "locations": list(created.get("locations", [])),
            "factions": list(created.get("factions", [])),
            "lore": list(created.get("lore", [])),
        }
    return record
