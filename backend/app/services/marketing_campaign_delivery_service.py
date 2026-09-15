from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.marketing import (
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)
from app.models.marketing_campaign_delivery import (
    MarketingReactivationCampaignBranchSendORM,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


TZ = ZoneInfo("America/Tijuana")
UTC = timezone.utc


class MarketingCampaignDeliveryValidationError(ValueError):
    pass


class MarketingCampaignDeliveryNotFoundError(LookupError):
    pass


class MarketingCampaignDeliveryConflictError(RuntimeError):
    pass


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def _utc_now(now: datetime | None = None) -> datetime:
    value = now if now is not None else datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _parse_sent_at_local(value: Any, *, now: datetime | None = None) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MarketingCampaignDeliveryValidationError(
            "sent_at_local es obligatorio."
        )
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise MarketingCampaignDeliveryValidationError(
            "sent_at_local debe ser una fecha/hora ISO válida."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    else:
        parsed = parsed.astimezone(TZ)

    sent_at_utc = parsed.astimezone(UTC)
    if sent_at_utc > _utc_now(now) + timedelta(minutes=5):
        raise MarketingCampaignDeliveryValidationError(
            "La hora de envío no puede estar en el futuro."
        )
    return sent_at_utc


def _read_campaign(
    *,
    campaign_id: int,
    session: Any,
    for_update: bool = False,
) -> MarketingReactivationCampaignORM:
    if not isinstance(campaign_id, int) or isinstance(campaign_id, bool) or campaign_id <= 0:
        raise MarketingCampaignDeliveryValidationError(
            "campaign_id debe ser un entero positivo."
        )
    query = session.query(MarketingReactivationCampaignORM)
    if for_update:
        query = query.with_for_update()
    else:
        query = query.options(
            joinedload(MarketingReactivationCampaignORM.recipients)
        )
    campaign = query.filter(
        MarketingReactivationCampaignORM.id == campaign_id
    ).one_or_none()
    if campaign is None:
        raise MarketingCampaignDeliveryNotFoundError(
            f"No existe la campaña id={campaign_id}."
        )
    if for_update:
        # Load the frozen audience while the campaign row remains locked.
        _ = list(campaign.recipients)
    return campaign


def _branch_counts(campaign: MarketingReactivationCampaignORM) -> Counter[str]:
    return Counter(
        str(recipient.sucursal).strip()
        for recipient in campaign.recipients
        if str(recipient.sucursal or "").strip()
    )


def _read_sends(*, campaign_id: int, session: Any) -> dict[str, Any]:
    rows = (
        session.query(MarketingReactivationCampaignBranchSendORM)
        .filter(
            MarketingReactivationCampaignBranchSendORM.campaign_id == campaign_id
        )
        .order_by(MarketingReactivationCampaignBranchSendORM.sucursal.asc())
        .all()
    )
    return {str(row.sucursal): row for row in rows}


def _delivery_status(
    *,
    campaign: MarketingReactivationCampaignORM,
    total_branches: int,
    sent_branches: int,
) -> str:
    if campaign.status == "CANCELLED":
        return "CANCELLED"
    if campaign.status == "DRAFT":
        return "DRAFT"
    if total_branches > 0 and sent_branches >= total_branches:
        return "SENT"
    if sent_branches > 0:
        return "PARTIALLY_SENT"
    return "EXPORTED"


def _serialize_delivery(
    *,
    campaign: MarketingReactivationCampaignORM,
    branch_counts: Counter[str],
    sends: dict[str, Any],
) -> dict[str, Any]:
    branches = []
    sent_contacts = 0
    for sucursal in sorted(branch_counts, key=str.casefold):
        send = sends.get(sucursal)
        count = int(branch_counts[sucursal])
        sent = send is not None
        if sent:
            sent_contacts += count
        branches.append(
            {
                "sucursal": sucursal,
                "recipient_count": count,
                "sent": sent,
                "sent_at": _to_iso(send.sent_at) if send is not None else None,
                "sent_by_user_id": (
                    int(send.sent_by_user_id)
                    if send is not None and send.sent_by_user_id is not None
                    else None
                ),
            }
        )

    total_branches = len(branches)
    sent_branches = sum(1 for row in branches if row["sent"])
    total_contacts = sum(int(row["recipient_count"]) for row in branches)
    return {
        "status": _delivery_status(
            campaign=campaign,
            total_branches=total_branches,
            sent_branches=sent_branches,
        ),
        "total_branches": total_branches,
        "sent_branches": sent_branches,
        "pending_branches": max(total_branches - sent_branches, 0),
        "total_contacts": total_contacts,
        "sent_contacts": sent_contacts,
        "pending_contacts": max(total_contacts - sent_contacts, 0),
        "branches": branches,
    }


def get_campaign_delivery(
    *,
    campaign_id: int,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    active_session = _session_or_default(session)
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=active_session,
    )
    branch_counts = _branch_counts(campaign)
    if allowed_sucursal_keys is not None:
        allowed = set(allowed_sucursal_keys)
        for sucursal in branch_counts:
            if normalize_socios_vencidos_branch_key(sucursal) not in allowed:
                raise MarketingCampaignDeliveryValidationError(
                    "La campaña contiene sucursales fuera del alcance actual del usuario."
                )
    delivery = _serialize_delivery(
        campaign=campaign,
        branch_counts=branch_counts,
        sends=_read_sends(campaign_id=campaign_id, session=active_session),
    )
    return {
        "campaign_id": int(campaign.id),
        "name": str(campaign.name),
        "campaign_status": str(campaign.status),
        "delivery": delivery,
    }


def register_campaign_branch_sends(
    *,
    campaign_id: int,
    sucursales: Any,
    sent_at_local: Any,
    sent_by_user_id: int,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(sucursales, list) or not sucursales:
        raise MarketingCampaignDeliveryValidationError(
            "Selecciona al menos una sucursal pendiente."
        )
    normalized_requested = []
    for value in sucursales:
        if not isinstance(value, str) or not value.strip():
            raise MarketingCampaignDeliveryValidationError(
                "Cada sucursal debe ser texto no vacío."
            )
        normalized_requested.append(value.strip())
    if len(set(normalized_requested)) != len(normalized_requested):
        raise MarketingCampaignDeliveryValidationError(
            "La selección contiene sucursales duplicadas."
        )

    sent_at_utc = _parse_sent_at_local(sent_at_local, now=now)
    active_session = _session_or_default(session)
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=active_session,
        for_update=True,
    )
    if campaign.status == "DRAFT":
        raise MarketingCampaignDeliveryConflictError(
            "La campaña debe exportarse antes de registrar envíos."
        )
    if campaign.status == "CANCELLED":
        raise MarketingCampaignDeliveryConflictError(
            "Una campaña cancelada no puede registrar envíos."
        )

    created_at = campaign.created_at
    if created_at is not None:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if sent_at_utc < created_at.astimezone(UTC):
            raise MarketingCampaignDeliveryValidationError(
                "La hora de envío no puede ser anterior a la creación de la campaña."
            )

    branch_counts = _branch_counts(campaign)
    requested = set(normalized_requested)
    unknown = sorted(requested - set(branch_counts))
    if unknown:
        raise MarketingCampaignDeliveryValidationError(
            "Sucursales no incluidas en la campaña: " + ", ".join(unknown) + "."
        )
    if allowed_sucursal_keys is not None:
        allowed = set(allowed_sucursal_keys)
        out_of_scope = sorted(
            sucursal
            for sucursal in requested
            if normalize_socios_vencidos_branch_key(sucursal) not in allowed
        )
        if out_of_scope:
            raise MarketingCampaignDeliveryValidationError(
                "Sucursales fuera del alcance autorizado: "
                + ", ".join(out_of_scope)
                + "."
            )

    existing = _read_sends(campaign_id=campaign_id, session=active_session)
    already_sent = sorted(requested & set(existing))
    if already_sent:
        raise MarketingCampaignDeliveryConflictError(
            "Estas sucursales ya tienen un envío registrado y no se modifican "
            "desde esta acción: " + ", ".join(already_sent) + "."
        )

    now_utc = _utc_now(now)
    for sucursal in normalized_requested:
        active_session.add(
            MarketingReactivationCampaignBranchSendORM(
                campaign_id=int(campaign.id),
                sucursal=sucursal,
                sent_at=sent_at_utc,
                sent_by_user_id=int(sent_by_user_id),
                created_at=now_utc,
            )
        )

    try:
        active_session.flush()
        sends = _read_sends(campaign_id=campaign_id, session=active_session)
        if branch_counts and len(sends) >= len(branch_counts):
            campaign.status = "SENT"
            campaign.sent_at = max(row.sent_at for row in sends.values())
        else:
            # A partial send intentionally remains EXPORTED so pending branches
            # can continue to be exported/reviewed without inventing a global send.
            campaign.status = "EXPORTED"
            campaign.sent_at = None
        campaign.updated_at = now_utc
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingCampaignDeliveryConflictError(
            "El registro de envío cambió mientras guardabas. Actualiza y vuelve a intentar."
        ) from exc
    except Exception:
        active_session.rollback()
        raise

    return get_campaign_delivery(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=active_session,
    )


def attach_delivery_summaries(
    campaigns: list[dict[str, Any]],
    *,
    session: Any | None = None,
) -> list[dict[str, Any]]:
    if not campaigns:
        return campaigns
    active_session = _session_or_default(session)
    campaign_ids = [int(row["id"]) for row in campaigns]

    recipient_rows = (
        active_session.query(
            MarketingReactivationCampaignRecipientORM.campaign_id,
            MarketingReactivationCampaignRecipientORM.sucursal,
            func.count(MarketingReactivationCampaignRecipientORM.id),
        )
        .filter(
            MarketingReactivationCampaignRecipientORM.campaign_id.in_(campaign_ids)
        )
        .group_by(
            MarketingReactivationCampaignRecipientORM.campaign_id,
            MarketingReactivationCampaignRecipientORM.sucursal,
        )
        .all()
    )
    counts_by_campaign: dict[int, Counter[str]] = defaultdict(Counter)
    for campaign_id, sucursal, count in recipient_rows:
        counts_by_campaign[int(campaign_id)][str(sucursal)] = int(count)

    send_rows = (
        active_session.query(MarketingReactivationCampaignBranchSendORM)
        .filter(
            MarketingReactivationCampaignBranchSendORM.campaign_id.in_(campaign_ids)
        )
        .all()
    )
    sends_by_campaign: dict[int, dict[str, Any]] = defaultdict(dict)
    for send in send_rows:
        sends_by_campaign[int(send.campaign_id)][str(send.sucursal)] = send

    orm_rows = (
        active_session.query(MarketingReactivationCampaignORM)
        .filter(MarketingReactivationCampaignORM.id.in_(campaign_ids))
        .all()
    )
    orm_by_id = {int(row.id): row for row in orm_rows}
    for payload in campaigns:
        campaign_id = int(payload["id"])
        campaign = orm_by_id[campaign_id]
        delivery = _serialize_delivery(
            campaign=campaign,
            branch_counts=counts_by_campaign.get(campaign_id, Counter()),
            sends=sends_by_campaign.get(campaign_id, {}),
        )
        payload["delivery"] = {
            key: value
            for key, value in delivery.items()
            if key != "branches"
        }
    return campaigns


def branch_send_times_for_campaigns(
    *,
    campaign_ids: Iterable[int],
    session: Any | None = None,
) -> dict[tuple[int, str], datetime]:
    normalized = tuple(sorted({int(value) for value in campaign_ids}))
    if not normalized:
        return {}
    active_session = _session_or_default(session)
    rows = (
        active_session.query(MarketingReactivationCampaignBranchSendORM)
        .filter(
            MarketingReactivationCampaignBranchSendORM.campaign_id.in_(normalized)
        )
        .all()
    )
    return {
        (int(row.campaign_id), str(row.sucursal)): row.sent_at
        for row in rows
    }
