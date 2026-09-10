"""Read-only drill-down for the Campaigns V1 audience preview.

The explorer intentionally rebuilds the same frozen-in-memory plan used by the
preview endpoint and then selects one summary bucket from that plan. This keeps
row detail aligned with the numbers shown in "Cómo se construye la campaña".

This service does not call iVentas live. Message state is read only from the
canonical iVentas run already used by the campaign plan.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
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


def build_marketing_campaign_preview_detail(
    *,
    filters: Any,
    bucket: Any,
    page: Any = 1,
    page_size: Any = 50,
    date_from: Any = None,
    date_to: Any = None,
    campaign_cooldown_days: int | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return one paged bucket from the exact campaign preview plan."""

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

    total = len(bucket_rows)
    total_pages = max(1, (total + normalized_page_size - 1) // normalized_page_size)
    if normalized_page > total_pages and total > 0:
        raise reactivation.MarketingReactivationValidationError(
            "page está fuera del rango disponible para este detalle."
        )

    start = (normalized_page - 1) * normalized_page_size
    page_rows = bucket_rows[start : start + normalized_page_size]
    enriched_rows = _enrich_page_rows(
        rows=page_rows,
        sources=plan.get("sources") or {},
        session=session,
    )

    return {
        "bucket": normalized_bucket,
        "label": _BUCKET_LABELS[normalized_bucket],
        "sources": plan.get("sources") or {},
        "total": total,
        "pagination": {
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": normalized_page > 1,
            "has_next": normalized_page < total_pages,
        },
        "composition": _category_composition(bucket_rows),
        "operational_counts": dict(
            Counter(
                str(row.get("operational_status") or "SIN_ESTADO")
                for row in bucket_rows
            )
        ),
        "rows": enriched_rows,
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


def _category_composition(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        str(row.get("tarifa_categoria") or "Sin categoría")
        for row in rows
    )
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
