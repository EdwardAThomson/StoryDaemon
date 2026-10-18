"""Lifecycle status for characters and locations: who is dead, what is gone.

Until this existed a character had no way to die. "Dead" could land in the
free-text ``physical_state``, which nothing read for decisions, so a dead
character stayed in every roster: the beat generator could cast them, the
planner could pick them as POV and the writer listed them as cast. A ship or a
city destroyed on the page stayed a valid scene location the same way.

Status lives under ``entity.metadata["status"]`` so no entity schema changes
and every legacy file loads unchanged; an entity with no record has the
default status (``alive`` / ``intact``). Changes are proposed by the fact
extractor and confirmed by a focused judge before they land
(``agent/consequences.py``); this module only reads and writes the record.
"""

from typing import Any, Dict, Optional

CHARACTER_STATUSES = ("alive", "dead", "missing")
LOCATION_STATUSES = ("intact", "destroyed", "inaccessible")
DEFAULT_STATUS = {"character": "alive", "location": "intact"}

# How a status reads in a roster: " (deceased, S012)".
_LABELS = {"dead": "deceased", "missing": "missing", "destroyed": "destroyed",
           "inaccessible": "inaccessible"}


def entity_kind(entity) -> str:
    """"character" or "location" (by the entity's ``type``, else its id prefix)."""
    kind = getattr(entity, "type", "") or ""
    if kind in DEFAULT_STATUS:
        return kind
    entity_id = str(getattr(entity, "id", "") or "")
    return "location" if entity_id.startswith("L") else "character"


def allowed_statuses(kind: str) -> tuple:
    return CHARACTER_STATUSES if kind == "character" else LOCATION_STATUSES


def status_record(entity) -> Dict[str, Any]:
    metadata = getattr(entity, "metadata", None) or {}
    record = metadata.get("status") if isinstance(metadata, dict) else None
    return record if isinstance(record, dict) else {}


def status_of(entity) -> str:
    """The entity's current status; the kind's default when none is recorded."""
    if entity is None:
        return ""
    return status_record(entity).get("status") or DEFAULT_STATUS[entity_kind(entity)]


def is_unavailable(entity) -> bool:
    """True when the entity can no longer appear on the page as itself:
    a dead or missing character, a destroyed or inaccessible location."""
    if entity is None:
        return False
    return status_of(entity) != DEFAULT_STATUS[entity_kind(entity)]


def status_note(entity) -> str:
    """" (deceased, S012)" for a non-default status, else ""."""
    if not is_unavailable(entity):
        return ""
    record = status_record(entity)
    label = _LABELS.get(record.get("status"), record.get("status", ""))
    scene = record.get("scene_id")
    return f" ({label}, {scene})" if scene else f" ({label})"


def set_status(entity, status: str, tick: Optional[int], scene_id: str,
               evidence: str, reason: str = "") -> bool:
    """Record a status change on the entity (caller saves it). False when the
    status is not valid for the kind or is unchanged."""
    kind = entity_kind(entity)
    if status not in allowed_statuses(kind) or status == status_of(entity):
        return False
    previous = status_of(entity)
    if not isinstance(getattr(entity, "metadata", None), dict):
        entity.metadata = {}
    entity.metadata["status"] = {
        "status": status,
        "previous": previous,
        "tick": tick,
        "scene_id": scene_id,
        "evidence": evidence,
        "reason": reason,
    }
    return True
