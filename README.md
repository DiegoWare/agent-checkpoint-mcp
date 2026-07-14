# agent-checkpoint-mcp

**Never lose your place when an AI agent session gets cut off.**

A tiny, 100% local [MCP](https://modelcontextprotocol.io) server that saves
work-in-progress checkpoints to SQLite. When a session dies mid-plan —
context limit hit, quota exhausted, laptop closed — the next session (same
agent or a different one: Claude Code, Codex, Cursor) reads the exact state
and continues from the last sub-task instead of redoing work.

- **Local-first**: SQLite on your machine. No network calls, no API keys, no LLM, zero cost.
- **Cross-agent**: checkpoints are keyed by project directory, so Claude Code can resume what Codex started.
- **Cross-platform**: macOS (incl. Apple Silicon), Linux, Windows. Python 3.11+, single dependency (`mcp`).

## The problem

You're 40 minutes into a 6-step plan. The session hits the context limit and
compacts — or your quota runs out and you switch agents. The new session sees
the plan, maybe, but not that step 3 was half done: the migration file was
written but not applied, two of five tests were fixed. So it starts step 3
over. This server makes "exactly where were we?" a tool call.

## Install (one command)

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/DiegoWare/agent-checkpoint-mcp/main/install/install.sh | bash
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/DiegoWare/agent-checkpoint-mcp/main/install/install.ps1 | iex
```

That single command does everything:

1. Installs the package with `uv`, `pipx`, or `pip --user` (whichever you have).
2. Detects installed agents — **Claude Code**, **Cursor**, **Codex** — and
   registers the server in each one's MCP config (non-destructively).
3. Installs the Claude Code **recovery hooks** (see below): every new,
   resumed, or compacted session automatically receives the latest
   checkpoint, and an emergency checkpoint is saved right before every
   compaction.
4. Prints what it changed. Restart your agent and everything is live.

Re-running the installer upgrades and re-registers.

**Don't want a piece of it?** Everything is reversible with one command:

```bash
agent-checkpoint-mcp uninstall --hooks   # remove the Claude Code hooks only
agent-checkpoint-mcp uninstall --mcp     # remove the MCP registrations only
agent-checkpoint-mcp uninstall           # remove both
```

(Or skip hooks at install time: `AGENT_CHECKPOINT_NO_HOOKS=1 curl ... | bash`,
and `agent-checkpoint-mcp setup --no-hooks` thereafter. `--dry-run` previews
any of these without writing.)

Prefer manual control end to end?

```bash
pipx install agent-checkpoint-mcp   # or: uv tool install agent-checkpoint-mcp
agent-checkpoint-mcp setup          # same as the installer's registration step
```

## Docker-isolated install (Agent Checkpoint + Codebase Memory)

If you do not want either MCP installed into the host Python environment, this
repository includes an optional Docker path for macOS and Linux. From a clone
of this repository, run:

```bash
./install/docker.sh install
```

That one command builds a local `agent-checkpoint-mcp:local` image containing
this project and the checksum-verified
[`codebase-memory-mcp`](https://github.com/DeusData/codebase-memory-mcp)
v0.8.1 binary, then registers both servers with detected Claude Code, Cursor,
and Codex installations. The clients launch one short-lived stdio container
per MCP connection; there are no background services or open ports.

At runtime each container has no network, runs as a non-root user with dropped
capabilities, and sees only the active Git repository at its original absolute
path. The repository mount and container root are read-only. Checkpoints and
code indexes persist in separate Docker volumes, so Codebase Memory cannot
create `.codebase-memory/graph.db.zst` or otherwise edit source files.

Manage either MCP independently:

```bash
./install/docker.sh disable codebase       # keep Agent Checkpoint
./install/docker.sh enable codebase
./install/docker.sh disable checkpoint     # also removes its Claude hooks
./install/docker.sh enable checkpoint
./install/docker.sh doctor                 # config + stdio handshake checks
./install/docker.sh uninstall              # keep image and persistent data
```

Disabling or uninstalling never deletes data. Purging is separate and requires
an explicit confirmation flag:

```bash
./install/docker.sh purge checkpoint --yes
./install/docker.sh purge codebase --yes
./install/docker.sh purge all --yes
```

The registrations point to the launcher inside this checkout, so keep the
clone at the same path. Docker limits accidental host exposure, but anyone who
controls the Docker daemon or the host root account can still access Docker
volumes and mounts.

Or register by hand — the server command is just `agent-checkpoint-mcp`:

```jsonc
// Claude Code (~/.claude.json) and Cursor (~/.cursor/mcp.json)
{ "mcpServers": { "agent-checkpoint": { "command": "agent-checkpoint-mcp", "args": [] } } }
```

```toml
# Codex (~/.codex/config.toml)
[mcp_servers.agent-checkpoint]
command = "agent-checkpoint-mcp"
args = []
```

## Tools

| Tool | What it does |
|---|---|
| `save_checkpoint(plan, current_step, total_steps, step_status, what_was_done, what_remains)` | Save progress. Designed to be called after **every sub-task** (a file edited, a test passing), not just when a numbered step completes. |
| `get_checkpoint()` | The latest checkpoint for this project, formatted as a resume brief: current step, what's done (don't redo), the exact next action, remaining steps. |
| `list_checkpoints(limit=20)` | Session history with timestamps, newest first. |
| `clear_checkpoints(confirm=false)` | Wipe this project's history. Dry-run by default; requires `confirm=true` to delete. |

All tools take an optional `project_dir` override. By default the project is
detected from the server's working directory, walking up to the nearest
`.git` root — so checkpoints saved from `repo/src/` and `repo/` land in the
same bucket, and different projects never mix.

### Example flow

```text
Session A (Claude Code, dies at context limit):
  save_checkpoint(plan="1. Schema\n2. Endpoints\n3. Tests", current_step=2,
                  total_steps=3, step_status="in_progress",
                  what_was_done="- schema migrated\n- POST /users done",
                  what_remains="- GET /users/:id handler, then wire router")

Session B (Codex, next morning):
  get_checkpoint()
  → # Resume point — step 2/3 (in_progress)
    ## What was already done (do NOT redo this) ...
    ## What remains in the current step — continue HERE ...
```

## How recovery works

Two mechanisms, both installed automatically by the one-command installer:

### Claude Code hooks (installed for you)

The installer merges two hooks into `~/.claude/settings.json`
(non-destructively — your existing hooks are untouched):

- **`SessionStart`** (`startup|resume|compact`) runs `agent-checkpoint-mcp show`,
  which prints the latest checkpoint — Claude Code injects that output into
  the fresh context. The resuming agent knows where it left off *without even
  calling a tool*. This is the main recovery mechanism.
- **`PreCompact`** runs `agent-checkpoint-mcp precompact-snapshot`, which
  parses the session transcript locally (last todo-list state + last
  assistant messages) and stores an emergency checkpoint right before
  compaction. Honest caveat: hooks can't force the model to call an MCP tool,
  so this snapshot is reconstructed from the transcript — cruder than a
  proper `save_checkpoint`, but it means even a session that never saved
  manually leaves a trail.

Remove them anytime with `agent-checkpoint-mcp uninstall --hooks`. To merge
them by hand instead (e.g. per-project in `.claude/settings.json`), use
[`examples/claude-settings-hooks.json`](examples/claude-settings-hooks.json).

### Per-project instructions (one command per project)

For the best checkpoints — saved deliberately after every sub-task, not just
recovered from transcripts — run this once inside a project:

```bash
agent-checkpoint-mcp init
```

It appends a checkpoint-discipline section to the project's `CLAUDE.md` and
`AGENTS.md` (creating them if needed, skipping if already present). The key
rule it teaches: **save after every concrete sub-task**, and call
`get_checkpoint` first when a task looks like a continuation. Prefer to copy
by hand? See [`examples/`](examples/).

## Where data lives

One SQLite database, keyed by project path — nothing is written inside your repos:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/agent-checkpoint-mcp/checkpoints.db` |
| Linux | `$XDG_DATA_HOME/agent-checkpoint-mcp/checkpoints.db` (default `~/.local/share/...`) |
| Windows | `%LOCALAPPDATA%\agent-checkpoint-mcp\checkpoints.db` |

The Docker variant stores checkpoints in the
`agent-checkpoint-mcp-checkpoints` volume and Codebase Memory indexes in the
`agent-checkpoint-mcp-codebase` volume.

Override with the `AGENT_CHECKPOINT_HOME` environment variable.

## CLI

```text
agent-checkpoint-mcp                      # run the MCP server (stdio) — what agent configs execute
agent-checkpoint-mcp show [--project D]   # print the latest checkpoint (used by the SessionStart hook)
agent-checkpoint-mcp list [--project D]   # checkpoint history
agent-checkpoint-mcp clear [--yes]        # delete this project's checkpoints
agent-checkpoint-mcp init [--project D]   # add checkpoint instructions to CLAUDE.md/AGENTS.md
agent-checkpoint-mcp setup [--no-hooks]   # (re)register with detected agents + install hooks
agent-checkpoint-mcp uninstall [--hooks|--mcp]  # remove what setup installed
agent-checkpoint-mcp precompact-snapshot  # used by the PreCompact hook (hook JSON on stdin)
```

`setup` and `uninstall` accept `--dry-run` to preview changes without writing.

## Development

```bash
git clone https://github.com/DiegoWare/agent-checkpoint-mcp
cd agent-checkpoint-mcp
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

## License

[MIT](LICENSE)
