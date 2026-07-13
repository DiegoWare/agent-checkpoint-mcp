"""MCP server exposing the checkpoint tools over stdio."""

from __future__ import annotations

import uuid

from mcp.server.fastmcp import FastMCP

from .project import find_project_root
from .render import format_checkpoint, format_checkpoint_list
from .storage import Storage, VALID_STATUSES

# One session id per server process: MCP clients spawn a fresh server per
# agent session, so this groups checkpoints written by the same session.
SESSION_ID = uuid.uuid4().hex[:8]

mcp = FastMCP(
    "agent-checkpoint",
    instructions=(
        "Local checkpoint store so a multi-step plan survives session cuts "
        "(context limit, quota). Call save_checkpoint after EVERY completed "
        "sub-task, and call get_checkpoint at the start of a task that looks "
        "like a continuation of earlier work."
    ),
)

_storage: Storage | None = None


def _store() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


def _project(project_dir: str | None) -> str:
    return find_project_root(project_dir)


@mcp.tool()
def save_checkpoint(
    plan: str,
    current_step: int,
    total_steps: int,
    step_status: str,
    what_was_done: str,
    what_remains: str,
    project_dir: str | None = None,
) -> str:
    """Save a progress checkpoint so any future agent session can resume exactly here.

    Call this after EVERY concrete sub-task (a file edited, a test passing, a
    command run) — not only when a numbered step finishes. Frequent, small
    checkpoints are the point: if the session dies mid-step, the next agent
    resumes from the last sub-task instead of redoing the whole step.

    Args:
        plan: The full numbered plan being executed (all steps, verbatim).
        current_step: 1-based number of the step currently being worked on.
        total_steps: Total number of steps in the plan.
        step_status: "in_progress", "done", or "blocked" — status of current_step.
        what_was_done: Everything completed so far, across all steps, specific
            enough that another agent will not redo any of it.
        what_remains: What is still missing IN THE CURRENT STEP, specific enough
            to be the very next action (plus any known remaining steps).
        project_dir: Optional project directory override; defaults to the
            server's working directory (walking up to the nearest .git root).
    """
    cp = _store().save(
        project=_project(project_dir),
        session_id=SESSION_ID,
        plan=plan,
        current_step=current_step,
        total_steps=total_steps,
        step_status=step_status,
        what_was_done=what_was_done,
        what_remains=what_remains,
    )
    return (
        f"Checkpoint #{cp.id} saved at {cp.created_at} "
        f"(step {cp.current_step}/{cp.total_steps}, {cp.step_status})."
    )


@mcp.tool()
def get_checkpoint(project_dir: str | None = None) -> str:
    """Get the latest checkpoint for this project — where to resume from.

    Call this FIRST when a task looks like a continuation of earlier work
    (e.g. after a session was cut off). It returns the plan, the current step,
    what was already done (do not redo it), and the exact next action.

    Args:
        project_dir: Optional project directory override; defaults to the
            server's working directory (walking up to the nearest .git root).
    """
    project = _project(project_dir)
    cp = _store().latest(project)
    if cp is None:
        return (
            f"No checkpoint exists for project {project}. "
            "This is a fresh start — no earlier progress to resume."
        )
    return format_checkpoint(cp)


@mcp.tool()
def list_checkpoints(limit: int = 20, project_dir: str | None = None) -> str:
    """List the checkpoint history for this project, newest first, with timestamps.

    Args:
        limit: Maximum number of checkpoints to return (default 20).
        project_dir: Optional project directory override; defaults to the
            server's working directory (walking up to the nearest .git root).
    """
    project = _project(project_dir)
    return format_checkpoint_list(_store().list(project, limit=limit), project)


@mcp.tool()
def clear_checkpoints(confirm: bool = False, project_dir: str | None = None) -> str:
    """Delete all checkpoints for this project. Requires confirm=true.

    Called without confirm, it only reports how many checkpoints would be
    deleted; ask the user before calling again with confirm=true.

    Args:
        confirm: Must be true to actually delete. False = dry run.
        project_dir: Optional project directory override; defaults to the
            server's working directory (walking up to the nearest .git root).
    """
    project = _project(project_dir)
    store = _store()
    n = store.count(project)
    if n == 0:
        return f"Nothing to clear: no checkpoints for project {project}."
    if not confirm:
        return (
            f"This would delete {n} checkpoint(s) for project {project}. "
            "Confirm with the user, then call clear_checkpoints again with "
            "confirm=true."
        )
    deleted = store.clear(project)
    return f"Deleted {deleted} checkpoint(s) for project {project}."


def run() -> None:
    mcp.run()  # stdio transport
