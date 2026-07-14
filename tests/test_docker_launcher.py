import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = (
    Path(__file__).parents[1] / "install" / "agent-checkpoint-mcp-docker"
)


@pytest.mark.parametrize(
    ("target", "expected_volume", "expected_env"),
    [
        (
            "checkpoint",
            "source=agent-checkpoint-mcp-checkpoints,target=/data/checkpoint",
            "AGENT_CHECKPOINT_HOME=/data/checkpoint",
        ),
        (
            "codebase",
            "source=agent-checkpoint-mcp-codebase,target=/data/codebase",
            "CBM_CACHE_DIR=/data/codebase",
        ),
    ],
)
def test_launcher_builds_hardened_docker_command(
    tmp_path, target, expected_volume, expected_env
):
    repo = tmp_path / "repo with spaces"
    workdir = repo / "nested"
    workdir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-args"
    docker = fake_bin / "docker"
    docker.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["CAPTURE"] = str(capture)
    subprocess.run(
        [str(LAUNCHER), target, "--test-argument"],
        cwd=workdir,
        env=env,
        check=True,
    )

    args = capture.read_text(encoding="utf-8").splitlines()
    assert args[:3] == ["run", "--rm", "-i"]
    assert "--network" in args and "none" in args
    assert "--read-only" in args
    assert "ALL" in args
    assert "no-new-privileges" in args
    assert expected_env in args
    assert target in args
    assert args[-1] == "--test-argument"

    root = str(repo.resolve())
    assert f"type=bind,source={root},target={root},readonly" in args
    assert any(expected_volume in arg for arg in args)
    assert str(workdir.resolve()) in args
    if target == "codebase":
        assert f"CBM_ALLOWED_ROOT={root}" in args
