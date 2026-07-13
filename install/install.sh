#!/usr/bin/env bash
# One-command installer for agent-checkpoint-mcp (macOS / Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/DiegoWare/agent-checkpoint-mcp/main/install/install.sh | bash
#
# Installs the package (uv > pipx > pip --user), then runs
# `agent-checkpoint-mcp setup` to register the server with every detected
# agent (Claude Code, Cursor, Codex). Idempotent: re-running upgrades and
# re-registers.
set -euo pipefail

PACKAGE="agent-checkpoint-mcp"
GITHUB_REPO="DiegoWare/agent-checkpoint-mcp"
# Set AGENT_CHECKPOINT_FROM_GIT=1 to install from GitHub instead of PyPI.
if [ "${AGENT_CHECKPOINT_FROM_GIT:-0}" = "1" ]; then
  SPEC="git+https://github.com/${GITHUB_REPO}"
else
  SPEC="$PACKAGE"
fi

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

check_python() {
  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        echo "$py"; return 0
      fi
    fi
  done
  return 1
}

PY="$(check_python)" || fail "Python 3.11+ is required. Install it from https://python.org and re-run."

if command -v uv >/dev/null 2>&1; then
  info "Installing $PACKAGE with uv"
  uv tool install --force --python "$PY" "$SPEC"
elif command -v pipx >/dev/null 2>&1; then
  info "Installing $PACKAGE with pipx"
  pipx install --force "$SPEC"
else
  info "Installing $PACKAGE with pip --user (tip: install uv or pipx for cleaner isolation)"
  "$PY" -m pip install --user --upgrade "$SPEC"
fi

if ! command -v agent-checkpoint-mcp >/dev/null 2>&1; then
  # pip --user and pipx put scripts in dirs that may not be on PATH yet.
  for dir in "$HOME/.local/bin" "$HOME/Library/Python/"*/bin; do
    [ -x "$dir/agent-checkpoint-mcp" ] && export PATH="$dir:$PATH" && break
  done
fi

command -v agent-checkpoint-mcp >/dev/null 2>&1 \
  || fail "installed, but 'agent-checkpoint-mcp' is not on PATH. Add your Python scripts dir to PATH and run: agent-checkpoint-mcp setup"

info "Registering with installed agents"
agent-checkpoint-mcp setup

info "Done. Restart your agent (Claude Code / Cursor / Codex) to load the MCP server."
