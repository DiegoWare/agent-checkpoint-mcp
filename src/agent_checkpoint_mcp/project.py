"""Project-root detection and per-OS data directory resolution.

No external dependencies: this replicates the small slice of platformdirs
behavior we need.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "agent-checkpoint-mcp"
DATA_HOME_ENV = "AGENT_CHECKPOINT_HOME"


def data_dir() -> Path:
    """Directory where the SQLite database lives. Created on demand."""
    override = os.environ.get(DATA_HOME_ENV)
    if override:
        base = Path(override).expanduser()
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        root = Path(local) if local else Path.home() / "AppData" / "Local"
        base = root / APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        root = Path(xdg) if xdg else Path.home() / ".local" / "share"
        base = root / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "checkpoints.db"


def find_project_root(start: str | os.PathLike[str] | None = None) -> str:
    """Canonical project identifier for a working directory.

    Walks up from `start` (default: cwd) to the nearest directory containing
    `.git`, so checkpoints saved from a subdirectory of a repo land under the
    same project key. Falls back to the resolved start directory itself.
    """
    path = Path(start) if start else Path.cwd()
    path = path.expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return str(candidate)
    return str(path)
