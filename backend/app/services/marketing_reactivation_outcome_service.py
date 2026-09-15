from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.marketing import (
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)
from app.models.marketing_reactivation_outcome import (
    MarketingReactivationCampaignRecipientOutcomeORM,
)
from app.models.warehouse import (
    SociosActivosSnapshotORM,
    SociosActivosSnapshotRowORM,
    SociosVencidosCarteraORM,
)
from app.services.marketing_campaign_delivery_service import (
    branch_send_times_for_campaigns,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    STATUS_ACTIVE_CONFIRMED,
    STATUS_ACTIVE_REVIEW,
    STATUS_AMBIGUOUS,
    STATUS_IDENTIFIER_CONFLICT,
    prepare_socios_vencidos_current_status_context,
    resolve_socios_vencidos_rows_with_context,
    normalize_socios_vencidos_branch_key,
)


TZ = ZoneInfo("America/Tijuana")
UTC = timezone.utc
DEFAULT_ATTRIBUTION_WINDOW_DAYS = 14

OUTCOME_PENDING = "PENDING"
OUTCOME_REACTIVATED = "REACTIVATED"
OUTCOME_REVIEW = "REVIEW"
OUTCOME_WINDOW_CLOSED = "WINDOW_CLOSED"

ATTRIBUTABLE_CAMPAIGN_TYPES = frozenset(
    {
        "WINBACK",
        "VENCIDOS_RECIENTES",
        "COBRANZA_LIGERA",
        "BORRON_CUENTA_NUEVA",
    }
)
_REVIEW_RESOLVER_STATUSES = frozenset(
    {
        STATUS_ACTIVE_REVIEW,
        STATUS_AMBIGUOUS,
        STATUS_IDENTIFIER_CONFLICT,
    }
)


class MarketingReactivationOutcomeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _RecipientEntry:
    campaign: MarketingReactivationCampaignORM
    recipient: MarketingReactivationCampaignRecipientORM
    sent_local: datetime
    window_end_local: datetime


@dataclass(frozen=True, slots=True)
class _ReactivationEvent:
    payment_local: datetime
    snapshot_id: int
    snapshot_row_id: int
    active_id_socio: str
    active_sucursal: str | None


@dataclass(frozen=True, slots=True)
class _EpisodeObservation:
    resolver_status: str | None
    resolver_reason: str | None


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def _utc_now(now: datetime | None = None) -> datetime:
    value = now if now is not None else datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _sent_local(sent_at: datetime) -> datetime:
    value = sent_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(TZ).replace(tzinfo=None)


def _campaign_filters(campaign: MarketingReactivationCampaignORM) -> dict[str, Any]:
    payload = campaign.filters_json if isinstance(campaign.filters_json, dict) else {}
    nested = payload.get("filters")
    if isinstance(nested, dict):
        return nested
    return payload


def _campaign_type(campaign: MarketingReactivationCampaignORM) -> str | None:
    filters = _campaign_filters(campaign)
    raw = filters.get("campaign_type")
    if raw is None and isinstance(campaign.filters_json, dict):
        raw = campaign.filters_json.get("campaign_type")
    value = str(raw or "").strip().upper()
    return value or None


def is_attributable_campaign(campaign: MarketingReactivationCampaignORM) -> bool:
    campaign_type = _campaign_type(campaign)
    if campaign_type in ATTRIBUTABLE_CAMPAIGN_TYPES:
        return True
    if campaign_type != "PERSONALIZADA":
        return False
    universe = str(_campaign_filters(campaign).get("universo") or "").strip().upper()
    return universe == "VENCIDOS"


def _window_days(campaign: MarketingReactivationCampaignORM) -> int:
    raw = getattr(campaign, "attribution_window_days", None)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_ATTRIBUTION_WINDOW_DAYS
    if value < 1 or value > 90:
        raise MarketingReactivationOutcomeError(
            f"Campaña {campaign.id} tiene attribution_window_days inválido: {value}."
        )
    return value


def _build_entries(
    campaigns: Iterable[MarketingReactivationCampaignORM],
    *,
    session: Any,
) -> tuple[list[_RecipientEntry], dict[int, list[_RecipientEntry]]]:
    campaigns = list(campaigns)
    send_times = branch_send_times_for_campaigns(
        campaign_ids=(int(campaign.id) for campaign in campaigns),
        session=session,
    )
    campaigns_with_branch_sends = {
        campaign_id for campaign_id, _ in send_times
    }

    entries: list[_RecipientEntry] = []
    by_episode: dict[int, list[_RecipientEntry]] = defaultdict(list)
    for campaign in campaigns:
        if not is_attributable_campaign(campaign):
            continue
        campaign_id = int(campaign.id)
        legacy_sent_at = (
            campaign.sent_at
            if campaign_id not in campaigns_with_branch_sends
            and campaign.status == "SENT"
            and campaign.sent_at is not None
            else None
        )
        for recipient in campaign.recipients:
            sent_at = send_times.get(
                (campaign_id, str(recipient.sucursal))
            ) or legacy_sent_at
            if sent_at is None:
                continue
            sent_local = _sent_local(sent_at)
            entry = _RecipientEntry(
                campaign=campaign,
                recipient=recipient,
                sent_local=sent_local,
                window_end_local=(
                    sent_local + timedelta(days=_window_days(campaign))
                ),
            )
            entries.append(entry)
            if recipient.socios_vencidos_cartera_id is not None:
                by_episode[int(recipient.socios_vencidos_cartera_id)].append(entry)
    return entries, by_episode


def _eligible_entries_for_payment(
    entries: Iterable[_RecipientEntry],
    payment_local: datetime,
) -> list[_RecipientEntry]:
    return [
        entry
        for entry in entries
        if entry.sent_local < payment_local <= entry.window_end_local
    ]


def _last_touch_winner(
    entries: Iterable[_RecipientEntry],
    payment_local: datetime,
) -> _RecipientEntry | None:
    eligible = _eligible_entries_for_payment(entries, payment_local)
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda entry: (
            entry.sent_local,
            int(entry.campaign.id),
            int(entry.recipient.id),
        ),
    )


def _read_campaigns(*, session: Any, campaign_ids: Iterable[int] | None = None):
    query = (
        session.query(MarketingReactivationCampaignORM)
        .options(joinedload(MarketingReactivationCampaignORM.recipients))
        .filter(
            MarketingReactivationCampaignORM.status.in_(("EXPORTED", "SENT")),
        )
    )
    if campaign_ids is not None:
        normalized = tuple(sorted({int(value) for value in campaign_ids}))
        if not normalized:
            return []
        query = query.filter(MarketingReactivationCampaignORM.id.in_(normalized))
    return query.order_by(
        MarketingReactivationCampaignORM.created_at.asc(),
        MarketingReactivationCampaignORM.id.asc(),
    ).all()


def _read_or_create_outcomes(
    *,
    entries: list[_RecipientEntry],
    session: Any,
    now_utc: datetime,
) -> dict[int, MarketingReactivationCampaignRecipientOutcomeORM]:
    recipient_ids = [int(entry.recipient.id) for entry in entries]
    if not recipient_ids:
        return {}
    rows = (
        session.query(MarketingReactivationCampaignRecipientOutcomeORM)
        .filter(
            MarketingReactivationCampaignRecipientOutcomeORM.campaign_recipient_id.in_(
                recipient_ids
            )
        )
        .all()
    )
    by_recipient = {int(row.campaign_recipient_id): row for row in rows}
    for recipient_id in recipient_ids:
        if recipient_id in by_recipient:
            continue
        row = MarketingReactivationCampaignRecipientOutcomeORM(
            campaign_recipient_id=recipient_id,
            status=OUTCOME_PENDING,
            last_checked_at=now_utc,
            created_at=now_utc,
            updated_at=now_utc,
        )
        session.add(row)
        by_recipient[recipient_id] = row
    session.flush()
    return by_recipient


def _latest_canonical_snapshot(*, session: Any):
    return (
        session.query(SociosActivosSnapshotORM)
        .filter(SociosActivosSnapshotORM.is_canonical.is_(True))
        .order_by(
            SociosActivosSnapshotORM.cutoff_date.desc(),
            SociosActivosSnapshotORM.id.desc(),
        )
        .first()
    )


def _needs_recheck(
    outcome: MarketingReactivationCampaignRecipientOutcomeORM,
    *,
    latest_snapshot: SociosActivosSnapshotORM | None,
) -> bool:
    if outcome.status == OUTCOME_REACTIVATED:
        return False
    if outcome.status != OUTCOME_WINDOW_CLOSED:
        return True
    if latest_snapshot is None or outcome.last_checked_at is None:
        return False
    captured_at = latest_snapshot.captured_at
    if captured_at is None:
        return False
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)
    last_checked = outcome.last_checked_at
    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=UTC)
    return captured_at.astimezone(UTC) > last_checked.astimezone(UTC)


def _read_vencidos_by_id(*, ids: Iterable[int], session: Any) -> dict[int, Any]:
    normalized = tuple(sorted({int(value) for value in ids}))
    if not normalized:
        return {}
    rows = (
        session.query(SociosVencidosCarteraORM)
        .filter(SociosVencidosCarteraORM.id.in_(normalized))
        .all()
    )
    return {int(row.id): row for row in rows}


def _candidate_snapshots(
    *,
    minimum_sent_date: date,
    session: Any,
) -> list[SociosActivosSnapshotORM]:
    return (
        session.query(SociosActivosSnapshotORM)
        .filter(
            SociosActivosSnapshotORM.is_canonical.is_(True),
            SociosActivosSnapshotORM.cutoff_date >= minimum_sent_date,
        )
        .order_by(
            SociosActivosSnapshotORM.cutoff_date.asc(),
            SociosActivosSnapshotORM.id.asc(),
        )
        .all()
    )


def _active_rows_for_ids(
    *,
    snapshot_id: int,
    active_ids: Iterable[str],
    session: Any,
) -> dict[str, list[SociosActivosSnapshotRowORM]]:
    normalized = tuple(sorted({str(value) for value in active_ids if value is not None}))
    if not normalized:
        return {}
    rows = (
        session.query(SociosActivosSnapshotRowORM)
        .filter(
            SociosActivosSnapshotRowORM.snapshot_id == snapshot_id,
            SociosActivosSnapshotRowORM.id_socio.in_(normalized),
        )
        .all()
    )
    grouped: dict[str, list[SociosActivosSnapshotRowORM]] = defaultdict(list)
    for row in rows:
        grouped[str(row.id_socio)].append(row)
    return grouped


def _observe_episode_events(
    *,
    by_episode: dict[int, list[_RecipientEntry]],
    vencidos: dict[int, Any],
    snapshots: list[SociosActivosSnapshotORM],
    session: Any,
) -> tuple[
    dict[int, _ReactivationEvent],
    dict[int, _EpisodeObservation],
]:
    events: dict[int, _ReactivationEvent] = {}
    observations: dict[int, _EpisodeObservation] = {}

    for snapshot in snapshots:
        eligible_episode_ids = [
            episode_id
            for episode_id, entries in by_episode.items()
            if episode_id in vencidos
            and episode_id not in events
            and snapshot.cutoff_date >= min(entry.sent_local.date() for entry in entries)
        ]
        if not eligible_episode_ids:
            continue

        rows = [vencidos[episode_id] for episode_id in eligible_episode_ids]
        context = prepare_socios_vencidos_current_status_context(
            minimum_cutoff_date=snapshot.cutoff_date,
            activos_snapshot_id=int(snapshot.id),
            session=session,
        )
        resolved = resolve_socios_vencidos_rows_with_context(
            vencidos_rows=rows,
            context=context,
            session=session,
        )
        confirmed_ids = {
            str(item.active_id_socio)
            for item in resolved
            if item.status == STATUS_ACTIVE_CONFIRMED
            and item.active_id_socio is not None
        }
        active_rows = _active_rows_for_ids(
            snapshot_id=int(snapshot.id),
            active_ids=confirmed_ids,
            session=session,
        )

        for item in resolved:
            episode_id = int(item.vencido_row_id)
            observations[episode_id] = _EpisodeObservation(
                resolver_status=str(item.status),
                resolver_reason=str(item.status),
            )
            if item.status != STATUS_ACTIVE_CONFIRMED or item.active_id_socio is None:
                continue
            matches = active_rows.get(str(item.active_id_socio), [])
            if len(matches) != 1:
                observations[episode_id] = _EpisodeObservation(
                    resolver_status=STATUS_AMBIGUOUS,
                    resolver_reason="ACTIVE_ROW_IDENTITY_AMBIGUOUS",
                )
                continue
            active_row = matches[0]
            payment_local = active_row.fecha_ultimo_pago_local
            if payment_local is None:
                observations[episode_id] = _EpisodeObservation(
                    resolver_status=STATUS_ACTIVE_REVIEW,
                    resolver_reason="ACTIVE_WITHOUT_LAST_PAYMENT",
                )
                continue
            if payment_local.tzinfo is not None:
                payment_local = payment_local.astimezone(TZ).replace(tzinfo=None)
            if not _eligible_entries_for_payment(
                by_episode[episode_id],
                payment_local,
            ):
                continue
            event = _ReactivationEvent(
                payment_local=payment_local,
                snapshot_id=int(snapshot.id),
                snapshot_row_id=int(active_row.id),
                active_id_socio=str(active_row.id_socio),
                active_sucursal=(
                    str(active_row.sucursal_raw)
                    if active_row.sucursal_raw is not None
                    else None
                ),
            )
            previous = events.get(episode_id)
            if previous is None or event.payment_local < previous.payment_local:
                events[episode_id] = event

    return events, observations


def _clear_evidence(outcome: MarketingReactivationCampaignRecipientOutcomeORM) -> None:
    outcome.reactivated_at_local = None
    outcome.active_snapshot_id = None
    outcome.active_snapshot_row_id = None
    outcome.active_id_socio = None
    outcome.active_sucursal = None


def _transition(
    outcome: MarketingReactivationCampaignRecipientOutcomeORM,
    *,
    status: str,
    now_utc: datetime,
    review_reason: str | None = None,
    event: _ReactivationEvent | None = None,
) -> None:
    if outcome.status == OUTCOME_REACTIVATED:
        outcome.last_checked_at = now_utc
        outcome.updated_at = now_utc
        return
    previous_status = outcome.status
    outcome.status = status
    outcome.review_reason = review_reason if status == OUTCOME_REVIEW else None
    outcome.last_checked_at = now_utc
    outcome.updated_at = now_utc
    if status == OUTCOME_REACTIVATED:
        if event is None:
            raise MarketingReactivationOutcomeError(
                "REACTIVATED requiere evidencia de reactivación."
            )
        outcome.reactivated_at_local = event.payment_local
        outcome.active_snapshot_id = event.snapshot_id
        outcome.active_snapshot_row_id = event.snapshot_row_id
        outcome.active_id_socio = event.active_id_socio
        outcome.active_sucursal = event.active_sucursal
    else:
        _clear_evidence(outcome)
    if (
        outcome.first_detected_at is None
        and status != OUTCOME_PENDING
        and status != previous_status
    ):
        outcome.first_detected_at = now_utc


def run_marketing_reactivation_outcomes(
    *,
    campaign_ids: Iterable[int] | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = _session_or_default(session)
    now_utc = _utc_now(now)
    campaigns = _read_campaigns(
        session=active_session,
        campaign_ids=campaign_ids,
    )
    entries, all_by_episode = _build_entries(
        campaigns,
        session=active_session,
    )
    if not entries:
        return {
            "campaigns": 0,
            "recipients": 0,
            "checked": 0,
            "reactivated": 0,
            "pending": 0,
            "review": 0,
            "window_closed": 0,
        }

    outcomes = _read_or_create_outcomes(
        entries=entries,
        session=active_session,
        now_utc=now_utc,
    )
    latest_snapshot = _latest_canonical_snapshot(session=active_session)

    entries_to_check = [
        entry
        for entry in entries
        if _needs_recheck(
            outcomes[int(entry.recipient.id)],
            latest_snapshot=latest_snapshot,
        )
    ]
    episode_ids_to_check = {
        int(entry.recipient.socios_vencidos_cartera_id)
        for entry in entries_to_check
        if entry.recipient.socios_vencidos_cartera_id is not None
    }
    by_episode = {
        episode_id: all_by_episode[episode_id]
        for episode_id in episode_ids_to_check
        if episode_id in all_by_episode
    }
    vencidos = _read_vencidos_by_id(
        ids=episode_ids_to_check,
        session=active_session,
    )

    events: dict[int, _ReactivationEvent] = {}
    observations: dict[int, _EpisodeObservation] = {}
    if by_episode:
        minimum_sent_date = min(
            entry.sent_local.date()
            for episode_entries in by_episode.values()
            for entry in episode_entries
        )
        snapshots = _candidate_snapshots(
            minimum_sent_date=minimum_sent_date,
            session=active_session,
        )
        events, observations = _observe_episode_events(
            by_episode=by_episode,
            vencidos=vencidos,
            snapshots=snapshots,
            session=active_session,
        )

    latest_cutoff = latest_snapshot.cutoff_date if latest_snapshot is not None else None

    for entry in entries_to_check:
        recipient_id = int(entry.recipient.id)
        outcome = outcomes[recipient_id]
        raw_episode_id = entry.recipient.socios_vencidos_cartera_id
        if raw_episode_id is None:
            _transition(
                outcome,
                status=OUTCOME_REVIEW,
                now_utc=now_utc,
                review_reason="MISSING_VENCIDO_IDENTITY",
            )
            continue
        episode_id = int(raw_episode_id)
        if episode_id not in vencidos:
            _transition(
                outcome,
                status=OUTCOME_REVIEW,
                now_utc=now_utc,
                review_reason="VENCIDO_EPISODE_NOT_FOUND",
            )
            continue

        event = events.get(episode_id)
        if event is not None:
            winner = _last_touch_winner(
                all_by_episode.get(episode_id, []),
                event.payment_local,
            )
            if winner is not None and int(winner.recipient.id) == recipient_id:
                _transition(
                    outcome,
                    status=OUTCOME_REACTIVATED,
                    now_utc=now_utc,
                    event=event,
                )
                continue

        observation = observations.get(episode_id)
        if observation is not None and observation.resolver_status in _REVIEW_RESOLVER_STATUSES:
            _transition(
                outcome,
                status=OUTCOME_REVIEW,
                now_utc=now_utc,
                review_reason=observation.resolver_reason,
            )
            continue

        if latest_cutoff is not None and latest_cutoff >= entry.window_end_local.date():
            _transition(
                outcome,
                status=OUTCOME_WINDOW_CLOSED,
                now_utc=now_utc,
            )
        else:
            _transition(
                outcome,
                status=OUTCOME_PENDING,
                now_utc=now_utc,
            )

    try:
        active_session.commit()
    except Exception:
        active_session.rollback()
        raise

    counts = defaultdict(int)
    for outcome in outcomes.values():
        counts[str(outcome.status)] += 1
    return {
        "campaigns": len(
            [campaign for campaign in campaigns if is_attributable_campaign(campaign)]
        ),
        "recipients": len(entries),
        "checked": len(entries_to_check),
        "reactivated": counts[OUTCOME_REACTIVATED],
        "pending": counts[OUTCOME_PENDING],
        "review": counts[OUTCOME_REVIEW],
        "window_closed": counts[OUTCOME_WINDOW_CLOSED],
        "latest_activos_cutoff_date": (
            latest_cutoff.isoformat() if latest_cutoff is not None else None
        ),
    }


def _normalize_optional_date(value: date | str | None, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} debe ser YYYY-MM-DD.") from exc


def _entry_in_branch_scope(
    entry: _RecipientEntry,
    *,
    allowed_sucursal_keys: tuple[str, ...] | None,
    selected_sucursal_keys: set[str] | None,
) -> bool:
    key = normalize_socios_vencidos_branch_key(entry.recipient.sucursal)
    if key is None:
        return False
    if allowed_sucursal_keys is not None and key not in set(allowed_sucursal_keys):
        return False
    if selected_sucursal_keys is not None and key not in selected_sucursal_keys:
        return False
    return True


def _serialize_counts(
    *,
    entries: list[_RecipientEntry],
    outcomes: dict[int, MarketingReactivationCampaignRecipientOutcomeORM],
) -> dict[str, Any]:
    sent = len(entries)
    counts = defaultdict(int)
    for entry in entries:
        outcome = outcomes.get(int(entry.recipient.id))
        status = str(outcome.status) if outcome is not None else OUTCOME_PENDING
        counts[status] += 1
    reactivated = counts[OUTCOME_REACTIVATED]
    return {
        "sent": sent,
        "reactivated": reactivated,
        "pending": counts[OUTCOME_PENDING],
        "review": counts[OUTCOME_REVIEW],
        "window_closed": counts[OUTCOME_WINDOW_CLOSED],
        "in_tracking": counts[OUTCOME_PENDING] + counts[OUTCOME_REVIEW],
        "conversion_rate": round((reactivated / sent * 100), 2) if sent else 0.0,
    }


def build_marketing_reactivation_outcome_summary(
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    selected_sucursal_keys: Iterable[str] | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    normalized_from = _normalize_optional_date(date_from, "date_from")
    normalized_to = _normalize_optional_date(date_to, "date_to")
    if normalized_from and normalized_to and normalized_from > normalized_to:
        raise ValueError("date_from no puede ser posterior a date_to.")

    active_session = _session_or_default(session)
    campaigns = _read_campaigns(session=active_session)
    entries, _ = _build_entries(campaigns, session=active_session)
    selected = (
        {
            key
            for key in (
                normalize_socios_vencidos_branch_key(value)
                for value in selected_sucursal_keys
            )
            if key is not None
        }
        if selected_sucursal_keys is not None
        else None
    )

    filtered_entries = []
    for entry in entries:
        sent_date = entry.sent_local.date()
        if normalized_from is not None and sent_date < normalized_from:
            continue
        if normalized_to is not None and sent_date > normalized_to:
            continue
        if not _entry_in_branch_scope(
            entry,
            allowed_sucursal_keys=allowed_sucursal_keys,
            selected_sucursal_keys=selected,
        ):
            continue
        filtered_entries.append(entry)

    recipient_ids = [int(entry.recipient.id) for entry in filtered_entries]
    outcome_rows = (
        active_session.query(MarketingReactivationCampaignRecipientOutcomeORM)
        .filter(
            MarketingReactivationCampaignRecipientOutcomeORM.campaign_recipient_id.in_(
                recipient_ids
            )
        )
        .all()
        if recipient_ids
        else []
    )
    outcomes = {int(row.campaign_recipient_id): row for row in outcome_rows}
    by_campaign: dict[int, list[_RecipientEntry]] = defaultdict(list)
    for entry in filtered_entries:
        by_campaign[int(entry.campaign.id)].append(entry)

    campaign_rows = []
    for campaign in campaigns:
        campaign_entries = by_campaign.get(int(campaign.id), [])
        if not campaign_entries:
            continue
        row = _serialize_counts(entries=campaign_entries, outcomes=outcomes)
        first_sent_local = min(entry.sent_local for entry in campaign_entries)
        row.update(
            {
                "campaign_id": int(campaign.id),
                "name": str(campaign.name),
                "campaign_type": _campaign_type(campaign),
                "sent_at": (
                    campaign.sent_at.isoformat()
                    if campaign.sent_at is not None
                    else None
                ),
                "sent_date_local": first_sent_local.date().isoformat(),
                "attribution_window_days": _window_days(campaign),
            }
        )
        campaign_rows.append(row)

    return {
        "date_from": normalized_from.isoformat() if normalized_from else None,
        "date_to": normalized_to.isoformat() if normalized_to else None,
        "summary": _serialize_counts(entries=filtered_entries, outcomes=outcomes),
        "campaigns": campaign_rows,
    }


def _days_to_reactivation(sent_local: datetime, reactivated_local: datetime | None):
    if reactivated_local is None:
        return None
    return max((reactivated_local.date() - sent_local.date()).days, 0)


def build_marketing_reactivation_campaign_outcome_detail(
    *,
    campaign_id: int,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    active_session = _session_or_default(session)
    campaign = (
        active_session.query(MarketingReactivationCampaignORM)
        .options(joinedload(MarketingReactivationCampaignORM.recipients))
        .filter(MarketingReactivationCampaignORM.id == int(campaign_id))
        .one_or_none()
    )
    if campaign is None:
        raise LookupError("Campaña no encontrada.")

    all_entries, _ = _build_entries([campaign], session=active_session)
    entries = [
        entry
        for entry in all_entries
        if _entry_in_branch_scope(
            entry,
            allowed_sucursal_keys=allowed_sucursal_keys,
            selected_sucursal_keys=None,
        )
    ]
    if not is_attributable_campaign(campaign) or not entries:
        return {
            "campaign_id": int(campaign.id),
            "name": str(campaign.name),
            "applicable": False,
            "summary": {
                "sent": 0,
                "reactivated": 0,
                "pending": 0,
                "review": 0,
                "window_closed": 0,
                "in_tracking": 0,
                "conversion_rate": 0.0,
            },
            "rows": [],
        }

    recipient_ids = [int(entry.recipient.id) for entry in entries]
    outcome_rows = (
        active_session.query(MarketingReactivationCampaignRecipientOutcomeORM)
        .filter(
            MarketingReactivationCampaignRecipientOutcomeORM.campaign_recipient_id.in_(
                recipient_ids
            )
        )
        .all()
        if recipient_ids
        else []
    )
    outcomes = {int(row.campaign_recipient_id): row for row in outcome_rows}
    rows = []
    for entry in entries:
        outcome = outcomes.get(int(entry.recipient.id))
        status = str(outcome.status) if outcome is not None else OUTCOME_PENDING
        reactivated_at = outcome.reactivated_at_local if outcome is not None else None
        sent_at_utc = entry.sent_local.replace(tzinfo=TZ).astimezone(UTC)
        rows.append(
            {
                "recipient_id": int(entry.recipient.id),
                "member_name": entry.recipient.member_name,
                "campaign_branch": entry.recipient.sucursal,
                "fecha_vencimiento": (
                    entry.recipient.fecha_vencimiento_date.isoformat()
                    if entry.recipient.fecha_vencimiento_date is not None
                    else None
                ),
                "status": status,
                "review_reason": outcome.review_reason if outcome is not None else None,
                "sent_at": sent_at_utc.isoformat(),
                "sent_at_local": entry.sent_local.isoformat(),
                "reactivated_at_local": (
                    reactivated_at.isoformat() if reactivated_at is not None else None
                ),
                "days_to_reactivation": _days_to_reactivation(
                    entry.sent_local,
                    reactivated_at,
                ),
                "active_id_socio": (
                    outcome.active_id_socio if outcome is not None else None
                ),
                "active_sucursal": (
                    outcome.active_sucursal if outcome is not None else None
                ),
            }
        )

    return {
        "campaign_id": int(campaign.id),
        "name": str(campaign.name),
        "applicable": True,
        "attribution_window_days": _window_days(campaign),
        "summary": _serialize_counts(entries=entries, outcomes=outcomes),
        "rows": rows,
    }
