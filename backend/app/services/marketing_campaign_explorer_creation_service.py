"""Create frozen Marketing campaigns from an Audience Explorer selection.

The browser never supplies recipient ids as authority. The service rebuilds the
same Campaign V1 plan used by preview, reapplies the explorer bucket/filters and
intersects the result with the plan's eligible recipients before persisting.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.models.marketing import (
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)


def build_explorer_campaign_selection(
    *,
    filters: Any,
    bucket: Any,
    explorer_filters: Any = None,
    date_from: Any = None,
    date_to: Any = None,
    campaign_cooldown_days: int | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the final sendable count for one filtered explorer result."""

    prepared = _prepare_explorer_selection(
        filters=filters,
        bucket=bucket,
        explorer_filters=explorer_filters,
        date_from=date_from,
        date_to=date_to,
        campaign_cooldown_days=campaign_cooldown_days,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=session,
        now=now,
    )
    return _serialize_prepared_selection(prepared)


def create_campaign_from_explorer(
    *,
    name: Any,
    filters: Any,
    bucket: Any,
    explorer_filters: Any = None,
    notes: Any = None,
    date_from: Any = None,
    date_to: Any = None,
    created_by_user_id: int,
    campaign_cooldown_days: int | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rebuild, validate and freeze all sendable recipients in the selection."""

    from app.services import marketing_reactivation_service as reactivation

    normalized_name = reactivation._validate_required_text(
        name,
        "name",
        max_length=255,
    )
    normalized_notes = reactivation._validate_optional_text(
        notes,
        "notes",
        max_length=5000,
    )
    now_value = reactivation._validate_now(now)

    prepared = _prepare_explorer_selection(
        filters=filters,
        bucket=bucket,
        explorer_filters=explorer_filters,
        date_from=date_from,
        date_to=date_to,
        campaign_cooldown_days=campaign_cooldown_days,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=session,
        now=now_value,
    )
    selection = _serialize_prepared_selection(prepared)
    final_rows = prepared["final_rows"]

    if not final_rows:
        raise reactivation.MarketingReactivationValidationError(
            "El resultado filtrado no contiene destinatarios elegibles para campaña."
        )
    if selection["weekly_frequency_decision_required"]:
        raise reactivation.MarketingReactivationValidationError(
            "Hay contactos con dos campañas exportadas esta semana. "
            "Elige Retirarlos o Conservarlos en el preview antes de crear la campaña."
        )

    plan = prepared["plan"]
    sources = plan.get("sources") or {}
    campaign = MarketingReactivationCampaignORM(
        name=normalized_name,
        status=reactivation.CAMPAIGN_STATUS_DRAFT,
        date_from=date.fromisoformat(str(sources["date_from"])),
        date_to=date.fromisoformat(str(sources["date_to"])),
        created_by_user_id=int(created_by_user_id),
        created_at=now_value,
        updated_at=now_value,
        notes=normalized_notes,
        filters_json={
            **(
                {"campaign_type": plan["filters"]["campaign_type"]}
                if "campaign_type" in (plan.get("filters") or {})
                else {}
            ),
            "filters": plan.get("filters") or {},
            "sources": sources,
            "summary": plan.get("summary") or {},
            "scope": plan.get(
                "scope",
                reactivation._serialize_campaign_scope(allowed_sucursal_keys),
            ),
            "audience_explorer": {
                "bucket": prepared["bucket"],
                "explorer_filters": prepared["serialized_explorer_filters"],
                "bucket_total": prepared["bucket_total"],
                "filtered_total": prepared["filtered_total"],
                "selection": selection,
            },
        },
        recipient_count=len(final_rows),
    )

    try:
        session.add(campaign)
        session.flush()
        for row in final_rows:
            session.add(
                MarketingReactivationCampaignRecipientORM(
                    campaign_id=int(campaign.id),
                    socios_vencidos_cartera_id=(
                        int(row["vencido_row_id"])
                        if row.get("vencido_row_id") is not None
                        else None
                    ),
                    phone_mx10=str(row["phone_mx10"]),
                    member_name=row.get("nombre"),
                    sucursal=str(row.get("sucursal") or ""),
                    fecha_vencimiento_date=(
                        date.fromisoformat(str(row["fecha_vencimiento"]))
                        if row.get("fecha_vencimiento") is not None
                        else None
                    ),
                    tarifa=row.get("tarifa"),
                    inclusion_status=reactivation.ELIGIBILITY_ELIGIBLE,
                    exclusion_reason=None,
                    operational_status=str(
                        row.get("operational_status")
                        or reactivation.OPERATIONAL_AVAILABLE
                    ),
                    operational_reason=str(
                        row.get("reason")
                        or row.get("eligibility_reason")
                        or "AUDIENCE_EXPLORER"
                    ),
                    created_at=now_value,
                )
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise reactivation.MarketingReactivationConflictError(
            "Conflicto al guardar destinatarios únicos de la campaña."
        ) from exc
    except Exception:
        session.rollback()
        raise

    return {
        "campaign": reactivation.serialize_marketing_reactivation_campaign(campaign),
        "selection": selection,
    }


def _prepare_explorer_selection(
    *,
    filters: Any,
    bucket: Any,
    explorer_filters: Any,
    date_from: Any,
    date_to: Any,
    campaign_cooldown_days: int | None,
    allowed_sucursal_keys: tuple[str, ...] | None,
    session: Any,
    now: datetime | None,
) -> dict[str, Any]:
    from app.services import marketing_campaign_audience_service as audience
    from app.services import marketing_campaign_preview_detail_service as detail
    from app.services import marketing_reactivation_service as reactivation

    now_value = reactivation._validate_now(now)
    normalized_bucket = detail._validate_bucket(
        bucket,
        reactivation=reactivation,
    )
    normalized_explorer_filters = detail._validate_explorer_filters(
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
        now=now_value,
    )
    bucket_rows = detail._select_bucket_rows(
        plan=plan,
        bucket=normalized_bucket,
        audience=audience,
        reactivation=reactivation,
    )
    summary_field = detail._BUCKET_SUMMARY_FIELDS[normalized_bucket]
    expected_total = int((plan.get("summary") or {}).get(summary_field) or 0)
    if len(bucket_rows) != expected_total:
        raise RuntimeError(
            "El detalle de audiencia no coincide con el contador del preview: "
            f"{normalized_bucket} detalle={len(bucket_rows)} preview={expected_total}."
        )

    filtered_rows = detail._apply_base_explorer_filters(
        bucket_rows,
        filters=normalized_explorer_filters,
    )
    if (
        normalized_explorer_filters.get("suite_history")
        or normalized_explorer_filters.get("iventas_status")
    ):
        enriched_rows = detail._enrich_rows_for_filtering(
            rows=filtered_rows,
            sources=plan.get("sources") or {},
            session=session,
        )
        matched_enriched = detail._apply_enriched_explorer_filters(
            enriched_rows,
            filters=normalized_explorer_filters,
        )
        matched_keys = Counter(_row_identity(row) for row in matched_enriched)
        matched_raw: list[dict[str, Any]] = []
        for row in filtered_rows:
            key = _row_identity(row)
            if matched_keys[key] <= 0:
                continue
            matched_keys[key] -= 1
            matched_raw.append(row)
        filtered_rows = matched_raw

    valid_rows = [row for row in filtered_rows if row.get("phone_mx10")]
    selected_phones: list[str] = []
    seen_phones: set[str] = set()
    for row in valid_rows:
        phone = str(row["phone_mx10"])
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        selected_phones.append(phone)

    eligible_by_phone = {
        str(row["phone_mx10"]): row
        for row in plan.get("eligible_rows") or []
        if row.get("phone_mx10")
    }
    final_rows = [
        eligible_by_phone[phone]
        for phone in selected_phones
        if phone in eligible_by_phone
    ]

    weekly_action = (plan.get("filters") or {}).get("weekly_frequency_action")
    weekly_limit_contacts = 0
    if weekly_action is None and final_rows:
        weekly_counts = audience.exported_counts(
            {str(row["phone_mx10"]) for row in final_rows},
            session=session,
            now=now_value,
        )
        weekly_limit_contacts = sum(
            1
            for row in final_rows
            if int(weekly_counts.get(str(row["phone_mx10"]), 0)) >= 2
        )

    return {
        "bucket": normalized_bucket,
        "label": detail._BUCKET_LABELS[normalized_bucket],
        "plan": plan,
        "bucket_total": expected_total,
        "filtered_total": len(filtered_rows),
        "valid_phone_rows": len(valid_rows),
        "unique_valid_contacts": len(selected_phones),
        "duplicate_phone_rows": len(valid_rows) - len(selected_phones),
        "excluded_by_campaign_rules": len(selected_phones) - len(final_rows),
        "weekly_limit_contacts": weekly_limit_contacts,
        "weekly_frequency_decision_required": weekly_limit_contacts > 0,
        "final_rows": final_rows,
        "serialized_explorer_filters": detail._serialize_explorer_filters(
            normalized_explorer_filters
        ),
    }


def _serialize_prepared_selection(prepared: dict[str, Any]) -> dict[str, Any]:
    return {
        "bucket": prepared["bucket"],
        "label": prepared["label"],
        "bucket_total": int(prepared["bucket_total"]),
        "filtered_total": int(prepared["filtered_total"]),
        "valid_phone_rows": int(prepared["valid_phone_rows"]),
        "unique_valid_contacts": int(prepared["unique_valid_contacts"]),
        "duplicate_phone_rows": int(prepared["duplicate_phone_rows"]),
        "excluded_by_campaign_rules": int(prepared["excluded_by_campaign_rules"]),
        "weekly_limit_contacts": int(prepared["weekly_limit_contacts"]),
        "weekly_frequency_decision_required": bool(
            prepared["weekly_frequency_decision_required"]
        ),
        "recipient_count": len(prepared["final_rows"]),
        "can_create": bool(prepared["final_rows"])
        and not prepared["weekly_frequency_decision_required"],
        "explorer_filters": dict(prepared["serialized_explorer_filters"]),
    }


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    row_id = row.get("vencido_row_id")
    if row_id is not None:
        return ("ROW", str(row_id))
    return ("PHONE", str(row.get("phone_mx10") or ""))
