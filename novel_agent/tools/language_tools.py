"""Native-language tools: one phrase or one word from an imported tongue.

These are the only way a constructed language reaches the prose as words.
The writer is never shown a word list; the planner requests a phrase of a
given kind, or a word for a given meaning, for one people, and only what it
requested lands in the writer prompt ("native speech available this scene",
see ``WriterContextBuilder``). Both tools are deterministic lookups in the
project's ``memory/languages.json``, written at ``novel new --world
--languages``: no LLM, no I/O after loading, no state.

The people is resolved sanitize-not-trust through ``NameGenerator.
resolve_people`` (id, people name, language name, near miss, or a people
name inside the text), the same resolution ``name.generate`` applies. A
people that resolves to nothing, or a meaning the lexicon lacks, is answered
with ``found: False`` and a note rather than an invented word, and the tools
never raise, because the plan executor halts the tick on an exception.
"""

from __future__ import annotations

import difflib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Tool
from .name_generator import NameGenerator

logger = logging.getLogger(__name__)

PHRASE_KINDS = ("greeting", "farewell", "thanks", "oath", "curse", "toast",
                "proverb", "question")

# With no phrasebook, language.phrase answers with the single word nearest the
# kind: the first of these English meanings the lexicon has. A two-word
# "phrase" pasted from the lexicon reads as gibberish ("water fire"), so the
# fallback is one word and says so.
KIND_WORDS: Dict[str, List[str]] = {
    "greeting": ["greetings", "hello", "welcome", "peace", "friend", "day"],
    "farewell": ["farewell", "goodbye", "go", "peace", "road", "night"],
    "thanks": ["thanks", "thank", "gratitude", "gift", "friend", "good"],
    "oath": ["oath", "swear", "promise", "truth", "god", "blood", "king"],
    "curse": ["curse", "death", "dog", "rot", "blood", "fire", "die"],
    "toast": ["health", "life", "drink", "wine", "friend", "king", "home"],
    "proverb": ["wisdom", "truth", "stone", "river", "time", "wind", "road"],
    "question": ["who", "what", "where", "why", "how", "when"],
}

WORD_MATCH_CUTOFF = 0.75   # difflib ratio for a near-meaning match


class LanguageLexicon:
    """The lexicon and phrasebook of every imported people, read once.

    ``memory/languages.json`` is the same file ``NameGenerator`` loads for
    names; this reads its ``lexicon`` and ``phrases`` arrays, which a bank
    written before they existed does not have (``has_words`` is then False
    and the tools are not registered).
    """

    def __init__(self, path: Optional[Path] = None, name_generator: Optional[NameGenerator] = None):
        self.path: Optional[Path] = None
        self.peoples: Dict[str, Dict[str, Any]] = {}
        self.name_generator = name_generator
        if path:
            self.load(path)

    def load(self, path) -> int:
        path = Path(path)
        if not path.exists():
            return 0
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        peoples: Dict[str, Dict[str, Any]] = {}
        for pid, bank in ((data or {}).get("peoples") or {}).items():
            if not isinstance(bank, dict):
                continue
            peoples[str(pid)] = {
                "people_name": bank.get("people_name") or str(pid),
                "language": bank.get("language") or "",
                "family": bank.get("family"),
                "family_name": bank.get("family_name") or "",
                "lexicon": [w for w in bank.get("lexicon") or []
                            if isinstance(w, dict) and w.get("english") and w.get("spelling")],
                "phrases": [p for p in bank.get("phrases") or []
                            if isinstance(p, dict) and p.get("text") and p.get("english")],
            }
        self.peoples = peoples
        self.path = path
        return len(peoples)

    @property
    def has_words(self) -> bool:
        """Whether any people has a lexicon to answer from."""
        return any(p["lexicon"] for p in self.peoples.values())

    def roster(self) -> List[str]:
        return [
            f"{b['people_name']} ({b['language']})" if b.get("language") else b["people_name"]
            for b in self.peoples.values()
        ]

    def resolve_people(self, people: Optional[str]) -> Optional[str]:
        """The people id ``people`` names, via ``NameGenerator.resolve_people``
        when a generator was given (it loaded the same file), else the same
        rule on this file's keys."""
        if self.name_generator is not None and self.name_generator.language_banks:
            pid = self.name_generator.resolve_people(people)
            return pid if pid in self.peoples else None
        key = (people or "").strip().lower()
        if not key:
            return None
        by_key: Dict[str, str] = {}
        for pid, bank in self.peoples.items():
            by_key.setdefault(pid.lower(), pid)
            by_key.setdefault((bank.get("people_name") or "").lower(), pid)
            if bank.get("language"):
                by_key.setdefault(bank["language"].lower(), pid)
        by_key.pop("", None)
        if key in by_key:
            return by_key[key]
        close = difflib.get_close_matches(key, list(by_key), n=1, cutoff=0.8)
        if close:
            return by_key[close[0]]
        for name, pid in by_key.items():
            if len(name) >= 4 and f" {name} " in f" {key} ":
                return pid
        return None

    def _header(self, pid: str) -> Dict[str, Any]:
        bank = self.peoples[pid]
        return {"people": pid, "people_name": bank["people_name"], "language": bank["language"]}

    def _unknown_people(self, people: Optional[str]) -> Dict[str, Any]:
        logger.warning("language tool: %r is no people with an imported language (%s)",
                       people, ", ".join(sorted(self.peoples)))
        return {
            "success": False, "found": False,
            "error": f"No imported language for {people!r}. Peoples: {'; '.join(self.roster())}.",
        }

    # ------------------------------------------------------------------ words

    def word(self, people: Optional[str], english: Optional[str]) -> Dict[str, Any]:
        """One word for an English meaning: exact match first, then the
        nearest meaning by difflib, else ``found: False``."""
        pid = self.resolve_people(people)
        if not pid:
            return self._unknown_people(people)
        wanted = (english or "").strip().lower()
        result: Dict[str, Any] = {"success": True, "found": False, "english": english or "",
                                  **self._header(pid)}
        lexicon = self.peoples[pid]["lexicon"]
        if not wanted or not lexicon:
            result["note"] = ("No meaning given." if not wanted else
                              f"{result['language']} has no lexicon in this project.")
            return result
        by_english: Dict[str, Dict[str, Any]] = {}
        for w in lexicon:
            by_english.setdefault(w["english"].strip().lower(), w)
        entry = by_english.get(wanted)
        approximate = False
        if entry is None:
            close = difflib.get_close_matches(wanted, list(by_english), n=1, cutoff=WORD_MATCH_CUTOFF)
            if not close:
                result["note"] = (f"{result['language']} has no word for '{english}' in its "
                                  "lexicon; do not coin one. Leave the thing unnamed or say it in English.")
                return result
            entry = by_english[close[0]]
            approximate = True
        result.update({
            "found": True,
            "word": entry["spelling"],
            "text": entry["spelling"],
            "ipa": entry.get("ipa") or "",
            "pos": entry.get("pos") or "",
            "matched_english": entry["english"],
            "gloss": entry["english"],
            "approximate": approximate,
        })
        if approximate:
            result["note"] = f"No word for '{english}'; the nearest meaning is '{entry['english']}'."
        return result

    # ---------------------------------------------------------------- phrases

    def phrase(self, people: Optional[str], kind: Optional[str]) -> Dict[str, Any]:
        """A phrase of ``kind`` from the people's phrasebook, the first of that
        kind (a people's phrasebook is fixed, so the same request gives the
        same phrase: a greeting a people uses is a greeting they always use).
        Without a phrasebook, the nearest single word, flagged ``word_only``."""
        pid = self.resolve_people(people)
        if not pid:
            return self._unknown_people(people)
        kind_key = (kind or "").strip().lower()
        bank = self.peoples[pid]
        result: Dict[str, Any] = {"success": True, "found": False, "kind": kind_key,
                                  **self._header(pid)}
        phrases = bank["phrases"]
        if phrases:
            of_kind = [p for p in phrases if (p.get("kind") or "").lower() == kind_key]
            if not of_kind and kind_key:
                kinds = sorted({(p.get("kind") or "").lower() for p in phrases})
                close = difflib.get_close_matches(kind_key, kinds, n=1, cutoff=0.6)
                if close:
                    of_kind = [p for p in phrases if (p.get("kind") or "").lower() == close[0]]
                    result["kind"] = close[0]
            if of_kind:
                p = of_kind[0]
                result.update({"found": True, "text": p["text"], "gloss": p.get("gloss") or "",
                               "english": p["english"], "word_only": False})
                return result
            result["note"] = (f"{bank['language']} has no {kind_key or 'such'} phrase; kinds: "
                              + ", ".join(sorted({p.get('kind') or '' for p in phrases})) + ".")
            return result
        # No phrasebook: one word, never a pasted pair.
        candidates = KIND_WORDS.get(kind_key, [])
        by_english = {w["english"].strip().lower(): w for w in reversed(bank["lexicon"])}
        entry = next((by_english[c] for c in candidates if c in by_english), None)
        if entry is None and kind_key and by_english:
            close = difflib.get_close_matches(kind_key, list(by_english), n=1, cutoff=WORD_MATCH_CUTOFF)
            if close:
                entry = by_english[close[0]]
        if entry is None:
            result["note"] = (f"{bank['language']} has no phrasebook in this project and no word "
                              f"near '{kind_key}'; do not coin a phrase.")
            return result
        result.update({
            "found": True, "word_only": True,
            "text": entry["spelling"], "word": entry["spelling"], "ipa": entry.get("ipa") or "",
            "gloss": entry["english"], "english": entry["english"],
            "note": (f"{bank['language']} has no phrasebook in this project; this is the single "
                     f"word '{entry['english']}', not a phrase. Use it alone, never string words together."),
        })
        return result


def _people_parameter(lexicon: LanguageLexicon) -> Dict[str, Any]:
    return {
        "type": "string",
        "description": ("The people whose tongue it is, by name "
                        "(peoples: " + "; ".join(lexicon.roster()) + ")."),
    }


class LanguagePhraseTool(Tool):
    """``language.phrase(people, kind)``: one set phrase in a people's tongue."""

    def __init__(self, lexicon: LanguageLexicon):
        self.lexicon = lexicon
        super().__init__(
            name="language.phrase",
            description=(
                "One set phrase in a people's own language (a greeting, farewell, "
                "thanks, oath, curse, toast, proverb or question) with its meaning, "
                "for a character of that people to say in the scene. Request at most "
                "one per scene, and only when a line of native speech is the point."
            ),
            parameters={
                "people": _people_parameter(lexicon),
                "kind": {
                    "type": "string",
                    "enum": list(PHRASE_KINDS),
                    "description": "What sort of phrase: " + ", ".join(PHRASE_KINDS) + ".",
                },
            },
        )

    def execute(self, people: str, kind: str = "greeting", **_ignored) -> Dict[str, Any]:
        try:
            return self.lexicon.phrase(people, kind)
        except Exception as e:  # never halt the tick
            logger.warning("language.phrase failed: %s", e)
            return {"success": False, "found": False, "error": str(e)}


class LanguageWordTool(Tool):
    """``language.word(people, english)``: one word with gloss and IPA."""

    def __init__(self, lexicon: LanguageLexicon):
        self.lexicon = lexicon
        super().__init__(
            name="language.word",
            description=(
                "One word in a people's own language for an English meaning, with "
                "its pronunciation. For a single native term the POV character would "
                "use (a title, a food, a thing with no English name). The lexicon is "
                "fixed: a meaning it lacks comes back found=false, so never coin one."
            ),
            parameters={
                "people": _people_parameter(lexicon),
                "english": {
                    "type": "string",
                    "description": "The English meaning wanted, one word (e.g. 'water', 'king', 'friend').",
                },
            },
        )

    def execute(self, people: str, english: str = "", **_ignored) -> Dict[str, Any]:
        try:
            return self.lexicon.word(people, english)
        except Exception as e:  # never halt the tick
            logger.warning("language.word failed: %s", e)
            return {"success": False, "found": False, "error": str(e)}


def language_tools_for(languages_file: Optional[Path],
                       name_generator: Optional[NameGenerator] = None) -> List[Tool]:
    """The ``language.*`` tools for a project, or [] when it imported no
    languages (or a bank written before lexicons were kept). Registered in
    both ``tick()`` and ``run()``; the planner only ever sees them when they
    can answer."""
    if not languages_file:
        return []
    try:
        lexicon = LanguageLexicon(languages_file, name_generator=name_generator)
    except Exception as e:
        logger.warning("language tools unavailable: %s", e)
        return []
    if not lexicon.has_words:
        return []
    return [LanguagePhraseTool(lexicon), LanguageWordTool(lexicon)]


def native_speech_from_results(execution_results: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """The native words and phrases this tick's plan actually requested.

    Reads ``language.phrase``/``language.word`` results out of the plan
    executor's ``actions_executed``; only ``found`` ones count, in plan order,
    de-duplicated by text. This is what the writer is handed, so the prose
    uses exactly what the planner asked for and nothing else.
    """
    out: List[Dict[str, str]] = []
    seen = set()
    for action in (execution_results or {}).get("actions_executed") or []:
        if not str(action.get("tool") or "").startswith("language."):
            continue
        result = action.get("result") or {}
        if not (result.get("success") and result.get("found") and result.get("text")):
            continue
        text = str(result["text"]).strip()
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        if action.get("tool") == "language.word" or result.get("word_only"):
            kind = "word"
        else:
            kind = str(result.get("kind") or "phrase")
        out.append({
            "text": text,
            "meaning": str(result.get("english") or result.get("gloss") or ""),
            "gloss": str(result.get("gloss") or ""),
            "ipa": str(result.get("ipa") or ""),
            "language": str(result.get("language") or ""),
            "kind": kind,
        })
    return out


def native_speech_section(items: List[Dict[str, str]]) -> str:
    """Render the requested native speech for the writer, or ''."""
    if not items:
        return ""
    lines = ["**Native speech available this scene** (what the plan asked for; use these "
             "exactly, and no other words in any of the world's tongues):"]
    for item in items:
        label = item["language"] + (f" {item['kind']}" if item.get("kind") and item["kind"] != "phrase" else "")
        detail = f"— {item['meaning']}" if item.get("meaning") else ""
        if item.get("kind") == "word" and item.get("ipa"):
            detail += f" /{item['ipa']}/"
        lines.append(f"- “{item['text']}” {detail} ({label.strip()})")
    return "\n".join(lines)
