"""Install/remove the Claude Code hooks in ~/.claude/settings.json.

Two hooks make recovery automatic:
  SessionStart (startup|resume|compact) -> `agent-checkpoint-mcp show`
      injects the latest checkpoint into every fresh/resumed/compacted context.
  PreCompact (manual|auto) -> `agent-checkpoint-mcp precompact-snapshot`
      stores an emergency checkpoint parsed from the transcript right before
      compaction.

Merging is non-destructive and idempotent: entries are recognized as ours by
the binary name in their command, updated in place if present, appended
otherwise. Everything else in settings.json is preserved.
"""

from __future__ import annotations

import json
from pathlib import Path

HOOK_MARKER = "agent-checkpoint-mcp"


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _hook_config(command: str) -> dict[str, dict]:
    return {
        "SessionStart": {
            "matcher": "startup|resume|compact",
            "hooks": [{"type": "command", "command": f"{command} show"}],
        },
        "PreCompact": {
            "matcher": "manual|auto",
            "hooks": [{"type": "command", "command": f"{command} precompact-snapshot"}],
        },
    }


def _is_ours(entry: dict) -> bool:
    return any(
        HOOK_MARKER in h.get("command", "")
        for h in entry.get("hooks", [])
        if isinstance(h, dict)
    )


def _load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{path} is not valid JSON ({e}); fix it and re-run") from e
    return {}


def _save(path: Path, settings: dict, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def install_hooks(command: str, path: Path | None = None, dry_run: bool = False) -> str:
    """Merge our two hooks into Claude Code settings. Returns a summary line."""
    path = path or settings_path()
    settings = _load(path)
    hooks = settings.setdefault("hooks", {})
    for event, entry in _hook_config(command).items():
        entries = hooks.setdefault(event, [])
        for i, existing in enumerate(entries):
            if isinstance(existing, dict) and _is_ours(existing):
                entries[i] = entry
                break
        else:
            entries.append(entry)
    _save(path, settings, dry_run)
    return f"Claude Code hooks (SessionStart + PreCompact): updated {path}"


def remove_hooks(path: Path | None = None, dry_run: bool = False) -> str | None:
    """Remove our hooks from Claude Code settings. Returns a summary or None."""
    path = path or settings_path()
    if not path.exists():
        return None
    settings = _load(path)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return None
    changed = False
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not (isinstance(e, dict) and _is_ours(e))]
        if len(kept) != len(entries):
            changed = True
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    if not changed:
        return None
    if not hooks:
        del settings["hooks"]
    _save(path, settings, dry_run)
    return f"Claude Code hooks: removed from {path}"
