import pytest

from agent_checkpoint_mcp.project import data_dir, find_project_root
from agent_checkpoint_mcp.storage import Storage


@pytest.fixture
def store(tmp_path):
    s = Storage(tmp_path / "test.db")
    yield s
    s.close()


def _save(store, project="/p/alpha", **overrides):
    fields = dict(
        project=project,
        session_id="sess0001",
        plan="1. First\n2. Second",
        current_step=1,
        total_steps=2,
        step_status="in_progress",
        what_was_done="- created foo.py",
        what_remains="- wire foo into bar.py",
    )
    fields.update(overrides)
    return store.save(**fields)


def test_save_and_latest_roundtrip(store):
    cp = _save(store)
    latest = store.latest("/p/alpha")
    assert latest == cp
    assert latest.plan == "1. First\n2. Second"
    assert latest.created_at.endswith("Z")


def test_latest_returns_most_recent(store):
    _save(store, what_was_done="first")
    cp2 = _save(store, what_was_done="second", current_step=2)
    assert store.latest("/p/alpha").id == cp2.id


def test_projects_are_isolated(store):
    _save(store, project="/p/alpha")
    _save(store, project="/p/beta", what_was_done="beta work")
    assert store.latest("/p/alpha").what_was_done == "- created foo.py"
    assert store.latest("/p/beta").what_was_done == "beta work"
    assert store.count("/p/alpha") == 1


def test_list_orders_newest_first_and_limits(store):
    for i in range(5):
        _save(store, current_step=i + 1, total_steps=5)
    listed = store.list("/p/alpha", limit=3)
    assert len(listed) == 3
    assert [cp.current_step for cp in listed] == [5, 4, 3]


def test_clear_only_touches_one_project(store):
    _save(store, project="/p/alpha")
    _save(store, project="/p/beta")
    assert store.clear("/p/alpha") == 1
    assert store.latest("/p/alpha") is None
    assert store.count("/p/beta") == 1


def test_invalid_status_rejected(store):
    with pytest.raises(ValueError):
        _save(store, step_status="almost-done")


def test_data_dir_honors_env_override(tmp_path):
    assert str(data_dir()).startswith(str(tmp_path))  # via conftest env var


def test_find_project_root_walks_to_git(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "src" / "deep"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == str(repo)


def test_find_project_root_without_git_uses_dir(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert find_project_root(plain) == str(plain.resolve())
