#!/usr/bin/env bash
# Build and configure the Docker-isolated Agent Checkpoint + Codebase Memory MCPs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
LAUNCHER="$SCRIPT_DIR/agent-checkpoint-mcp-docker"
DOCKERFILE="$REPO_ROOT/docker/Dockerfile"

IMAGE="${AGENT_CHECKPOINT_DOCKER_IMAGE:-agent-checkpoint-mcp:local}"
CHECKPOINT_VOLUME="${AGENT_CHECKPOINT_DOCKER_CHECKPOINT_VOLUME:-agent-checkpoint-mcp-checkpoints}"
CODEBASE_VOLUME="${AGENT_CHECKPOINT_DOCKER_CODEBASE_VOLUME:-agent-checkpoint-mcp-codebase}"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  !\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  ./install/docker.sh install
  ./install/docker.sh enable checkpoint|codebase
  ./install/docker.sh disable checkpoint|codebase
  ./install/docker.sh uninstall
  ./install/docker.sh purge checkpoint|codebase|all --yes
  ./install/docker.sh doctor

The install is global for detected Claude Code, Cursor, and Codex clients,
but each MCP container receives only the current repository as a read-only mount.
EOF
}

require_docker() {
  command -v docker >/dev/null 2>&1 || fail "Docker is required. Install Docker Desktop/Engine and re-run."
  docker info >/dev/null 2>&1 || fail "Docker is installed, but its daemon is not running."
}

require_image() {
  docker image inspect "$IMAGE" >/dev/null 2>&1 \
    || fail "Docker image '$IMAGE' is missing. Run: ./install/docker.sh install"
}

append_agent() {
  local agent="$1"
  if [[ -z "${DETECTED_AGENTS:-}" ]]; then
    DETECTED_AGENTS="$agent"
  else
    DETECTED_AGENTS+=",$agent"
  fi
}

detect_agents() {
  DETECTED_AGENTS=""
  if command -v claude >/dev/null 2>&1 || [[ -e "$HOME/.claude.json" || -d "$HOME/.claude" ]]; then
    append_agent claude
  fi
  if command -v cursor >/dev/null 2>&1 || [[ -d "$HOME/.cursor" ]]; then
    append_agent cursor
  fi
  if command -v codex >/dev/null 2>&1 || [[ -d "$HOME/.codex" ]]; then
    append_agent codex
  fi
}

stage_file() {
  local relative="$1"
  local source="$HOME/$relative"
  local destination="$STAGE/$relative"
  mkdir -p "$(dirname "$destination")"
  if [[ -f "$source" ]]; then
    cp "$source" "$destination"
  fi
}

write_back() {
  local relative="$1"
  local source="$STAGE/$relative"
  local destination="$HOME/$relative"
  [[ -f "$source" ]] || return 0
  [[ ! -L "$destination" ]] || fail "refusing to replace symlink: $destination"
  mkdir -p "$(dirname "$destination")"
  local temp
  temp="$(mktemp "${destination}.tmp.XXXXXX")"
  cp "$source" "$temp"
  chmod 600 "$temp"
  mv "$temp" "$destination"
}

configure_agents() {
  local action="$1"
  local target="${2:-}"
  detect_agents
  if [[ -z "$DETECTED_AGENTS" ]]; then
    warn "No supported agents detected; the image and volumes are ready for manual registration."
    return 0
  fi

  STAGE="$(mktemp -d "${TMPDIR:-/tmp}/agent-checkpoint-docker.XXXXXX")"
  trap 'rm -rf "${STAGE:-}"' RETURN

  [[ "$DETECTED_AGENTS" != *claude* ]] || {
    stage_file .claude.json
    stage_file .claude/settings.json
  }
  [[ "$DETECTED_AGENTS" != *cursor* ]] || stage_file .cursor/mcp.json
  [[ "$DETECTED_AGENTS" != *codex* ]] || stage_file .codex/config.toml

  local command=(
    docker run --rm
    --network none
    --read-only
    --cap-drop ALL
    --security-opt no-new-privileges
    --tmpfs /tmp:rw,nosuid,nodev,noexec,size=67108864
    --user "$(id -u):$(id -g)"
    --mount "type=bind,source=${STAGE},target=/config"
    "$IMAGE" config "$action"
  )
  [[ -z "$target" ]] || command+=("$target")
  command+=(--home /config --launcher "$LAUNCHER" --agents "$DETECTED_AGENTS")

  info "Updating staged MCP configuration for: $DETECTED_AGENTS"
  "${command[@]}"

  [[ "$DETECTED_AGENTS" != *claude* ]] || {
    write_back .claude.json
    write_back .claude/settings.json
  }
  [[ "$DETECTED_AGENTS" != *cursor* ]] || write_back .cursor/mcp.json
  [[ "$DETECTED_AGENTS" != *codex* ]] || write_back .codex/config.toml
  trap - RETURN
  rm -rf "$STAGE"
}

build_image() {
  info "Building local image $IMAGE"
  docker build \
    --file "$DOCKERFILE" \
    --tag "$IMAGE" \
    --build-arg CODEBASE_MEMORY_VERSION=0.8.1 \
    "$REPO_ROOT"
}

ensure_volumes() {
  docker volume create "$CHECKPOINT_VOLUME" >/dev/null
  docker volume create "$CODEBASE_VOLUME" >/dev/null
  docker run --rm \
    --network none \
    --read-only \
    --cap-drop ALL \
    --cap-add CHOWN \
    --security-opt no-new-privileges \
    --user 0:0 \
    --mount "type=volume,source=${CHECKPOINT_VOLUME},target=/data/checkpoint" \
    --mount "type=volume,source=${CODEBASE_VOLUME},target=/data/codebase" \
    "$IMAGE" init-volumes
  ok "Persistent volumes ready"
}

purge_volume() {
  local volume="$1"
  if docker volume inspect "$volume" >/dev/null 2>&1; then
    docker volume rm "$volume" >/dev/null
    ok "Removed volume $volume"
  else
    warn "Volume $volume does not exist"
  fi
}

check_registration() {
  local path="$1"
  local name="$2"
  if [[ -f "$path" ]] && grep -Fq "$name" "$path"; then
    ok "$name registered in $path"
  else
    warn "$name not found in $path"
  fi
}

check_handshake() {
  local target="$1"
  local response
  local request='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"docker-doctor","version":"1"}}}'
  if ! response="$(printf '%s\n' "$request" | "$LAUNCHER" "$target")"; then
    fail "$target MCP handshake failed"
  fi
  if printf '%s\n' "$response" | grep -Eq '"id"[[:space:]]*:[[:space:]]*1'; then
    ok "$target MCP stdio handshake"
  else
    fail "$target MCP returned no initialize response"
  fi
}

action="${1:-}"
case "$action" in
  install)
    [[ "$#" -eq 1 ]] || { usage; exit 2; }
    require_docker
    build_image
    ensure_volumes
    configure_agents install
    ok "Installed both Docker MCP registrations. Restart your agent(s)."
    ;;
  enable|disable)
    [[ "$#" -eq 2 ]] || { usage; exit 2; }
    [[ "$2" == checkpoint || "$2" == codebase ]] || fail "target must be checkpoint or codebase"
    require_docker
    require_image
    configure_agents "$action" "$2"
    ok "$action completed for $2. Restart your agent(s)."
    ;;
  uninstall)
    [[ "$#" -eq 1 ]] || { usage; exit 2; }
    require_docker
    require_image
    configure_agents uninstall
    ok "Registrations removed; image and data volumes were preserved."
    ;;
  purge)
    [[ "$#" -eq 3 && "$3" == --yes ]] || fail "purge is destructive; use: purge checkpoint|codebase|all --yes"
    require_docker
    case "$2" in
      checkpoint) purge_volume "$CHECKPOINT_VOLUME" ;;
      codebase) purge_volume "$CODEBASE_VOLUME" ;;
      all)
        purge_volume "$CHECKPOINT_VOLUME"
        purge_volume "$CODEBASE_VOLUME"
        ;;
      *) fail "purge target must be checkpoint, codebase, or all" ;;
    esac
    ;;
  doctor)
    [[ "$#" -eq 1 ]] || { usage; exit 2; }
    require_docker
    require_image
    [[ -x "$LAUNCHER" ]] || fail "launcher is not executable: $LAUNCHER"
    ok "Docker daemon, image, and launcher are available"
    docker volume inspect "$CHECKPOINT_VOLUME" >/dev/null 2>&1 \
      && ok "Checkpoint volume exists" || warn "Checkpoint volume is missing"
    docker volume inspect "$CODEBASE_VOLUME" >/dev/null 2>&1 \
      && ok "Codebase Memory volume exists" || warn "Codebase Memory volume is missing"
    detect_agents
    [[ "$DETECTED_AGENTS" != *claude* ]] || {
      check_registration "$HOME/.claude.json" agent-checkpoint
      check_registration "$HOME/.claude.json" codebase-memory-mcp
    }
    [[ "$DETECTED_AGENTS" != *cursor* ]] || {
      check_registration "$HOME/.cursor/mcp.json" agent-checkpoint
      check_registration "$HOME/.cursor/mcp.json" codebase-memory-mcp
    }
    [[ "$DETECTED_AGENTS" != *codex* ]] || {
      check_registration "$HOME/.codex/config.toml" agent-checkpoint
      check_registration "$HOME/.codex/config.toml" codebase-memory-mcp
    }
    check_handshake checkpoint
    check_handshake codebase
    ok "Docker MCP doctor completed"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
