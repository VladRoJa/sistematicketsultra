from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2TariffORM,
    MarketingCampaignV2TariffOverrideORM,
)
from app.services import marketing_campaign_v2_audience_service as audience
from app.services.marketing_tariff_normalization import normalize_marketing_tariff_key


AUDIENCE_FAMILIES = (
    "DOMICILIADO",
    "TRIMESTRAL",
    "CONVENIO",
    "SEMESTRE",
    "ESTUDIANTE",
    "MES",
    "OUT_OF_SEGMENT",
)


class MarketingCampaignV2TariffClassifierError(RuntimeError):
    """Base para errores del catalogador V2."""


class MarketingCampaignV2TariffClassifierValidationError(
    MarketingCampaignV2TariffClassifierError,
    ValueError,
):
    """Entrada inválida del catalogador."""


class MarketingCampaignV2TariffClassifierPersistenceError(
    MarketingCampaignV2TariffClassifierError,
):
    """No fue posible persistir una clasificación V2."""


def list_unclassified_tariffs(
    *,
    source: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expiration_date_from: Any = None,
    expiration_date_to: Any = None,
    session: Any | None = None,
) -> dict[str, Any]:
    """Agrupa tarifas efectivamente no clasificadas por tarifa_key."""

    active_session = session if session is not None else db.session
    normalized_source = audience._normalize_source(source)
    normalized_scope = audience._normalize_scope(allowed_sucursal_keys)

    if normalized_source == audience.SOURCE_EXPIRED_MEMBERS:
        date_from = audience._ensure_date(
            expiration_date_from,
            field_name="expiration_date_from",
        )
        date_to = audience._ensure_date(
            expiration_date_to,
            field_name="expiration_date_to",
        )
        if date_from > date_to:
            raise MarketingCampaignV2TariffClassifierValidationError(
                "expiration_date_from no puede ser posterior a expiration_date_to."
            )
        source_result = audience._load_expired_source(
            date_from=date_from,
            date_to=date_to,
            allowed_sucursal_keys=normalized_scope,
            session=active_session,
        )
        filters = {
            "source": normalized_source,
            "expiration_date_from": date_from.isoformat(),
            "expiration_date_to": date_to.isoformat(),
        }
    else:
        if expiration_date_from is not None or expiration_date_to is not None:
            raise MarketingCampaignV2TariffClassifierValidationError(
                "Los filtros de vencimiento sólo aplican a EXPIRED_MEMBERS."
            )
        source_result = audience._load_active_source(
            allowed_sucursal_keys=normalized_scope,
            session=active_session,
        )
        filters = {"source": normalized_source}

    effective_catalog = audience._read_v2_tariff_catalog(session=active_session)
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"row_count": 0, "raw_values": set()}
    )
    unkeyed_row_count = 0

    for candidate in source_result.candidates:
        tarifa_key = normalize_marketing_tariff_key(candidate.tarifa_raw)
        if tarifa_key is None:
            unkeyed_row_count += 1
            continue
        if tarifa_key in effective_catalog:
            continue
        bucket = grouped[tarifa_key]
        bucket["row_count"] += 1
        if candidate.tarifa_raw is not None:
            bucket["raw_values"].add(str(candidate.tarifa_raw))

    rows = []
    for tarifa_key, bucket in grouped.items():
        raw_values = sorted(
            bucket["raw_values"],
            key=lambda value: (value.casefold(), value),
        )
        rows.append(
            {
                "tarifa_raw": raw_values[0] if raw_values else tarifa_key,
                "tarifa_key": tarifa_key,
                "source": normalized_source,
                "row_count": int(bucket["row_count"]),
            }
        )

    rows.sort(key=lambda row: (-int(row["row_count"]), str(row["tarifa_key"])))
    total_classifiable_rows = sum(int(row["row_count"]) for row in rows)
    return {
        "source": normalized_source,
        "source_metadata": dict(source_result.metadata),
        "filters": filters,
        "total_unique_tariffs": len(rows),
        "total_unclassified_rows": total_classifiable_rows + unkeyed_row_count,
        "unkeyed_row_count": unkeyed_row_count,
        "rows": rows,
    }


def upsert_tariff_classification(
    *,
    tarifa_key: Any,
    categoria_tarifa: Any,
    audience_family: Any,
    user_id: Any,
    representative_raw: Any = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_key = normalize_marketing_tariff_key(tarifa_key)
    if normalized_key is None:
        raise MarketingCampaignV2TariffClassifierValidationError(
            "tarifa_key es obligatorio."
        )
    normalized_category = _required_text(
        categoria_tarifa,
        field_name="categoria_tarifa",
        maximum=100,
    )
    normalized_family = str(audience_family or "").strip().upper()
    if normalized_family not in AUDIENCE_FAMILIES:
        raise MarketingCampaignV2TariffClassifierValidationError(
            "audience_family no es válida para Campaign V2."
        )
    normalized_user_id = _positive_int(user_id, field_name="user_id")
    timestamp = _normalize_now(now)

    override = (
        active_session.query(MarketingCampaignV2TariffOverrideORM)
        .filter(MarketingCampaignV2TariffOverrideORM.tarifa_key == normalized_key)
        .first()
    )
    created = override is None
    if override is None:
        raw = _optional_text(representative_raw)
        if raw is None:
            baseline = (
                active_session.query(MarketingCampaignV2TariffORM)
                .filter(MarketingCampaignV2TariffORM.tarifa_key == normalized_key)
                .first()
            )
            raw = (
                str(baseline.tarifa_raw)
                if baseline is not None
                else normalized_key
            )
        override = MarketingCampaignV2TariffOverrideORM(
            tarifa_key=normalized_key,
            tarifa_raw=raw,
            categoria_tarifa=normalized_category,
            audience_family=normalized_family,
            created_by_user_id=normalized_user_id,
            updated_by_user_id=normalized_user_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        active_session.add(override)
    else:
        override.categoria_tarifa = normalized_category
        override.audience_family = normalized_family
        override.updated_by_user_id = normalized_user_id
        override.updated_at = timestamp
        raw = _optional_text(representative_raw)
        if raw is not None:
            override.tarifa_raw = raw

    try:
        active_session.flush()
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingCampaignV2TariffClassifierPersistenceError(
            "Conflicto de integridad al guardar clasificación de tarifa V2."
        ) from exc
    except SQLAlchemyError as exc:
        active_session.rollback()
        raise MarketingCampaignV2TariffClassifierPersistenceError(
            "No fue posible guardar clasificación de tarifa V2."
        ) from exc

    return {
        "id": int(override.id),
        "tarifa_key": override.tarifa_key,
        "tarifa_raw": override.tarifa_raw,
        "categoria_tarifa": override.categoria_tarifa,
        "audience_family": override.audience_family,
        "created_by_user_id": override.created_by_user_id,
        "updated_by_user_id": override.updated_by_user_id,
        "created_at": _iso_datetime(override.created_at),
        "updated_at": _iso_datetime(override.updated_at),
        "created": created,
    }


def stable_representative_for_key(
    *,
    tarifa_key: Any,
    source: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expiration_date_from: Any = None,
    expiration_date_to: Any = None,
    session: Any | None = None,
) -> str | None:
    normalized_key = normalize_marketing_tariff_key(tarifa_key)
    if normalized_key is None:
        return None
    result = list_unclassified_tariffs(
        source=source,
        allowed_sucursal_keys=allowed_sucursal_keys,
        expiration_date_from=expiration_date_from,
        expiration_date_to=expiration_date_to,
        session=session,
    )
    for row in result["rows"]:
        if row["tarifa_key"] == normalized_key:
            return str(row["tarifa_raw"])
    return None


def _required_text(value: Any, *, field_name: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MarketingCampaignV2TariffClassifierValidationError(
            f"{field_name} es obligatorio."
        )
    if len(normalized) > maximum:
        raise MarketingCampaignV2TariffClassifierValidationError(
            f"{field_name} excede {maximum} caracteres."
        )
    return normalized


def _positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2TariffClassifierValidationError(
            f"{field_name} debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2TariffClassifierValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized <= 0:
        raise MarketingCampaignV2TariffClassifierValidationError(
            f"{field_name} debe ser entero positivo."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise MarketingCampaignV2TariffClassifierValidationError(
            "now debe incluir zona horaria."
        )
    return current.astimezone(timezone.utc)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _iso_datetime(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
