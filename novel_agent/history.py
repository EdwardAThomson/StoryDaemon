"""Version history for a novel: one git repository per novel directory.

Each novel made with ``novel new`` is a git repository, and every tick ends
with a commit of what that tick wrote (``tick 15: S015 "The Vent" ...``). A
tick that fails partway gets its own commit (``tick 15 FAILED: ...``) of the
partial writes it left on disk, so the next successful tick's commit holds
only its own work. Nothing is ever rolled back: the vector index
(``memory/index/``) is not tracked, so resetting the files would leave the two
out of step, and ``novel run --retries`` already builds on whatever a failed
attempt left behind.

Rules every function here holds:

- **Never touch another repository.** Every git call passes ``--git-dir`` and
  ``--work-tree`` explicitly. A plain ``git -C <novel>`` climbs to a parent
  repository when the novel's own ``.git`` is missing, and would commit the
  novel into it.
- **Never depend on the user's git setup.** Commits carry their own identity
  (``StoryDaemon <storydaemon@localhost>``) and disable signing and hooks, so
  a machine with no git identity works, one set to sign commits does not
  prompt, and StoryDaemon's commits are told apart from the author's own.
- **Never cost a tick.** Every public function catches everything and reports
  failure as a return value; the tick hook prints one warning line.

On by default for new novels (``history.git``, default True); an existing
novel opts in with ``novel history enable``. Committing happens only when the
novel's own ``.git`` exists, so a novel that never had history is untouched.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUTHOR_NAME = "StoryDaemon"
AUTHOR_EMAIL = "storydaemon@localhost"

# What a novel's history does not track: the vector index is binary and
# rebuildable, prompts/ holds large debug dumps, checkpoints/ are full copies
# that would double the repository.
GITIGNORE = """\
# Written by StoryDaemon (novel_agent/history.py).
# The vector index is binary and rebuilt from the JSON files.
memory/index/
# Debug prompt dumps from --save-prompts.
prompts/
# Full-copy checkpoints; each one is tagged in the history instead.
checkpoints/
"""

_TIMEOUT = 60  # seconds per git call


class HistoryError(Exception):
    """A git call failed. Internal: public functions never let it escape."""


def git_available() -> bool:
    return shutil.which("git") is not None


def has_repo(project_dir) -> bool:
    """True when the novel has its OWN repository (``<novel>/.git``)."""
    return (Path(project_dir) / ".git").is_dir()


def _switched_off_in_project(project_dir) -> bool:
    """True when the novel's own config.yaml sets ``history: {git: false}``."""
    try:
        import yaml
        path = Path(project_dir) / "config.yaml"
        if not path.exists():
            return False
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return (data.get("history") or {}).get("git", True) is False
    except Exception:
        return False


def is_enabled(project_dir, config: Any = None) -> bool:
    """Commit for this novel? Needs ``history.git`` not false (the loaded
    config when given, else the novel's config.yaml), the novel's own
    ``.git``, and git on the PATH."""
    try:
        if config is not None:
            if config.get("history.git", True) is False:
                return False
        elif _switched_off_in_project(project_dir):
            return False
    except Exception:
        pass
    return has_repo(project_dir) and git_available()


def _git(project_dir, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    root = Path(project_dir).resolve()
    cmd = [
        "git",
        f"--git-dir={root / '.git'}",
        f"--work-tree={root}",
        "-c", f"user.name={AUTHOR_NAME}",
        "-c", f"user.email={AUTHOR_EMAIL}",
        "-c", "commit.gpgsign=false",
        "-c", "tag.gpgsign=false",
        "-c", "core.hooksPath=/dev/null",
        *args,
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                              timeout=_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise HistoryError(str(e)) from e
    if check and proc.returncode != 0:
        raise HistoryError((proc.stderr or proc.stdout).strip() or f"git {args[0]} failed")
    return proc


def _commit_all(project_dir, message: str) -> Optional[str]:
    """Stage everything (respecting .gitignore) and commit. Returns the short
    hash, or None when there was nothing to commit."""
    _git(project_dir, "add", "-A")
    if _git(project_dir, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return None
    _git(project_dir, "commit", "-q", "--no-verify", "-m", message)
    return _git(project_dir, "rev-parse", "--short", "HEAD").stdout.strip()


def init(project_dir, message: str = "novel created") -> Dict[str, Any]:
    """Make the novel a repository and commit its current files.

    A no-op (``ok`` with ``created: False``) when the novel already has its own
    repository. Never raises."""
    try:
        if not git_available():
            return {"ok": False, "reason": "git is not on the PATH"}
        root = Path(project_dir).resolve()
        if has_repo(root):
            return {"ok": True, "created": False, "commit": None}
        proc = subprocess.run(["git", "init", "-q", str(root)], capture_output=True,
                              text=True, timeout=_TIMEOUT)
        if proc.returncode != 0:
            raise HistoryError((proc.stderr or proc.stdout).strip())
        gitignore = root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(GITIGNORE, encoding="utf-8")
        return {"ok": True, "created": True, "commit": _commit_all(root, message)}
    except Exception as e:
        logger.warning(f"History init failed: {e}")
        return {"ok": False, "reason": str(e)}


def commit(project_dir, message: str) -> Dict[str, Any]:
    """Commit whatever changed, with ``message``. Never raises; ``commit`` is
    None when nothing changed."""
    try:
        if not is_enabled(project_dir):
            return {"ok": False, "reason": "history is off for this novel"}
        return {"ok": True, "commit": _commit_all(project_dir, message)}
    except Exception as e:
        logger.warning(f"History commit failed: {e}")
        return {"ok": False, "reason": str(e)}


def tag(project_dir, name: str) -> Dict[str, Any]:
    """Tag the current commit (used for checkpoints). Never raises."""
    try:
        if not is_enabled(project_dir):
            return {"ok": False, "reason": "history is off for this novel"}
        _git(project_dir, "tag", "-f", name)
        return {"ok": True, "tag": name}
    except Exception as e:
        logger.warning(f"History tag failed: {e}")
        return {"ok": False, "reason": str(e)}


def recent(project_dir, limit: int = 10) -> List[Dict[str, str]]:
    """The last ``limit`` commits, newest first: ``{hash, date, subject}``."""
    try:
        if not has_repo(project_dir):
            return []
        out = _git(project_dir, "log", f"-n{int(limit)}",
                   "--date=format:%Y-%m-%d %H:%M", "--format=%h%x09%ad%x09%s").stdout
        rows = []
        for line in out.splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                rows.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
        return rows
    except Exception as e:
        logger.warning(f"History log failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Commit messages
# ---------------------------------------------------------------------------

_STATUS_WORDS = {"dead": "died", "missing": "went missing", "alive": "returned",
                 "destroyed": "destroyed", "inaccessible": "cut off",
                 "intact": "restored"}


def _status_changes_at(memory, tick: int) -> List[str]:
    """``C001 died``-style notes for every status recorded at ``tick``."""
    notes = []
    try:
        from .memory.entity_status import status_record
        for list_ids, load in ((memory.list_characters, memory.load_character),
                               (memory.list_locations, memory.load_location)):
            for entity_id in sorted(list_ids()):
                entity = load(entity_id)
                record = status_record(entity) if entity is not None else {}
                if record and record.get("tick") == tick:
                    word = _STATUS_WORDS.get(record.get("status"), record.get("status"))
                    notes.append(f"{entity_id} {word}")
    except Exception as e:
        logger.debug(f"History: status notes skipped: {e}")
    return notes


def tick_message(tick: int, result: Dict[str, Any], memory=None) -> str:
    """``tick 15: S015 "The Vent" (pov C000, L005), 2,840 words | C001 died | loops +2 -1``.

    Built from the tick's result dict plus the committed scene; any piece that
    cannot be read is left out rather than guessed."""
    head = f"tick {tick}"
    scene_id = result.get("scene_id") or ""
    title = pov = loc = ""
    if memory is not None and scene_id:
        try:
            scene = memory.load_scene(scene_id)
            if scene is not None:
                title = (scene.title or "").strip()
                pov = scene.pov_character_id or ""
                loc = scene.location_id or ""
        except Exception:
            pass
    parts = [scene_id] if scene_id else []
    if title:
        parts.append(f'"{title}"')
    where = ", ".join(x for x in (f"pov {pov}" if pov else "", loc) if x)
    if where:
        parts.append(f"({where})")
    summary = " ".join(parts)
    words = result.get("word_count")
    if isinstance(words, int):
        summary = f"{summary}, {words:,} words" if summary else f"{words:,} words"
    segments = [f"{head}: {summary}" if summary else head]
    if memory is not None:
        segments.extend(_status_changes_at(memory, tick))
    stats = result.get("entities_updated") or {}
    created = stats.get("loops_created") or 0
    resolved = stats.get("loops_resolved") or 0
    if created or resolved:
        segments.append(f"loops +{created} -{resolved}")
    return " | ".join(segments)


def failed_message(tick: int, error: BaseException) -> str:
    text = " ".join(str(error).split()) or type(error).__name__
    if len(text) > 160:
        text = text[:157] + "..."
    return f"tick {tick} FAILED: {text}"


def commit_tick(project_dir, tick: int, result: Dict[str, Any], memory=None,
                config: Any = None) -> Optional[Dict[str, Any]]:
    """The tick hook for a successful tick. None when history is off."""
    if not is_enabled(project_dir, config):
        return None
    try:
        message = tick_message(tick, result, memory)
    except Exception:
        message = f"tick {tick}"
    return _safe_commit(project_dir, message)


def commit_failed(project_dir, tick: int, error: BaseException,
                  config: Any = None) -> Optional[Dict[str, Any]]:
    """The tick hook for a failed tick: commit its partial writes. None when
    history is off."""
    if not is_enabled(project_dir, config):
        return None
    return _safe_commit(project_dir, failed_message(tick, error))


def _safe_commit(project_dir, message: str) -> Dict[str, Any]:
    try:
        return {"ok": True, "commit": _commit_all(project_dir, message)}
    except Exception as e:
        logger.warning(f"History commit failed: {e}")
        return {"ok": False, "reason": str(e)}
