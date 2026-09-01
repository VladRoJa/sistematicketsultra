from datetime import date, datetime as real_datetime

import pytest
from flask import Flask

from app.warehouse.services import gasca_single_report_runner_impl as runner


class _FixedDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 8, 7, 12, 0, 0)

        if tz is not None:
            return tz.localize(value)

        return value


class _FakeAjaxResponse:
    url = (
        "https://example.test/"
        "Modulo/Reporte/ReporteVentaTotal_Ajax"
    )
    status = 200


class _FakeExpectedResponse:
    value = _FakeAjaxResponse()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePage:
    def goto(self, *args, **kwargs):
        return None

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def wait_for_selector(self, *args, **kwargs):
        return None

    def expect_response(self, predicate, **kwargs):
        response = _FakeAjaxResponse()
        assert predicate(response)
        return _FakeExpectedResponse()


def _build_runtime():
    return runner.GascaRuntimeConfig(
        user="test",
        password="test",
        login_url="https://example.test/login",
        reportes_url="https://example.test/reportes",
        show_browser=False,
        timezone_name="America/Tijuana",
    )


def test_venta_total_uses_target_business_date_for_historical_close(
    monkeypatch,
    tmp_path,
):
    captured_dates = {}

    monkeypatch.setattr(runner, "datetime", _FixedDateTime)

    monkeypatch.setattr(
        runner,
        "_seleccionar_tipo_reporte",
        lambda *args, **kwargs: None,
    )

    def fake_fill_dates(*, page, fecha_inicio, fecha_fin):
        captured_dates["fecha_inicio"] = fecha_inicio
        captured_dates["fecha_fin"] = fecha_fin

    monkeypatch.setattr(
        runner,
        "_rellenar_fechas_rango_simple",
        fake_fill_dates,
    )

    monkeypatch.setattr(
        runner,
        "_click_boton_generar",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        runner,
        "_esperar_fin_carga_venta_total",
        lambda *args, **kwargs: None,
    )

    artifact_path = tmp_path / "venta_total.xlsx"

    monkeypatch.setattr(
        runner,
        "_resolve_contractual_output_path",
        lambda **kwargs: artifact_path,
    )

    def fake_download(*, destination_path, **kwargs):
        destination_path.write_bytes(b"fake-xlsx")

    monkeypatch.setattr(
        runner,
        "_descargar_excel_desde_tabla",
        fake_download,
    )

    monkeypatch.setattr(
        runner,
        "_limpiar_excel_inplace",
        lambda *args, **kwargs: None,
    )

    app = Flask(__name__)

    with app.app_context():
        returned_path, metadata = runner._run_venta_total_report(
            page=_FakePage(),
            runtime=_build_runtime(),
            target_business_date=date(2026, 7, 31),
        )

    assert returned_path == artifact_path

    assert captured_dates == {
        "fecha_inicio": date(2026, 7, 1),
        "fecha_fin": date(2026, 7, 31),
    }

    assert metadata["date_from"] == "2026-07-01"
    assert metadata["date_to"] == "2026-07-31"
    assert metadata["snapshot_kind_hint"] == "daily"


def test_venta_total_rejects_future_target_business_date(monkeypatch):
    monkeypatch.setattr(runner, "datetime", _FixedDateTime)

    monkeypatch.setattr(
        runner,
        "_seleccionar_tipo_reporte",
        lambda *args, **kwargs: None,
    )

    app = Flask(__name__)

    with app.app_context():
        with pytest.raises(
            runner.GascaSingleReportRunnerError,
            match="target_business_date no puede ser una fecha futura",
        ):
            runner._run_venta_total_report(
                page=_FakePage(),
                runtime=_build_runtime(),
                target_business_date=date(2026, 8, 8),
            )


def test_venta_total_ajax_302_is_detected_as_report_failure():
    class FakeResponse:
        url = (
            "https://ultragimnasios.com/"
            "Modulo/Reporte/ReporteVentaTotal_Ajax"
        )
        status = 302

    with pytest.raises(
        runner.GascaSingleReportRunnerError,
        match="ReporteVentaTotal_Ajax.*302",
    ):
        runner._validate_venta_total_ajax_response(
            FakeResponse()
        )


def test_venta_total_stops_before_loader_wait_when_ajax_returns_302(
    monkeypatch,
    tmp_path,
):
    class FakeResponse:
        url = (
            "https://ultragimnasios.com/"
            "Modulo/Reporte/ReporteVentaTotal_Ajax"
        )
        status = 302

    class FakeExpectedResponse:
        value = FakeResponse()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakePage:
        def goto(self, *args, **kwargs):
            return None

        def wait_for_load_state(self, *args, **kwargs):
            return None

        def wait_for_selector(self, *args, **kwargs):
            return None

        def expect_response(self, predicate, **kwargs):
            assert predicate(FakeResponse())
            return FakeExpectedResponse()

    monkeypatch.setattr(runner, "datetime", _FixedDateTime)

    monkeypatch.setattr(
        runner,
        "_seleccionar_tipo_reporte",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        runner,
        "_rellenar_fechas_rango_simple",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        runner,
        "_click_boton_generar",
        lambda *args, **kwargs: None,
    )

    loader_wait_called = {"value": False}

    def fake_wait_loader(*args, **kwargs):
        loader_wait_called["value"] = True

    monkeypatch.setattr(
        runner,
        "_esperar_fin_carga_venta_total",
        fake_wait_loader,
    )

    monkeypatch.setattr(
        runner,
        "_resolve_contractual_output_path",
        lambda **kwargs: tmp_path / "venta_total.xlsx",
    )

    monkeypatch.setattr(
        runner,
        "_descargar_excel_desde_tabla",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        runner,
        "_limpiar_excel_inplace",
        lambda *args, **kwargs: None,
    )

    app = Flask(__name__)

    with app.app_context():
        with pytest.raises(
            runner.GascaSingleReportRunnerError,
            match="ReporteVentaTotal_Ajax.*302",
        ):
            runner._run_venta_total_report(
                page=FakePage(),
                runtime=_build_runtime(),
                target_business_date=date(2026, 7, 31),
            )

    assert loader_wait_called["value"] is False

