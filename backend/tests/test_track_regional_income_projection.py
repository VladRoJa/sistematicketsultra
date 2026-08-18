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
