"""Consulta base exportable para relacionar leads iVentas con Meta.

El origen publicitario autoritativo de snapshots nuevos es
isFromAds/adsSourceId. Los tags ad_fb_* quedan como fallback de
snapshots históricos que todavía no persistían esos campos.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, or_, select

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

    resolved_ad_id = case(
        (
            MarketingIventasContactORM.is_from_ads.is_(True),
            MarketingIventasContactORM.ads_source_id,
        ),
        else_=MarketingIventasContactTagORM.meta_ad_id,
    )

    provider_evidence = and_(
        MarketingIventasContactORM.is_from_ads.is_(True),
        MarketingIventasContactORM.ads_source_id.is_not(None),
    )
    legacy_evidence = and_(
        MarketingIventasContactORM.is_from_ads.is_(None),
        MarketingIventasContactTagORM.tag_kind == TAG_KIND_META_AD,
        MarketingIventasContactTagORM.meta_ad_id.is_not(None),
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
            resolved_ad_id.label("meta_ad_id"),
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
        .outerjoin(
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
                resolved_ad_id
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
            or_(provider_evidence, legacy_evidence),
        )
        .distinct()
        .order_by(
            MarketingIventasContactORM.first_message_at_local.asc(),
            MarketingIventasContactORM.sucursal_id.asc(),
            MarketingIventasContactORM.contact_id.asc(),
            resolved_ad_id.asc(),
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
