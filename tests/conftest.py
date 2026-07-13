import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Keep every test's database inside tmp_path, never the real data dir."""
    monkeypatch.setenv("AGENT_CHECKPOINT_HOME", str(tmp_path / "data"))
    import agent_checkpoint_mcp.server as server

    server._storage = None
    yield
    if server._storage is not None:
        server._storage.close()
        server._storage = None
