"""Human/agent-readable rendering of checkpoints.

Shared by the MCP tools and the `show` CLI subcommand (which the SessionStart
hook uses to inject the latest checkpoint into a fresh agent context).
"""

from __future__ import annotations

from .storage import Checkpoint


def format_checkpoint(cp: Checkpoint) -> str:
    origin = (
        "emergency pre-compaction snapshot (parsed from session transcript)"
        if cp.kind == "precompact"
        else "saved by the working agent"
    )
    return f"""# Resume point — step {cp.current_step}/{cp.total_steps} ({cp.step_status})

Last checkpoint: {cp.created_at} · session `{cp.session_id}` · {origin}
Project: {cp.project}

## The plan
{cp.plan}

## What was already done (do NOT redo this)
{cp.what_was_done}

## What remains in the current step (step {cp.current_step}) — continue HERE
{cp.what_remains}
"""


def format_checkpoint_line(cp: Checkpoint) -> str:
    summary = " ".join(cp.what_was_done.split())
    if len(summary) > 80:
        summary = summary[:77] + "..."
    kind = " [precompact]" if cp.kind == "precompact" else ""
    return (
        f"#{cp.id}  {cp.created_at}  session {cp.session_id}  "
        f"step {cp.current_step}/{cp.total_steps} ({cp.step_status}){kind}  — {summary}"
    )


def format_checkpoint_list(checkpoints: list[Checkpoint], project: str) -> str:
    if not checkpoints:
        return f"No checkpoints recorded for project {project}."
    lines = [f"Checkpoint history for {project} (newest first):", ""]
    lines += [format_checkpoint_line(cp) for cp in checkpoints]
    return "\n".join(lines)
