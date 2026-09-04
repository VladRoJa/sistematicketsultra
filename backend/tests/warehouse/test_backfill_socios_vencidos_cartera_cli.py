from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date
from io import StringIO
import json
from types import SimpleNamespace

from scripts import backfill_socios_vencidos_cartera as cli
import app.warehouse.services.socios_vencidos_cartera_sync_service as sync_service


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _App:
    def app_context(self):
        return _Context()


class _SessionCleanup:
    def rollback(self):
        pass

    def remove(self):
        pass


def test_continue_on_error_cli_exits_one_after_processing_full_window(
    monkeypatch,
):
    calls = []

    def runner(**kwargs):
        calls.append((kwargs["date_from"], kwargs["date_to"]))
        if kwargs["date_from"] == date(2024, 2, 1):
            raise RuntimeError("febrero falló")
        return {
            "ingestion_status": "ingested",
            "snapshot_id": 91,
            "ingestion_metadata": {},
        }

    def backfill_service(**kwargs):
        return sync_service.backfill_socios_vencidos_cartera(
            **kwargs,
            job_runner=runner,
        )

    monkeypatch.setattr(cli, "create_app", _App)
    monkeypatch.setattr(
        cli,
        "backfill_socios_vencidos_cartera",
        backfill_service,
    )
    monkeypatch.setattr(
        sync_service,
        "db",
        SimpleNamespace(session=_SessionCleanup()),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_socios_vencidos_cartera.py",
            "--date-from",
            "2024-01-01",
            "--date-to",
            "2024-03-31",
            "--continue-on-error",
        ],
    )
    output = StringIO()

    with redirect_stdout(output):
        exit_code = cli.main()

    payload = json.loads(output.getvalue())
    assert exit_code == 1
    assert calls == [
        (date(2024, 1, 1), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2024, 3, 1), date(2024, 3, 31)),
    ]
    assert payload == {
        "date_from": "2024-01-01",
        "date_to": "2024-03-31",
        "chunks_processed": 2,
        "chunks_failed": 1,
        "last_successful_range": {
            "date_from": "2024-03-01",
            "date_to": "2024-03-31",
        },
        "failed_ranges": [
            {
                "date_from": "2024-02-01",
                "date_to": "2024-02-29",
                "error": "febrero falló",
            }
        ],
        "cleanup_warnings": [],
    }


def test_continue_on_error_cli_exits_zero_when_all_chunks_succeed(
    monkeypatch,
):
    observed = {}

    def backfill_service(**kwargs):
        observed.update(kwargs)
        return sync_service.SociosVencidosBackfillResult(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 31),
            chunks_processed=1,
            last_successful_range=(date(2024, 1, 1), date(2024, 1, 31)),
            cleanup_warnings=(),
        )

    monkeypatch.setattr(cli, "create_app", _App)
    monkeypatch.setattr(
        cli,
        "backfill_socios_vencidos_cartera",
        backfill_service,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_socios_vencidos_cartera.py",
            "--date-from",
            "2024-01-01",
            "--date-to",
            "2024-01-31",
            "--continue-on-error",
        ],
    )
    output = StringIO()

    with redirect_stdout(output):
        exit_code = cli.main()

    assert exit_code == 0
    assert observed["continue_on_error"] is True
    assert json.loads(output.getvalue())["chunks_failed"] == 0
