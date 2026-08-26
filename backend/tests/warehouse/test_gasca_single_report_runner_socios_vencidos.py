from contextlib import nullcontext
from datetime import date, datetime as real_datetime

import pytest
from flask import Flask

from app.warehouse.services import gasca_single_report_runner_impl as runner


class _FixedDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 8, 24, 12, 0, 0)

        if tz is not None:
            return tz.localize(value)

        return value


class _FakePage:
    def goto(self, *args, **kwargs):
        return None

    def wait_for_load_state(self, *args, **kwargs):
        return None


class _FakeLoadingLocator:
    @property
    def first(self):
        return self

    def wait_for(self, *args, **kwargs):
        raise runner.PlaywrightTimeoutError("loader not observed")


class _FakeRowsLocator:
    def count(self):
        return 17


class _FakeWaitPage:
    def __init__(self):
        self.waited_selectors = []
        self.located_selectors = []

    def get_by_text(self, *args, **kwargs):
        return _FakeLoadingLocator()

    def wait_for_selector(self, selector, *args, **kwargs):
        self.waited_selectors.append(selector)

    def locator(self, selector):
        self.located_selectors.append(selector)
        return _FakeRowsLocator()


def _build_runtime():
    return runner.GascaRuntimeConfig(
        user="test",
        password="test",
        login_url="https://example.test/login",
        reportes_url="https://example.test/reportes",
        show_browser=False,
        timezone_name="America/Tijuana",
    )


@pytest.mark.parametrize(
    ("date_from", "date_to", "message"),
    [
        (None, date(2026, 8, 23), "date_from es requerido"),
        (date(2026, 8, 23), None, "date_to es requerido"),
        (
            date(2026, 8, 24),
            date(2026, 8, 23),
            "date_from no puede ser posterior",
        ),
        (
            date(2026, 8, 23),
            date(2026, 8, 25),
            "date_to no puede ser una fecha futura",
        ),
    ],
)
def test_socios_vencidos_rejects_invalid_ranges(
    monkeypatch,
    date_from,
    date_to,
    message,
):
    monkeypatch.setattr(runner, "datetime", _FixedDateTime)

    with pytest.raises(runner.GascaSingleReportRunnerError, match=message):
        runner._validate_socios_vencidos_date_range(
            runtime=_build_runtime(),
            date_from=date_from,
            date_to=date_to,
        )


def test_socios_vencidos_downloads_raw_without_generic_cleanup(
    monkeypatch,
    tmp_path,
):
    captured = {}
    artifact_path = tmp_path / "socios_vencidos.xlsx"

    monkeypatch.setattr(runner, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        runner,
        "_seleccionar_tipo_reporte",
        lambda page, report_name: captured.setdefault(
            "report_name",
            report_name,
        ),
    )

    def fake_fill_dates(*, page, fecha_inicio, fecha_fin):
        captured["fecha_inicio"] = fecha_inicio
        captured["fecha_fin"] = fecha_fin

    monkeypatch.setattr(
        runner,
        "_rellenar_fechas_rango_simple",
        fake_fill_dates,
    )
    monkeypatch.setattr(
        runner,
        "_click_boton_generar",
        lambda page: None,
    )
    monkeypatch.setattr(
        runner,
        "_esperar_tabla_socios_vencidos",
        lambda **kwargs: 17,
    )
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
        lambda *args, **kwargs: pytest.fail(
            "socios_vencidos no debe usar la limpieza genérica"
        ),
    )

    app = Flask(__name__)
    with app.app_context():
        returned_path, metadata = runner._run_socios_vencidos_report(
            page=_FakePage(),
            runtime=_build_runtime(),
            date_from=date(2026, 8, 23),
            date_to=date(2026, 8, 23),
        )

    assert returned_path == artifact_path
    assert captured == {
        "report_name": "Reporte Socios Vencidos",
        "fecha_inicio": date(2026, 8, 23),
        "fecha_fin": date(2026, 8, 23),
    }
    assert metadata["date_from"] == "2026-08-23"
    assert metadata["date_to"] == "2026-08-23"
    assert metadata["branch_scope"] == "unfiltered"
    assert metadata["approximate_row_count"] == 17
    assert metadata["raw_file_preserved"] is True


def test_socios_vencidos_waits_for_visible_rows_only():
    page = _FakeWaitPage()
    app = Flask(__name__)

    with app.app_context():
        row_count = runner._esperar_tabla_socios_vencidos(
            page=page,
            timeout_seconds=1,
        )

    assert row_count == 17
    assert page.waited_selectors == [
        "table tbody tr:visible",
        "button:has-text('Exportar')",
    ]
    assert page.located_selectors == [
        "table tbody tr:visible",
    ]


def test_run_gasca_single_report_dispatches_explicit_date_range(
    monkeypatch,
    tmp_path,
):
    captured = {}
    artifact_path = tmp_path / "socios_vencidos.xlsx"
    artifact_path.write_bytes(b"fake-xlsx")

    monkeypatch.setattr(runner, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        runner,
        "_resolve_runtime_config",
        _build_runtime,
    )
    monkeypatch.setattr(
        runner,
        "_authenticated_page",
        lambda runtime: nullcontext(_FakePage()),
    )

    def fake_run(*, page, runtime, date_from, date_to):
        captured["date_from"] = date_from
        captured["date_to"] = date_to
        return artifact_path, {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }

    monkeypatch.setattr(
        runner,
        "_run_socios_vencidos_report",
        fake_run,
    )

    app = Flask(__name__)
    with app.app_context():
        result = runner.run_gasca_single_report(
            report_type_key=runner.SOCIOS_VENCIDOS_REPORT_TYPE_KEY,
            run_mode="manual_retry",
            snapshot_kind="daily",
            date_from=date(2026, 8, 23),
            date_to=date(2026, 8, 23),
        )

    assert captured == {
        "date_from": date(2026, 8, 23),
        "date_to": date(2026, 8, 23),
    }
    assert result["report_type_key"] == "socios_vencidos"
    assert result["metadata"]["date_from"] == "2026-08-23"
    assert result["metadata"]["date_to"] == "2026-08-23"
