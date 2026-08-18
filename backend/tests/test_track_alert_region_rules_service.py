from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.track_alerts.services import track_alert_region_rules_service as service


def test_regional_detail_resolves_once_and_uses_only_resolved_version():
    resolved_version = SimpleNamespace(
        id=321,
        version_type="cierre_canonico",
        status="success",
    )

    empty_rankings = {
        "income_ranking": [],
        "income_compliance_ranking": [],
        "new_clients_ranking": [],
    }

    with (
        patch.object(
            service,
            "resolve_effective_track_daily_version",
            return_value=resolved_version,
        ) as resolve_version,
        patch.object(
            service,
            "evaluate_regional_rankings",
            return_value=empty_rankings,
        ) as evaluate_rankings,
        patch.object(
            service,
            "_load_track_rows_with_region",
            return_value=[],
        ) as load_rows,
    ):
        result = service.get_regional_detail(
            track_date=date(2026, 4, 30),
            generation_mode="official_closed_day",
        )

    resolve_version.assert_called_once_with(
        track_date=date(2026, 4, 30),
        generation_mode="official_closed_day",
    )
    evaluate_rankings.assert_called_once_with(
        track_date=date(2026, 4, 30),
        generation_mode="official_closed_day",
        track_daily_version_id=321,
    )
    load_rows.assert_called_once_with(track_daily_version_id=321)
    assert result["resolved_version"] == {
        "id": 321,
        "version_type": "cierre_canonico",
        "status": "success",
    }


def test_regional_detail_is_explicitly_empty_without_version():
    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=None,
    ), patch.object(
        service,
        "_load_track_rows_with_region",
    ) as load_rows:
        result = service.get_regional_detail(
            track_date=date(2026, 8, 17),
            generation_mode="manual_preview",
        )

    load_rows.assert_not_called()
    assert result["resolved_version"] is None
    assert result["regions"] == []
    assert result["rankings"] == {
        "income_compliance": [],
        "income": [],
        "new_clients": [],
    }


def test_regional_loader_filters_by_version_id_not_date_and_mode():
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = []

    with patch.object(service.db.session, "query", return_value=query):
        service._load_track_rows_with_region(track_daily_version_id=777)

    filter_expressions = query.filter.call_args.args
    filter_sql = " ".join(str(expression) for expression in filter_expressions)

    assert "track_daily_mart.track_daily_version_id" in filter_sql
    assert "track_daily_mart.track_date" not in filter_sql
    assert "track_daily_mart.generation_mode" not in filter_sql
