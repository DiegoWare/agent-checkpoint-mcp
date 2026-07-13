import tomllib

from agent_checkpoint_mcp.setup_agents import _merge_codex_text

CMD = ["/opt/bin/agent-checkpoint-mcp"]


def test_append_to_existing_config():
    text = '[mcp_servers.other]\ncommand = "other"\nargs = []\n'
    merged = _merge_codex_text(text, CMD)
    parsed = tomllib.loads(merged)
    assert set(parsed["mcp_servers"]) == {"other", "agent-checkpoint"}
    assert parsed["mcp_servers"]["agent-checkpoint"]["command"] == CMD[0]


def test_rerun_replaces_own_section_even_with_brackets_in_args():
    # Regression: `args = []` contains '[', which used to truncate the
    # section match and corrupt the file on re-run.
    text = _merge_codex_text("", CMD)
    assert "args = []" in text
    merged = _merge_codex_text(text, ["/new/bin/agent-checkpoint-mcp", "--flag"])
    parsed = tomllib.loads(merged)
    servers = parsed["mcp_servers"]
    assert list(servers) == ["agent-checkpoint"]
    assert servers["agent-checkpoint"]["command"] == "/new/bin/agent-checkpoint-mcp"
    assert servers["agent-checkpoint"]["args"] == ["--flag"]


def test_replace_preserves_following_sections():
    text = (
        '[mcp_servers."agent-checkpoint"]\ncommand = "/old"\nargs = []\n'
        "\n[hooks.state]\nfoo = 1\n"
    )
    merged = _merge_codex_text(text, CMD)
    parsed = tomllib.loads(merged)
    assert parsed["hooks"]["state"]["foo"] == 1
    assert parsed["mcp_servers"]["agent-checkpoint"]["command"] == CMD[0]


def test_empty_config():
    parsed = tomllib.loads(_merge_codex_text("", CMD))
    assert parsed["mcp_servers"]["agent-checkpoint"]["args"] == []
