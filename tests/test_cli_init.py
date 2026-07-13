from agent_checkpoint_mcp.cli import main


def test_init_creates_both_files(tmp_path, capsys):
    assert main(["init", "--project", str(tmp_path)]) == 0
    for name in ("CLAUDE.md", "AGENTS.md"):
        content = (tmp_path / name).read_text(encoding="utf-8")
        assert "Checkpoint discipline" in content
        assert "save_checkpoint" in content


def test_init_appends_without_clobbering(tmp_path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My project\n\nRun tests with make test.\n", encoding="utf-8")
    main(["init", "--project", str(tmp_path)])
    content = claude_md.read_text(encoding="utf-8")
    assert content.startswith("# My project")
    assert "Checkpoint discipline" in content


def test_init_is_idempotent(tmp_path):
    main(["init", "--project", str(tmp_path)])
    once = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    main(["init", "--project", str(tmp_path)])
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == once
