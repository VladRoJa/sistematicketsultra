from contextlib import nullcontext
from datetime import date, datetime as real_datetime

import pytest
from flask import Flask

from app.warehouse.services import gasca_single_report_runner_impl as runner


class _FixedDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 7, 12, 0, 0)
        if tz is not None:
            return tz.localize(value)
        return value


class _FakePage:
    def goto(self, *args, **kwargs):
        return None

    def wait_for_load_state(self, *args, **kwargs):
        return None


def _runtime():
    return runner.GascaRuntimeConfig(
        user="test",
        password="test",
        login_url="https://example.test/login",
        reportes_url="https://example.test/reportes",
        show_browser=False,
        timezone_name="America/Tijuana",
    )


def test_socios_activos_rejects_historical_cutoff(monkeypatch):
    monkeypatch.setattr(runner, "datetime", _FixedDateTime)
    with pytest.raises(
        runner.GascaSingleReportRunnerError,
        match="universo actual",
    ):
        runner._resolve_socios_activos_cutoff_date(
            runtime=_runtime(),
            target_business_date=date(2026, 9, 6),
        )


def test_socios_activos_downloads_current_raw_without_date_filters(
    monkeypatch,
    tmp_path,
):
    artifact_path = tmp_path / "socios_activos.xlsx"
    captured = {}

    monkeypatch.setattr(runner, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        runner,
        "_seleccionar_tipo_reporte",
        lambda page, report_name: captured.setdefault("report_name", report_name),
    )
    monkeypatch.setattr(
        runner,
        "_rellenar_fechas_rango_simple",
        lambda *args, **kwargs: pytest.fail(
            "socios_activos no debe llenar un rango de fechas"
        ),
    )
    monkeypatch.setattr(
        runner,
        "_rellenar_corte_socios_activos",
        lambda *, page, cutoff_date: captured.setdefault(
            "cutoff_date",
            cutoff_date,
        ),
    )
    monkeypatch.setattr(runner, "_click_boton_generar", lambda page: None)
    monkeypatch.setattr(
        runner,
        "_esperar_tabla_socios_activos",
        lambda **kwargs: 26,
    )
    monkeypatch.setattr(
        runner,
        "_resolve_contractual_output_path",
        lambda **kwargs: artifact_path,
    )

    def fake_download(*, destination_path, **kwargs):
        destination_path.write_bytes(b"fake-xlsx")

    monkeypatch.setattr(runner, "_descargar_excel_desde_tabla", fake_download)

    app = Flask(__name__)
    with app.app_context():
        _, metadata = runner._run_socios_activos_report(
            page=_FakePage(),
            runtime=_runtime(),
            target_business_date=date(2026, 9, 7),
        )

    assert captured["report_name"] == "Reporte Socios Activos"
    assert captured["cutoff_date"] == date(2026, 9, 7)
    assert metadata["cutoff_date"] == "2026-09-07"
    assert metadata["branch_scope"] == "unfiltered"
    assert metadata["raw_file_preserved"] is True


def test_run_single_report_dispatches_socios_activos(monkeypatch, tmp_path):
    artifact_path = tmp_path / "socios_activos.xlsx"
    artifact_path.write_bytes(b"fake-xlsx")
    captured = {}

    monkeypatch.setattr(runner, "datetime", _FixedDateTime)
    monkeypatch.setattr(runner, "_resolve_runtime_config", _runtime)
    monkeypatch.setattr(
        runner,
        "_authenticated_page",
        lambda runtime: nullcontext(_FakePage()),
    )

    def fake_run(*, page, runtime, target_business_date):
        captured["target_business_date"] = target_business_date
        return artifact_path, {
            "cutoff_date": target_business_date.isoformat(),
        }

    monkeypatch.setattr(runner, "_run_socios_activos_report", fake_run)

    app = Flask(__name__)
    with app.app_context():
        result = runner.run_gasca_single_report(
            report_type_key="socios_activos",
            run_mode="scheduled_daily",
            snapshot_kind="daily",
            target_business_date=date(2026, 9, 7),
        )

    assert captured["target_business_date"] == date(2026, 9, 7)
    assert result["metadata"]["cutoff_date"] == "2026-09-07"
