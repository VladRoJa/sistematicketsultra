"""Issue #1129: actual worker process lifecycle with ALL send gates closed.

This subprocess smoke test uses an in-memory SQLite configuration solely for
Flask initialization. It never opens PostgreSQL or calls the provider. The
separate PostgreSQL 16 Gate A exercises durable job transitions and fencing.
"""
from __future__ import annotations

import os
import re
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = """
import logging
import sys
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(levelname)s:%(message)s")
from app.services import marketing_campaign_v2_background_worker as worker

# The Flask import may reconfigure the root logger in CI. Capture only the
# worker logger explicitly, so lifecycle assertions observe its INFO events.
worker_handler = logging.StreamHandler(sys.stdout)
worker_handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
worker.LOG.addHandler(worker_handler)
worker.LOG.setLevel(logging.INFO)

original_create_app = worker.create_app
def safe_app():
    app = original_create_app()
    assert app.config["CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY"] is False
    assert not worker._enabled(app.config)
    print("QA_WORKER_GATE_HARD_OFF", flush=True)
    return app

worker.create_app = safe_app
worker.main()
"""


def _boot_worker():
    env = os.environ.copy()
    env.update({
        "APP_ENV": "testing",
        "SECRET_KEY": "synthetic-worker-process-only",
        "JWT_SECRET_KEY": "synthetic-worker-process-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED": "true",
        "CAMPAIGN_V2_PROVIDER_SEND_ENABLED": "true",
        "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED": "true",
        "IVENTAS_CAMPAIGN_SEND_API_KEY": "",
        "IVENTAS_CAMPAIGN_SEND_API_BASE_URL": "http://127.0.0.1:9",
        "CAMPAIGN_V2_BG_POLL_SECONDS": "2",
    })
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", BOOTSTRAP],
        cwd=ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    seen = []
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AssertionError(
                    f"Worker exited before ready: code={proc.returncode}, output={''.join(seen)}"
                )
            remaining = max(0.0, min(1.0, deadline - time.monotonic()))
            readable, _, _ = select.select([proc.stdout], [], [], remaining)
            if not readable:
                continue
            line = proc.stdout.readline()
            seen.append(line)
            if "Background dispatch worker ready (id=" in line:
                output = "".join(seen)
                assert "QA_WORKER_GATE_HARD_OFF" in output, output
                matched = re.search(r"worker ready \(id=([0-9a-f]{32})\)", line)
                assert matched is not None, output
                return proc, matched.group(1)
        raise AssertionError(f"Worker did not start within test gate: {''.join(seen)}")
    except Exception:
        proc.kill()
        proc.communicate(timeout=10)
        raise


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal lifecycle gate")
def test_disabled_worker_start_sigterm_sigkill_and_safe_restart():
    # Real Python process and app factory; NO provider/DB sends are possible.
    first, first_id = _boot_worker()
    try:
        first.send_signal(signal.SIGTERM)
        output, _ = first.communicate(timeout=12)
        assert first.returncode == 0, output
        assert "Background dispatch worker stopped" in output
        assert "Background dispatch cycle blocked" not in output
    finally:
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=10)

    crashed, crashed_id = _boot_worker()
    try:
        crashed.kill()  # simulate abrupt process/container death
        crashed.communicate(timeout=10)
        assert crashed.returncode == -signal.SIGKILL
    finally:
        if crashed.poll() is None:
            crashed.kill()
            crashed.communicate(timeout=10)

    restarted, restarted_id = _boot_worker()
    try:
        restarted.send_signal(signal.SIGTERM)
        output, _ = restarted.communicate(timeout=12)
        assert restarted.returncode == 0, output
        assert "Background dispatch worker stopped" in output
        assert "Background dispatch cycle blocked" not in output
    finally:
        if restarted.poll() is None:
            restarted.kill()
            restarted.communicate(timeout=10)
    assert len({first_id, crashed_id, restarted_id}) == 3
