from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_delivery_service as service


UTC = timezone.utc


def _campaign(status="EXPORTED"):
    return NS(
        id=10,
        status=status,
        sent_at=None,
        name="Campaña",
    )


def test_delivery_status_distinguishes_partial_send():
    campaign = _campaign()

    assert service._delivery_status(
        campaign=campaign,
        total_branches=24,
        sent_branches=0,
    ) == "EXPORTED"
    assert service._delivery_status(
        campaign=campaign,
        total_branches=24,
        sent_branches=22,
    ) == "PARTIALLY_SENT"
    assert service._delivery_status(
        campaign=campaign,
        total_branches=24,
        sent_branches=24,
    ) == "SENT"


def test_delivery_summary_counts_only_registered_branches_as_sent():
    campaign = _campaign()
    sent_at = datetime(2026, 9, 14, 17, 15, tzinfo=UTC)
    result = service._serialize_delivery(
        campaign=campaign,
        branch_counts=Counter({
            "TEC MXL": 80,
            "INDEPENDENCIA": 11,
            "VILLAS DEL REY": 55,
        }),
        sends={
            "VILLAS DEL REY": NS(
                sent_at=sent_at,
                sent_by_user_id=7,
            ),
        },
    )

    assert result["status"] == "PARTIALLY_SENT"
    assert result["total_branches"] == 3
    assert result["sent_branches"] == 1
    assert result["pending_branches"] == 2
    assert result["total_contacts"] == 146
    assert result["sent_contacts"] == 55
    assert result["pending_contacts"] == 91
    assert [row["sucursal"] for row in result["branches"]] == [
        "INDEPENDENCIA",
        "TEC MXL",
        "VILLAS DEL REY",
    ]


def test_sent_at_local_is_interpreted_as_tijuana_time():
    parsed = service._parse_sent_at_local(
        "2026-09-14T10:15:00",
        now=datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
    )

    assert parsed == datetime(2026, 9, 14, 17, 15, tzinfo=UTC)


def test_future_send_is_rejected():
    with pytest.raises(service.MarketingCampaignDeliveryValidationError):
        service._parse_sent_at_local(
            "2026-09-15T10:00:00",
            now=datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
        )


def test_branch_scope_requires_all_campaign_branches_in_user_scope():
    counts = Counter({"TEC MXL": 80, "INDEPENDENCIA": 11})

    assert service._branch_counts_are_allowed(counts, None) is True
    assert service._branch_counts_are_allowed(
        counts,
        ("TEC MXL", "INDEPENDENCIA"),
    ) is True
    assert service._branch_counts_are_allowed(
        counts,
        ("TEC MXL",),
    ) is False


def test_migration_creates_auditable_branch_send_table_and_backfills_legacy_sent():
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "d6b7e3f1a9c4_add_marketing_campaign_branch_sends.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "d6b7e3f1a9c4"' in migration
    assert 'down_revision = "c4e7a9b2d6f1"' in migration
    assert '"marketing_reactivation_campaign_branch_sends"' in migration
    assert '"sent_by_user_id"' in migration
    assert "WHERE c.status = 'SENT'" in migration
    assert "GROUP BY c.id, r.sucursal" in migration
