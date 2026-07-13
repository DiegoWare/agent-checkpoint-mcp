"""Detect installed agents and register this MCP server in their configs.

Non-destructive: each config file is read first and only the
`agent-checkpoint` entry is added or updated; everything else is preserved.

Supported agents:
  Claude Code  ~/.claude.json            (mcpServers, user scope)
  Cursor       ~/.cursor/mcp.json        (mcpServers)
  Codex        ~/.codex/config.toml      ([mcp_servers.agent-checkpoint])
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "agent-checkpoint"


def server_command() -> list[str]:
    """Absolute command agents should run to start the server.

    Prefer the installed console script (survives independently of which
    Python launched setup); fall back to `python -m agent_checkpoint_mcp`.
    """
    exe = shutil.which("agent-checkpoint-mcp")
    if exe:
        return [str(Path(exe).resolve())]
    return [sys.executable, "-m", "agent_checkpoint_mcp"]


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{path} is not valid JSON ({e}); fix it and re-run") from e
    return {}


def _write_json(path: Path, data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _merge_mcp_servers_json(path: Path, command: list[str], dry_run: bool) -> None:
    config = _load_json(path)
    servers = config.setdefault("mcpServers", {})
    servers[SERVER_NAME] = {"command": command[0], "args": command[1:]}
    _write_json(path, config, dry_run)


# --- Claude Code -------------------------------------------------------------

def setup_claude_code(command: list[str], dry_run: bool) -> str | None:
    claude_cli = shutil.which("claude")
    config_path = Path.home() / ".claude.json"
    if not claude_cli and not config_path.exists() and not (Path.home() / ".claude").exists():
        return None

    if claude_cli and not dry_run:
        # The CLI owns ~/.claude.json; let it do the write when available.
        subprocess.run(
            [claude_cli, "mcp", "remove", "--scope", "user", SERVER_NAME],
            capture_output=True,
        )
        result = subprocess.run(
            [claude_cli, "mcp", "add", "--scope", "user", SERVER_NAME, "--", *command],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return "Claude Code: registered via `claude mcp add --scope user`"
        # fall through to direct config edit

    _merge_mcp_servers_json(config_path, command, dry_run)
    return f"Claude Code: updated {config_path}"


# --- Cursor ------------------------------------------------------------------

def setup_cursor(command: list[str], dry_run: bool) -> str | None:
    cursor_dir = Path.home() / ".cursor"
    if not cursor_dir.exists():
        return None
    path = cursor_dir / "mcp.json"
    _merge_mcp_servers_json(path, command, dry_run)
    return f"Cursor: updated {path}"


# --- Codex -------------------------------------------------------------------

_CODEX_SECTION_RE = re.compile(
    r"\[mcp_servers\.(?:\"agent-checkpoint\"|agent-checkpoint)\][^\[]*",
    re.DOTALL,
)


def _codex_section(command: list[str]) -> str:
    args = ", ".join(json.dumps(a) for a in command[1:])
    return (
        f'[mcp_servers."{SERVER_NAME}"]\n'
        f"command = {json.dumps(command[0])}\n"
        f"args = [{args}]\n"
    )


def setup_codex(command: list[str], dry_run: bool) -> str | None:
    codex_dir = Path.home() / ".codex"
    if not codex_dir.exists():
        return None
    path = codex_dir / "config.toml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    # Validate before touching anything; refuse to edit a broken file.
    import tomllib

    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise RuntimeError(f"{path} is not valid TOML ({e}); fix it and re-run") from e

    # The stdlib can parse TOML but not write it. Instead of pulling in a
    # writer dependency, we replace/append only our own section textually and
    # re-validate the result.
    section = _codex_section(command)
    if _CODEX_SECTION_RE.search(text):
        new_text = _CODEX_SECTION_RE.sub(section + "\n", text).rstrip() + "\n"
    else:
        sep = "\n" if not text or text.endswith("\n") else "\n\n"
        new_text = text + sep + section

    tomllib.loads(new_text)  # sanity check our own edit
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return f"Codex: updated {path}"


# --- Entry point -------------------------------------------------------------

def run_setup(dry_run: bool = False) -> int:
    command = server_command()
    print(f"MCP server command: {' '.join(command)}")
    if dry_run:
        print("(dry run — no files will be written)")

    results: list[str] = []
    errors: list[str] = []
    for setup in (setup_claude_code, setup_cursor, setup_codex):
        try:
            outcome = setup(command, dry_run)
            if outcome:
                results.append(outcome)
        except RuntimeError as e:
            errors.append(str(e))

    if not results and not errors:
        print("No supported agents detected (Claude Code, Cursor, Codex).")
        print("You can still register the server manually — see the README.")
        return 0

    for line in results:
        print(f"  ✓ {line}")
    for line in errors:
        print(f"  ✗ {line}", file=sys.stderr)
    if results:
        print("\nRestart your agent(s) and the 'agent-checkpoint' MCP server will be available.")
    return 1 if errors else 0
