from __future__ import annotations

from datetime import datetime, timezone

from app.models.marketing import (
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)
from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_campaign_explorer_creation_service as creation
from app.services import marketing_reactivation_service as reactivation


NOW = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)


def _row(
    row_id: int,
    *,
    phone: str | None,
    branch: str = "MISION ENS",
    eligibility: str = "ELIGIBLE",
    reason: str | None = None,
):
    return {
        "vencido_row_id": row_id,
        "pin": f"PIN-{row_id}",
        "nombre": f"Socio {row_id}",
        "phone_mx10": phone,
        "sucursal": branch,
        "fecha_vencimiento": "2026-08-20",
        "tarifa": "MENSUALIDAD",
        "tarifa_categoria": "Mensualidad",
        "tarifa_group": "REACTIVATE",
        "adeudo": "500.00",
        "operational_status": "AVAILABLE",
        "campaign_eligibility": eligibility,
        "eligibility_reason": reason,
        "reason": "NO_OUTBOUND_EVIDENCE",
        "iventas_contact_id": None,
        "latest_outbound_at_utc": None,
    }


def _plan(decision_rows, eligible_rows):
    return {
        "sources": {
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
            "iventas_sync_run_id": 87,
        },
        "filters": {
            "campaign_type": "PERSONALIZADA",
            "universo": "VENCIDOS",
            "modo_vencidos": "FECHAS",
            "fecha_hasta": "2026-08-31",
        },
        "scope": {"is_global": True, "sucursal_keys": None},
        "summary": {
            "total_candidates": len(decision_rows),
            "eligible": len(eligible_rows),
            "excluded_active": 0,
            "excluded_invalid_phone": 0,
            "review_identity": 0,
            "duplicate_phone": 0,
            "excluded_tariff": 0,
            "excluded_tariff_general": 0,
            "domiciliated_flow": 0,
            "borron_cuenta_nueva": 0,
            "review_tariff": 0,
            "excluded_recent_campaign": 0,
            "review": 0,
        },
        "decision_rows": decision_rows,
        "eligible_rows": eligible_rows,
    }


def _install_plan(monkeypatch, plan):
    monkeypatch.setattr(
        reactivation,
        "_prepare_campaign_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(
        audience,
        "exported_counts",
        lambda *args, **kwargs: {},
    )


class WriteSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.next_campaign_id = 50

    def add(self, row):
        if isinstance(row, MarketingReactivationCampaignORM) and row.id is None:
            row.id = self.next_campaign_id
            self.next_campaign_id += 1
        self.added.append(row)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_selection_intersects_filtered_bucket_with_campaign_eligible_phones(monkeypatch):
    eligible = _row(1, phone="6861000001")
    duplicate = _row(2, phone="6861000001")
    excluded = _row(
        3,
        phone="6861000002",
        eligibility="EXCLUDED_TARIFF",
        reason="TARIFF_EXCLUDED",
    )
    invalid = _row(4, phone=None, eligibility="EXCLUDED_INVALID_PHONE")
    plan = _plan([eligible, duplicate, excluded, invalid], [eligible])
    _install_plan(monkeypatch, plan)

    result = creation.build_explorer_campaign_selection(
        filters=plan["filters"],
        bucket="TOTAL_CANDIDATES",
        explorer_filters={},
        session=object(),
        now=NOW,
    )

    assert result["filtered_total"] == 4
    assert result["valid_phone_rows"] == 3
    assert result["unique_valid_contacts"] == 2
    assert result["duplicate_phone_rows"] == 1
    assert result["excluded_by_campaign_rules"] == 1
    assert result["recipient_count"] == 1
    assert result["can_create"] is True


def test_selection_requires_weekly_choice_only_for_selected_eligible_contacts(monkeypatch):
    eligible = _row(1, phone="6861000001")
    plan = _plan([eligible], [eligible])
    _install_plan(monkeypatch, plan)
    monkeypatch.setattr(
        audience,
        "exported_counts",
        lambda *args, **kwargs: {"6861000001": 2},
    )

    result = creation.build_explorer_campaign_selection(
        filters=plan["filters"],
        bucket="ELIGIBLE",
        explorer_filters={},
        session=object(),
        now=NOW,
    )

    assert result["recipient_count"] == 1
    assert result["weekly_limit_contacts"] == 1
    assert result["weekly_frequency_decision_required"] is True
    assert result["can_create"] is False


def test_create_freezes_only_filtered_final_recipients_and_selection_metadata(monkeypatch):
    first = _row(1, phone="6861000001", branch="MISION ENS")
    second = _row(2, phone="6861000002", branch="SEND MXL")
    plan = _plan([first, second], [first, second])
    _install_plan(monkeypatch, plan)
    session = WriteSession()

    result = creation.create_campaign_from_explorer(
        name="Misión adeudo 500",
        filters=plan["filters"],
        bucket="ELIGIBLE",
        explorer_filters={"sucursal": "MISION ENS"},
        created_by_user_id=7,
        session=session,
        now=NOW,
    )

    assert result["campaign"]["id"] == 50
    assert result["campaign"]["status"] == "DRAFT"
    assert result["campaign"]["recipient_count"] == 1
    assert result["selection"]["filtered_total"] == 1
    assert result["selection"]["recipient_count"] == 1
    assert session.commits == 1
    assert session.rollbacks == 0

    campaign = session.added[0]
    recipients = [
        row
        for row in session.added
        if isinstance(row, MarketingReactivationCampaignRecipientORM)
    ]
    assert len(recipients) == 1
    assert recipients[0].phone_mx10 == "6861000001"
    assert campaign.filters_json["filters"] == plan["filters"]
    assert campaign.filters_json["audience_explorer"]["bucket"] == "ELIGIBLE"
    assert campaign.filters_json["audience_explorer"]["explorer_filters"] == {
        "sucursal": "MISION ENS"
    }
    assert campaign.filters_json["audience_explorer"]["selection"]["recipient_count"] == 1
