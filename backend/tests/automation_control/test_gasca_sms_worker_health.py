"""La observabilidad SMS no inicia sesiones de navegador ni envía mensajes."""
from unittest.mock import patch

from app.rpa.workers.gasca_sms_worker import _report_worker_health


def test_heartbeat_reports_queue_on_demand_not_a_fixed_schedule():
    with patch(
        "app.rpa.workers.gasca_sms_worker.emit_worker_heartbeat"
    ) as heartbeat:
        _report_worker_health()

    heartbeat.assert_called_once()
    args, kwargs = heartbeat.call_args
    assert args == ("gasca-sms-worker",)
    assert kwargs["poll_interval_seconds"] == 30
    snapshot = kwargs["schedules_provider"]()
    assert set(snapshot) == {"gasca.sms_dispatch"}
    assert snapshot["gasca.sms_dispatch"]["enabled"] is True
    assert snapshot["gasca.sms_dispatch"]["kind"] == "PENDING_REQUEST"
    assert snapshot["gasca.sms_dispatch"]["conditional"] is True
    assert snapshot["gasca.sms_dispatch"]["slots"] == []


def test_heartbeat_failure_never_interrupts_sms_worker():
    with patch(
        "app.rpa.workers.gasca_sms_worker.emit_worker_heartbeat",
        side_effect=RuntimeError("monitor unavailable"),
    ):
        _report_worker_health()
