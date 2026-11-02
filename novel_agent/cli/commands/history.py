"""History command: a novel's own git history (novel_agent/history.py)."""
import json
from pathlib import Path

from ... import history


def _current_tick(project_dir: Path) -> int:
    try:
        with open(project_dir / "state.json", "r", encoding="utf-8") as f:
            return int(json.load(f).get("current_tick", 0))
    except Exception:
        return 0


def enable_history_cmd(project_dir: Path) -> bool:
    """Turn history on for an existing novel. Idempotent. Returns success."""
    if history.has_repo(project_dir):
        print("✅ Version history is already on for this novel.")
        return True
    if not history.git_available():
        print("❌ git is not on the PATH; install git to use version history.")
        return False
    tick = _current_tick(project_dir)
    outcome = history.init(project_dir, message=f"history enabled at tick {tick}")
    if not outcome.get("ok"):
        print(f"❌ Could not enable version history: {outcome.get('reason')}")
        return False
    print(f"✅ Version history on, starting at tick {tick}.")
    print("   Everything before this point is one snapshot; every tick from now on is a commit.")
    print("   Read it with git in the novel folder: git log, git show, git diff.")
    return True


def show_history_cmd(project_dir: Path, limit: int = 10) -> None:
    """Print the most recent commits."""
    if not history.has_repo(project_dir):
        print("Version history is off for this novel. Turn it on with: novel history enable")
        return
    rows = history.recent(project_dir, limit)
    if not rows:
        print("No commits yet.")
        return
    print(f"🗂️  Last {len(rows)} commits (newest first):\n")
    for row in rows:
        print(f"   {row['hash']}  {row['date']}  {row['subject']}")
    print("\n   More: git log (or git log -p for the changes) in the novel folder.")
