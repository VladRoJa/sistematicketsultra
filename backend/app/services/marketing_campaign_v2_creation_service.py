from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services import marketing_campaign_v2_audience_service as audience


PREVIEW_FINGERPRINT_VERSION = "campaign-v2-freeze-v1"
_ALLOWED_PURPOSES = frozenset(
    {
        "NEW_SALE",
        "REACTIVATION",
        "ACTIVE_MEMBERS",
        "UNCLASSIFIED",
    }
)
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class MarketingCampaignV2CreationError(RuntimeError):
    """Base para errores de freeze/create de Campaign V2."""


class MarketingCampaignV2CreationValidationError(
    MarketingCampaignV2CreationError,
    ValueError,
):
    """La definición de negocio no cumple el contrato de creación."""


class MarketingCampaignV2PreviewMismatchError(MarketingCampaignV2CreationError):
    """El universo reconstruido ya no coincide con el Preview aprobado."""


class MarketingCampaignV2EmptyAudienceError(MarketingCampaignV2CreationError):
    """El builder produjo una audiencia final vacía."""


class MarketingCampaignV2PersistenceError(MarketingCampaignV2CreationError):
    """La transacción de Campaign + Recipients + Evidence no pudo persistirse."""


def build_campaign_v2_freeze_preview(
    *,
    source: Any,
    audience_families: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expiration_date_from: Any = None,
    expiration_date_to: Any = None,
    session: Any | None = None,
) -> dict[str, Any]:
    """Reconstruye con M3 y entrega Preview más fingerprint server-side."""

    plan = _rebuild_plan(
        source=source,
        audience_families=audience_families,
        allowed_sucursal_keys=allowed_sucursal_keys,
        expiration_date_from=expiration_date_from,
        expiration_date_to=expiration_date_to,
        session=session,
    )
    preview = audience._serialize_preview(plan)
    fingerprint = _fingerprint_plan(plan)

    return {
        **preview,
        "preview_fingerprint_version": PREVIEW_FINGERPRINT_VERSION,
        "preview_fingerprint": fingerprint,
    }


def freeze_campaign_v2(
    *,
    name: Any,
    purpose: Any,
    source: Any,
    audience_families: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expected_preview_fingerprint: Any,
    created_by_user_id: Any,
    expiration_date_from: Any = None,
    expiration_date_to: Any = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reconstruye, valida Preview y congela Campaign V2 de forma atómica."""

    normalized_name = _normalize_name(name)
    normalized_purpose = _normalize_purpose(purpose)
    normalized_created_by_user_id = _normalize_created_by_user_id(
        created_by_user_id
    )
    expected_fingerprint = _normalize_expected_fingerprint(
        expected_preview_fingerprint
    )
    frozen_at = _normalize_now(now)
    active_session = session if session is not None else db.session

    plan = _rebuild_plan(
        source=source,
        audience_families=audience_families,
        allowed_sucursal_keys=allowed_sucursal_keys,
        expiration_date_from=expiration_date_from,
        expiration_date_to=expiration_date_to,
        session=active_session,
    )
    preview = audience._serialize_preview(plan)

    if int(preview["unique_recipient_count"]) == 0:
        raise MarketingCampaignV2EmptyAudienceError(
            "Campaign V2 no puede congelarse con una audiencia vacía."
        )

    actual_fingerprint = _fingerprint_plan(plan)
    if actual_fingerprint != expected_fingerprint:
        raise MarketingCampaignV2PreviewMismatchError(
            "El Preview Campaign V2 cambió; vuelve a generar Preview antes de congelar."
        )

    campaign = MarketingCampaignV2ORM(
        name=normalized_name,
        purpose=normalized_purpose,
        source=plan.source,
        audience_definition_json=_build_audience_definition(
            plan=plan,
            preview=preview,
            fingerprint=actual_fingerprint,
        ),
        created_by_user_id=normalized_created_by_user_id,
        frozen_at=frozen_at,
        created_at=frozen_at,
        updated_at=frozen_at,
    )

    for recipient_candidate in plan.recipients:
        recipient = _build_recipient_orm(
            recipient_candidate,
            frozen_at=frozen_at,
        )
        campaign.recipients.append(recipient)
        for evidence_order, evidence_candidate in enumerate(
            recipient_candidate.evidence_rows
        ):
            recipient.evidence_rows.append(
                _build_evidence_orm(
                    recipient_candidate=recipient_candidate,
                    evidence_candidate=evidence_candidate,
                    evidence_order=evidence_order,
                    frozen_at=frozen_at,
                )
            )

    try:
        active_session.add(campaign)
        active_session.flush()
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingCampaignV2PersistenceError(
            "Conflicto de integridad al congelar Campaign V2."
        ) from exc
    except SQLAlchemyError as exc:
        active_session.rollback()
        raise MarketingCampaignV2PersistenceError(
            "Error de persistencia al congelar Campaign V2."
        ) from exc
    except Exception:
        active_session.rollback()
        raise

    return {
        "campaign_id": int(campaign.id),
        "name": campaign.name,
        "purpose": campaign.purpose,
        "source": campaign.source,
        "frozen_at": _iso_datetime(campaign.frozen_at),
        "recipient_count": len(plan.recipients),
        "preview_fingerprint_version": PREVIEW_FINGERPRINT_VERSION,
        "preview_fingerprint": actual_fingerprint,
        "preview": preview,
    }


def _rebuild_plan(
    *,
    source: Any,
    audience_families: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expiration_date_from: Any,
    expiration_date_to: Any,
    session: Any | None,
):
    try:
        return audience._build_campaign_v2_audience_plan(
            source=source,
            audience_families=audience_families,
            allowed_sucursal_keys=allowed_sucursal_keys,
            expiration_date_from=expiration_date_from,
            expiration_date_to=expiration_date_to,
            session=session,
        )
    except audience.MarketingCampaignV2AudienceValidationError as exc:
        raise MarketingCampaignV2CreationValidationError(str(exc)) from exc


def _build_audience_definition(
    *,
    plan: Any,
    preview: dict[str, Any],
    fingerprint: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "filters": _canonical_value(plan.filters),
        "source_metadata": _canonical_value(plan.source_metadata),
        "preview": {
            "fingerprint_version": PREVIEW_FINGERPRINT_VERSION,
            "fingerprint": fingerprint,
            "summary": _preview_summary(preview),
        },
    }


def _preview_summary(preview: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "universe_count",
        "scoped_count",
        "current_status_counts",
        "current_status_blocked_count",
        "filtered_count",
        "family_counts",
        "unclassified_family_count",
        "out_of_segment_count",
        "invalid_phone_count",
        "duplicate_count",
        "unique_recipient_count",
    )
    return {
        key: _canonical_value(preview[key])
        for key in keys
    }


def _fingerprint_plan(plan: Any) -> str:
    preview = audience._serialize_preview(plan)
    payload = {
        "version": PREVIEW_FINGERPRINT_VERSION,
        "source": plan.source,
        "filters": _canonical_value(plan.filters),
        "source_metadata": _canonical_value(plan.source_metadata),
        "preview_summary": _preview_summary(preview),
        "recipients": [
            _canonical_recipient(recipient)
            for recipient in sorted(
                plan.recipients,
                key=lambda row: str(row.phone_mx10),
            )
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_recipient(recipient: Any) -> dict[str, Any]:
    evidence_rows = sorted(
        recipient.evidence_rows,
        key=_canonical_evidence_sort_key,
    )
    return {
        "source": recipient.source,
        "phone_mx10": recipient.phone_mx10,
        "member_id": recipient.member_id,
        "member_pin": recipient.member_pin,
        "member_name": recipient.member_name,
        "sucursal": recipient.sucursal,
        "tarifa_raw": recipient.tarifa_raw,
        "tarifa_key": recipient.tarifa_key,
        "categoria_tarifa": recipient.categoria_tarifa,
        "audience_family": recipient.audience_family,
        "fecha_vencimiento": _iso_date(recipient.fecha_vencimiento),
        "inclusion_reason": recipient.inclusion_reason,
        "conflict_fields": sorted(recipient.conflict_fields),
        "evidence_rows": [
            _canonical_evidence(evidence)
            for evidence in evidence_rows
        ],
    }


def _canonical_evidence(candidate: Any) -> dict[str, Any]:
    return {
        "source": candidate.source,
        "source_ref_type": candidate.source_ref_type,
        "source_ref_id": candidate.source_ref_id,
        "source_snapshot_id": candidate.source_snapshot_id,
        "phone_raw": candidate.phone_raw,
        "phone_mx10": candidate.phone_mx10,
        "member_id": candidate.member_id,
        "member_pin": candidate.member_pin,
        "member_name": candidate.member_name,
        "sucursal": candidate.sucursal,
        "sucursal_key": candidate.sucursal_key,
        "tarifa_raw": candidate.tarifa_raw,
        "tarifa_key": candidate.tarifa_key,
        "categoria_tarifa": candidate.categoria_tarifa,
        "audience_family": candidate.audience_family,
        "fecha_vencimiento": _iso_date(candidate.fecha_vencimiento),
        "current_status": candidate.current_status,
        "evidence": sorted(str(value) for value in candidate.evidence),
    }


def _canonical_evidence_sort_key(candidate: Any) -> tuple[Any, ...]:
    return (
        str(candidate.source),
        str(candidate.source_ref_type),
        -1 if candidate.source_ref_id is None else int(candidate.source_ref_id),
        -1 if candidate.source_snapshot_id is None else int(candidate.source_snapshot_id),
        str(candidate.phone_mx10 or ""),
        str(candidate.member_id or ""),
        str(candidate.member_pin or ""),
        str(candidate.tarifa_key or ""),
    )


def _build_recipient_orm(
    candidate: Any,
    *,
    frozen_at: datetime,
) -> MarketingCampaignV2RecipientORM:
    vencidos_id, activos_row_id = _summary_source_refs(candidate)
    return MarketingCampaignV2RecipientORM(
        phone_mx10=str(candidate.phone_mx10),
        source=str(candidate.source),
        socios_vencidos_cartera_id=vencidos_id,
        socios_activos_snapshot_row_id=activos_row_id,
        member_id=candidate.member_id,
        member_pin=candidate.member_pin,
        member_name=candidate.member_name,
        sucursal=candidate.sucursal,
        tarifa_raw=candidate.tarifa_raw,
        categoria_tarifa=candidate.categoria_tarifa,
        audience_family=candidate.audience_family,
        fecha_vencimiento_date=candidate.fecha_vencimiento,
        inclusion_reason=candidate.inclusion_reason,
        conflict_fields_json=list(candidate.conflict_fields),
        created_at=frozen_at,
    )


def _summary_source_refs(candidate: Any) -> tuple[int | None, int | None]:
    if len(candidate.evidence_rows) != 1 or candidate.conflict_fields:
        return None, None
    evidence = candidate.evidence_rows[0]
    if (
        evidence.source == audience.SOURCE_EXPIRED_MEMBERS
        and evidence.source_ref_type == "SOCIOS_VENCIDOS_CARTERA"
        and evidence.source_ref_id is not None
    ):
        return int(evidence.source_ref_id), None
    if (
        evidence.source == audience.SOURCE_ACTIVE_MEMBERS
        and evidence.source_ref_type == "SOCIOS_ACTIVOS_SNAPSHOT_ROW"
        and evidence.source_ref_id is not None
    ):
        return None, int(evidence.source_ref_id)
    return None, None


def _build_evidence_orm(
    *,
    recipient_candidate: Any,
    evidence_candidate: Any,
    evidence_order: int,
    frozen_at: datetime,
) -> MarketingCampaignV2RecipientEvidenceORM:
    vencidos_id = None
    activos_row_id = None
    activos_snapshot_id = None

    if (
        evidence_candidate.source == audience.SOURCE_EXPIRED_MEMBERS
        and evidence_candidate.source_ref_type == "SOCIOS_VENCIDOS_CARTERA"
        and evidence_candidate.source_ref_id is not None
    ):
        vencidos_id = int(evidence_candidate.source_ref_id)
    elif (
        evidence_candidate.source == audience.SOURCE_ACTIVE_MEMBERS
        and evidence_candidate.source_ref_type == "SOCIOS_ACTIVOS_SNAPSHOT_ROW"
        and evidence_candidate.source_ref_id is not None
    ):
        activos_row_id = int(evidence_candidate.source_ref_id)
        if evidence_candidate.source_snapshot_id is not None:
            activos_snapshot_id = int(evidence_candidate.source_snapshot_id)

    return MarketingCampaignV2RecipientEvidenceORM(
        evidence_order=evidence_order,
        source=str(evidence_candidate.source),
        phone_raw=evidence_candidate.phone_raw,
        phone_mx10=str(recipient_candidate.phone_mx10),
        socios_vencidos_cartera_id=vencidos_id,
        socios_activos_snapshot_row_id=activos_row_id,
        socios_activos_snapshot_id=activos_snapshot_id,
        member_id=evidence_candidate.member_id,
        member_pin=evidence_candidate.member_pin,
        member_name=evidence_candidate.member_name,
        sucursal=evidence_candidate.sucursal,
        sucursal_key=evidence_candidate.sucursal_key,
        tarifa_raw=evidence_candidate.tarifa_raw,
        tarifa_key=evidence_candidate.tarifa_key,
        categoria_tarifa=evidence_candidate.categoria_tarifa,
        audience_family=evidence_candidate.audience_family,
        fecha_vencimiento_date=evidence_candidate.fecha_vencimiento,
        current_status=evidence_candidate.current_status,
        evidence_json=list(evidence_candidate.evidence),
        created_at=frozen_at,
    )


def _normalize_name(value: Any) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2CreationValidationError(
            "name debe ser texto."
        )
    normalized = value.strip()
    if not normalized:
        raise MarketingCampaignV2CreationValidationError(
            "name es obligatorio."
        )
    if len(normalized) > 255:
        raise MarketingCampaignV2CreationValidationError(
            "name no puede exceder 255 caracteres."
        )
    return normalized


def _normalize_purpose(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in _ALLOWED_PURPOSES:
        raise MarketingCampaignV2CreationValidationError(
            "purpose debe ser NEW_SALE, REACTIVATION, ACTIVE_MEMBERS o UNCLASSIFIED."
        )
    return normalized


def _normalize_created_by_user_id(value: Any) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2CreationValidationError(
            "created_by_user_id debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2CreationValidationError(
            "created_by_user_id debe ser entero positivo."
        ) from exc
    if normalized <= 0:
        raise MarketingCampaignV2CreationValidationError(
            "created_by_user_id debe ser entero positivo."
        )
    return normalized


def _normalize_expected_fingerprint(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not _FINGERPRINT_RE.fullmatch(normalized):
        raise MarketingCampaignV2CreationValidationError(
            "expected_preview_fingerprint debe ser SHA-256 hexadecimal."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise MarketingCampaignV2CreationValidationError(
            "now debe incluir zona horaria."
        )
    return current.astimezone(timezone.utc)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _iso_date(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
