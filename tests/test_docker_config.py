import json
import tomllib

import pytest

from agent_checkpoint_mcp.docker_config import configure

LAUNCHER = "/opt/agent-checkpoint-mcp/install/agent-checkpoint-mcp-docker"
AGENTS = {"claude", "cursor", "codex"}


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _codex(home):
    return tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))


def test_install_is_idempotent_and_preserves_other_config(tmp_path):
    (tmp_path / ".claude.json").write_text(
        json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "other"}}}),
        encoding="utf-8",
    )
    configure(
        home=tmp_path,
        action="install",
        target=None,
        launcher=LAUNCHER,
        agents=AGENTS,
    )
    configure(
        home=tmp_path,
        action="install",
        target=None,
        launcher=LAUNCHER,
        agents=AGENTS,
    )

    claude = _json(tmp_path / ".claude.json")
    assert claude["theme"] == "dark"
    assert set(claude["mcpServers"]) == {
        "other",
        "agent-checkpoint",
        "codebase-memory-mcp",
    }
    assert claude["mcpServers"]["agent-checkpoint"] == {
        "command": LAUNCHER,
        "args": ["checkpoint"],
    }
    cursor = _json(tmp_path / ".cursor" / "mcp.json")
    assert set(cursor["mcpServers"]) == {"agent-checkpoint", "codebase-memory-mcp"}
    assert set(_codex(tmp_path)["mcp_servers"]) == {
        "agent-checkpoint",
        "codebase-memory-mcp",
    }
    hooks = _json(tmp_path / ".claude" / "settings.json")["hooks"]
    assert len(hooks["SessionStart"]) == 1
    assert f"{LAUNCHER} checkpoint show" in str(hooks["SessionStart"])


def test_disable_and_reenable_servers_independently(tmp_path):
    configure(
        home=tmp_path,
        action="install",
        target=None,
        launcher=LAUNCHER,
        agents=AGENTS,
    )
    configure(
        home=tmp_path,
        action="disable",
        target="codebase",
        launcher=LAUNCHER,
        agents=AGENTS,
    )
    assert set(_json(tmp_path / ".claude.json")["mcpServers"]) == {
        "agent-checkpoint"
    }
    assert set(_codex(tmp_path)["mcp_servers"]) == {"agent-checkpoint"}
    assert (tmp_path / ".claude" / "settings.json").exists()

    configure(
        home=tmp_path,
        action="enable",
        target="codebase",
        launcher=LAUNCHER,
        agents=AGENTS,
    )
    assert set(_codex(tmp_path)["mcp_servers"]) == {
        "agent-checkpoint",
        "codebase-memory-mcp",
    }

    configure(
        home=tmp_path,
        action="disable",
        target="checkpoint",
        launcher=LAUNCHER,
        agents=AGENTS,
    )
    assert set(_codex(tmp_path)["mcp_servers"]) == {"codebase-memory-mcp"}
    settings = _json(tmp_path / ".claude" / "settings.json")
    assert "hooks" not in settings


def test_uninstall_keeps_unrelated_entries(tmp_path):
    configure(
        home=tmp_path,
        action="install",
        target=None,
        launcher=LAUNCHER,
        agents=AGENTS,
    )
    cursor_path = tmp_path / ".cursor" / "mcp.json"
    cursor = _json(cursor_path)
    cursor["mcpServers"]["other"] = {"command": "other"}
    cursor_path.write_text(json.dumps(cursor), encoding="utf-8")

    configure(
        home=tmp_path,
        action="uninstall",
        target=None,
        launcher=LAUNCHER,
        agents=AGENTS,
    )
    assert set(_json(cursor_path)["mcpServers"]) == {"other"}
    assert "mcp_servers" not in _codex(tmp_path)


def test_disable_does_not_remove_non_docker_registration_or_hooks(tmp_path):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text(
        '[mcp_servers."agent-checkpoint"]\n'
        'command = "/usr/local/bin/agent-checkpoint-mcp"\n'
        "args = []\n",
        encoding="utf-8",
    )
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/usr/local/bin/agent-checkpoint-mcp show",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    configure(
        home=tmp_path,
        action="disable",
        target="checkpoint",
        launcher=LAUNCHER,
        agents={"claude", "codex"},
    )
    assert _codex(tmp_path)["mcp_servers"]["agent-checkpoint"]["command"] == (
        "/usr/local/bin/agent-checkpoint-mcp"
    )
    assert "agent-checkpoint-mcp show" in settings.read_text(encoding="utf-8")


def test_rejects_missing_target(tmp_path):
    with pytest.raises(ValueError, match="requires target"):
        configure(
            home=tmp_path,
            action="enable",
            target=None,
            launcher=LAUNCHER,
            agents={"codex"},
        )
