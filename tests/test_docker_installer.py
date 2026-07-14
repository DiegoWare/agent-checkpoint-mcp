import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "install" / "docker.sh"


def _servers(home):
    path = home / ".codex" / "config.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")).get("mcp_servers", {})


def test_one_command_install_disable_and_uninstall(tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    # The fake Docker CLI exercises the host installer without a daemon. For
    # the staged config container it maps /config back to the bind source and
    # executes the same Python module the real image entrypoint uses.
    docker = fake_bin / "docker"
    docker.write_text(
        f"""#!{sys.executable}
import os
import subprocess
import sys

args = sys.argv[1:]
if args[:1] in (["info"], ["build"]):
    raise SystemExit(0)
if args[:2] == ["image", "inspect"]:
    raise SystemExit(0)
if args[:2] == ["volume", "create"]:
    print(args[-1])
    raise SystemExit(0)
if args[:1] == ["run"] and "config" in args:
    stage = None
    for value in args:
        if value.startswith("type=bind,source=") and value.endswith(",target=/config"):
            stage = value.removeprefix("type=bind,source=").removesuffix(",target=/config")
            break
    if stage is None:
        raise SystemExit("missing staged config mount")
    config_args = args[args.index("config") + 1:]
    config_args = [stage if value == "/config" else value for value in config_args]
    result = subprocess.run(
        [sys.executable, "-m", "agent_checkpoint_mcp.docker_config", *config_args],
        env=os.environ,
    )
    raise SystemExit(result.returncode)
if args[:1] == ["run"] and "init-volumes" in args:
    raise SystemExit(0)
raise SystemExit(f"unexpected docker invocation: {{args}}")
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    codex = fake_bin / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o755)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["PYTHONPATH"] = str(ROOT / "src")

    subprocess.run([str(INSTALLER), "install"], cwd=ROOT, env=env, check=True)
    assert set(_servers(home)) == {"agent-checkpoint", "codebase-memory-mcp"}

    subprocess.run(
        [str(INSTALLER), "disable", "codebase"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    assert set(_servers(home)) == {"agent-checkpoint"}

    subprocess.run([str(INSTALLER), "uninstall"], cwd=ROOT, env=env, check=True)
    assert _servers(home) == {}
