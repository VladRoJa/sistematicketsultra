from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Any, Iterable

from sqlalchemy import and_, exists, false, func, or_, true
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services import marketing_campaign_v2_audience_service as audience
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


CAMPAIGN_V2_PURPOSES = (
    "NEW_SALE",
    "REACTIVATION",
    "ACTIVE_MEMBERS",
    "UNCLASSIFIED",
)

CAMPAIGN_V2_RECIPIENT_PROVIDER_STATUSES = frozenset({
    "SENT", "DELIVERED", "VIEWED", "FAILED",
    "SUCCESSFUL", "NO_PROVIDER_STATUS", "NO_SNAPSHOT",
})


class MarketingCampaignV2QueryError(RuntimeError):
    """Base para errores de lectura/mutación segura de Campaign V2."""


class MarketingCampaignV2QueryValidationError(
    MarketingCampaignV2QueryError,
    ValueError,
):
    """Parámetros de lectura o purpose inválidos."""


class MarketingCampaignV2NotFoundError(MarketingCampaignV2QueryError):
    """Campaña/recipient inexistente o no visible para el scope actual."""


def list_campaign_v2(
    *,
    allowed_sucursal_keys: Iterable[str] | None,
    page: Any = 1,
    page_size: Any = 50,
    purpose: Any = None,
    source: Any = None,
    session=None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_page = _positive_int(page, field_name="page", maximum=1_000_000)
    normalized_page_size = _positive_int(
        page_size,
        field_name="page_size",
        maximum=100,
    )
    normalized_purpose = _normalize_optional_purpose(purpose)
    normalized_source = _normalize_optional_source(source)
    normalized_scope = _normalize_current_scope(allowed_sucursal_keys)

    query = (
        active_session.query(
            MarketingCampaignV2ORM,
            func.count(MarketingCampaignV2RecipientORM.id).label("recipient_count"),
        )
        .outerjoin(
            MarketingCampaignV2RecipientORM,
            MarketingCampaignV2RecipientORM.campaign_id == MarketingCampaignV2ORM.id,
        )
    )
    if normalized_purpose is not None:
        query = query.filter(MarketingCampaignV2ORM.purpose == normalized_purpose)
    if normalized_source is not None:
        query = query.filter(MarketingCampaignV2ORM.source == normalized_source)

    rows = (
        query.group_by(MarketingCampaignV2ORM.id)
        .order_by(
            MarketingCampaignV2ORM.frozen_at.desc(),
            MarketingCampaignV2ORM.id.desc(),
        )
        .all()
    )
    visible = [
        (campaign, int(recipient_count or 0))
        for campaign, recipient_count in rows
        if _campaign_visible_to_scope(campaign, normalized_scope)
    ]
    total = len(visible)
    offset = (normalized_page - 1) * normalized_page_size
    page_rows = visible[offset : offset + normalized_page_size]
    return {
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "total_pages": _total_pages(total, normalized_page_size),
        "rows": [
            _serialize_campaign_summary(campaign, recipient_count=recipient_count)
            for campaign, recipient_count in page_rows
        ],
    }


def get_campaign_v2(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_id = _positive_int(campaign_id, field_name="campaign_id", maximum=None)
    scope = _normalize_current_scope(allowed_sucursal_keys)
    campaign = (
        active_session.query(MarketingCampaignV2ORM)
        .filter(MarketingCampaignV2ORM.id == normalized_id)
        .first()
    )
    campaign = _require_visible_campaign(campaign, scope)
    recipient_count = int(
        active_session.query(func.count(MarketingCampaignV2RecipientORM.id))
        .filter(MarketingCampaignV2RecipientORM.campaign_id == normalized_id)
        .scalar()
        or 0
    )
    return _serialize_campaign_detail(campaign, recipient_count=recipient_count)


def list_campaign_v2_recipients(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    page: Any = 1,
    page_size: Any = 50,
    provider_status: Any = None,
    session=None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_id = _positive_int(campaign_id, field_name="campaign_id", maximum=None)
    normalized_page = _positive_int(page, field_name="page", maximum=1_000_000)
    normalized_page_size = _positive_int(page_size, field_name="page_size", maximum=100)
    normalized_status = _normalize_optional_recipient_provider_status(provider_status)
    scope = _normalize_current_scope(allowed_sucursal_keys)

    with active_session.no_autoflush:
        _load_visible_campaign_orm(
            campaign_id=normalized_id,
            scope=scope,
            session=active_session,
        )

        # Un único snapshot persistido rige el filtro, el total y las filas.
        # No mezclar estados históricos ni consultar al proveedor al paginar.
        latest_snapshot = (
            active_session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
            .filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id
                == normalized_id
            )
            .order_by(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.desc(),
                MarketingCampaignV2ProviderStatsSnapshotORM.id.desc(),
            )
            .first()
        )
        status_predicate = _recipient_provider_status_predicate(
            latest_snapshot, normalized_status,
        )

        count_query = (
            active_session.query(func.count(MarketingCampaignV2RecipientORM.id))
            .filter(MarketingCampaignV2RecipientORM.campaign_id == normalized_id)
        )
        page_query = (
            active_session.query(
                MarketingCampaignV2RecipientORM,
                func.count(MarketingCampaignV2RecipientEvidenceORM.id).label("evidence_count"),
            )
            .outerjoin(
                MarketingCampaignV2RecipientEvidenceORM,
                MarketingCampaignV2RecipientEvidenceORM.recipient_id
                == MarketingCampaignV2RecipientORM.id,
            )
            .filter(MarketingCampaignV2RecipientORM.campaign_id == normalized_id)
        )
        if status_predicate is not None:
            count_query = count_query.filter(status_predicate)
            page_query = page_query.filter(status_predicate)
        total = int(count_query.scalar() or 0)
        rows = (
            page_query.group_by(MarketingCampaignV2RecipientORM.id)
            .order_by(MarketingCampaignV2RecipientORM.id.asc())
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
            .all()
        )
    observations_by_recipient = {}
    if latest_snapshot is not None and rows:
        recipient_ids = [int(recipient.id) for recipient, _ in rows]
        observations = (
            active_session.query(MarketingCampaignV2ProviderRecipientObservationORM)
            .filter(
                MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id
                == latest_snapshot.id,
                MarketingCampaignV2ProviderRecipientObservationORM.campaign_recipient_id.in_(
                    recipient_ids
                ),
            )
            .order_by(MarketingCampaignV2ProviderRecipientObservationORM.id.asc())
            .all()
        )
        observations_by_recipient = {
            int(observation.campaign_recipient_id): observation
            for observation in observations
        }

    return {
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "total_pages": _total_pages(total, normalized_page_size),
        "rows": [
            {
                **_serialize_recipient_summary(
                    recipient, evidence_count=int(evidence_count or 0)
                ),
                "provider_status": _serialize_recipient_provider_status(
                    latest_snapshot,
                    observations_by_recipient.get(int(recipient.id)),
                ),
            }
            for recipient, evidence_count in rows
        ],
    }


def get_campaign_v2_recipient(
    *,
    campaign_id: Any,
    recipient_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_campaign_id = _positive_int(
        campaign_id,
        field_name="campaign_id",
        maximum=None,
    )
    normalized_recipient_id = _positive_int(
        recipient_id,
        field_name="recipient_id",
        maximum=None,
    )
    scope = _normalize_current_scope(allowed_sucursal_keys)
    _load_visible_campaign_orm(
        campaign_id=normalized_campaign_id,
        scope=scope,
        session=active_session,
    )
    recipient = (
        active_session.query(MarketingCampaignV2RecipientORM)
        .filter(
            MarketingCampaignV2RecipientORM.id == normalized_recipient_id,
            MarketingCampaignV2RecipientORM.campaign_id == normalized_campaign_id,
        )
        .first()
    )
    if recipient is None:
        raise MarketingCampaignV2NotFoundError("Recipient V2 no encontrado.")

    evidence_rows = (
        active_session.query(MarketingCampaignV2RecipientEvidenceORM)
        .filter(
            MarketingCampaignV2RecipientEvidenceORM.recipient_id
            == normalized_recipient_id
        )
        .order_by(
            MarketingCampaignV2RecipientEvidenceORM.evidence_order.asc(),
            MarketingCampaignV2RecipientEvidenceORM.id.asc(),
        )
        .all()
    )
    return {
        **_serialize_recipient_summary(recipient, evidence_count=len(evidence_rows)),
        "evidence": [_serialize_evidence(row) for row in evidence_rows],
    }


def update_campaign_v2_purpose(
    *,
    campaign_id: Any,
    purpose: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_id = _positive_int(campaign_id, field_name="campaign_id", maximum=None)
    normalized_purpose = _normalize_required_purpose(purpose)
    scope = _normalize_current_scope(allowed_sucursal_keys)
    campaign = _load_visible_campaign_orm(
        campaign_id=normalized_id,
        scope=scope,
        session=active_session,
    )
    recipient_count = int(
        active_session.query(func.count(MarketingCampaignV2RecipientORM.id))
        .filter(MarketingCampaignV2RecipientORM.campaign_id == normalized_id)
        .scalar()
        or 0
    )
    updated_at = _normalize_now(now)
    campaign.purpose = normalized_purpose
    campaign.updated_at = updated_at
    result = _serialize_campaign_detail(
        campaign,
        recipient_count=recipient_count,
    )
    try:
        active_session.commit()
    except SQLAlchemyError:
        active_session.rollback()
        raise
    return result


def _load_visible_campaign_orm(*, campaign_id: int, scope, session):
    campaign = (
        session.query(MarketingCampaignV2ORM)
        .filter(MarketingCampaignV2ORM.id == campaign_id)
        .first()
    )
    return _require_visible_campaign(campaign, scope)


def _require_visible_campaign(campaign, scope):
    if campaign is None or not _campaign_visible_to_scope(campaign, scope):
        raise MarketingCampaignV2NotFoundError("Campaign V2 no encontrada.")
    return campaign


def _campaign_visible_to_scope(campaign, scope: tuple[str, ...] | None) -> bool:
    frozen_scope = _extract_frozen_scope(campaign)
    if frozen_scope == ():
        return False
    if scope is None:
        return True
    if frozen_scope is None:
        return False
    return set(frozen_scope).issubset(set(scope))


def _extract_frozen_scope(campaign) -> tuple[str, ...] | None:
    definition = getattr(campaign, "audience_definition_json", None)
    if not isinstance(definition, dict):
        return ()
    filters = definition.get("filters")
    if not isinstance(filters, dict) or "allowed_sucursal_keys" not in filters:
        return ()
    raw_scope = filters.get("allowed_sucursal_keys")
    if raw_scope is None:
        return None
    if isinstance(raw_scope, str) or not isinstance(raw_scope, (list, tuple)):
        return ()
    keys: set[str] = set()
    for value in raw_scope:
        if not isinstance(value, str):
            return ()
        key = normalize_socios_vencidos_branch_key(value)
        if key is None:
            return ()
        keys.add(key)
    return tuple(sorted(keys))


def _normalize_current_scope(value: Iterable[str] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raise MarketingCampaignV2QueryValidationError(
            "allowed_sucursal_keys debe ser una colección interna o null."
        )
    keys: set[str] = set()
    for raw in value:
        key = normalize_socios_vencidos_branch_key(raw)
        if key:
            keys.add(key)
    if not keys:
        raise MarketingCampaignV2QueryValidationError(
            "El scope backend de Campaign V2 no contiene sucursales válidas."
        )
    return tuple(sorted(keys))


def _serialize_campaign_summary(campaign, *, recipient_count: int) -> dict[str, Any]:
    fingerprint, version = _preview_identity(campaign)
    return {
        "id": int(campaign.id),
        "name": campaign.name,
        "purpose": campaign.purpose,
        "source": campaign.source,
        "provider": campaign.provider,
        "provider_campaign_id": campaign.provider_campaign_id,
        "frozen_at": _iso_datetime(campaign.frozen_at),
        "created_at": _iso_datetime(campaign.created_at),
        "created_by_user_id": campaign.created_by_user_id,
        "recipient_count": int(recipient_count),
        "preview_fingerprint": fingerprint,
        "preview_fingerprint_version": version,
    }


def _serialize_campaign_detail(campaign, *, recipient_count: int) -> dict[str, Any]:
    return {
        **_serialize_campaign_summary(campaign, recipient_count=recipient_count),
        "updated_at": _iso_datetime(campaign.updated_at),
        "audience_definition": _json_copy(campaign.audience_definition_json),
    }


def _normalize_optional_recipient_provider_status(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise MarketingCampaignV2QueryValidationError("provider_status inválido.")
    normalized = value.strip().upper()
    if normalized == "ALL":
        return None
    if normalized not in CAMPAIGN_V2_RECIPIENT_PROVIDER_STATUSES:
        raise MarketingCampaignV2QueryValidationError(
            "provider_status debe ser SENT, DELIVERED, VIEWED, FAILED, "
            "SUCCESSFUL, NO_PROVIDER_STATUS, NO_SNAPSHOT o ALL."
        )
    return normalized


def _recipient_provider_status_predicate(snapshot, status: str | None):
    """Filtro SQL previo a count/paginación para el snapshot más reciente."""
    if status is None:
        return None
    if status == "NO_SNAPSHOT":
        return true() if snapshot is None else false()
    if snapshot is None:
        return false()

    obs = MarketingCampaignV2ProviderRecipientObservationORM
    observation = exists().where(
        and_(
            obs.snapshot_id == snapshot.id,
            obs.campaign_recipient_id == MarketingCampaignV2RecipientORM.id,
        )
    )
    if status == "NO_PROVIDER_STATUS":
        return ~observation

    if status == "FAILED":
        matching_outcome = obs.outcome == "FAILED"
    elif status in {"SENT", "DELIVERED", "VIEWED"}:
        matching_outcome = and_(
            obs.outcome == "SUCCESSFUL",
            obs.delivery_bucket == status,
        )
    else:
        # Fallback defensivo del serializer: SUCCESSFUL sin bucket reconocido.
        matching_outcome = and_(
            obs.outcome == "SUCCESSFUL",
            or_(
                obs.delivery_bucket.is_(None),
                ~obs.delivery_bucket.in_(("SENT", "DELIVERED", "VIEWED")),
            ),
        )
    return exists().where(
        and_(
            obs.snapshot_id == snapshot.id,
            obs.campaign_recipient_id == MarketingCampaignV2RecipientORM.id,
            matching_outcome,
        )
    )


def _serialize_recipient_summary(recipient, *, evidence_count: int) -> dict[str, Any]:
    return {
        "id": int(recipient.id),
        "phone_mx10": recipient.phone_mx10,
        "source": recipient.source,
        "member_id": recipient.member_id,
        "member_pin": recipient.member_pin,
        "member_name": recipient.member_name,
        "sucursal": recipient.sucursal,
        "tarifa_raw": recipient.tarifa_raw,
        "categoria_tarifa": recipient.categoria_tarifa,
        "audience_family": recipient.audience_family,
        "fecha_vencimiento_date": _iso_date(recipient.fecha_vencimiento_date),
        "inclusion_reason": recipient.inclusion_reason,
        "conflict_fields": list(recipient.conflict_fields_json or []),
        "evidence_count": int(evidence_count),
    }


def _serialize_recipient_provider_status(snapshot, observation) -> dict[str, Any]:
    # Sin snapshot no equivale a fallido; sin match tampoco.
    if snapshot is None:
        return {
            "status": "NO_SNAPSHOT",
            "snapshot_id": None,
            "observed_at": None,
            "outcome": None,
            "delivery_bucket": None,
            "button_labels": [],
        }

    outcome = str(observation.outcome or "").upper() if observation else None
    bucket = (str(observation.delivery_bucket).upper()
              if observation and observation.delivery_bucket else None)
    if outcome == "FAILED":
        status = "FAILED"
    elif outcome == "SUCCESSFUL":
        status = bucket if bucket in {"SENT", "DELIVERED", "VIEWED"} else "SUCCESSFUL"
    else:
        status = "NO_PROVIDER_STATUS"

    return {
        "status": status,
        "snapshot_id": int(snapshot.id),
        "observed_at": _iso_datetime(snapshot.fetched_at),
        "outcome": outcome,
        "delivery_bucket": bucket,
        "button_labels": list(observation.button_labels_json or []) if observation else [],
    }


def _serialize_evidence(row) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "evidence_order": int(row.evidence_order),
        "source": row.source,
        "phone_raw": row.phone_raw,
        "phone_mx10": row.phone_mx10,
        "socios_vencidos_cartera_id": row.socios_vencidos_cartera_id,
        "socios_activos_snapshot_row_id": row.socios_activos_snapshot_row_id,
        "socios_activos_snapshot_id": row.socios_activos_snapshot_id,
        "member_id": row.member_id,
        "member_pin": row.member_pin,
        "member_name": row.member_name,
        "sucursal": row.sucursal,
        "sucursal_key": row.sucursal_key,
        "tarifa_raw": row.tarifa_raw,
        "tarifa_key": row.tarifa_key,
        "categoria_tarifa": row.categoria_tarifa,
        "audience_family": row.audience_family,
        "fecha_vencimiento_date": _iso_date(row.fecha_vencimiento_date),
        "current_status": row.current_status,
        "evidence": list(row.evidence_json or []),
        "created_at": _iso_datetime(row.created_at),
    }


def _preview_identity(campaign) -> tuple[str | None, str | None]:
    definition = getattr(campaign, "audience_definition_json", None)
    if not isinstance(definition, dict):
        return None, None
    preview = definition.get("preview")
    if not isinstance(preview, dict):
        return None, None
    fingerprint = preview.get("fingerprint")
    version = preview.get("fingerprint_version")
    return (
        str(fingerprint) if fingerprint is not None else None,
        str(version) if version is not None else None,
    )


def _normalize_optional_purpose(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _normalize_required_purpose(value)


def _normalize_required_purpose(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in CAMPAIGN_V2_PURPOSES:
        raise MarketingCampaignV2QueryValidationError(
            "purpose debe ser NEW_SALE, REACTIVATION, ACTIVE_MEMBERS o UNCLASSIFIED."
        )
    return normalized


def _normalize_optional_source(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    normalized = str(value).strip().upper()
    if normalized not in audience.SUPPORTED_SOURCES:
        raise MarketingCampaignV2QueryValidationError(
            "source debe ser EXPIRED_MEMBERS, ACTIVE_MEMBERS o FUNNEL_PORTFOLIO."
        )
    return normalized


def _positive_int(value: Any, *, field_name: str, maximum: int | None) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2QueryValidationError(
            f"{field_name} debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2QueryValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized <= 0 or (maximum is not None and normalized > maximum):
        suffix = f" y máximo {maximum}" if maximum is not None else ""
        raise MarketingCampaignV2QueryValidationError(
            f"{field_name} debe ser entero positivo{suffix}."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise MarketingCampaignV2QueryValidationError("now debe incluir zona horaria.")
    return current.astimezone(timezone.utc)


def _total_pages(total: int, page_size: int) -> int:
    return int(ceil(total / page_size)) if total else 0


def _iso_date(value) -> str | None:
    return value.isoformat() if value is not None else None


def _iso_datetime(value) -> str | None:
    return value.isoformat() if value is not None else None


def _json_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_copy(item) for item in value]
    if isinstance(value, tuple):
        return [_json_copy(item) for item in value]
    return value
