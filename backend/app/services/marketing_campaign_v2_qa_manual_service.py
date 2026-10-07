"QA-only frozen Campaign V2 creation for controlled provider smoke tests."

from __future__ import annotations

from datetime import datetime, timezone
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
from app.models.warehouse import TrackBranchCatalogORM
from app.services.marketing_phone import normalize_phone


SOURCE_QA_MANUAL = "QA_MANUAL"
QA_FINGERPRINT_VERSION = "campaign-v2-qa-manual-v1"
MAX_QA_RECIPIENTS = 10
_ALLOWED_PURPOSES = frozenset(
    {"NEW_SALE", "REACTIVATION", "ACTIVE_MEMBERS", "UNCLASSIFIED"}
)
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class MarketingCampaignV2QAManualError(RuntimeError):
    pass


class MarketingCampaignV2QAManualValidationError(
    MarketingCampaignV2QAManualError,
    ValueError,
):
    pass


class MarketingCampaignV2QAManualConflictError(MarketingCampaignV2QAManualError):
    pass


class MarketingCampaignV2QAManualPersistenceError(MarketingCampaignV2QAManualError):
    pass


def build_campaign_v2_qa_manual_preview(
    *,
    name: Any,
    purpose: Any,
    sucursal_id: Any,
    recipients: Any,
    session: Any | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_name = _normalize_name(name)
    normalized_purpose = _normalize_purpose(purpose)
    normalized_sucursal_id = _positive_int(sucursal_id, "sucursal_id")
    branch = _resolve_branch(
        sucursal_id=normalized_sucursal_id,
        session=active_session,
    )
    normalized_recipients = _normalize_recipients(recipients)

    fingerprint_payload = {
        "version": QA_FINGERPRINT_VERSION,
        "name": normalized_name,
        "purpose": normalized_purpose,
        "source": SOURCE_QA_MANUAL,
        "branch": branch,
        "recipients": [
            {
                "phone_mx10": row["phone_mx10"],
                "name": row["name"],
            }
            for row in normalized_recipients
        ],
    }
    encoded = json.dumps(
        fingerprint_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fingerprint = hashlib.sha256(encoded).hexdigest()

    return {
        "name": normalized_name,
        "purpose": normalized_purpose,
        "source": SOURCE_QA_MANUAL,
        "sucursal_id": branch["sucursal_id"],
        "sucursal_canon": branch["sucursal_canon"],
        "track_label": branch["track_label"],
        "recipient_count": len(normalized_recipients),
        "recipients": [
            {
                "name": row["name"],
                "phone_mx10": row["phone_mx10"],
            }
            for row in normalized_recipients
        ],
        "preview_fingerprint_version": QA_FINGERPRINT_VERSION,
        "preview_fingerprint": fingerprint,
    }


def freeze_campaign_v2_qa_manual(
    *,
    name: Any,
    purpose: Any,
    sucursal_id: Any,
    recipients: Any,
    expected_preview_fingerprint: Any,
    created_by_user_id: Any,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    preview = build_campaign_v2_qa_manual_preview(
        name=name,
        purpose=purpose,
        sucursal_id=sucursal_id,
        recipients=recipients,
        session=active_session,
    )
    expected = _normalize_expected_fingerprint(expected_preview_fingerprint)
    if preview["preview_fingerprint"] != expected:
        raise MarketingCampaignV2QAManualConflictError(
            "El Preview QA cambió; vuelve a generar Preview antes de congelar."
        )

    actor_user_id = _positive_int(created_by_user_id, "created_by_user_id")
    frozen_at = _normalize_now(now)

    existing = (
        active_session.query(MarketingCampaignV2ORM)
        .filter(
            MarketingCampaignV2ORM.name == preview["name"],
            MarketingCampaignV2ORM.source == SOURCE_QA_MANUAL,
        )
        .first()
    )
    if existing is not None:
        raise MarketingCampaignV2QAManualConflictError(
            "Ya existe una Campaign V2 QA_MANUAL con ese nombre."
        )

    normalized_recipients = _normalize_recipients(recipients)
    campaign = MarketingCampaignV2ORM(
        name=preview["name"],
        purpose=preview["purpose"],
        source=SOURCE_QA_MANUAL,
        audience_definition_json={
            "schema_version": 1,
            "filters": {
                "source": SOURCE_QA_MANUAL,
                "allowed_sucursal_keys": [preview["sucursal_canon"]],
                "sucursal_id": preview["sucursal_id"],
            },
            "source_metadata": {
                "qa_manual": True,
                "sucursal_canon": preview["sucursal_canon"],
                "track_label": preview["track_label"],
            },
            "preview": {
                "fingerprint_version": QA_FINGERPRINT_VERSION,
                "fingerprint": preview["preview_fingerprint"],
                "summary": {
                    "source": SOURCE_QA_MANUAL,
                    "universe_count": preview["recipient_count"],
                    "scoped_count": preview["recipient_count"],
                    "unique_recipient_count": preview["recipient_count"],
                    "invalid_phone_count": 0,
                    "duplicate_count": 0,
                    "blacklist_excluded_count": 0,
                },
            },
        },
        created_by_user_id=actor_user_id,
        frozen_at=frozen_at,
        created_at=frozen_at,
        updated_at=frozen_at,
    )

    for row in normalized_recipients:
        recipient = MarketingCampaignV2RecipientORM(
            phone_mx10=row["phone_mx10"],
            source=SOURCE_QA_MANUAL,
            member_name=row["name"],
            sucursal=preview["track_label"],
            inclusion_reason="QA_MANUAL_SMOKE",
            conflict_fields_json=[],
            created_at=frozen_at,
        )
        recipient.evidence_rows.append(
            MarketingCampaignV2RecipientEvidenceORM(
                evidence_order=0,
                source=SOURCE_QA_MANUAL,
                phone_raw=row["phone_raw"],
                phone_mx10=row["phone_mx10"],
                member_name=row["name"],
                sucursal=preview["track_label"],
                sucursal_key=preview["sucursal_canon"],
                evidence_json=["QA_MANUAL_SMOKE"],
                created_at=frozen_at,
            )
        )
        campaign.recipients.append(recipient)

    try:
        active_session.add(campaign)
        active_session.flush()
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingCampaignV2QAManualPersistenceError(
            "Conflicto de integridad al congelar Campaign V2 QA."
        ) from exc
    except SQLAlchemyError as exc:
        active_session.rollback()
        raise MarketingCampaignV2QAManualPersistenceError(
            "Error de persistencia al congelar Campaign V2 QA."
        ) from exc
    except Exception:
        active_session.rollback()
        raise

    return {
        "campaign_id": int(campaign.id),
        "name": campaign.name,
        "purpose": campaign.purpose,
        "source": campaign.source,
        "sucursal_id": preview["sucursal_id"],
        "sucursal_canon": preview["sucursal_canon"],
        "recipient_count": len(normalized_recipients),
        "frozen_at": _iso_datetime(campaign.frozen_at),
        "preview_fingerprint_version": QA_FINGERPRINT_VERSION,
        "preview_fingerprint": preview["preview_fingerprint"],
    }


def _resolve_branch(*, sucursal_id: int, session: Any) -> dict[str, Any]:
    rows = (
        session.query(TrackBranchCatalogORM)
        .filter(
            TrackBranchCatalogORM.sucursal_id == sucursal_id,
            TrackBranchCatalogORM.is_track_active.is_(True),
        )
        .all()
    )
    if len(rows) != 1:
        raise MarketingCampaignV2QAManualValidationError(
            "La sucursal QA debe tener una identidad Track activa y única."
        )
    row = rows[0]
    return {
        "sucursal_id": int(row.sucursal_id),
        "sucursal_canon": str(row.sucursal_canon),
        "track_label": str(row.track_label),
    }


def _normalize_recipients(value: Any) -> tuple[dict[str, str], ...]:
    if isinstance(value, (str, bytes)) or value is None:
        raise MarketingCampaignV2QAManualValidationError(
            "recipients debe ser una lista."
        )
    try:
        rows = list(value)
    except TypeError as exc:
        raise MarketingCampaignV2QAManualValidationError(
            "recipients debe ser una lista."
        ) from exc

    if not rows:
        raise MarketingCampaignV2QAManualValidationError(
            "recipients debe contener al menos un destinatario."
        )
    if len(rows) > MAX_QA_RECIPIENTS:
        raise MarketingCampaignV2QAManualValidationError(
            f"QA_MANUAL admite máximo {MAX_QA_RECIPIENTS} destinatarios."
        )

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            raise MarketingCampaignV2QAManualValidationError(
                f"recipient {index} debe ser objeto."
            )
        phone_raw = str(raw.get("phone") or "").strip()
        phone_mx10 = normalize_phone(phone_raw)
        if phone_mx10 is None:
            raise MarketingCampaignV2QAManualValidationError(
                f"recipient {index} tiene teléfono inválido."
            )
        if phone_mx10 in seen:
            raise MarketingCampaignV2QAManualValidationError(
                f"Teléfono duplicado en QA_MANUAL: {phone_mx10}."
            )
        seen.add(phone_mx10)

        name = str(raw.get("name") or "").strip()
        if len(name) > 255:
            raise MarketingCampaignV2QAManualValidationError(
                f"recipient {index} excede 255 caracteres en name."
            )
        normalized.append(
            {
                "phone_raw": phone_raw,
                "phone_mx10": phone_mx10,
                "name": name,
            }
        )

    return tuple(sorted(normalized, key=lambda row: row["phone_mx10"]))


def _normalize_name(value: Any) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2QAManualValidationError("name debe ser texto.")
    normalized = value.strip()
    if not normalized:
        raise MarketingCampaignV2QAManualValidationError("name es obligatorio.")
    if len(normalized) > 255:
        raise MarketingCampaignV2QAManualValidationError(
            "name no puede exceder 255 caracteres."
        )
    return normalized


def _normalize_purpose(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in _ALLOWED_PURPOSES:
        raise MarketingCampaignV2QAManualValidationError(
            "purpose no soportado para Campaign V2 QA."
        )
    return normalized


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2QAManualValidationError(
            f"{field_name} debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2QAManualValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized <= 0:
        raise MarketingCampaignV2QAManualValidationError(
            f"{field_name} debe ser entero positivo."
        )
    return normalized


def _normalize_expected_fingerprint(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not _FINGERPRINT_RE.fullmatch(normalized):
        raise MarketingCampaignV2QAManualValidationError(
            "expected_preview_fingerprint debe ser SHA-256 hexadecimal."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
