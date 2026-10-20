"""La recuperación no puede ocupar el perfil Chrome con worker activo."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/google_messages_rpa.sh"


def _fake_docker(tmp_path: Path, *, inspect_result: str = "true") -> dict[str, str]:
    docker_bin = tmp_path / "bin"
    docker_bin.mkdir()
    executable = docker_bin / "docker"
    executable.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$DOCKER_CALLS"\n'
        'if [[ "$1" == "compose" && "$2" == "--profile" '
        '&& "$3" == "scheduler" && "$4" == "ps" ]]; then\n'
        '  echo "fake-sms-container"\n'
        '  exit 0\n'
        'fi\n'
        'if [[ "$1" == "inspect" ]]; then\n'
        '  if [[ "$FAKE_INSPECT_RESULT" == "unavailable" ]]; then exit 2; fi\n'
        '  echo "$FAKE_INSPECT_RESULT"\n'
        '  exit 0\n'
        'fi\n'
        'echo "Unexpected docker call" >&2\n'
        'exit 88\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(docker_bin) + os.pathsep + env.get("PATH", "")
    env["FAKE_INSPECT_RESULT"] = inspect_result
    env["DOCKER_CALLS"] = str(tmp_path / "docker_calls.txt")
    return env


@pytest.mark.parametrize("command", [
    ("start-pairing",), ("diagnose",), ("test", "5555555555"),
])
def test_profile_owning_commands_blocked_when_sms_worker_is_running(
    tmp_path: Path, command: tuple[str, ...]
) -> None:
    env = _fake_docker(tmp_path)
    result = subprocess.run(
        ["bash", str(SCRIPT), *command],
        capture_output=True, text=True, env=env, timeout=5,
    )
    assert result.returncode != 0
    assert "gasca-sms-worker sigue activo" in result.stderr
    calls = Path(env["DOCKER_CALLS"]).read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
    assert "ps -a -q gasca-sms-worker" in calls[0]
    assert calls[1].startswith("inspect ")
    assert "exec" not in "\n".join(calls)
    assert "stop" not in "\n".join(calls)


@pytest.mark.parametrize("inspect", ["unavailable", "maybe"])
def test_recovery_fails_closed_if_worker_state_cannot_be_verified(
    tmp_path: Path, inspect: str
) -> None:
    env = _fake_docker(tmp_path, inspect_result=inspect)
    result = subprocess.run(
        ["bash", str(SCRIPT), "start-pairing"],
        capture_output=True, text=True, env=env, timeout=5,
    )
    assert result.returncode != 0
    assert "Operación cancelada" in result.stderr
    calls = Path(env["DOCKER_CALLS"]).read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
