import json

from agent_checkpoint_mcp.hooks import install_hooks, remove_hooks

CMD = "/opt/bin/agent-checkpoint-mcp"


def _settings(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_install_into_fresh_settings(tmp_path):
    path = tmp_path / "settings.json"
    install_hooks(CMD, path=path)
    hooks = _settings(path)["hooks"]
    assert hooks["SessionStart"][0]["hooks"][0]["command"] == f"{CMD} show"
    assert hooks["PreCompact"][0]["hooks"][0]["command"] == f"{CMD} precompact-snapshot"
    assert hooks["SessionStart"][0]["matcher"] == "startup|resume|compact"


def test_install_preserves_existing_settings_and_hooks(tmp_path):
    path = tmp_path / "settings.json"
    existing = {
        "model": "opus",
        "hooks": {
            "SessionStart": [
                {"matcher": "startup", "hooks": [{"type": "command", "command": "other-tool go"}]}
            ],
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "lint"}]}
            ],
        },
    }
    path.write_text(json.dumps(existing), encoding="utf-8")

    install_hooks(CMD, path=path)
    settings = _settings(path)
    assert settings["model"] == "opus"
    session_start = settings["hooks"]["SessionStart"]
    assert len(session_start) == 2  # other-tool entry kept, ours appended
    assert session_start[0]["hooks"][0]["command"] == "other-tool go"
    assert settings["hooks"]["PostToolUse"] == existing["hooks"]["PostToolUse"]


def test_install_is_idempotent(tmp_path):
    path = tmp_path / "settings.json"
    install_hooks(CMD, path=path)
    install_hooks("/new/path/agent-checkpoint-mcp", path=path)
    hooks = _settings(path)["hooks"]
    assert len(hooks["SessionStart"]) == 1  # updated in place, not duplicated
    assert hooks["SessionStart"][0]["hooks"][0]["command"].startswith("/new/path/")


def test_remove_only_deletes_ours(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"matcher": "startup", "hooks": [{"type": "command", "command": "other-tool go"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    install_hooks(CMD, path=path)
    assert remove_hooks(path=path) is not None
    settings = _settings(path)
    assert "PreCompact" not in settings.get("hooks", {})
    assert settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "other-tool go"


def test_remove_when_nothing_installed(tmp_path):
    path = tmp_path / "settings.json"
    assert remove_hooks(path=path) is None
    path.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    assert remove_hooks(path=path) is None


def test_dry_run_writes_nothing(tmp_path):
    path = tmp_path / "settings.json"
    install_hooks(CMD, path=path, dry_run=True)
    assert not path.exists()
