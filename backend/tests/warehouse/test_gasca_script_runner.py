from datetime import date

import pytest
from flask import Flask

from app.warehouse.services import gasca_script_runner as runner


def _build_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        WAREHOUSE_GASCA_SCRIPT_STRATEGY="single_report",
    )
    return app


def test_socios_vencidos_is_allowed_and_dispatched_to_single_report():
    app = _build_app()
    captured = {}

    def fake_single_report_runner(**kwargs):
        captured.update(kwargs)
        return {
            "report_type_key": kwargs["report_type_key"],
            "original_filename": "socios_vencidos_test.xlsx",
            "file_bytes": b"fake-xlsx",
        }

    app.config["WAREHOUSE_GASCA_SINGLE_REPORT_RUNNER"] = (
        fake_single_report_runner
    )

    with app.app_context():
        result = runner.run_gasca_script_report(
            report_type_key="socios_vencidos",
            run_mode="manual_retry",
            snapshot_kind="daily",
            requested_by="unit_test",
            trigger_source="unit_test",
            date_from=date(2026, 8, 23),
            date_to=date(2026, 8, 23),
        )

    assert captured["report_type_key"] == "socios_vencidos"
    assert captured["date_from"] == date(2026, 8, 23)
    assert captured["date_to"] == date(2026, 8, 23)

    assert result["report_type_key"] == "socios_vencidos"


def test_unknown_report_type_remains_rejected():
    app = _build_app()

    with app.app_context():
        with pytest.raises(
            ValueError,
            match="report_type_key.*no es válido",
        ):
            runner.run_gasca_script_report(
                report_type_key="reporte_inventado",
                run_mode="manual_retry",
                snapshot_kind="daily",
            )
