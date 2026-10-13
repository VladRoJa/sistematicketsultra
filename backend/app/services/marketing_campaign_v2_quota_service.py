"""Read-only, operator-evidenced Campaign V2 capacity planning.

No Meta API quota is claimed. Evidence is append-only; unknown/stale is a
hard blocker for capacity *recommendations*. Assessment never reserves/send.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2QuotaPolicyRevisionORM,
    MarketingCampaignV2QuotaCapacityAttestationORM,
)


class CampaignV2QuotaValidationError(ValueError):
    pass


class CampaignV2QuotaConflictError(RuntimeError):
    pass


def _date(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CampaignV2QuotaValidationError("Fecha UTC con zona horaria requerida.")
    return value.astimezone(timezone.utc)


def _parse_iso(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CampaignV2QuotaValidationError("Fecha ISO con zona requerida.")
    try:
        return _date(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (ValueError, TypeError) as exc:
        raise CampaignV2QuotaValidationError("Fecha ISO inválida.") from exc


def _database_date(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _required(value: Any, key: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_len:
        raise CampaignV2QuotaValidationError(f"{key} es obligatorio y acotado.")
    return value.strip()


def _int(value: Any, key: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise CampaignV2QuotaValidationError(f"{key} debe ser entero no negativo" + (" y positivo." if positive else "."))
    return value


def _serialize_policy(row: MarketingCampaignV2QuotaPolicyRevisionORM) -> dict[str, Any]:
    return {
        "revision_id": int(row.id),
        "provider_channel_id": row.provider_channel_id,
        "portfolio_key": row.portfolio_key,
        "account_key": row.account_key,
        "phone_alias": row.phone_alias,
        "nominal_channel_limit": row.nominal_channel_limit,
        "reset_timezone": row.reset_timezone,
        "valid_from": _database_date(row.valid_from).isoformat(),
        "source_reference": row.source_reference,
    }


def _serialize_capacity(row: MarketingCampaignV2QuotaCapacityAttestationORM) -> dict[str, Any]:
    return {
        "attestation_id": int(row.id),
        "scope_kind": row.scope_kind,
        "scope_key": row.scope_key,
        "remaining_messages": int(row.remaining_messages),
        "observed_at": _database_date(row.observed_at).isoformat(),
        "expires_at": _database_date(row.expires_at).isoformat(),
        "window_ends_at": _database_date(row.window_ends_at).isoformat(),
        "source_reference": row.source_reference,
    }


def list_quota_evidence(*, session: Any | None = None) -> dict[str, Any]:
    active = session if session is not None else db.session
    return {
        "policies": [
            _serialize_policy(row)
            for row in active.query(MarketingCampaignV2QuotaPolicyRevisionORM)
            .order_by(MarketingCampaignV2QuotaPolicyRevisionORM.id.desc()).limit(2000).all()
        ],
        "attestations": [
            _serialize_capacity(row)
            for row in active.query(MarketingCampaignV2QuotaCapacityAttestationORM)
            .order_by(MarketingCampaignV2QuotaCapacityAttestationORM.id.desc()).limit(2000).all()
        ],
    }


def register_quota_policy(
    *,
    provider_channel_id: Any, portfolio_key: Any, account_key: Any,
    phone_alias: Any, nominal_channel_limit: Any,
    reset_timezone: Any, source_reference: Any,
    actor_user_id: Any, session: Any | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    channel = _required(provider_channel_id, "provider_channel_id", 255)
    portfolio = _required(portfolio_key, "portfolio_key", 128)
    account = _required(account_key, "account_key", 128)
    phone = _required(phone_alias, "phone_alias", 128)
    tz = _required(reset_timezone, "reset_timezone", 80)
    reference = _required(source_reference, "source_reference", 255)
    actor = _int(actor_user_id, "actor_user_id", positive=True)
    if nominal_channel_limit is not None:
        nominal_channel_limit = _int(nominal_channel_limit, "nominal_channel_limit", positive=True)
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise CampaignV2QuotaValidationError("Zona horaria IANA desconocida.") from exc
    active_binding = active.query(MarketingCampaignV2ChannelBindingORM.id).filter(
        MarketingCampaignV2ChannelBindingORM.provider == "IVENTAS",
        MarketingCampaignV2ChannelBindingORM.provider_channel_id == channel,
        MarketingCampaignV2ChannelBindingORM.is_active.is_(True),
    ).one_or_none()
    if not active_binding:
        raise CampaignV2QuotaValidationError("No existe canal activo con ese ID.")
    timestamp = _date(now or datetime.now(timezone.utc))
    row = MarketingCampaignV2QuotaPolicyRevisionORM(
        provider_channel_id=channel, portfolio_key=portfolio,
        account_key=account, phone_alias=phone,
        nominal_channel_limit=nominal_channel_limit,
        reset_timezone=tz, valid_from=timestamp,
        source_reference=reference, created_by_user_id=actor, created_at=timestamp,
    )
    active.add(row)
    try:
        active.commit()
    except IntegrityError as exc:
        active.rollback()
        raise CampaignV2QuotaConflictError("Ya existe revisión de política para ese instante.") from exc
    return _serialize_policy(row)


def register_quota_capacity(
    *,
    scope_kind: Any, scope_key: Any, observed_at: Any,
    expires_at: Any, window_ends_at: Any, remaining_messages: Any,
    source_reference: Any, actor_user_id: Any,
    session: Any | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    kind = _required(scope_kind, "scope_kind", 20).upper()
    if kind not in {"PORTFOLIO", "CHANNEL"}:
        raise CampaignV2QuotaValidationError("scope_kind solo PORTFOLIO o CHANNEL.")
    key = _required(scope_key, "scope_key", 255)
    observed = _parse_iso(observed_at)
    expires = _parse_iso(expires_at)
    window = _parse_iso(window_ends_at)
    timestamp = _date(now or datetime.now(timezone.utc))
    if not observed <= timestamp or not observed < expires <= window:
        raise CampaignV2QuotaValidationError("Vigencia/cierre de ventana inválidos.")
    if expires - observed > timedelta(hours=24):
        raise CampaignV2QuotaValidationError("Evidencia operativa máxima 24 horas.")
    remaining = _int(remaining_messages, "remaining_messages")
    reference = _required(source_reference, "source_reference", 255)
    actor = _int(actor_user_id, "actor_user_id", positive=True)
    # Attestation is only for registered channels or portfolios; never invent an identity.
    policies = active.query(MarketingCampaignV2QuotaPolicyRevisionORM).filter(
        MarketingCampaignV2QuotaPolicyRevisionORM.valid_from <= timestamp,
    ).all()
    known = {
        r.provider_channel_id if kind == "CHANNEL" else r.portfolio_key
        for r in policies
    }
    if key not in known:
        raise CampaignV2QuotaValidationError("Primero registra un vínculo de canal/portafolio.")
    row = MarketingCampaignV2QuotaCapacityAttestationORM(
        scope_kind=kind, scope_key=key, observed_at=observed,
        expires_at=expires, window_ends_at=window,
        remaining_messages=remaining, source_reference=reference,
        created_by_user_id=actor, created_at=timestamp,
    )
    active.add(row)
    try:
        active.commit()
    except IntegrityError as exc:
        active.rollback()
        raise CampaignV2QuotaConflictError("Ya hay evidencia para esa hora y ámbito.") from exc
    return _serialize_capacity(row)


def assess_preflight_capacity(
    *, plan: Any, session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail-closed display only: never reserves capacity or authorizes submit."""
    active = session if session is not None else db.session
    timestamp = _date(now or datetime.now(timezone.utc))
    channels = {
        str(batch.provider_channel_id)
        for batch in plan.batches if batch.provider_channel_id
    }
    policies = active.query(MarketingCampaignV2QuotaPolicyRevisionORM).filter(
        MarketingCampaignV2QuotaPolicyRevisionORM.provider_channel_id.in_(sorted(channels)),
        MarketingCampaignV2QuotaPolicyRevisionORM.valid_from <= timestamp,
    ).order_by(
        MarketingCampaignV2QuotaPolicyRevisionORM.valid_from.desc(),
        MarketingCampaignV2QuotaPolicyRevisionORM.id.desc(),
    ).all() if channels else []
    by_channel = {}
    for row in policies:
        by_channel.setdefault(row.provider_channel_id, row)
    portfolios = {row.portfolio_key for row in by_channel.values()}
    attestations = active.query(MarketingCampaignV2QuotaCapacityAttestationORM).filter(
        MarketingCampaignV2QuotaCapacityAttestationORM.observed_at <= timestamp,
        MarketingCampaignV2QuotaCapacityAttestationORM.expires_at > timestamp,
        MarketingCampaignV2QuotaCapacityAttestationORM.scope_key.in_(
            sorted(channels | portfolios),
        ),
    ).order_by(
        MarketingCampaignV2QuotaCapacityAttestationORM.observed_at.desc(),
        MarketingCampaignV2QuotaCapacityAttestationORM.id.desc(),
    ).all() if channels else []
    capacity = {}
    for row in attestations:
        capacity.setdefault((row.scope_kind, row.scope_key), row)
    total_by_channel = defaultdict(int)
    total_by_portfolio = defaultdict(int)
    for batch in plan.batches:
        channel = str(batch.provider_channel_id or "")
        count = len(batch.recipients)
        total_by_channel[channel] += count
        policy = by_channel.get(channel)
        if policy:
            total_by_portfolio[policy.portfolio_key] += count

    # Shared-portfolio activity can come from OTHER channels not in this plan.
    # HELD is explicitly unattempted, never counted as Meta consumption.
    all_policies = active.query(MarketingCampaignV2QuotaPolicyRevisionORM).filter(
        MarketingCampaignV2QuotaPolicyRevisionORM.portfolio_key.in_(sorted(portfolios)),
        MarketingCampaignV2QuotaPolicyRevisionORM.valid_from <= timestamp,
    ).order_by(
        MarketingCampaignV2QuotaPolicyRevisionORM.valid_from.desc(),
        MarketingCampaignV2QuotaPolicyRevisionORM.id.desc(),
    ).all() if portfolios else []
    latest_policies = {}
    for policy in all_policies:
        latest_policies.setdefault(policy.provider_channel_id, policy)
    events = []
    if latest_policies:
        events = active.query(MarketingCampaignV2ProviderCampaignORM).filter(
            MarketingCampaignV2ProviderCampaignORM.provider == "IVENTAS",
            MarketingCampaignV2ProviderCampaignORM.provider_channel_id.in_(
                sorted(latest_policies)
            ),
            MarketingCampaignV2ProviderCampaignORM.status.in_(
                ("SUBMITTING", "SUBMITTED", "SCHEDULED", "RECONCILIATION_REQUIRED"),
            ),
        ).all()
    rows = []
    ready_count = held_count = 0
    for batch in plan.batches:
        channel = str(batch.provider_channel_id or "")
        count = len(batch.recipients)
        policy = by_channel.get(channel)
        reason = None
        c = capacity.get(("CHANNEL", channel))
        p = capacity.get(("PORTFOLIO", policy.portfolio_key)) if policy else None
        if not policy:
            reason = "MISSING_QUOTA_POLICY"
        elif not c or not p:
            reason = "MISSING_VERIFIED_REMAINING"
        elif total_by_channel[channel] > int(c.remaining_messages):
            reason = "CHANNEL_REMAINING_EXCEEDED"
        elif total_by_portfolio[policy.portfolio_key] > int(p.remaining_messages):
            reason = "SHARED_PORTFOLIO_REMAINING_EXCEEDED"
        elif any(
            latest_policies.get(evt.provider_channel_id) is not None
            and latest_policies[evt.provider_channel_id].portfolio_key == policy.portfolio_key
            and _database_date(evt.submit_started_at or evt.submitted_at or evt.created_at)
            >= _database_date(p.observed_at)
            for evt in events
        ):
            reason = "ACTIVITY_AFTER_QUOTA_ATTESTATION"
        if reason:
            held_count += count
        else:
            ready_count += count
        rows.append({
            "sucursal_canon": batch.sucursal_canon,
            "provider_channel_id": channel or None,
            "portfolio_key": policy.portfolio_key if policy else None,
            "account_key": policy.account_key if policy else None,
            "phone_alias": policy.phone_alias if policy else None,
            "reset_timezone": policy.reset_timezone if policy else None,
            "reported_nominal_channel_limit": policy.nominal_channel_limit if policy else None,
            "channel_remaining": int(c.remaining_messages) if c else None,
            "portfolio_remaining": int(p.remaining_messages) if p else None,
            "channel_evidence_id": int(c.id) if c else None,
            "portfolio_evidence_id": int(p.id) if p else None,
            "recipients": count,
            "recommendation": "REVIEW_HOLD" if reason else "CAPACITY_REVIEWED",
            "blocking_reason": reason,
        })
    return {
        "basis": "OPERATOR_ATTESTED_NOT_META_VERIFIED",
        "status": "REVIEWABLE" if rows and not held_count else "INCOMPLETE",
        "send_authorized": False,
        "as_of": timestamp.isoformat(),
        "reviewed_recipients": ready_count,
        "hold_recommended_recipients": held_count,
        "batches": rows,
        "portfolio_demands": [
            {"portfolio_key": key, "recipients": total_by_portfolio[key],
             "attested_remaining": int(capacity[("PORTFOLIO", key)].remaining_messages)
             if ("PORTFOLIO", key) in capacity else None}
            for key in sorted(total_by_portfolio)
        ],
    }
