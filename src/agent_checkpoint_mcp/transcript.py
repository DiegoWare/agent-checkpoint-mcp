"""Extract an emergency checkpoint from a Claude Code transcript JSONL.

The PreCompact hook cannot instruct the model to call save_checkpoint (hooks
can only run commands or block). Instead, the hook pipes its JSON input to
`agent-checkpoint-mcp precompact-snapshot`, and we reconstruct a best-effort
checkpoint locally from the transcript: the most recent TodoWrite state gives
plan/step structure, and the last assistant messages give narrative context.
No LLM, no network — plain JSONL parsing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_ASSISTANT_CHARS = 1500


def _iter_entries(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _content_blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    content = entry.get("message", {}).get("content")
    return content if isinstance(content, list) else []


def extract_snapshot(transcript_path: str | Path) -> dict[str, Any] | None:
    """Return checkpoint fields recovered from the transcript, or None if empty."""
    path = Path(transcript_path)
    if not path.exists():
        return None

    last_todos: list[dict[str, Any]] | None = None
    assistant_texts: list[str] = []

    for entry in _iter_entries(path):
        if entry.get("type") != "assistant":
            continue
        for block in _content_blocks(entry):
            btype = block.get("type")
            if btype == "tool_use" and block.get("name") == "TodoWrite":
                todos = block.get("input", {}).get("todos")
                if isinstance(todos, list) and todos:
                    last_todos = todos
            elif btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    assistant_texts.append(text)

    if last_todos is None and not assistant_texts:
        return None

    recent = "\n---\n".join(assistant_texts[-3:])[-MAX_ASSISTANT_CHARS:]

    if last_todos:
        done = [t["content"] for t in last_todos if t.get("status") == "completed"]
        active = [t["content"] for t in last_todos if t.get("status") == "in_progress"]
        pending = [t["content"] for t in last_todos if t.get("status") == "pending"]
        total = len(last_todos)
        current = len(done) + 1 if (active or pending) else total
        plan = "\n".join(f"{i}. {t['content']}" for i, t in enumerate(last_todos, 1))
        what_was_done = (
            "\n".join(f"- {d}" for d in done) if done else "- (no step completed yet)"
        )
        remains_parts = []
        if active:
            remains_parts.append("In progress when the context was compacted:")
            remains_parts += [f"- {a}" for a in active]
        if pending:
            remains_parts.append("Pending steps:")
            remains_parts += [f"- {p}" for p in pending]
        if recent:
            remains_parts.append(
                "\nLast assistant messages before compaction (raw context):\n" + recent
            )
        return {
            "plan": plan,
            "current_step": current,
            "total_steps": total,
            "step_status": "in_progress" if (active or pending) else "done",
            "what_was_done": what_was_done,
            "what_remains": "\n".join(remains_parts) or "(unknown)",
        }

    return {
        "plan": "(no todo list found — recovered from transcript text only)",
        "current_step": 1,
        "total_steps": 1,
        "step_status": "in_progress",
        "what_was_done": "(unknown — see raw context below)",
        "what_remains": (
            "Last assistant messages before compaction (raw context):\n" + recent
        ),
    }
