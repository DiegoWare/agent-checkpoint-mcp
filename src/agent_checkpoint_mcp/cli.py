"""Command-line entry point.

Without a subcommand this runs the MCP server over stdio — that is what the
agent configs execute. Subcommands support the install flow and the Claude
Code hooks:

  show                 print the latest checkpoint (used by the SessionStart hook)
  precompact-snapshot  save an emergency checkpoint from hook JSON on stdin
  setup                detect installed agents and write their MCP configs
  clear                delete this project's checkpoints from the terminal
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .project import find_project_root
from .render import format_checkpoint, format_checkpoint_list
from .storage import Storage


def _cmd_show(args: argparse.Namespace) -> int:
    project = find_project_root(args.project)
    store = Storage()
    try:
        cp = store.latest(project)
        if cp is None:
            # Stay silent so the SessionStart hook adds no noise on projects
            # that never used checkpoints.
            return 0
        print(
            "A previous agent session left a checkpoint for this project. "
            "Resume from it instead of restarting the plan:\n"
        )
        print(format_checkpoint(cp))
    finally:
        store.close()
    return 0


def _cmd_precompact_snapshot(_args: argparse.Namespace) -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("precompact-snapshot: expected hook JSON on stdin", file=sys.stderr)
        return 1

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        print("precompact-snapshot: no transcript_path in hook input", file=sys.stderr)
        return 1

    from .transcript import extract_snapshot

    snapshot = extract_snapshot(transcript_path)
    if snapshot is None:
        return 0  # nothing recoverable; not an error

    project = find_project_root(payload.get("cwd"))
    session_id = (payload.get("session_id") or "precompact")[:8]
    store = Storage()
    try:
        cp = store.save(project=project, session_id=session_id, kind="precompact", **snapshot)
        print(f"Saved pre-compaction checkpoint #{cp.id} for {project}", file=sys.stderr)
    finally:
        store.close()
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    from .setup_agents import run_setup

    return run_setup(dry_run=args.dry_run)


def _cmd_clear(args: argparse.Namespace) -> int:
    project = find_project_root(args.project)
    store = Storage()
    try:
        n = store.count(project)
        if n == 0:
            print(f"No checkpoints for {project}.")
            return 0
        if not args.yes:
            reply = input(f"Delete {n} checkpoint(s) for {project}? [y/N] ")
            if reply.strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return 1
        print(f"Deleted {store.clear(project)} checkpoint(s) for {project}.")
    finally:
        store.close()
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    project = find_project_root(args.project)
    store = Storage()
    try:
        print(format_checkpoint_list(store.list(project, limit=args.limit), project))
    finally:
        store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-checkpoint-mcp",
        description="Local MCP checkpoint server (runs the stdio server when "
        "invoked without a subcommand).",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p_show = sub.add_parser("show", help="print the latest checkpoint for a project")
    p_show.add_argument("--project", default=None, help="project directory (default: cwd)")
    p_show.set_defaults(func=_cmd_show)

    p_snap = sub.add_parser(
        "precompact-snapshot",
        help="save an emergency checkpoint from Claude Code PreCompact hook JSON on stdin",
    )
    p_snap.set_defaults(func=_cmd_precompact_snapshot)

    p_setup = sub.add_parser(
        "setup", help="detect installed agents and register this MCP server in their configs"
    )
    p_setup.add_argument("--dry-run", action="store_true", help="show changes without writing")
    p_setup.set_defaults(func=_cmd_setup)

    p_clear = sub.add_parser("clear", help="delete all checkpoints for a project")
    p_clear.add_argument("--project", default=None, help="project directory (default: cwd)")
    p_clear.add_argument("--yes", action="store_true", help="skip confirmation")
    p_clear.set_defaults(func=_cmd_clear)

    p_list = sub.add_parser("list", help="list checkpoints for a project")
    p_list.add_argument("--project", default=None, help="project directory (default: cwd)")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args(argv)
    if args.command is None:
        from .server import run

        run()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
