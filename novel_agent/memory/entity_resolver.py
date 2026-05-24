"""Resolve LLM-supplied entity references to canonical IDs.

The LLM may reference an entity by its canonical ID (``C000``), by name
("Joran"), or by a nickname/alias. It may also hallucinate a reference that
matches nothing. This resolver maps any reference to a real entity ID, or
returns ``None`` so callers can drop the phantom rather than persist it.
"""

from typing import List, Optional, Tuple


class EntityResolver:
    """Map character/location references to canonical IDs against current memory."""

    def __init__(self, memory_manager):
        self.memory = memory_manager
        self._char_index = None
        self._loc_index = None

    def _char_idx(self) -> dict:
        if self._char_index is None:
            idx = {}
            for cid in self.memory.list_characters():
                c = self.memory.load_character(cid)
                if not c:
                    continue
                tokens = [cid, c.full_name, c.first_name, c.family_name]
                tokens += list(getattr(c, "nicknames", None) or [])
                for tok in tokens:
                    if tok and str(tok).strip():
                        idx.setdefault(str(tok).strip().lower(), cid)
            self._char_index = idx
        return self._char_index

    def _loc_idx(self) -> dict:
        if self._loc_index is None:
            idx = {}
            for lid in self.memory.list_locations():
                loc = self.memory.load_location(lid)
                if not loc:
                    continue
                tokens = [lid, loc.name] + list(getattr(loc, "aliases", None) or [])
                for tok in tokens:
                    if tok and str(tok).strip():
                        idx.setdefault(str(tok).strip().lower(), lid)
            self._loc_index = idx
        return self._loc_index

    def resolve_character(self, ref) -> Optional[str]:
        if not ref:
            return None
        return self._char_idx().get(str(ref).strip().lower())

    def resolve_location(self, ref) -> Optional[str]:
        if not ref:
            return None
        return self._loc_idx().get(str(ref).strip().lower())

    def resolve_beat(self, beat) -> Tuple[List[str], Optional[str]]:
        """Rewrite a beat's entity references in place to canonical IDs.

        Drops character references that resolve to nothing and clears an
        unresolved location. Returns ``(dropped_character_refs, dropped_location)``
        so the caller can log what was discarded.
        """
        resolved: List[str] = []
        dropped: List[str] = []
        for ref in (beat.characters_involved or []):
            cid = self.resolve_character(ref)
            if cid:
                if cid not in resolved:
                    resolved.append(cid)
            else:
                dropped.append(ref)
        beat.characters_involved = resolved

        dropped_location = None
        if beat.location:
            loc = self.resolve_location(beat.location)
            if loc:
                beat.location = loc
            else:
                dropped_location = beat.location
                beat.location = None

        return dropped, dropped_location
