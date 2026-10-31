"""Consequences that stick: judged deaths and destruction (entity status).

The fact extractor proposes a status change (a character died or went
missing, a location was destroyed or cut off) with the sentence from the
scene that shows it. Because the change cannot be quietly undone (a dead
character leaves every roster), each claim is confirmed before it lands, by
the same pattern as judged loop closure (``loop_closure.py``):

1. Python checks the claim: a real id, a status valid for that kind of
   entity, a change from the current status, and evidence that actually
   occurs in the scene text.
2. A focused judge sees ONE claim and the scene and answers whether the
   scene shows it happening on the page (not threatened, feared, rumored or
   believed by a character).
3. Only then is the status written (``memory/entity_status.py``), with the
   evidence and the judge's reason, plus a history entry on the entity.

Python owns the consequences from there: rosters mark the entity, it cannot
be the POV or the scene location, and the writer's canon section lists it.
Gated by ``coherence.entity_status`` (default True); off means the extractor
is never asked and nothing changes. Nothing here may kill a tick.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..memory.entity_status import (allowed_statuses, entity_kind, set_status,
                                    status_of)

logger = logging.getLogger(__name__)

STATUS_CHANGE_RULES = """
Status changes: if, and only if, this scene SHOWS ON THE PAGE that a character
died or vanished, or that a place was destroyed or cut off, add a top-level
"status_changes" list:

  "status_changes": [
    {"id": "C003", "status": "dead", "evidence": "<one sentence copied exactly from the scene>"}
  ]

Character statuses: dead, missing, alive (alive only for someone shown alive
after being thought dead or missing). Location statuses: destroyed,
inaccessible, intact. Use the exact ids listed above. Leave it out for a
threat, a fear, a rumor, a plan, a dream, a near miss or an injury: only a
change that has actually happened by the end of the scene counts. A character
who is wounded or dying but still alive at the end is not dead and not
missing. Most scenes have none.
"""

# What the judge is asked to confirm, per status.
_STATUS_QUESTIONS = {
    "dead": "{name} dies or is killed in this scene",
    "missing": "{name} vanishes or is lost in this scene, with their fate unknown",
    "alive": "{name}, previously believed dead or missing, is shown alive in this scene",
    "destroyed": "{name} is destroyed in this scene",
    "inaccessible": "{name} becomes unreachable in this scene (sealed off, cut off, occupied or lost)",
    "intact": "{name}, previously destroyed or unreachable, is shown restored or reachable again in this scene",
}

STATUS_JUDGE_PROMPT = """You are checking one claim about a scene from a novel.

Claim: {question}.
The passage offered as evidence: "{evidence}"

Does the scene actually SHOW this happening, as a fact of the story by the end of the scene? Answer no if it is only threatened, feared, rumored, planned, assumed by a character without confirmation, dreamed, remembered from before, or a near miss.

{refine}Respond with JSON only: {{"confirmed": true or false, {status_field}"reason": "<one short sentence>"}}

Scene:
\"\"\"
{scene_text}
\"\"\""""


# A confirmed loss of one kind may be better described as the other: the
# extractor picks the label, but the judge reads the whole scene (live test,
# 2026-10-31: a crawlspace the prose called "destroyed", "a vented ruin" was
# recorded as inaccessible because that was the label claimed). Restorations
# (alive, intact) are not refined.
_REFINEMENTS = {
    "dead": ("dead", "missing"),
    "missing": ("dead", "missing"),
    "destroyed": ("destroyed", "inaccessible"),
    "inaccessible": ("destroyed", "inaccessible"),
}

_REFINE_TEXT = {
    "dead": ("If it is confirmed, also say which word fits the character at the end "
             "of the scene: \"dead\" (shown dead) or \"missing\" (gone, fate unknown).\n\n"),
    "destroyed": ("If it is confirmed, also say which word fits the place at the end "
                  "of the scene: \"destroyed\" (ruined, wrecked, collapsed, gone) or "
                  "\"inaccessible\" (still standing but sealed, cut off or occupied).\n\n"),
}
_REFINE_TEXT["missing"] = _REFINE_TEXT["dead"]
_REFINE_TEXT["inaccessible"] = _REFINE_TEXT["destroyed"]


def status_change_rules(config: Any = None) -> str:
    """The extraction-prompt rules, or "" when coherence.entity_status is off."""
    try:
        if config is not None and not config.get('coherence.entity_status', True):
            return ""
    except Exception:
        pass
    return STATUS_CHANGE_RULES


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[‘’“”\"'`*_]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def evidence_in_scene(evidence: str, scene_text: str) -> bool:
    """True when the quoted evidence occurs in the scene (quotes, emphasis,
    case and whitespace ignored). A paraphrase does not count: the claim must
    point at the page."""
    needle = _normalize(evidence).rstrip(".!?")
    return len(needle) >= 12 and needle in _normalize(scene_text)


def _parse_judgment(response: str) -> Dict[str, Any]:
    start = response.find("{")
    end = response.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("no JSON object in status judgment")
    data = json.loads(response[start:end])
    verdict = data["confirmed"]
    if isinstance(verdict, str):
        verdict = {"true": True, "yes": True, "false": False, "no": False}.get(
            verdict.strip().lower(), verdict)
    if not isinstance(verdict, bool):
        raise ValueError(f"unusable status verdict {data['confirmed']!r}")
    result = {"confirmed": verdict, "reason": str(data.get("reason", "")).strip()}
    status = str(data.get("status") or "").strip().lower()
    if status:
        result["status"] = status
    return result


def judge_status_change(llm, name: str, status: str, evidence: str,
                        scene_text: str, config) -> Optional[Dict[str, Any]]:
    """One small LLM check of one claim. Retries once; None on a double
    failure, which the caller must treat as NOT confirmed. Never raises."""
    if llm is None:
        return None
    chars = config.get('coherence.loop_closure_scene_chars', 12000)
    choices = _REFINEMENTS.get(status)
    prompt = STATUS_JUDGE_PROMPT.format(
        question=_STATUS_QUESTIONS[status].format(name=name),
        refine=_REFINE_TEXT.get(status, ""),
        status_field=(f'"status": "{choices[0]}" or "{choices[1]}", ' if choices else ""),
        evidence=(evidence or "").replace('"', "'"),
        scene_text=(scene_text or "")[:chars])
    max_tokens = config.get('coherence.loop_closure_max_tokens', 200)
    for attempt in (1, 2):
        try:
            return _parse_judgment(llm.generate(prompt, max_tokens=max_tokens))
        except Exception as e:
            if attempt == 2:
                logger.error(f"Status-change judge failed after retry: {e}")
            else:
                logger.warning(f"Status-change judge failed, retrying: {e}")
    return None


def _load(memory, entity_id: str):
    try:
        if entity_id.startswith("C"):
            return memory.load_character(entity_id)
        if entity_id.startswith("L"):
            return memory.load_location(entity_id)
    except Exception:
        return None
    return None


def _save(memory, entity) -> None:
    if entity_kind(entity) == "character":
        memory.save_character(entity)
    else:
        memory.save_location(entity)


def apply_status_changes(llm, memory, claims: List[Dict[str, Any]], tick: int,
                         scene_id: str, scene_text: str, config) -> Optional[Dict[str, Any]]:
    """Check, judge and apply the extractor's status-change claims.

    Returns ``{"claimed", "applied", "refused"}`` (each refusal names its
    reason), or None when the gate is off or nothing was claimed. At most
    ``coherence.status_changes_judged_cap`` claims (default 3) are judged per
    tick. Never raises.
    """
    try:
        if not config.get('coherence.entity_status', True):
            return None
        claims = [c for c in (claims or []) if isinstance(c, dict)]
        if not claims:
            return None
        cap = config.get('coherence.status_changes_judged_cap', 3) or 0
        result = {"claimed": len(claims), "applied": [], "refused": []}
        judged = 0
        for claim in claims:
            entity_id = str(claim.get("id") or "").strip()
            status = str(claim.get("status") or "").strip().lower()
            evidence = str(claim.get("evidence") or "").strip()

            def refuse(why):
                result["refused"].append({"id": entity_id, "status": status, "why": why})

            entity = _load(memory, entity_id) if entity_id else None
            if entity is None:
                refuse("unknown id")
                continue
            if status not in allowed_statuses(entity_kind(entity)):
                refuse("status not valid for this kind of entity")
                continue
            if status == status_of(entity):
                refuse("unchanged")
                continue
            if not evidence_in_scene(evidence, scene_text):
                refuse("evidence not found in the scene")
                continue
            if judged >= cap:
                refuse("over the per-tick judge cap")
                continue
            judged += 1
            name = getattr(entity, "display_name", None) or getattr(entity, "name", entity_id)
            verdict = judge_status_change(llm, name, status, evidence, scene_text, config)
            if not verdict or not verdict.get("confirmed"):
                refuse("judge: " + ((verdict or {}).get("reason") or "no verdict"))
                continue
            refined = verdict.get("status")
            if refined in _REFINEMENTS.get(status, ()) and refined != status_of(entity):
                status = refined
            if not set_status(entity, status, tick, scene_id, evidence, verdict.get("reason", "")):
                refuse("could not record")
                continue
            _record_history(entity, status, tick, scene_id)
            _save(memory, entity)
            result["applied"].append({"id": entity_id, "status": status,
                                      "reason": verdict.get("reason", "")})
            logger.info(f"Status change applied: {entity_id} -> {status} ({scene_id})")
        return result
    except Exception as e:
        logger.warning(f"Status changes skipped: {e}")
        return None


def _record_history(entity, status: str, tick: int, scene_id: str) -> None:
    try:
        from ..memory.entities import HistoryEntry
        entity.history.append(HistoryEntry(
            tick=tick, scene_id=scene_id, changes={"status": status},
            summary=f"Status became {status} in scene {scene_id}"))
    except Exception:
        pass
