# One-command installer for agent-checkpoint-mcp (Windows).
#
#   irm https://raw.githubusercontent.com/DiegoWare/agent-checkpoint-mcp/main/install/install.ps1 | iex
#
# Installs the package (uv > pipx > pip --user), then runs
# `agent-checkpoint-mcp setup` to register the server with every detected
# agent (Claude Code, Cursor, Codex). Idempotent.
$ErrorActionPreference = "Stop"

$Package = "agent-checkpoint-mcp"
$Spec = if ($env:AGENT_CHECKPOINT_FROM_GIT -eq "1") {
    "git+https://github.com/DiegoWare/agent-checkpoint-mcp"
} else {
    $Package
}

function Info($msg) { Write-Host "==> $msg" -ForegroundColor Blue }

# Require Python 3.11+
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
    }
}
if (-not $python) {
    throw "Python 3.11+ is required. Install it from https://python.org and re-run."
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Info "Installing $Package with uv"
    uv tool install --force --python $python $Spec
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Info "Installing $Package with pipx"
    pipx install --force $Spec
} else {
    Info "Installing $Package with pip --user (tip: install uv or pipx for cleaner isolation)"
    & $python -m pip install --user --upgrade $Spec
}

# pip --user scripts dir may not be on PATH in this session.
if (-not (Get-Command agent-checkpoint-mcp -ErrorAction SilentlyContinue)) {
    $scriptsDir = & $python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))" 2>$null
    if ($scriptsDir -and (Test-Path (Join-Path $scriptsDir "agent-checkpoint-mcp.exe"))) {
        $env:PATH = "$scriptsDir;$env:PATH"
    }
}
if (-not (Get-Command agent-checkpoint-mcp -ErrorAction SilentlyContinue)) {
    throw "Installed, but 'agent-checkpoint-mcp' is not on PATH. Add your Python Scripts dir to PATH and run: agent-checkpoint-mcp setup"
}

Info "Registering with installed agents"
agent-checkpoint-mcp setup

Info "Done. Restart your agent (Claude Code / Cursor / Codex) to load the MCP server."
