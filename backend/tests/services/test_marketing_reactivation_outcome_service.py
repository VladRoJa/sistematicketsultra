from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

from app.services import marketing_reactivation_outcome_service as service


UTC = timezone.utc


def _recipient(recipient_id=1, episode_id=101):
    return NS(
        id=recipient_id,
        socios_vencidos_cartera_id=episode_id,
        member_name="Socio",
        sucursal="TEC MXL",
        fecha_vencimiento_date=None,
    )


def _campaign(
    campaign_id,
    sent_at,
    *,
    campaign_type="WINBACK",
    status="SENT",
    universe=None,
    recipients=None,
    window_days=14,
):
    filters = {"campaign_type": campaign_type}
    if universe is not None:
        filters["universo"] = universe
    return NS(
        id=campaign_id,
        name=f"Campaña {campaign_id}",
        status=status,
        sent_at=sent_at,
        filters_json={"filters": filters},
        attribution_window_days=window_days,
        recipients=list(recipients or [_recipient()]),
    )


def _outcome(status="PENDING"):
    return NS(
        status=status,
        last_checked_at=None,
        updated_at=None,
        review_reason=None,
        reactivated_at_local=None,
        active_snapshot_id=None,
        active_snapshot_row_id=None,
        active_id_socio=None,
        active_sucursal=None,
        first_detected_at=None,
    )


def test_sent_at_is_compared_in_tijuana_local_time():
    sent_utc = datetime(2026, 9, 13, 18, 0, tzinfo=UTC)

    assert service._sent_local(sent_utc).isoformat() == "2026-09-13T11:00:00"


def test_only_sent_expired_campaigns_are_attributable():
    sent = datetime(2026, 9, 13, 18, tzinfo=UTC)
    campaigns = [
        _campaign(1, sent, campaign_type="WINBACK"),
        _campaign(2, sent, campaign_type="VENCIDOS_RECIENTES"),
        _campaign(3, sent, campaign_type="COBRANZA_LIGERA"),
        _campaign(4, sent, campaign_type="BORRON_CUENTA_NUEVA"),
        _campaign(5, sent, campaign_type="PERSONALIZADA", universe="VENCIDOS"),
        _campaign(6, sent, campaign_type="PERSONALIZADA", universe="ACTIVOS"),
        _campaign(7, sent, campaign_type="PROXIMOS_VENCER"),
        _campaign(8, sent, campaign_type="WINBACK", status="EXPORTED"),
    ]

    entries, _ = service._build_entries(campaigns)

    assert [entry.campaign.id for entry in entries] == [1, 2, 3, 4, 5]


def test_attribution_window_is_strict_after_send_and_inclusive_at_day_14():
    sent = datetime(2026, 9, 1, 17, tzinfo=UTC)
    campaign = _campaign(1, sent)
    entry = service._build_entries([campaign])[0][0]

    assert service._eligible_entries_for_payment(
        [entry], entry.sent_local
    ) == []
    assert service._eligible_entries_for_payment(
        [entry], entry.sent_local.replace(minute=entry.sent_local.minute + 1)
    ) == [entry]
    assert service._eligible_entries_for_payment(
        [entry], entry.window_end_local
    ) == [entry]
    assert service._eligible_entries_for_payment(
        [entry], entry.window_end_local.replace(minute=entry.window_end_local.minute + 1)
    ) == []


def test_last_touch_credits_only_latest_eligible_campaign():
    recipient_a = _recipient(recipient_id=1, episode_id=77)
    recipient_b = _recipient(recipient_id=2, episode_id=77)
    first = _campaign(
        10,
        datetime(2026, 9, 1, 16, tzinfo=UTC),
        recipients=[recipient_a],
    )
    second = _campaign(
        20,
        datetime(2026, 9, 8, 16, tzinfo=UTC),
        recipients=[recipient_b],
    )
    entries, by_episode = service._build_entries([first, second])
    assert len(entries) == 2

    payment = datetime(2026, 9, 10, 12, 0)
    winner = service._last_touch_winner(by_episode[77], payment)

    assert winner is not None
    assert winner.campaign.id == 20
    assert winner.recipient.id == 2


def test_reactivated_is_terminal_and_keeps_original_evidence():
    now = datetime(2026, 9, 15, 18, tzinfo=UTC)
    outcome = _outcome("PENDING")
    event = service._ReactivationEvent(
        payment_local=datetime(2026, 9, 14, 10, 30),
        snapshot_id=300,
        snapshot_row_id=900,
        active_id_socio="382442",
        active_sucursal="TEC MXL",
    )

    service._transition(
        outcome,
        status=service.OUTCOME_REACTIVATED,
        now_utc=now,
        event=event,
    )
    service._transition(
        outcome,
        status=service.OUTCOME_WINDOW_CLOSED,
        now_utc=datetime(2026, 9, 20, 18, tzinfo=UTC),
    )

    assert outcome.status == "REACTIVATED"
    assert outcome.reactivated_at_local == event.payment_local
    assert outcome.active_snapshot_id == 300
    assert outcome.active_snapshot_row_id == 900
    assert outcome.active_id_socio == "382442"
    assert outcome.active_sucursal == "TEC MXL"


def test_review_can_be_promoted_to_reactivated():
    outcome = _outcome("REVIEW")
    outcome.review_reason = "AMBIGUOUS"
    event = service._ReactivationEvent(
        payment_local=datetime(2026, 9, 14, 10, 30),
        snapshot_id=301,
        snapshot_row_id=901,
        active_id_socio="500001",
        active_sucursal="VILLALTA",
    )

    service._transition(
        outcome,
        status=service.OUTCOME_REACTIVATED,
        now_utc=datetime(2026, 9, 15, 18, tzinfo=UTC),
        event=event,
    )

    assert outcome.status == "REACTIVATED"
    assert outcome.review_reason is None


def test_missing_outcome_counts_as_pending_and_conversion_uses_sent_denominator():
    sent = datetime(2026, 9, 1, 17, tzinfo=UTC)
    campaign = _campaign(
        1,
        sent,
        recipients=[
            _recipient(1, 101),
            _recipient(2, 102),
            _recipient(3, 103),
            _recipient(4, 104),
        ],
    )
    entries, _ = service._build_entries([campaign])
    outcomes = {
        1: NS(status="REACTIVATED"),
        2: NS(status="WINDOW_CLOSED"),
        3: NS(status="REVIEW"),
    }

    summary = service._serialize_counts(entries=entries, outcomes=outcomes)

    assert summary == {
        "sent": 4,
        "reactivated": 1,
        "pending": 1,
        "review": 1,
        "window_closed": 1,
        "in_tracking": 2,
        "conversion_rate": 25.0,
    }


def test_days_to_reactivation_is_derived_not_persisted():
    assert service._days_to_reactivation(
        datetime(2026, 9, 10, 16, 0),
        datetime(2026, 9, 13, 9, 0),
    ) == 3


def test_outcome_migration_follows_previous_single_head_and_contains_contract_fields():
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "f4a1c8d2e6b7_add_marketing_reactivation_outcomes.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "f4a1c8d2e6b7"' in migration
    assert 'down_revision = "b7e4d8c2a1f9"' in migration
    assert '"attribution_window_days"' in migration
    assert '"marketing_reactivation_campaign_recipient_outcomes"' in migration
    assert '"reactivated_at_local"' in migration
    assert '"active_snapshot_row_id"' in migration
    assert '"WINDOW_CLOSED"' in migration
