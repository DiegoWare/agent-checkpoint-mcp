#!/bin/sh
set -eu

target="${1:-checkpoint}"
[ "$#" -eq 0 ] || shift

case "$target" in
  checkpoint)
    exec agent-checkpoint-mcp "$@"
    ;;
  codebase)
    # These settings live in the Codebase Memory volume. Suppress normal CLI
    # output so stdout remains a clean JSON-RPC stdio channel.
    if ! codebase-memory-mcp config set auto_index true >/dev/null 2>&1; then
      echo "failed to enable Codebase Memory auto_index" >&2
      exit 1
    fi
    if ! codebase-memory-mcp config set auto_watch false >/dev/null 2>&1; then
      echo "failed to disable Codebase Memory auto_watch" >&2
      exit 1
    fi
    exec codebase-memory-mcp "$@"
    ;;
  config)
    exec python -m agent_checkpoint_mcp.docker_config "$@"
    ;;
  versions)
    agent-checkpoint-mcp --version
    codebase-memory-mcp --version
    ;;
  init-volumes)
    if [ "$(id -u)" -ne 0 ]; then
      echo "init-volumes must run as root" >&2
      exit 1
    fi
    chown -R 10001:10001 /data/checkpoint /data/codebase
    ;;
  *)
    echo "unknown container target: $target" >&2
    echo "expected checkpoint, codebase, config, versions, or init-volumes" >&2
    exit 2
    ;;
esac
