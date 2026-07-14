"""Configure host coding agents to launch the Docker-isolated MCP servers.

This module is executed inside the locally-built image against a staged copy
of the few host configuration files it is allowed to edit.  The outer shell
installer copies the results back atomically, so the container never receives
the user's whole home directory.
"""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from .hooks import install_hooks, remove_hooks
from .setup_agents import (
    _load_json,
    _merge_codex_text,
    _merge_mcp_servers_json,
    _remove_codex_text,
    _remove_from_mcp_json,
)

SERVER_COMMANDS = {
    "checkpoint": "agent-checkpoint",
    "codebase": "codebase-memory-mcp",
}
SUPPORTED_AGENTS = {"claude", "cursor", "codex"}


def _codex_path(home: Path) -> Path:
    return home / ".codex" / "config.toml"


def _set_server(
    home: Path,
    agent: str,
    server_name: str,
    command: list[str],
) -> bool:
    if agent == "claude":
        _merge_mcp_servers_json(home / ".claude.json", command, False, server_name)
    elif agent == "cursor":
        _merge_mcp_servers_json(
            home / ".cursor" / "mcp.json", command, False, server_name
        )
    elif agent == "codex":
        path = _codex_path(home)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _merge_codex_text(text, command, server_name), encoding="utf-8"
        )
    else:  # guarded by configure(), kept explicit for direct callers
        raise ValueError(f"unsupported agent: {agent}")
    return True


def _registration_matches(
    home: Path,
    agent: str,
    server_name: str,
    command: list[str],
) -> bool:
    if agent == "claude":
        path = home / ".claude.json"
        if not path.exists():
            return False
        entry = _load_json(path).get("mcpServers", {}).get(server_name)
    elif agent == "cursor":
        path = home / ".cursor" / "mcp.json"
        if not path.exists():
            return False
        entry = _load_json(path).get("mcpServers", {}).get(server_name)
    elif agent == "codex":
        import tomllib

        path = _codex_path(home)
        if not path.exists():
            return False
        servers = tomllib.loads(path.read_text(encoding="utf-8")).get(
            "mcp_servers", {}
        )
        entry = servers.get(server_name)
    else:
        raise ValueError(f"unsupported agent: {agent}")
    return (
        isinstance(entry, dict)
        and entry.get("command") == command[0]
        and entry.get("args", []) == command[1:]
    )


def _remove_server(
    home: Path,
    agent: str,
    server_name: str,
    command: list[str],
) -> bool:
    if not _registration_matches(home, agent, server_name, command):
        return False
    if agent == "claude":
        return _remove_from_mcp_json(
            home / ".claude.json", False, server_name
        )
    if agent == "cursor":
        return _remove_from_mcp_json(
            home / ".cursor" / "mcp.json", False, server_name
        )
    if agent == "codex":
        path = _codex_path(home)
        if not path.exists():
            return False
        new_text = _remove_codex_text(
            path.read_text(encoding="utf-8"), server_name
        )
        if new_text is None:
            return False
        path.write_text(new_text, encoding="utf-8")
        return True
    raise ValueError(f"unsupported agent: {agent}")


def configure(
    *,
    home: Path,
    action: str,
    target: str | None,
    launcher: str,
    agents: set[str],
) -> list[str]:
    """Apply one Docker registration action and return human-readable changes."""
    unknown = agents - SUPPORTED_AGENTS
    if unknown:
        raise ValueError(f"unsupported agents: {', '.join(sorted(unknown))}")
    if not agents:
        raise ValueError("no supported agents were selected")
    if action in {"enable", "disable"} and target not in SERVER_COMMANDS:
        raise ValueError("enable/disable requires target checkpoint or codebase")
    if action in {"install", "uninstall"} and target is not None:
        raise ValueError(f"{action} does not accept a target")

    if action == "install":
        selected = list(SERVER_COMMANDS)
        adding = True
    elif action == "uninstall":
        selected = list(SERVER_COMMANDS)
        adding = False
    else:
        assert target is not None
        selected = [target]
        adding = action == "enable"

    changes: list[str] = []
    for short_name in selected:
        server_name = SERVER_COMMANDS[short_name]
        command = [launcher, short_name]
        for agent in sorted(agents):
            if adding:
                _set_server(home, agent, server_name, command)
                changes.append(f"{agent}: enabled {server_name}")
            elif _remove_server(home, agent, server_name, command):
                changes.append(f"{agent}: disabled {server_name}")

    if "claude" in agents and "checkpoint" in selected:
        hook_path = home / ".claude" / "settings.json"
        if adding:
            hook_command = shlex.join([launcher, "checkpoint"])
            install_hooks(hook_command, path=hook_path)
            changes.append("claude: enabled checkpoint recovery hooks")
        elif remove_hooks(path=hook_path, marker=launcher):
            changes.append("claude: disabled checkpoint recovery hooks")

    return changes


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configure staged host files for Docker MCP launchers"
    )
    parser.add_argument(
        "action", choices=("install", "enable", "disable", "uninstall")
    )
    parser.add_argument("target", nargs="?", choices=tuple(SERVER_COMMANDS))
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--launcher", required=True)
    parser.add_argument(
        "--agents",
        required=True,
        help="comma-separated subset of claude,cursor,codex",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        changes = configure(
            home=args.home,
            action=args.action,
            target=args.target,
            launcher=args.launcher,
            agents={part for part in args.agents.split(",") if part},
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    if changes:
        for change in changes:
            print(f"  + {change}")
    else:
        print("  no matching Docker registrations were present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
