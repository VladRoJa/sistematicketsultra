"""Consulta base exportable para relacionar leads iVentas con Meta."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingMetaAdInsightORM,
)
from app.services.marketing_iventas_service import TAG_KIND_META_AD


def build_iventas_meta_export_statement(
    *,
    iventas_sync_run_id: int,
    meta_sync_run_id: int,
):
    if iventas_sync_run_id <= 0 or meta_sync_run_id <= 0:
        raise ValueError(
            "Los identificadores de sync run deben ser positivos."
        )

    return (
        select(
            MarketingIventasContactORM.first_message_date_local.label(
                "lead_date"
            ),
            MarketingIventasContactORM.sucursal_id,
            MarketingIventasContactORM.contact_id,
            MarketingIventasContactORM.name.label("contact_name"),
            MarketingIventasContactORM.phone_raw,
            MarketingIventasContactORM.phone_mx10,
            MarketingIventasContactORM.channel_id,
            MarketingIventasContactORM.channel_name,
            MarketingIventasContactORM.channel_platform,
            MarketingIventasContactORM.agent_json,
            MarketingIventasContactORM.first_message_at_utc,
            MarketingIventasContactORM.first_message_at_local,
            MarketingIventasContactTagORM.meta_ad_id,
            MarketingMetaAdInsightORM.account_id,
            MarketingMetaAdInsightORM.account_name,
            MarketingMetaAdInsightORM.campaign_id,
            MarketingMetaAdInsightORM.campaign_name,
            MarketingMetaAdInsightORM.adset_id,
            MarketingMetaAdInsightORM.adset_name,
            MarketingMetaAdInsightORM.ad_id,
            MarketingMetaAdInsightORM.ad_name,
            MarketingMetaAdInsightORM.date_start,
            MarketingMetaAdInsightORM.date_stop,
            MarketingMetaAdInsightORM.spend,
            MarketingMetaAdInsightORM.reach,
            MarketingMetaAdInsightORM.impressions,
            MarketingMetaAdInsightORM.clicks,
            MarketingMetaAdInsightORM.actions_json,
        )
        .select_from(MarketingIventasContactORM)
        .join(
            MarketingIventasContactTagORM,
            (
                MarketingIventasContactTagORM.iventas_contact_row_id
                == MarketingIventasContactORM.id
            )
            & (
                MarketingIventasContactTagORM.sync_run_id
                == MarketingIventasContactORM.sync_run_id
            ),
        )
        .outerjoin(
            MarketingMetaAdInsightORM,
            (
                MarketingIventasContactTagORM.meta_ad_id
                == MarketingMetaAdInsightORM.ad_id
            )
            & (
                MarketingMetaAdInsightORM.sync_run_id
                == meta_sync_run_id
            ),
        )
        .where(
            MarketingIventasContactORM.sync_run_id
            == iventas_sync_run_id,
            MarketingIventasContactORM.first_message_at_utc.is_not(None),
            MarketingIventasContactTagORM.tag_kind == TAG_KIND_META_AD,
            MarketingIventasContactTagORM.meta_ad_id.is_not(None),
        )
        .order_by(
            MarketingIventasContactORM.first_message_at_local.asc(),
            MarketingIventasContactORM.sucursal_id.asc(),
            MarketingIventasContactORM.contact_id.asc(),
            MarketingIventasContactTagORM.meta_ad_id.asc(),
        )
    )


def list_iventas_meta_export_rows(
    *,
    iventas_sync_run_id: int,
    meta_sync_run_id: int,
    session: Any | None = None,
) -> tuple[dict[str, Any], ...]:
    session_value = session if session is not None else db.session
    rows = (
        session_value.execute(
            build_iventas_meta_export_statement(
                iventas_sync_run_id=iventas_sync_run_id,
                meta_sync_run_id=meta_sync_run_id,
            )
        )
        .mappings()
        .all()
    )
    return tuple(dict(row) for row in rows)
