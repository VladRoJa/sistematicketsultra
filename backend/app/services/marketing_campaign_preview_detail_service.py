"""Read-only drill-down for the Campaigns V1 audience preview.

The explorer rebuilds the same in-memory plan used by the preview endpoint and
selects one summary bucket from that plan. Explorer filters are applied only
after the bucket has been validated against the preview counter, so filtering
cannot change the meaning of "Cómo se construye la campaña".

This service does not call iVentas live. Message state is read only from the
canonical iVentas run already used by the campaign plan.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.marketing import (
    MarketingIventasContactORM,
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)


BUCKET_TOTAL_CANDIDATES = "TOTAL_CANDIDATES"
BUCKET_EXCLUDED_ACTIVE = "EXCLUDED_ACTIVE"
BUCKET_REVIEW_IDENTITY = "REVIEW_IDENTITY"
BUCKET_EXCLUDED_TARIFF_GENERAL = "EXCLUDED_TARIFF_GENERAL"
BUCKET_DOMICILIATED_FLOW = "DOMICILIATED_FLOW"
BUCKET_BCN_CANDIDATES = "BCN_CANDIDATES"
BUCKET_REVIEW_TARIFF = "REVIEW_TARIFF"
BUCKET_INVALID_PHONE = "INVALID_PHONE"
BUCKET_DUPLICATE_PHONE = "DUPLICATE_PHONE"
BUCKET_ELIGIBLE = "ELIGIBLE"

EXPLORER_SUITE_NEVER = "NEVER"
EXPLORER_SUITE_ONE = "ONE"
EXPLORER_SUITE_TWO_PLUS = "TWO_PLUS"
EXPLORER_IVENTAS_NONE = "NONE"

_BUCKET_LABELS = {
    BUCKET_TOTAL_CANDIDATES: "Candidatos encontrados",
    BUCKET_EXCLUDED_ACTIVE: "Actualmente activos",
    BUCKET_REVIEW_IDENTITY: "Identidad por revisar",
    BUCKET_EXCLUDED_TARIFF_GENERAL: "Excluidos por tarifa",
    BUCKET_DOMICILIATED_FLOW: "Flujo domiciliados",
    BUCKET_BCN_CANDIDATES: "Con adeudo / candidatos BCN",
    BUCKET_REVIEW_TARIFF: "Tarifa por revisar",
    BUCKET_INVALID_PHONE: "Teléfono inválido",
    BUCKET_DUPLICATE_PHONE: "Teléfonos duplicados",
    BUCKET_ELIGIBLE: "Contactos elegibles",
}

_BUCKET_SUMMARY_FIELDS = {
    BUCKET_TOTAL_CANDIDATES: "total_candidates",
    BUCKET_EXCLUDED_ACTIVE: "excluded_active",
    BUCKET_REVIEW_IDENTITY: "review_identity",
    BUCKET_EXCLUDED_TARIFF_GENERAL: "excluded_tariff_general",
    BUCKET_DOMICILIATED_FLOW: "domiciliated_flow",
    BUCKET_BCN_CANDIDATES: "borron_cuenta_nueva",
    BUCKET_REVIEW_TARIFF: "review_tariff",
    BUCKET_INVALID_PHONE: "excluded_invalid_phone",
    BUCKET_DUPLICATE_PHONE: "duplicate_phone",
    BUCKET_ELIGIBLE: "eligible",
}

_EXPLORER_FILTER_FIELDS = frozenset(
    {
        "sucursal",
        "tariff_category",
        "tarifa",
        "adeudo_min",
        "adeudo_max",
        "operational_status",
        "suite_history",
        "iventas_status",
    }
)
_EXPLORER_OPERATIONAL_STATUSES = frozenset(
    {"AVAILABLE", "CONTACTED_THIS_MONTH", "REVIEW_IDENTITY", "ACTIVE", "SIN_ESTADO"}
)
_EXPLORER_SUITE_HISTORY_VALUES = frozenset(
    {EXPLORER_SUITE_NEVER, EXPLORER_SUITE_ONE, EXPLORER_SUITE_TWO_PLUS}
)
_EXPLORER_IVENTAS_STATUSES = frozenset(
    {EXPLORER_IVENTAS_NONE, "SENT", "DELIVERED", "VIEWED", "FAILED"}
)


def build_marketing_campaign_preview_detail(
    *,
    filters: Any,
    bucket: Any,
    page: Any = 1,
    page_size: Any = 50,
    explorer_filters: Any = None,
    date_from: Any = None,
    date_to: Any = None,
    campaign_cooldown_days: int | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return one filtered and paged bucket from the exact preview plan."""

    from app.services import marketing_campaign_audience_service as audience
    from app.services import marketing_reactivation_service as reactivation

    normalized_bucket = _validate_bucket(bucket, reactivation=reactivation)
    normalized_page = _positive_int(
        page,
        field="page",
        maximum=1_000_000,
        reactivation=reactivation,
    )
    normalized_page_size = _positive_int(
        page_size,
        field="page_size",
        maximum=100,
        reactivation=reactivation,
    )
    normalized_explorer_filters = _validate_explorer_filters(
        explorer_filters,
        reactivation=reactivation,
    )

    plan = reactivation._prepare_campaign_plan(
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        campaign_cooldown_days=campaign_cooldown_days,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=session,
        now=now,
    )

    bucket_rows = _select_bucket_rows(
        plan=plan,
        bucket=normalized_bucket,
        audience=audience,
        reactivation=reactivation,
    )

    summary_field = _BUCKET_SUMMARY_FIELDS[normalized_bucket]
    expected_total = int((plan.get("summary") or {}).get(summary_field) or 0)
    if len(bucket_rows) != expected_total:
        raise RuntimeError(
            "El detalle de audiencia no coincide con el contador del preview: "
            f"{normalized_bucket} detalle={len(bucket_rows)} "
            f"preview={expected_total}."
        )

    bucket_total = len(bucket_rows)
    filter_options = _filter_options(bucket_rows)
    base_filtered_rows = _apply_base_explorer_filters(
        bucket_rows,
        filters=normalized_explorer_filters,
    )

    needs_enriched_filtering = bool(
        normalized_explorer_filters.get("suite_history")
        or normalized_explorer_filters.get("iventas_status")
    )
    sources = plan.get("sources") or {}

    if needs_enriched_filtering:
        enriched_candidates = _enrich_page_rows(
            rows=base_filtered_rows,
            sources=sources,
            session=session,
        )
        filtered_rows = _apply_enriched_explorer_filters(
            enriched_candidates,
            filters=normalized_explorer_filters,
        )
        filtered_total = len(filtered_rows)
        _validate_requested_page(
            page=normalized_page,
            page_size=normalized_page_size,
            total=filtered_total,
            reactivation=reactivation,
        )
        start = (normalized_page - 1) * normalized_page_size
        page_rows = filtered_rows[start : start + normalized_page_size]
        summary_rows = filtered_rows
    else:
        filtered_total = len(base_filtered_rows)
        _validate_requested_page(
            page=normalized_page,
            page_size=normalized_page_size,
            total=filtered_total,
            reactivation=reactivation,
        )
        start = (normalized_page - 1) * normalized_page_size
        page_rows = _enrich_page_rows(
            rows=base_filtered_rows[start : start + normalized_page_size],
            sources=sources,
            session=session,
        )
        summary_rows = base_filtered_rows

    total_pages = max(
        1,
        (filtered_total + normalized_page_size - 1) // normalized_page_size,
    )

    return {
        "bucket": normalized_bucket,
        "label": _BUCKET_LABELS[normalized_bucket],
        "sources": sources,
        "total": bucket_total,
        "filtered_total": filtered_total,
        "explorer_filters": _serialize_explorer_filters(
            normalized_explorer_filters
        ),
        "filter_options": filter_options,
        "pagination": {
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": filtered_total,
            "total_pages": total_pages,
            "has_prev": normalized_page > 1,
            "has_next": normalized_page < total_pages,
        },
        "composition": _category_composition(summary_rows),
        "operational_counts": _operational_counts(summary_rows),
        "rows": page_rows,
    }


def _validate_bucket(bucket: Any, *, reactivation: Any) -> str:
    if not isinstance(bucket, str) or bucket not in _BUCKET_LABELS:
        raise reactivation.MarketingReactivationValidationError(
            "bucket no es válido para el visor de audiencia."
        )
    return bucket


def _positive_int(
    value: Any,
    *,
    field: str,
    maximum: int,
    reactivation: Any,
) -> int:
    if isinstance(value, bool):
        raise reactivation.MarketingReactivationValidationError(
            f"{field} debe ser un entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise reactivation.MarketingReactivationValidationError(
            f"{field} debe ser un entero positivo."
        ) from exc
    if normalized < 1 or normalized > maximum:
        raise reactivation.MarketingReactivationValidationError(
            f"{field} debe estar entre 1 y {maximum}."
        )
    return normalized


def _validate_requested_page(*, page: int, page_size: int, total: int, reactivation: Any) -> None:
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages and total > 0:
        raise reactivation.MarketingReactivationValidationError(
            "page está fuera del rango disponible para este detalle."
        )


def _validate_explorer_filters(value: Any, *, reactivation: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise reactivation.MarketingReactivationValidationError(
            "explorer_filters debe ser un objeto JSON."
        )
    unknown = sorted(set(value) - _EXPLORER_FILTER_FIELDS)
    if unknown:
        raise reactivation.MarketingReactivationValidationError(
            "Filtros del visor no permitidos: " + ", ".join(unknown) + "."
        )

    operational_status = _optional_choice(
        value.get("operational_status"),
        field="explorer_filters.operational_status",
        allowed=_EXPLORER_OPERATIONAL_STATUSES,
        reactivation=reactivation,
    )
    suite_history = _optional_choice(
        value.get("suite_history"),
        field="explorer_filters.suite_history",
        allowed=_EXPLORER_SUITE_HISTORY_VALUES,
        reactivation=reactivation,
    )
    iventas_status = _optional_choice(
        value.get("iventas_status"),
        field="explorer_filters.iventas_status",
        allowed=_EXPLORER_IVENTAS_STATUSES,
        reactivation=reactivation,
    )
    debt_min = _optional_decimal(
        value.get("adeudo_min"),
        field="explorer_filters.adeudo_min",
        reactivation=reactivation,
    )
    debt_max = _optional_decimal(
        value.get("adeudo_max"),
        field="explorer_filters.adeudo_max",
        reactivation=reactivation,
    )
    if debt_min is not None and debt_max is not None and debt_min > debt_max:
        raise reactivation.MarketingReactivationValidationError(
            "El adeudo mínimo no puede ser mayor que el adeudo máximo."
        )

    return {
        "sucursal": _optional_text(
            value.get("sucursal"),
            field="explorer_filters.sucursal",
            maximum=255,
            reactivation=reactivation,
        ),
        "tariff_category": _optional_text(
            value.get("tariff_category"),
            field="explorer_filters.tariff_category",
            maximum=100,
            reactivation=reactivation,
        ),
        "tarifa": _optional_text(
            value.get("tarifa"),
            field="explorer_filters.tarifa",
            maximum=255,
            reactivation=reactivation,
        ),
        "adeudo_min": debt_min,
        "adeudo_max": debt_max,
        "operational_status": operational_status,
        "suite_history": suite_history,
        "iventas_status": iventas_status,
    }


def _optional_text(
    value: Any,
    *,
    field: str,
    maximum: int,
    reactivation: Any,
) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise reactivation.MarketingReactivationValidationError(
            f"{field} debe ser texto."
        )
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise reactivation.MarketingReactivationValidationError(
            f"{field} excede {maximum} caracteres."
        )
    return normalized


def _optional_choice(
    value: Any,
    *,
    field: str,
    allowed: frozenset[str],
    reactivation: Any,
) -> str | None:
    normalized = _optional_text(
        value,
        field=field,
        maximum=64,
        reactivation=reactivation,
    )
    if normalized is None:
        return None
    normalized = normalized.upper()
    if normalized not in allowed:
        raise reactivation.MarketingReactivationValidationError(
            f"{field} no es válido."
        )
    return normalized


def _optional_decimal(value: Any, *, field: str, reactivation: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise reactivation.MarketingReactivationValidationError(
            f"{field} debe ser un número válido."
        )
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise reactivation.MarketingReactivationValidationError(
            f"{field} debe ser un número válido."
        ) from exc
    if not normalized.is_finite() or normalized < 0 or normalized > Decimal("1000000000"):
        raise reactivation.MarketingReactivationValidationError(
            f"{field} debe estar entre 0 y 1000000000."
        )
    return normalized


def _serialize_explorer_filters(filters: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in filters.items():
        if value is None:
            continue
        result[key] = str(value) if isinstance(value, Decimal) else value
    return result


def _filter_options(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "branches": sorted(
            {str(row.get("sucursal")) for row in rows if row.get("sucursal")}
        ),
        "tariff_categories": sorted({_category_label(row) for row in rows}),
        "tariffs": sorted({_tariff_label(row) for row in rows}),
        "operational_statuses": sorted(
            {
                str(row.get("operational_status") or "SIN_ESTADO")
                for row in rows
            }
        ),
    }


def _apply_base_explorer_filters(
    rows: list[dict[str, Any]],
    *,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if filters.get("sucursal") and str(row.get("sucursal") or "") != filters["sucursal"]:
            continue
        if filters.get("tariff_category") and _category_label(row) != filters["tariff_category"]:
            continue
        if filters.get("tarifa") and _tariff_label(row) != filters["tarifa"]:
            continue
        if filters.get("operational_status") and str(
            row.get("operational_status") or "SIN_ESTADO"
        ) != filters["operational_status"]:
            continue
        if not _matches_debt(row, filters=filters):
            continue
        result.append(row)
    return result


def _matches_debt(row: dict[str, Any], *, filters: dict[str, Any]) -> bool:
    debt_min = filters.get("adeudo_min")
    debt_max = filters.get("adeudo_max")
    if debt_min is None and debt_max is None:
        return True
    raw = row.get("adeudo")
    if raw is None or raw == "":
        return False
    try:
        debt = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return False
    if not debt.is_finite():
        return False
    if debt_min is not None and debt < debt_min:
        return False
    if debt_max is not None and debt > debt_max:
        return False
    return True


def _apply_enriched_explorer_filters(
    rows: list[dict[str, Any]],
    *,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    suite_history = filters.get("suite_history")
    iventas_status = filters.get("iventas_status")
    for row in rows:
        campaign_count = int(row.get("suite_campaigns_total") or 0)
        if suite_history == EXPLORER_SUITE_NEVER and campaign_count != 0:
            continue
        if suite_history == EXPLORER_SUITE_ONE and campaign_count != 1:
            continue
        if suite_history == EXPLORER_SUITE_TWO_PLUS and campaign_count < 2:
            continue

        observed_status = str(row.get("iventas_last_message_status") or "").strip().upper()
        if iventas_status == EXPLORER_IVENTAS_NONE and observed_status:
            continue
        if iventas_status and iventas_status != EXPLORER_IVENTAS_NONE and observed_status != iventas_status:
            continue
        result.append(row)
    return result


def _select_bucket_rows(
    *,
    plan: dict[str, Any],
    bucket: str,
    audience: Any,
    reactivation: Any,
) -> list[dict[str, Any]]:
    if bucket == BUCKET_ELIGIBLE:
        return list(plan.get("eligible_rows") or [])

    decision_rows = plan.get("decision_rows")
    if decision_rows is None:
        raise reactivation.MarketingReactivationValidationError(
            "En esta primera versión el desglose de etapas aplica a campañas "
            "con universo de vencidos. Contactos elegibles sí puede consultarse."
        )

    rows = list(decision_rows)

    if bucket == BUCKET_TOTAL_CANDIDATES:
        return rows
    if bucket == BUCKET_EXCLUDED_ACTIVE:
        return [
            row
            for row in rows
            if row.get("campaign_eligibility") == "EXCLUDED_ACTIVE"
        ]
    if bucket == BUCKET_REVIEW_IDENTITY:
        return [
            row
            for row in rows
            if row.get("campaign_eligibility") == "REVIEW"
            and row.get("eligibility_reason") == "REVIEW_IDENTITY"
        ]
    if bucket == BUCKET_EXCLUDED_TARIFF_GENERAL:
        return [
            row
            for row in rows
            if row.get("eligibility_reason") == "TARIFF_EXCLUDED"
        ]
    if bucket == BUCKET_DOMICILIATED_FLOW:
        return [
            row
            for row in rows
            if row.get("eligibility_reason") == "TARIFF_DOMICILIATED_FLOW"
        ]
    if bucket == BUCKET_BCN_CANDIDATES:
        return [row for row in rows if audience._is_bcn_base_candidate(row)]
    if bucket == BUCKET_REVIEW_TARIFF:
        return [
            row
            for row in rows
            if row.get("eligibility_reason") == "REVIEW_TARIFF"
        ]
    if bucket == BUCKET_INVALID_PHONE:
        if (plan.get("filters") or {}).get("campaign_type") == "BORRON_CUENTA_NUEVA":
            return [
                row
                for row in rows
                if audience._is_bcn_base_candidate(row)
                and row.get("phone_mx10") is None
            ]
        return [
            row
            for row in rows
            if row.get("campaign_eligibility") == "EXCLUDED_INVALID_PHONE"
        ]
    if bucket == BUCKET_DUPLICATE_PHONE:
        return _duplicate_rows(
            plan=plan,
            decision_rows=rows,
            audience=audience,
        )

    raise AssertionError(f"Bucket sin selector: {bucket}")


def _duplicate_rows(
    *,
    plan: dict[str, Any],
    decision_rows: list[dict[str, Any]],
    audience: Any,
) -> list[dict[str, Any]]:
    is_bcn = (plan.get("filters") or {}).get("campaign_type") == "BORRON_CUENTA_NUEVA"
    candidates = (
        [row for row in decision_rows if audience._is_bcn_base_candidate(row)]
        if is_bcn
        else [
            row
            for row in decision_rows
            if row.get("campaign_eligibility") == "ELIGIBLE"
        ]
    )
    seen: set[str] = set()
    duplicates: list[dict[str, Any]] = []
    for row in candidates:
        phone = row.get("phone_mx10")
        if phone is None:
            continue
        if phone in seen:
            duplicates.append(row)
        else:
            seen.add(phone)
    return duplicates


def _category_label(row: dict[str, Any]) -> str:
    return str(row.get("tarifa_categoria") or "Sin categoría")


def _tariff_label(row: dict[str, Any]) -> str:
    return str(row.get("tarifa") or "Sin tarifa")


def _category_composition(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(_category_label(row) for row in rows)
    total = len(rows)
    return [
        {
            "label": label,
            "count": count,
            "percentage": round((count / total * 100) if total else 0.0, 2),
        }
        for label, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _operational_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(
        Counter(
            str(row.get("operational_status") or "SIN_ESTADO")
            for row in rows
        )
    )


def _enrich_page_rows(
    *,
    rows: list[dict[str, Any]],
    sources: dict[str, Any],
    session: Any,
) -> list[dict[str, Any]]:
    phones = {
        str(row["phone_mx10"])
        for row in rows
        if row.get("phone_mx10")
    }
    suite_history = _suite_history_by_phone(phones=phones, session=session)
    iventas_state = _iventas_state_by_contact(
        rows=rows,
        sync_run_id=sources.get("iventas_sync_run_id"),
        session=session,
    )

    result: list[dict[str, Any]] = []
    for row in rows:
        phone = str(row["phone_mx10"]) if row.get("phone_mx10") else None
        history = suite_history.get(phone or "", {})
        contact_id = row.get("iventas_contact_id")
        state = iventas_state.get(str(contact_id), {}) if contact_id else {}
        result.append(
            {
                "vencido_row_id": row.get("vencido_row_id"),
                "pin": row.get("pin"),
                "nombre": row.get("nombre"),
                "phone_mx10": phone,
                "sucursal": row.get("sucursal"),
                "fecha_vencimiento": row.get("fecha_vencimiento"),
                "tarifa": row.get("tarifa"),
                "tarifa_categoria": row.get("tarifa_categoria"),
                "tarifa_group": row.get("tarifa_group"),
                "adeudo": row.get("adeudo"),
                "operational_status": row.get("operational_status"),
                "campaign_eligibility": row.get("campaign_eligibility"),
                "eligibility_reason": row.get("eligibility_reason"),
                "suite_campaigns_total": int(history.get("campaigns_total") or 0),
                "suite_sent_total": int(history.get("sent_total") or 0),
                "last_suite_exported_at": _iso(history.get("last_exported_at")),
                "last_suite_sent_at": _iso(history.get("last_sent_at")),
                "iventas_contact_id": contact_id,
                "iventas_last_message_status": state.get("last_message_status"),
                "iventas_last_outbound_at_utc": (
                    _iso(state.get("last_outbound_message_at_utc"))
                    or row.get("latest_outbound_at_utc")
                ),
            }
        )
    return result


def _suite_history_by_phone(*, phones: set[str], session: Any) -> dict[str, dict[str, Any]]:
    if not phones:
        return {}
    rows = (
        session.query(
            MarketingReactivationCampaignRecipientORM.phone_mx10,
            MarketingReactivationCampaignORM.id,
            MarketingReactivationCampaignORM.status,
            MarketingReactivationCampaignORM.exported_at,
            MarketingReactivationCampaignORM.sent_at,
        )
        .join(
            MarketingReactivationCampaignORM,
            MarketingReactivationCampaignORM.id
            == MarketingReactivationCampaignRecipientORM.campaign_id,
        )
        .filter(
            MarketingReactivationCampaignRecipientORM.phone_mx10.in_(
                tuple(sorted(phones))
            ),
            MarketingReactivationCampaignORM.status.in_(("EXPORTED", "SENT")),
        )
        .all()
    )
    result: dict[str, dict[str, Any]] = {}
    for phone, campaign_id, status, exported_at, sent_at in rows:
        key = str(phone)
        history = result.setdefault(
            key,
            {
                "campaign_ids": set(),
                "sent_ids": set(),
                "last_exported_at": None,
                "last_sent_at": None,
            },
        )
        history["campaign_ids"].add(int(campaign_id))
        if str(status) == "SENT":
            history["sent_ids"].add(int(campaign_id))
        history["last_exported_at"] = _latest(
            history["last_exported_at"],
            exported_at,
        )
        history["last_sent_at"] = _latest(history["last_sent_at"], sent_at)

    return {
        phone: {
            "campaigns_total": len(history["campaign_ids"]),
            "sent_total": len(history["sent_ids"]),
            "last_exported_at": history["last_exported_at"],
            "last_sent_at": history["last_sent_at"],
        }
        for phone, history in result.items()
    }


def _iventas_state_by_contact(
    *,
    rows: list[dict[str, Any]],
    sync_run_id: Any,
    session: Any,
) -> dict[str, dict[str, Any]]:
    if sync_run_id is None:
        return {}
    contact_ids = {
        str(row["iventas_contact_id"])
        for row in rows
        if row.get("iventas_contact_id")
    }
    if not contact_ids:
        return {}
    contacts = (
        session.query(MarketingIventasContactORM)
        .filter(
            MarketingIventasContactORM.sync_run_id == int(sync_run_id),
            MarketingIventasContactORM.contact_id.in_(tuple(sorted(contact_ids))),
        )
        .all()
    )
    result: dict[str, dict[str, Any]] = {}
    for contact in contacts:
        key = str(contact.contact_id)
        current = result.get(key)
        outbound = contact.last_outbound_message_at_utc
        if current is None or _is_newer(
            outbound,
            current.get("last_outbound_message_at_utc"),
        ):
            result[key] = {
                "last_message_status": contact.last_message_status,
                "last_outbound_message_at_utc": outbound,
            }
    return result


def _is_newer(candidate: Any, current: Any) -> bool:
    if candidate is None:
        return current is None
    if current is None:
        return True
    return candidate > current


def _latest(current: Any, candidate: Any) -> Any:
    if candidate is None:
        return current
    if current is None or candidate > current:
        return candidate
    return current


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
