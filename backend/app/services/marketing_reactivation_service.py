"""Operación de cartera y campañas para Reactivación de Marketing.

La evidencia CRM y el estado operativo siguen viniendo de los resolvers
existentes. Esta capa añade una elegibilidad separada, auditable y común
para preview, creación y revalidación previa a exportar.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from typing import Any
import unicodedata

from openpyxl import Workbook
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    MarketingIventasSyncRunORM,
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
    MarketingReactivationTariffORM,
)
from app.models.warehouse import SociosVencidosCarteraORM
from app.services.marketing_iventas_service import normalize_iventas_phone
from app.warehouse.services.socios_vencidos_reactivation_candidate_resolver import (
    SociosVencidosReactivationCandidateResolverError,
    resolve_socios_vencidos_reactivation_candidates_for_period,
)


CAMPAIGN_STATUS_DRAFT = "DRAFT"
CAMPAIGN_STATUS_EXPORTED = "EXPORTED"
CAMPAIGN_STATUS_SENT = "SENT"
CAMPAIGN_STATUS_CANCELLED = "CANCELLED"

ELIGIBILITY_ELIGIBLE = "ELIGIBLE"
ELIGIBILITY_EXCLUDED_ACTIVE = "EXCLUDED_ACTIVE"
ELIGIBILITY_EXCLUDED_INVALID_PHONE = "EXCLUDED_INVALID_PHONE"
ELIGIBILITY_EXCLUDED_TARIFF = "EXCLUDED_TARIFF"
ELIGIBILITY_EXCLUDED_RECENT_CAMPAIGN = "EXCLUDED_RECENT_CAMPAIGN"
ELIGIBILITY_REVIEW = "REVIEW"

REASON_REVIEW_IDENTITY = "REVIEW_IDENTITY"
REASON_REVIEW_DUPLICATE_PHONE = "REVIEW_DUPLICATE_PHONE"
REASON_REVIEW_TARIFF = "REVIEW_TARIFF"
REASON_INVALID_PHONE = "INVALID_PHONE"
REASON_RECENT_SUITE_CAMPAIGN = "RECENT_SUITE_CAMPAIGN"
REASON_TARIFF_EXCLUDED = "TARIFF_EXCLUDED"
REASON_TARIFF_DOMICILIATED_FLOW = "TARIFF_DOMICILIATED_FLOW"

TARIFF_GROUP_REACTIVATE = "REACTIVATE"
TARIFF_GROUP_DOMICILIATED_FLOW = "DOMICILIATED_FLOW"
TARIFF_GROUP_EXCLUDE = "EXCLUDE"
TARIFF_GROUP_REVIEW = "REVIEW"

OPERATIONAL_NO_CONTACT_IN_PERIOD = "NO_CONTACT_IN_PERIOD"
OPERATIONAL_NO_OUTBOUND_MESSAGE = "NO_OUTBOUND_MESSAGE"
OPERATIONAL_CONTACTED_BEFORE_EXPIRATION = "CONTACTED_BEFORE_EXPIRATION"
OPERATIONAL_CONTACTED_AFTER_EXPIRATION = "CONTACTED_AFTER_EXPIRATION"
OPERATIONAL_REVIEW_IDENTITY = "REVIEW_IDENTITY"
OPERATIONAL_ACTIVE = "ACTIVE"

FILTER_WORK_PENDING = "WORK_PENDING"
FILTER_ALL = "ALL"

_OPERATIONAL_FILTERS = frozenset(
    {
        FILTER_WORK_PENDING,
        FILTER_ALL,
        OPERATIONAL_NO_CONTACT_IN_PERIOD,
        OPERATIONAL_NO_OUTBOUND_MESSAGE,
        OPERATIONAL_CONTACTED_BEFORE_EXPIRATION,
        OPERATIONAL_CONTACTED_AFTER_EXPIRATION,
        OPERATIONAL_REVIEW_IDENTITY,
        OPERATIONAL_ACTIVE,
    }
)
_IDENTITY_REASONS = frozenset(
    {
        "ACTIVE_REVIEW",
        "AMBIGUOUS",
        "IDENTIFIER_CONFLICT",
        "AMBIGUOUS_IVENTAS_IDENTITY",
    }
)
_ALLOWED_CAMPAIGN_FILTERS = frozenset(
    {
        "iventas_period_key",
        "sucursal",
        "operational_status",
        "search",
        "tarifa",
        "campaign_cooldown_days",
    }
)


class MarketingReactivationValidationError(ValueError):
    pass


class MarketingReactivationNotFoundError(LookupError):
    pass


class MarketingReactivationConflictError(RuntimeError):
    pass


class MarketingReactivationInvalidTransitionError(RuntimeError):
    pass


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_marketing_reactivation_sources(
    *,
    session: Any | None = None,
) -> dict[str, object]:
    """Lista cobertura de cartera y runs iVentas canónicos disponibles."""

    active_session = _session_or_default(session)
    coverage = active_session.query(
        func.min(SociosVencidosCarteraORM.fecha_vencimiento_date),
        func.max(SociosVencidosCarteraORM.fecha_vencimiento_date),
        func.count(SociosVencidosCarteraORM.id),
    ).one()
    iventas_runs = (
        active_session.query(MarketingIventasSyncRunORM)
        .filter(
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasSyncRunORM.is_canonical.is_(True),
        )
        .order_by(
            MarketingIventasSyncRunORM.date_to.desc(),
            MarketingIventasSyncRunORM.id.desc(),
        )
        .all()
    )
    return {
        "vencidos_coverage": {
            "min_date": (
                _serialize_date(coverage[0]) if coverage[0] is not None else None
            ),
            "max_date": (
                _serialize_date(coverage[1]) if coverage[1] is not None else None
            ),
            "total_rows": int(coverage[2] or 0),
        },
        "iventas_periods": [
            {
                "period_key": str(run.period_key),
                "sync_run_id": int(run.id),
                "date_from": _serialize_date(run.date_from),
                "date_to": _serialize_date(run.date_to),
                "contacts_unique": int(run.contacts_unique),
            }
            for run in iventas_runs
        ],
    }


def list_marketing_reactivation_tariffs(
    *,
    date_from: date | str,
    date_to: date | str,
    session: Any | None = None,
) -> dict[str, object]:
    normalized_from, normalized_to = _validate_date_range(date_from, date_to)
    active_session = _session_or_default(session)
    rows = (
        active_session.query(
            SociosVencidosCarteraORM.tarifa,
            func.count(SociosVencidosCarteraORM.id),
        )
        .filter(
            SociosVencidosCarteraORM.fecha_vencimiento_date.between(
                normalized_from,
                normalized_to,
            )
        )
        .group_by(SociosVencidosCarteraORM.tarifa)
        .order_by(SociosVencidosCarteraORM.tarifa.asc().nullslast())
        .all()
    )
    catalog = _read_active_tariff_catalog(
        tariff_values=(tarifa for tarifa, _ in rows),
        session=active_session,
    )
    return {
        "date_from": normalized_from.isoformat(),
        "date_to": normalized_to.isoformat(),
        "rows": [
            {
                "tarifa": tarifa,
                "count": int(count_value),
                **_serialize_tariff_classification(
                    catalog.get(normalize_reactivation_tariff_key(tarifa))
                ),
            }
            for tarifa, count_value in rows
        ],
    }


def build_marketing_reactivation_candidates(
    *,
    date_from: date | str,
    date_to: date | str,
    iventas_period_key: str,
    session: Any | None = None,
) -> dict[str, object]:
    """Resuelve y enriquece candidatos sin modificar persistencia."""

    active_session = _session_or_default(session)
    result = resolve_socios_vencidos_reactivation_candidates_for_period(
        date_from=date_from,
        date_to=date_to,
        iventas_period_key=iventas_period_key,
        activos_snapshot_id=None,
        session=active_session,
    )
    row_ids = tuple(
        sorted(int(candidate.vencido_row_id) for candidate in result.rows)
    )
    vencido_rows = []
    if row_ids:
        vencido_rows = (
            active_session.query(SociosVencidosCarteraORM)
            .filter(SociosVencidosCarteraORM.id.in_(row_ids))
            .all()
        )
    vencido_rows_by_id = {int(row.id): row for row in vencido_rows}
    missing_row_ids = set(row_ids) - vencido_rows_by_id.keys()
    if missing_row_ids:
        raise SociosVencidosReactivationCandidateResolverError(
            "No se pudieron enriquecer episodios de cartera: "
            f"{sorted(missing_row_ids)}."
        )
    tariff_catalog = _read_active_tariff_catalog(
        tariff_values=(row.tarifa for row in vencido_rows),
        session=active_session,
    )
    return {
        "sources": {
            "date_from": str(result.date_from),
            "date_to": str(result.date_to),
            "activos_snapshot_id": int(result.activos_snapshot_id),
            "iventas_sync_run_id": int(result.iventas_sync_run_id),
            "iventas_period_key": str(result.iventas_period_key),
        },
        "summary": {
            "total_rows": int(result.total_rows),
            "status_counts": dict(result.status_counts),
            "reason_counts": dict(result.reason_counts),
        },
        "rows": [
            _serialize_candidate(
                candidate=candidate,
                vencido_row=vencido_rows_by_id[int(candidate.vencido_row_id)],
                tariff_catalog=tariff_catalog,
            )
            for candidate in result.rows
        ],
    }


def preview_marketing_reactivation_campaign(
    *,
    date_from: date | str,
    date_to: date | str,
    filters: Any,
    campaign_cooldown_days: int | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    plan = _build_campaign_plan(
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        campaign_cooldown_days=campaign_cooldown_days,
        session=_session_or_default(session),
        now=now,
    )
    return {
        "sources": plan["sources"],
        "filters": plan["filters"],
        "summary": plan["summary"],
    }


def create_marketing_reactivation_campaign(
    *,
    name: Any,
    date_from: date | str,
    date_to: date | str,
    filters: Any,
    notes: Any = None,
    created_by_user_id: int,
    campaign_cooldown_days: int | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized_name = _validate_required_text(name, "name", max_length=255)
    normalized_notes = _validate_optional_text(notes, "notes", max_length=5000)
    active_session = _session_or_default(session)
    now_value = _validate_now(now)
    plan = _build_campaign_plan(
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        campaign_cooldown_days=campaign_cooldown_days,
        session=active_session,
        now=now_value,
    )
    eligible_rows = plan["eligible_rows"]
    if not eligible_rows:
        raise MarketingReactivationValidationError(
            "La selección no contiene destinatarios elegibles."
        )

    campaign = MarketingReactivationCampaignORM(
        name=normalized_name,
        status=CAMPAIGN_STATUS_DRAFT,
        date_from=date.fromisoformat(str(plan["sources"]["date_from"])),
        date_to=date.fromisoformat(str(plan["sources"]["date_to"])),
        created_by_user_id=int(created_by_user_id),
        created_at=now_value,
        updated_at=now_value,
        notes=normalized_notes,
        filters_json={
            "filters": plan["filters"],
            "sources": plan["sources"],
            "summary": plan["summary"],
        },
        recipient_count=len(eligible_rows),
    )
    try:
        active_session.add(campaign)
        active_session.flush()
        for row in eligible_rows:
            active_session.add(
                MarketingReactivationCampaignRecipientORM(
                    campaign_id=int(campaign.id),
                    socios_vencidos_cartera_id=int(row["vencido_row_id"]),
                    phone_mx10=str(row["phone_mx10"]),
                    member_name=row["nombre"],
                    sucursal=str(row["sucursal"]),
                    fecha_vencimiento_date=date.fromisoformat(
                        str(row["fecha_vencimiento"])
                    ),
                    tarifa=row["tarifa"],
                    inclusion_status=ELIGIBILITY_ELIGIBLE,
                    exclusion_reason=None,
                    operational_status=str(row["operational_status"]),
                    operational_reason=str(row["reason"]),
                    created_at=now_value,
                )
            )
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingReactivationConflictError(
            "Conflicto al guardar destinatarios únicos de la campaña."
        ) from exc
    except Exception:
        active_session.rollback()
        raise
    return serialize_marketing_reactivation_campaign(campaign)


def list_marketing_reactivation_campaigns(
    *,
    limit: int = 50,
    session: Any | None = None,
) -> dict[str, object]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise MarketingReactivationValidationError(
            "limit debe ser un entero entre 1 y 200."
        )
    active_session = _session_or_default(session)
    rows = (
        active_session.query(MarketingReactivationCampaignORM)
        .options(joinedload(MarketingReactivationCampaignORM.created_by_user))
        .order_by(
            MarketingReactivationCampaignORM.created_at.desc(),
            MarketingReactivationCampaignORM.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return {
        "rows": [serialize_marketing_reactivation_campaign(row) for row in rows],
        "limit": limit,
    }


def get_marketing_reactivation_campaign(
    *,
    campaign_id: int,
    session: Any | None = None,
) -> dict[str, object]:
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=_session_or_default(session),
        include_recipients=True,
    )
    result = serialize_marketing_reactivation_campaign(campaign)
    result["recipients"] = [
        _serialize_campaign_recipient(row) for row in campaign.recipients
    ]
    return result


def export_marketing_reactivation_campaign(
    *,
    campaign_id: int,
    session: Any | None = None,
    now: datetime | None = None,
) -> tuple[bytes, str]:
    active_session = _session_or_default(session)
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=active_session,
        include_recipients=True,
        for_update=True,
    )
    if campaign.status not in {CAMPAIGN_STATUS_DRAFT, CAMPAIGN_STATUS_EXPORTED}:
        raise MarketingReactivationInvalidTransitionError(
            "Sólo una campaña DRAFT o EXPORTED puede exportarse."
        )
    stored_filters = dict((campaign.filters_json or {}).get("filters") or {})
    plan = _build_campaign_plan(
        date_from=campaign.date_from,
        date_to=campaign.date_to,
        filters=stored_filters,
        campaign_cooldown_days=stored_filters.get("campaign_cooldown_days"),
        session=active_session,
        now=now,
        exclude_campaign_id=int(campaign.id),
    )
    planned_keys = {
        (int(row["vencido_row_id"]), str(row["phone_mx10"]))
        for row in plan["eligible_rows"]
    }
    stored_keys = {
        (int(row.socios_vencidos_cartera_id), str(row.phone_mx10))
        for row in campaign.recipients
    }
    if planned_keys != stored_keys:
        raise MarketingReactivationConflictError(
            "La elegibilidad cambió desde la creación; prepara una campaña nueva."
        )

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Destinatarios")
    sheet.append(["Nombre", "Teléfono", "Sucursal", "Fecha vencimiento", "Tarifa"])
    for row in campaign.recipients:
        sheet.append(
            [
                row.member_name or "",
                row.phone_mx10,
                row.sucursal,
                row.fecha_vencimiento_date.isoformat(),
                row.tarifa or "",
            ]
        )
    output = BytesIO()
    workbook.save(output)
    export_bytes = output.getvalue()
    now_value = _validate_now(now)
    if campaign.status == CAMPAIGN_STATUS_DRAFT:
        campaign.status = CAMPAIGN_STATUS_EXPORTED
        campaign.exported_at = now_value
        campaign.updated_at = now_value
    try:
        active_session.commit()
    except Exception:
        active_session.rollback()
        raise
    return export_bytes, f"reactivacion_campana_{int(campaign.id)}.xlsx"


def mark_marketing_reactivation_campaign_sent(
    *,
    campaign_id: int,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    active_session = _session_or_default(session)
    campaign = _read_campaign(
        campaign_id=campaign_id,
        session=active_session,
        for_update=True,
    )
    if campaign.status != CAMPAIGN_STATUS_EXPORTED:
        raise MarketingReactivationInvalidTransitionError(
            "Sólo una campaña EXPORTED puede marcarse como SENT."
        )
    now_value = _validate_now(now)
    campaign.status = CAMPAIGN_STATUS_SENT
    campaign.sent_at = now_value
    campaign.updated_at = now_value
    try:
        active_session.commit()
    except Exception:
        active_session.rollback()
        raise
    return serialize_marketing_reactivation_campaign(campaign)


def serialize_marketing_reactivation_campaign(
    campaign: MarketingReactivationCampaignORM,
) -> dict[str, object]:
    user = getattr(campaign, "created_by_user", None)
    return {
        "id": int(campaign.id),
        "name": str(campaign.name),
        "status": str(campaign.status),
        "date_from": _serialize_date(campaign.date_from),
        "date_to": _serialize_date(campaign.date_to),
        "created_by_user_id": campaign.created_by_user_id,
        "created_by_username": getattr(user, "username", None),
        "created_at": _serialize_optional_aware_datetime(campaign.created_at),
        "updated_at": _serialize_optional_aware_datetime(campaign.updated_at),
        "exported_at": _serialize_optional_aware_datetime(campaign.exported_at),
        "sent_at": _serialize_optional_aware_datetime(campaign.sent_at),
        "notes": campaign.notes,
        "filters": dict((campaign.filters_json or {}).get("filters") or {}),
        "recipient_count": int(campaign.recipient_count),
    }


def _build_campaign_plan(
    *,
    date_from: date | str,
    date_to: date | str,
    filters: Any,
    campaign_cooldown_days: int | None,
    session: Any,
    now: datetime | None,
    exclude_campaign_id: int | None = None,
) -> dict[str, Any]:
    normalized_from, normalized_to = _validate_date_range(date_from, date_to)
    normalized_filters = _validate_campaign_filters(
        filters,
        campaign_cooldown_days=campaign_cooldown_days,
    )
    candidates = build_marketing_reactivation_candidates(
        date_from=normalized_from,
        date_to=normalized_to,
        iventas_period_key=str(normalized_filters["iventas_period_key"]),
        session=session,
    )
    filtered_rows = [
        {**row, "operational_status": _operational_status(row)}
        for row in candidates["rows"]
        if _matches_campaign_filters(row, normalized_filters)
    ]
    phone_by_row_id = {
        int(row["vencido_row_id"]): normalize_iventas_phone(
            row.get("telefono")
        ).phone_mx10
        for row in filtered_rows
    }
    phone_counts = Counter(
        phone for phone in phone_by_row_id.values() if phone is not None
    )
    last_sent_by_phone = _read_last_suite_campaign_sent_at(
        phone_mx10_values=set(phone_counts),
        session=session,
        exclude_campaign_id=exclude_campaign_id,
    )
    cooldown_days = normalized_filters.get("campaign_cooldown_days")
    now_value = _validate_now(now)
    eligibility_counts: Counter[str] = Counter()
    decision_rows: list[dict[str, Any]] = []
    for row in filtered_rows:
        phone_mx10 = phone_by_row_id[int(row["vencido_row_id"])]
        eligibility, reason = _resolve_campaign_eligibility(
            row=row,
            phone_mx10=phone_mx10,
            duplicate_phone=(
                phone_mx10 is not None and phone_counts[phone_mx10] > 1
            ),
            last_sent_at=(
                last_sent_by_phone.get(phone_mx10)
                if phone_mx10 is not None
                else None
            ),
            campaign_cooldown_days=cooldown_days,
            now=now_value,
        )
        eligibility_counts[eligibility] += 1
        decision_rows.append(
            {
                **row,
                "phone_mx10": phone_mx10,
                "campaign_eligibility": eligibility,
                "eligibility_reason": reason,
                "last_suite_campaign_sent_at": _serialize_optional_aware_datetime(
                    last_sent_by_phone.get(phone_mx10)
                    if phone_mx10 is not None
                    else None
                ),
            }
        )
    duplicate_count = sum(
        1
        for row in decision_rows
        if row["eligibility_reason"] == REASON_REVIEW_DUPLICATE_PHONE
    )
    review_identity_count = sum(
        1
        for row in decision_rows
        if row["campaign_eligibility"] == ELIGIBILITY_REVIEW
        and row["eligibility_reason"] == REASON_REVIEW_IDENTITY
    )
    domiciliated_flow_count = sum(
        1
        for row in decision_rows
        if row["eligibility_reason"] == REASON_TARIFF_DOMICILIATED_FLOW
    )
    review_tariff_count = sum(
        1
        for row in decision_rows
        if row["eligibility_reason"] == REASON_REVIEW_TARIFF
    )
    summary = {
        "total_candidates": len(decision_rows),
        "eligible": eligibility_counts[ELIGIBILITY_ELIGIBLE],
        "excluded_active": eligibility_counts[ELIGIBILITY_EXCLUDED_ACTIVE],
        "excluded_invalid_phone": eligibility_counts[
            ELIGIBILITY_EXCLUDED_INVALID_PHONE
        ],
        "review_identity": review_identity_count,
        "duplicate_phone": duplicate_count,
        "excluded_tariff": eligibility_counts[ELIGIBILITY_EXCLUDED_TARIFF],
        "domiciliated_flow": domiciliated_flow_count,
        "review_tariff": review_tariff_count,
        "excluded_recent_campaign": eligibility_counts[
            ELIGIBILITY_EXCLUDED_RECENT_CAMPAIGN
        ],
        "review": eligibility_counts[ELIGIBILITY_REVIEW],
    }
    return {
        "sources": candidates["sources"],
        "filters": normalized_filters,
        "summary": summary,
        "decision_rows": decision_rows,
        "eligible_rows": [
            row
            for row in decision_rows
            if row["campaign_eligibility"] == ELIGIBILITY_ELIGIBLE
        ],
    }


def _resolve_campaign_eligibility(
    *,
    row: dict[str, Any],
    phone_mx10: str | None,
    duplicate_phone: bool,
    last_sent_at: datetime | None,
    campaign_cooldown_days: int | None,
    now: datetime,
) -> tuple[str, str | None]:
    if row["status"] == "EXCLUDED_ACTIVE":
        return ELIGIBILITY_EXCLUDED_ACTIVE, "ACTIVE_CONFIRMED"
    if row["status"] == "REVIEW_ACTIVE_MATCH" or row["reason"] in _IDENTITY_REASONS:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_IDENTITY
    tariff_group = row.get("tarifa_group")
    if tariff_group == TARIFF_GROUP_EXCLUDE:
        return ELIGIBILITY_EXCLUDED_TARIFF, REASON_TARIFF_EXCLUDED
    if tariff_group == TARIFF_GROUP_DOMICILIATED_FLOW:
        return ELIGIBILITY_EXCLUDED_TARIFF, REASON_TARIFF_DOMICILIATED_FLOW
    if tariff_group in {None, TARIFF_GROUP_REVIEW}:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_TARIFF
    if tariff_group != TARIFF_GROUP_REACTIVATE:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_TARIFF
    if phone_mx10 is None:
        return ELIGIBILITY_EXCLUDED_INVALID_PHONE, REASON_INVALID_PHONE
    if duplicate_phone:
        return ELIGIBILITY_REVIEW, REASON_REVIEW_DUPLICATE_PHONE
    if (
        campaign_cooldown_days is not None
        and last_sent_at is not None
        and last_sent_at >= now - timedelta(days=campaign_cooldown_days)
    ):
        return ELIGIBILITY_EXCLUDED_RECENT_CAMPAIGN, REASON_RECENT_SUITE_CAMPAIGN
    return ELIGIBILITY_ELIGIBLE, None


def _read_last_suite_campaign_sent_at(
    *,
    phone_mx10_values: set[str],
    session: Any,
    exclude_campaign_id: int | None = None,
) -> dict[str, datetime]:
    if not phone_mx10_values:
        return {}
    query = (
        session.query(
            MarketingReactivationCampaignRecipientORM.phone_mx10,
            func.max(MarketingReactivationCampaignORM.sent_at),
        )
        .join(
            MarketingReactivationCampaignORM,
            MarketingReactivationCampaignORM.id
            == MarketingReactivationCampaignRecipientORM.campaign_id,
        )
        .filter(
            MarketingReactivationCampaignORM.status == CAMPAIGN_STATUS_SENT,
            MarketingReactivationCampaignRecipientORM.phone_mx10.in_(
                tuple(sorted(phone_mx10_values))
            ),
        )
    )
    if exclude_campaign_id is not None:
        query = query.filter(
            MarketingReactivationCampaignORM.id != exclude_campaign_id
        )
    rows = query.group_by(
        MarketingReactivationCampaignRecipientORM.phone_mx10
    ).all()
    return {str(phone): sent_at for phone, sent_at in rows if sent_at is not None}


def _read_campaign(
    *,
    campaign_id: int,
    session: Any,
    include_recipients: bool = False,
    for_update: bool = False,
) -> MarketingReactivationCampaignORM:
    if not isinstance(campaign_id, int) or isinstance(campaign_id, bool) or campaign_id <= 0:
        raise MarketingReactivationValidationError(
            "campaign_id debe ser un entero positivo."
        )
    query = session.query(MarketingReactivationCampaignORM)
    if not for_update:
        query = query.options(
            joinedload(MarketingReactivationCampaignORM.created_by_user)
        )
    if include_recipients and not for_update:
        query = query.options(
            joinedload(MarketingReactivationCampaignORM.recipients)
        )
    if for_update:
        query = query.with_for_update()
    campaign = query.filter(
        MarketingReactivationCampaignORM.id == campaign_id
    ).one_or_none()
    if campaign is None:
        raise MarketingReactivationNotFoundError(
            f"No existe la campaña id={campaign_id}."
        )
    return campaign


def _validate_campaign_filters(
    filters: Any,
    *,
    campaign_cooldown_days: int | None,
) -> dict[str, Any]:
    if not isinstance(filters, dict):
        raise MarketingReactivationValidationError(
            "filters debe ser un objeto JSON."
        )
    unknown = sorted(set(filters) - _ALLOWED_CAMPAIGN_FILTERS)
    if unknown:
        raise MarketingReactivationValidationError(
            "Filtros no permitidos: " + ", ".join(unknown) + "."
        )
    iventas_period_key = _validate_required_text(
        filters.get("iventas_period_key"),
        "filters.iventas_period_key",
        max_length=64,
    )
    operational_status = str(
        filters.get("operational_status") or FILTER_WORK_PENDING
    ).strip()
    if operational_status not in _OPERATIONAL_FILTERS:
        raise MarketingReactivationValidationError(
            "filters.operational_status no es válido."
        )
    effective_cooldown = (
        campaign_cooldown_days
        if campaign_cooldown_days is not None
        else filters.get("campaign_cooldown_days")
    )
    if effective_cooldown is not None and (
        not isinstance(effective_cooldown, int)
        or isinstance(effective_cooldown, bool)
        or not 0 <= effective_cooldown <= 3650
    ):
        raise MarketingReactivationValidationError(
            "campaign_cooldown_days debe ser un entero entre 0 y 3650."
        )
    return {
        "iventas_period_key": iventas_period_key,
        "sucursal": _validate_optional_text(
            filters.get("sucursal"), "filters.sucursal", max_length=255
        ),
        "operational_status": operational_status,
        "search": _validate_optional_text(
            filters.get("search"), "filters.search", max_length=255
        ),
        "tarifa": _validate_optional_text(
            filters.get("tarifa"), "filters.tarifa", max_length=255
        ),
        "campaign_cooldown_days": effective_cooldown,
    }


def _matches_campaign_filters(
    row: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    if filters["sucursal"] and row["sucursal"] != filters["sucursal"]:
        return False
    if filters["tarifa"] and row["tarifa"] != filters["tarifa"]:
        return False
    operational_status = _operational_status(row)
    requested_status = filters["operational_status"]
    if requested_status == FILTER_WORK_PENDING and operational_status in {
        OPERATIONAL_ACTIVE,
        OPERATIONAL_CONTACTED_AFTER_EXPIRATION,
    }:
        return False
    if requested_status not in {FILTER_ALL, FILTER_WORK_PENDING} and (
        operational_status != requested_status
    ):
        return False
    search = _normalize_search(filters["search"])
    if search and not any(
        search in _normalize_search(value)
        for value in (row["nombre"], row["pin"], row["telefono"])
    ):
        return False
    return True


def _operational_status(row: dict[str, Any]) -> str:
    if row["status"] == "EXCLUDED_ACTIVE":
        return OPERATIONAL_ACTIVE
    if row["status"] == "REVIEW_ACTIVE_MATCH" or row["reason"] in {
        *_IDENTITY_REASONS,
        "NO_MX10",
        "DUPLICATE_VENCIDO_PHONE",
    }:
        return OPERATIONAL_REVIEW_IDENTITY
    if row["reason"] == "NO_MATCH_CURRENT_IVENTAS_RUN":
        return OPERATIONAL_NO_CONTACT_IN_PERIOD
    if row["reason"] == "NO_OUTBOUND_EVIDENCE":
        return OPERATIONAL_NO_OUTBOUND_MESSAGE
    if row["reason"] == "ONLY_PRE_EXPIRATION_OUTBOUND":
        return OPERATIONAL_CONTACTED_BEFORE_EXPIRATION
    if row["status"] == "EXCLUDED_POST_EXPIRATION_CONTACT":
        return OPERATIONAL_CONTACTED_AFTER_EXPIRATION
    return OPERATIONAL_REVIEW_IDENTITY


def _serialize_candidate(
    *,
    candidate: Any,
    vencido_row: Any,
    tariff_catalog: dict[str, MarketingReactivationTariffORM],
) -> dict[str, object]:
    tariff = tariff_catalog.get(
        normalize_reactivation_tariff_key(vencido_row.tarifa)
    )
    return {
        "vencido_row_id": int(candidate.vencido_row_id),
        "pin": str(vencido_row.pin),
        "nombre": vencido_row.nombre,
        "sucursal": vencido_row.sucursal_raw,
        "telefono": vencido_row.telefono_raw,
        "correo": vencido_row.correo_raw,
        "fecha_vencimiento": _serialize_date(vencido_row.fecha_vencimiento_date),
        "fecha_ultimo_pago": _serialize_optional_date(
            vencido_row.fecha_ultimo_pago_local
        ),
        "tarifa": vencido_row.tarifa,
        "tarifa_categoria": (
            str(tariff.categoria_tarifa) if tariff is not None else None
        ),
        "tarifa_group": (
            str(tariff.reactivation_group) if tariff is not None else None
        ),
        "tarifa_classified": tariff is not None,
        "adeudo": _serialize_optional_decimal(vencido_row.adeudo),
        "status": str(candidate.status),
        "reason": str(candidate.reason),
        "active_status": str(candidate.active_status),
        "active_id_socio": candidate.active_id_socio,
        "iventas_contact_id": candidate.iventas_contact_id,
        "latest_outbound_at_utc": _serialize_optional_aware_datetime(
            candidate.latest_outbound_at_utc
        ),
    }


def normalize_reactivation_tariff_key(value: Any) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value)).strip().upper()
    normalized = " ".join(normalized.split())
    return normalized or None


def _read_active_tariff_catalog(
    *,
    tariff_values: Any,
    session: Any,
) -> dict[str, MarketingReactivationTariffORM]:
    tariff_keys = {
        key
        for key in (
            normalize_reactivation_tariff_key(value) for value in tariff_values
        )
        if key is not None
    }
    if not tariff_keys:
        return {}
    rows = (
        session.query(MarketingReactivationTariffORM)
        .filter(
            MarketingReactivationTariffORM.is_active.is_(True),
            MarketingReactivationTariffORM.tarifa_key.in_(
                tuple(sorted(tariff_keys))
            ),
        )
        .all()
    )
    return {str(row.tarifa_key): row for row in rows}


def _serialize_tariff_classification(
    tariff: MarketingReactivationTariffORM | None,
) -> dict[str, object]:
    return {
        "classified": tariff is not None,
        "categoria_tarifa": (
            str(tariff.categoria_tarifa) if tariff is not None else None
        ),
        "reactivation_group": (
            str(tariff.reactivation_group) if tariff is not None else None
        ),
    }


def _serialize_campaign_recipient(row: Any) -> dict[str, object]:
    return {
        "id": int(row.id),
        "socios_vencidos_cartera_id": int(row.socios_vencidos_cartera_id),
        "phone_mx10": str(row.phone_mx10),
        "member_name": row.member_name,
        "sucursal": str(row.sucursal),
        "fecha_vencimiento_date": _serialize_date(row.fecha_vencimiento_date),
        "tarifa": row.tarifa,
        "inclusion_status": str(row.inclusion_status),
        "exclusion_reason": row.exclusion_reason,
        "operational_status": str(row.operational_status),
        "operational_reason": str(row.operational_reason),
        "created_at": _serialize_optional_aware_datetime(row.created_at),
    }


def _validate_date_range(
    date_from: date | str,
    date_to: date | str,
) -> tuple[date, date]:
    normalized_from = _ensure_date(date_from, "date_from")
    normalized_to = _ensure_date(date_to, "date_to")
    if normalized_from > normalized_to:
        raise MarketingReactivationValidationError(
            "date_from no puede ser posterior a date_to."
        )
    return normalized_from, normalized_to


def _ensure_date(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise MarketingReactivationValidationError(
            f"{field_name} debe ser una fecha ISO válida (YYYY-MM-DD)."
        ) from exc


def _validate_required_text(
    value: Any,
    field_name: str,
    *,
    max_length: int,
) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MarketingReactivationValidationError(
            f"{field_name} es obligatorio."
        )
    if len(normalized) > max_length:
        raise MarketingReactivationValidationError(
            f"{field_name} no puede exceder {max_length} caracteres."
        )
    return normalized


def _validate_optional_text(
    value: Any,
    field_name: str,
    *,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MarketingReactivationValidationError(
            f"{field_name} debe ser texto o null."
        )
    normalized = value.strip() or None
    if normalized is not None and len(normalized) > max_length:
        raise MarketingReactivationValidationError(
            f"{field_name} no puede exceder {max_length} caracteres."
        )
    return normalized


def _validate_now(value: datetime | None) -> datetime:
    now_value = value if value is not None else _utc_now()
    if now_value.tzinfo is None or now_value.utcoffset() is None:
        raise MarketingReactivationValidationError(
            "now debe incluir zona horaria."
        )
    return now_value.astimezone(timezone.utc)


def _normalize_search(value: Any) -> str:
    normalized = unicodedata.normalize(
        "NFD",
        str(value or "").strip().lower(),
    )
    return " ".join(
        "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        ).split()
    )


def _serialize_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _serialize_optional_date(value: date | datetime | None) -> str | None:
    return None if value is None else _serialize_date(value)


def _serialize_optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _serialize_optional_aware_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise SociosVencidosReactivationCandidateResolverError(
            "El datetime debe incluir zona horaria."
        )
    return value.isoformat()
