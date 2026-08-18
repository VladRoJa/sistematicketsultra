"""Detalle auditable de leads canónicos iVentas para Marketing."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingMetaAdInsightORM,
)
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import (
    resolve_marketing_detail_scope,
)
from app.services.marketing_inputs_service import parse_month
from app.services.marketing_iventas_dashboard_data_service import (
    read_iventas_dashboard_month_data,
)
from app.services.marketing_iventas_service import TAG_KIND_META_AD
from app.services.marketing_meta_dashboard_service import (
    build_canonical_meta_run_statement,
    build_meta_month_period_key,
)
from app.services.marketing_phone import mask_phone


TIJUANA_TIMEZONE = ZoneInfo("America/Tijuana")


def build_marketing_lead_contacts_statement(
    *,
    iventas_sync_run_id: int,
    branch_ids: Iterable[int],
):
    normalized_branch_ids = tuple(sorted(set(branch_ids)))
    if iventas_sync_run_id <= 0:
        raise ValueError("iventas_sync_run_id debe ser positivo.")
    if not normalized_branch_ids:
        raise ValueError("branch_ids no puede estar vacío.")

    has_meta_tag = exists(
        select(MarketingIventasContactTagORM.id).where(
            MarketingIventasContactTagORM.sync_run_id
            == iventas_sync_run_id,
            MarketingIventasContactTagORM.iventas_contact_row_id
            == MarketingIventasContactORM.id,
            MarketingIventasContactTagORM.tag_kind
            == TAG_KIND_META_AD,
        )
    )

    return (
        select(
            MarketingIventasContactORM.id.label("contact_row_id"),
            MarketingIventasContactORM.sucursal_id,
            MarketingIventasContactORM.contact_id,
            MarketingIventasContactORM.name,
            MarketingIventasContactORM.phone_mx10,
            MarketingIventasContactORM.phone_digits,
            MarketingIventasContactORM.first_message_at_local,
            MarketingIventasContactORM.first_message_date_local,
            MarketingIventasContactORM.channel_name,
            MarketingIventasContactORM.channel_platform,
        )
        .where(
            MarketingIventasContactORM.sync_run_id
            == iventas_sync_run_id,
            MarketingIventasContactORM.sucursal_id.in_(
                normalized_branch_ids
            ),
            MarketingIventasContactORM.first_message_at_utc.is_not(None),
            has_meta_tag,
        )
        .order_by(
            MarketingIventasContactORM.sucursal_id.asc(),
            MarketingIventasContactORM.first_message_at_local.asc(),
            MarketingIventasContactORM.id.asc(),
        )
    )


def build_marketing_lead_tags_statement(
    *,
    iventas_sync_run_id: int,
    contact_row_ids: Iterable[int],
):
    normalized_ids = tuple(sorted(set(contact_row_ids)))
    if not normalized_ids:
        raise ValueError("contact_row_ids no puede estar vacío.")

    return (
        select(
            MarketingIventasContactTagORM.iventas_contact_row_id,
            MarketingIventasContactTagORM.meta_ad_id,
        )
        .where(
            MarketingIventasContactTagORM.sync_run_id
            == iventas_sync_run_id,
            MarketingIventasContactTagORM.iventas_contact_row_id.in_(
                normalized_ids
            ),
            MarketingIventasContactTagORM.tag_kind
            == TAG_KIND_META_AD,
        )
        .order_by(
            MarketingIventasContactTagORM.iventas_contact_row_id.asc(),
            MarketingIventasContactTagORM.meta_ad_id.asc(),
        )
    )


def build_marketing_lead_meta_statement(
    *,
    meta_sync_run_id: int,
    meta_ad_ids: Iterable[str],
):
    normalized_ad_ids = tuple(
        sorted(
            {
                str(ad_id).strip()
                for ad_id in meta_ad_ids
                if str(ad_id or "").strip()
            }
        )
    )
    if not normalized_ad_ids:
        raise ValueError("meta_ad_ids no puede estar vacío.")

    return select(
        MarketingMetaAdInsightORM.ad_id,
        MarketingMetaAdInsightORM.ad_name,
        MarketingMetaAdInsightORM.campaign_name,
    ).where(
        MarketingMetaAdInsightORM.sync_run_id == meta_sync_run_id,
        MarketingMetaAdInsightORM.ad_id.in_(normalized_ad_ids),
    )


def _build_marketing_lead_rows(
    *,
    contact_rows: Iterable[Mapping[str, Any]],
    tag_rows: Iterable[Mapping[str, Any]],
    meta_rows: Iterable[Mapping[str, Any]],
    branch_names: Mapping[int, str],
) -> list[dict[str, Any]]:
    ad_ids_by_contact: dict[int, set[str]] = {}
    for row in tag_rows:
        ad_id = str(row.get("meta_ad_id") or "").strip()
        if ad_id:
            ad_ids_by_contact.setdefault(
                int(row["iventas_contact_row_id"]),
                set(),
            ).add(ad_id)

    meta_by_ad: dict[str, dict[str, str | None]] = {}
    for row in meta_rows:
        ad_id = str(row["ad_id"] or "").strip()
        if ad_id:
            meta_by_ad[ad_id] = {
                "campaign_name": (
                    str(row.get("campaign_name") or "").strip()
                    or None
                ),
                "ad_name": (
                    str(row.get("ad_name") or "").strip()
                    or None
                ),
            }

    result: list[dict[str, Any]] = []
    for row in contact_rows:
        contact_row_id = int(row["contact_row_id"])
        meta_ad_ids = sorted(
            ad_ids_by_contact.get(contact_row_id, set())
        )
        campaign_names = sorted(
            {
                value
                for ad_id in meta_ad_ids
                for value in [
                    meta_by_ad.get(ad_id, {}).get("campaign_name")
                ]
                if value
            }
        )
        ad_names = sorted(
            {
                value
                for ad_id in meta_ad_ids
                for value in [meta_by_ad.get(ad_id, {}).get("ad_name")]
                if value
            }
        )
        branch_id = int(row["sucursal_id"])
        first_message_at_local = row["first_message_at_local"]
        first_message_date_local = row["first_message_date_local"]

        result.append(
            {
                "sucursal_id": branch_id,
                "sucursal": branch_names.get(
                    branch_id,
                    str(branch_id),
                ),
                "contact_id": str(row["contact_id"]),
                "name": (
                    str(row.get("name") or "").strip() or None
                ),
                "telefono": mask_phone(
                    row.get("phone_mx10")
                    or row.get("phone_digits")
                ),
                "first_message_at_local": (
                    first_message_at_local.isoformat()
                    if first_message_at_local is not None
                    else None
                ),
                "first_message_date_local": (
                    first_message_date_local.isoformat()
                    if first_message_date_local is not None
                    else None
                ),
                "channel_name": (
                    str(row.get("channel_name") or "").strip()
                    or None
                ),
                "channel_platform": (
                    str(row.get("channel_platform") or "").strip()
                    or None
                ),
                "meta_ad_ids": meta_ad_ids,
                "campaign_names": campaign_names,
                "ad_names": ad_names,
                "meta_enrichment_available": bool(
                    campaign_names or ad_names
                ),
            }
        )

    return result


def build_marketing_leads_detail(
    *,
    month: str,
    access: MarketingAccess,
    sucursal_id: int | None = None,
    today: date | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    month_start = parse_month(month)
    branches, selected_branch_ids, scope = (
        resolve_marketing_detail_scope(
            access=access,
            sucursal_id=sucursal_id,
        )
    )
    normalized_today = (
        today
        if today is not None
        else datetime.now(TIJUANA_TIMEZONE).date()
    )
    iventas_data = read_iventas_dashboard_month_data(
        month_date=month_start,
        today=normalized_today,
        session=session,
    )
    base_response = {
        "month": month_start.strftime("%Y-%m"),
        "scope": scope,
        "filters": {"sucursal_id": sucursal_id},
    }
    if not iventas_data.available or iventas_data.sync_run_id is None:
        return {
            **base_response,
            "summary": {"leads": None},
            "source": {
                "available": False,
                "iventas_sync_run_id": None,
                "period_key": iventas_data.period_key,
                "date_from": iventas_data.date_from.isoformat(),
                "date_to": iventas_data.date_to.isoformat(),
                "meta_sync_run_id": None,
                "meta_enrichment_available": False,
            },
            "rows": [],
        }

    session_value = session if session is not None else db.session
    contacts = (
        session_value.execute(
            build_marketing_lead_contacts_statement(
                iventas_sync_run_id=iventas_data.sync_run_id,
                branch_ids=selected_branch_ids,
            )
        )
        .mappings()
        .all()
    )
    contact_row_ids = [int(row["contact_row_id"]) for row in contacts]
    tags: Iterable[Mapping[str, Any]] = ()
    if contact_row_ids:
        tags = (
            session_value.execute(
                build_marketing_lead_tags_statement(
                    iventas_sync_run_id=iventas_data.sync_run_id,
                    contact_row_ids=contact_row_ids,
                )
            )
            .mappings()
            .all()
        )

    tags = tuple(tags)
    meta_ad_ids = {
        str(row.get("meta_ad_id") or "").strip()
        for row in tags
        if str(row.get("meta_ad_id") or "").strip()
    }
    canonical_meta = (
        session_value.execute(
            build_canonical_meta_run_statement(
                period_key=build_meta_month_period_key(month_start)
            )
        )
        .mappings()
        .first()
    )
    meta_window_matches = bool(
        canonical_meta is not None
        and canonical_meta["date_from"] == iventas_data.date_from
        and canonical_meta["date_to"] == iventas_data.date_to
    )
    meta_rows: Iterable[Mapping[str, Any]] = ()
    if meta_window_matches and meta_ad_ids:
        meta_rows = (
            session_value.execute(
                build_marketing_lead_meta_statement(
                    meta_sync_run_id=int(
                        canonical_meta["sync_run_id"]
                    ),
                    meta_ad_ids=meta_ad_ids,
                )
            )
            .mappings()
            .all()
        )

    rows = _build_marketing_lead_rows(
        contact_rows=contacts,
        tag_rows=tags,
        meta_rows=meta_rows,
        branch_names={
            branch.sucursal_id: branch.name
            for branch in branches
        },
    )
    return {
        **base_response,
        "summary": {"leads": len(rows)},
        "source": {
            "available": True,
            "iventas_sync_run_id": iventas_data.sync_run_id,
            "period_key": iventas_data.period_key,
            "date_from": iventas_data.date_from.isoformat(),
            "date_to": iventas_data.date_to.isoformat(),
            "meta_sync_run_id": (
                int(canonical_meta["sync_run_id"])
                if meta_window_matches
                else None
            ),
            "meta_enrichment_available": meta_window_matches,
        },
        "rows": rows,
    }
