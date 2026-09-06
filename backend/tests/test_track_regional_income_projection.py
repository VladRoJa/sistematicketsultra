from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.warehouse.services import track_forecast_service as service


def test_income_projection_is_available_only_with_qualified_history():
    curve = {
        "historical_months": 4,
        "historical_mtd_total": 400000.0,
        "historical_progress_pct": 0.5,
        "confidence": "alta",
    }

    with patch.object(
        service,
        "_build_historical_curve",
        return_value=curve,
    ), patch.object(
        service,
        "_resolve_branch_projection_quality_issue",
        return_value=None,
    ):
        result = service.build_branch_income_projection_summary(
            sucursal_canon="PAPALOTE_TJ",
            target_month=date(2026, 8, 1),
            cutoff_day=17,
            current_income_mtd=Decimal("125000"),
    )

    assert result["status"] == "available"
    assert Decimal(result["projected_close"]) == Decimal("250000")
    assert result["historical_progress_pct_at_cutoff"] == "50.0"


def test_income_projection_reports_insufficient_history_without_fallback():
    curve = {
        "historical_months": 2,
        "historical_mtd_total": 100000.0,
        "historical_progress_pct": 0.4,
        "confidence": "media",
    }
    quality_issue = {
        "code": "insufficient_branch_history",
        "message": "Histórico insuficiente.",
    }

    with patch.object(
        service,
        "_build_historical_curve",
        return_value=curve,
    ), patch.object(
        service,
        "_resolve_branch_projection_quality_issue",
        return_value=quality_issue,
    ):
        result = service.build_branch_income_projection_summary(
            sucursal_canon="PAPALOTE_TJ",
            target_month=date(2026, 8, 1),
            cutoff_day=17,
            current_income_mtd=Decimal("40000"),
        )

    assert result["status"] == "insufficient_history"
    assert result["projected_close"] is None
    assert result["quality_issue"] == quality_issue

def test_income_projection_uses_linear_pace_before_12_operating_months():
    with patch.object(
        service,
        "_build_historical_curve",
    ) as historical_curve:
        result = service.build_branch_income_projection_summary(
            sucursal_canon="METEPEC",
            target_month=date(2026, 9, 1),
            cutoff_day=6,
            current_income_mtd=Decimal("191790.12"),
            first_store_income_date=date(2026, 1, 21),
        )

    historical_curve.assert_not_called()

    assert result["status"] == "available"
    assert result["method"] == "linear_mtd_pace"
    assert result["projection_label"] == "Proyección lineal"
    assert Decimal(result["projected_close"]) == Decimal("958950.60")
    assert result["quality_issue"] is None

def test_income_projection_uses_historical_pace_after_12_operating_months():
    curve = {
        "historical_months": 1,
        "historical_mtd_total": 100000.0,
        "historical_progress_pct": 0.5,
        "confidence": "baja",
    }

    with patch.object(
        service,
        "_build_historical_curve",
        return_value=curve,
    ):
        result = service.build_branch_income_projection_summary(
            sucursal_canon="PAPALOTE_TJ",
            target_month=date(2026, 9, 1),
            cutoff_day=6,
            current_income_mtd=Decimal("125000"),
            first_store_income_date=date(2025, 8, 1),
        )

    assert result["status"] == "available"
    assert result["method"] == "existing_stable_historical_pace"
    assert result["projection_label"] == "Proyección histórica"
    assert Decimal(result["projected_close"]) == Decimal("250000")

def test_income_projection_without_operating_date_keeps_legacy_history_gate():
    curve = {
        "historical_months": 1,
        "historical_mtd_total": 100000.0,
        "historical_progress_pct": 0.5,
        "confidence": "baja",
    }

    with patch.object(
        service,
        "_build_historical_curve",
        return_value=curve,
    ):
        result = service.build_branch_income_projection_summary(
            sucursal_canon="BRANCH_TEST",
            target_month=date(2026, 9, 1),
            cutoff_day=6,
            current_income_mtd=Decimal("125000"),
        )

    assert result["status"] == "insufficient_history"
    assert result["projected_close"] is None
