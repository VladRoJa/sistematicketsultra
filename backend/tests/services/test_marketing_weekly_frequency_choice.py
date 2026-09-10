from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_campaign_export_service as export_service
from app.services import marketing_reactivation_service as reactivation


NOW = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)


def _active_plan():
    rows = [
        {"phone_mx10": "6861000001"},
        {"phone_mx10": "6861000002"},
    ]
    return {
        "sources": {},
        "summary": {"eligible": len(rows)},
        "eligible_rows": rows,
    }


def _prepare(monkeypatch, action=None):
    monkeypatch.setattr(
        audience,
        "exported_counts",
        lambda *args, **kwargs: {
            "6861000001": 2,
            "6861000002": 1,
        },
    )
    filters = {"campaign_type": "BASCULA_RETENCION"}
    if action is not None:
        filters["weekly_frequency_action"] = action
    return audience.prepare_v1_plan(
        filters=filters,
        allowed_sucursal_keys=None,
        session=None,
        now=NOW,
        expired_builder=None,
        active_builder=lambda **kwargs: _active_plan(),
    )


def test_preview_reports_weekly_contacts_without_preselecting_action(monkeypatch):
    result = _prepare(monkeypatch)

    assert [row["phone_mx10"] for row in result["eligible_rows"]] == [
        "6861000001",
        "6861000002",
    ]
    assert result["summary"]["eligible"] == 2
    assert result["summary"]["weekly_limit_contacts"] == 1
    assert result["summary"]["weekly_frequency_decision_required"] is True
    assert result["summary"]["excluded_weekly_limit"] == 0
    assert "weekly_frequency_action" not in result["filters"]


def test_preview_excludes_weekly_contacts_only_after_explicit_choice(monkeypatch):
    result = _prepare(monkeypatch, audience.WEEKLY_FREQUENCY_EXCLUDE)

    assert [row["phone_mx10"] for row in result["eligible_rows"]] == [
        "6861000002",
    ]
    assert result["summary"]["eligible"] == 1
    assert result["summary"]["weekly_limit_contacts"] == 1
    assert result["summary"]["weekly_frequency_decision_required"] is False
    assert result["summary"]["excluded_weekly_limit"] == 1
    assert result["filters"]["weekly_frequency_action"] == "EXCLUDE"


def test_preview_keeps_weekly_contacts_after_explicit_choice(monkeypatch):
    result = _prepare(monkeypatch, audience.WEEKLY_FREQUENCY_KEEP)

    assert [row["phone_mx10"] for row in result["eligible_rows"]] == [
        "6861000001",
        "6861000002",
    ]
    assert result["summary"]["eligible"] == 2
    assert result["summary"]["weekly_limit_contacts"] == 1
    assert result["summary"]["weekly_frequency_decision_required"] is False
    assert result["summary"]["excluded_weekly_limit"] == 0
    assert result["filters"]["weekly_frequency_action"] == "KEEP"


def test_preview_rejects_invalid_weekly_frequency_action(monkeypatch):
    monkeypatch.setattr(audience, "exported_counts", lambda *args, **kwargs: {})

    with pytest.raises(
        reactivation.MarketingReactivationValidationError,
        match="EXCLUDE o KEEP",
    ):
        audience.prepare_v1_plan(
            filters={
                "campaign_type": "BASCULA_RETENCION",
                "weekly_frequency_action": "ALWAYS",
            },
            allowed_sucursal_keys=None,
            session=None,
            now=NOW,
            expired_builder=None,
            active_builder=lambda **kwargs: _active_plan(),
        )


def _serialized_campaign(action=None):
    filters = {"campaign_type": "BASCULA_RETENCION"}
    if action is not None:
        filters["weekly_frequency_action"] = action
    return {
        "id": 1,
        "name": "Segunda pasada",
        "status": "DRAFT",
        "filters": filters,
        "recipients": [
            {"phone_mx10": "6861000001", "sucursal": "CENTRO"},
        ],
    }


def test_export_keep_choice_overrides_only_frequency_conflict(monkeypatch):
    calls = []
    session = object()
    monkeypatch.setattr(
        export_service,
        "get_marketing_reactivation_campaign",
        lambda **kwargs: _serialized_campaign("KEEP"),
    )
    monkeypatch.setattr(
        export_service,
        "_validate_and_mark_exported",
        lambda **kwargs: (_ for _ in ()).throw(
            reactivation.MarketingReactivationConflictError("frecuencia")
        ),
    )
    monkeypatch.setattr(
        export_service,
        "_mark_keep_override_exported",
        lambda **kwargs: calls.append(kwargs),
    )

    file_bytes, filename = export_service.export_marketing_reactivation_campaign(
        campaign_id=1,
        session=session,
        now=NOW,
    )

    assert file_bytes
    assert filename == "SEGUNDA_PASADA__CENTRO.xlsx"
    assert len(calls) == 1
    assert calls[0]["campaign_id"] == 1
    assert calls[0]["session"] is session
    assert calls[0]["now"] == NOW


@pytest.mark.parametrize("action", [None, "EXCLUDE"])
def test_export_without_keep_choice_preserves_frequency_block(monkeypatch, action):
    monkeypatch.setattr(
        export_service,
        "get_marketing_reactivation_campaign",
        lambda **kwargs: _serialized_campaign(action),
    )
    monkeypatch.setattr(
        export_service,
        "_validate_and_mark_exported",
        lambda **kwargs: (_ for _ in ()).throw(
            reactivation.MarketingReactivationConflictError("frecuencia")
        ),
    )
    monkeypatch.setattr(
        export_service,
        "_mark_keep_override_exported",
        lambda **kwargs: pytest.fail("KEEP override should not run"),
    )

    with pytest.raises(reactivation.MarketingReactivationConflictError):
        export_service.export_marketing_reactivation_campaign(
            campaign_id=1,
            session=object(),
            now=NOW,
        )


def test_mark_keep_override_sets_exported_state_and_commits():
    campaign = NS(status="DRAFT", exported_at=None, updated_at=None)

    class Query:
        def filter(self, *args):
            return self

        def one(self):
            return campaign

    events = []
    session = NS(
        query=lambda model: Query(),
        commit=lambda: events.append("commit"),
        rollback=lambda: events.append("rollback"),
    )

    export_service._mark_keep_override_exported(
        campaign_id=1,
        session=session,
        now=NOW,
    )

    assert campaign.status == "EXPORTED"
    assert campaign.exported_at == NOW
    assert campaign.updated_at == NOW
    assert events == ["commit"]
