"""Smoke test: drive the FastMCP server through a real in-memory MCP session."""

import pytest

from mcp.shared.memory import create_connected_server_and_client_session as client_session

import agent_checkpoint_mcp.server as server


def _text(result) -> str:
    return result.content[0].text


SAVE_ARGS = {
    "plan": "1. Build storage\n2. Build server\n3. Write docs",
    "current_step": 2,
    "total_steps": 3,
    "step_status": "in_progress",
    "what_was_done": "- storage.py done, tests pass",
    "what_remains": "- implement get_checkpoint formatting",
}


async def test_full_tool_flow(tmp_path):
    project = str(tmp_path / "proj")
    args = {**SAVE_ARGS, "project_dir": project}

    # anyio cancel scopes must open and close in the same task, so the
    # session lives inside the test rather than in a fixture.
    async with client_session(server.mcp._mcp_server) as client:
        await _run_full_tool_flow(client, project, args)


async def _run_full_tool_flow(client, project, args):
    tools = {t.name for t in (await client.list_tools()).tools}
    assert tools == {
        "save_checkpoint",
        "get_checkpoint",
        "list_checkpoints",
        "clear_checkpoints",
    }

    # No checkpoint yet
    out = _text(await client.call_tool("get_checkpoint", {"project_dir": project}))
    assert "No checkpoint exists" in out

    # Save → get
    out = _text(await client.call_tool("save_checkpoint", args))
    assert "Checkpoint #" in out and "step 2/3" in out

    out = _text(await client.call_tool("get_checkpoint", {"project_dir": project}))
    assert "step 2/3" in out
    assert "get_checkpoint formatting" in out
    assert "do NOT redo" in out

    # List
    out = _text(await client.call_tool("list_checkpoints", {"project_dir": project}))
    assert "storage.py done" in out

    # Clear requires confirm
    out = _text(await client.call_tool("clear_checkpoints", {"project_dir": project}))
    assert "would delete 1" in out
    out = _text(
        await client.call_tool(
            "clear_checkpoints", {"project_dir": project, "confirm": True}
        )
    )
    assert "Deleted 1" in out
    out = _text(await client.call_tool("get_checkpoint", {"project_dir": project}))
    assert "No checkpoint exists" in out


async def test_invalid_status_is_tool_error(tmp_path):
    args = {**SAVE_ARGS, "step_status": "nope", "project_dir": str(tmp_path)}
    async with client_session(server.mcp._mcp_server) as client:
        result = await client.call_tool("save_checkpoint", args)
        assert result.isError
