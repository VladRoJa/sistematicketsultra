"""Scheduler-only reconciliation of multichild Campaign V2 commercial sales.

The web endpoints must read the materialized result, never query Gasca rows.
All sources are persisted Warehouse/iVentas snapshots. No provider HTTP calls.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2CommercialResultORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientORM,
)
from app.models.warehouse import (
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
)
from app.services.marketing_campaign_v2_commercial_attribution_service import (
    CommercialChildResolutionError,
    direct_attribution_ineligibility_reason,
    required_commercial_sale_kind,
    COMMERCIAL_SALE_KIND_RULE_VERSION,
    resolve_submitted_child_recipients,
)
from app.services.marketing_campaign_v2_reporting_service import (
    _commercial_month_end_exclusive,
    _summarize_campaign_v2_multichild_membership_movements,
)
from app.services.marketing_phone import normalize_phone
from app.services.marketing_sales_funnel_service import _normalize_text

LOGGER = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Tijuana")
_MAX_SUCCESSFUL_PHONES = 50000
_MAX_MATCHED_ROWS = 100000


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _base(campaign_id: int, status: str) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "status": status,
        "buyers_attributed": None,
        "transactions_attributed": None,
        "revenue_attributed_mxn": None,
    }


def reconcile_multichild_campaign(*, campaign_id: int, session: Any) -> dict[str, Any]:
    """One campaign, one cumulative canonical Gasca cut, all submitted children."""
    base = _base(campaign_id, "PENDING")
    with session.no_autoflush:
        campaign = (
            session.query(MarketingCampaignV2ORM)
            .filter(MarketingCampaignV2ORM.id == campaign_id)
            .first()
        )
        if campaign is None:
            return {**base, "status": "EVIDENCE_INCONSISTENT"}
        reason = direct_attribution_ineligibility_reason(
            purpose=campaign.purpose, source=campaign.source,
        )
        if reason is not None:
            return {**base, "status": "NOT_ATTRIBUTABLE", "reason": reason}

        children = (
            session.query(MarketingCampaignV2ProviderCampaignORM)
            .filter(MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id)
            .all()
        )
        frozen = (
            session.query(MarketingCampaignV2RecipientORM)
            .filter(MarketingCampaignV2RecipientORM.campaign_id == campaign_id)
            .all()
        )
        try:
            scope = resolve_submitted_child_recipients(
                campaign_id=campaign_id, children=children, frozen_recipients=frozen,
            )
        except (CommercialChildResolutionError, TypeError, ValueError):
            return {**base, "status": "EVIDENCE_INCONSISTENT"}
        if scope.unresolved_child_ids:
            return {
                **base, "status": "PENDING_CHILD_STATE",
                "unresolved_child_count": len(scope.unresolved_child_ids),
            }
        if not scope.submitted:
            return {**base, "status": "NOT_SUBMITTED"}

        child_by_provider = {
            entry.provider_campaign_id: entry for entry in scope.submitted
        }
        sent_local = {entry.child_id: _utc(entry.submitted_at).astimezone(_TZ)
                      for entry in scope.submitted}
        months = {(value.year, value.month) for value in sent_local.values()}
        if len(months) != 1:
            return {**base, "status": "UNSUPPORTED_MULTIMONTH"}

        submitted_ids = tuple(entry.child_id for entry in scope.submitted)
        snapshot_rows = (
            session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
            .filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id == campaign_id,
                MarketingCampaignV2ProviderStatsSnapshotORM.provider == "IVENTAS",
                MarketingCampaignV2ProviderStatsSnapshotORM.provider_campaign_id.in_(
                    tuple(child_by_provider)
                ),
            )
            .order_by(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.desc(),
                MarketingCampaignV2ProviderStatsSnapshotORM.id.desc(),
            )
            .all()
        )
        provider_by_child = {}
        for snapshot in snapshot_rows:
            entry = child_by_provider.get(snapshot.provider_campaign_id)
            if entry is not None and entry.child_id not in provider_by_child:
                provider_by_child[entry.child_id] = snapshot
        if len(provider_by_child) != len(scope.submitted):
            return {**base, "status": "NO_PROVIDER_SNAPSHOT"}

        if any(
            (snapshot.analytics_status != "ok" and int(snapshot.raw_successful) == 0)
            for snapshot in provider_by_child.values()
        ):
            return {**base, "status": "PENDING_PROVIDER_SYNC"}

        snapshot_id_to_child = {
            int(snapshot.id): entry.child_id
            for entry in scope.submitted
            for snapshot in (provider_by_child[entry.child_id],)
        }
        eligible_by_child = {
            entry.child_id: dict(entry.recipients) for entry in scope.submitted
        }
        seen_ids = defaultdict(set)
        observations = (
            session.query(
                MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id,
                MarketingCampaignV2ProviderRecipientObservationORM.campaign_recipient_id,
                MarketingCampaignV2ProviderRecipientObservationORM.normalized_phone,
            )
            .filter(
                MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.in_(
                    tuple(snapshot_id_to_child)
                ),
                MarketingCampaignV2ProviderRecipientObservationORM.outcome == "SUCCESSFUL",
            )
            .all()
        )
        for snapshot_id, recipient_id, raw_phone in observations:
            child_id = snapshot_id_to_child[int(snapshot_id)]
            # Persisted iVentas observation identity is "mx10:<10 digits>",
            # not a raw telephone; passing that whole token to normalize_phone
            # would incorrectly include the "10" in the prefix.
            phone = normalize_phone(
                raw_phone[5:] if isinstance(raw_phone, str)
                and raw_phone.startswith("mx10:") else raw_phone
            )
            if (
                phone is not None
                and recipient_id is not None
                and eligible_by_child[child_id].get(phone) == int(recipient_id)
            ):
                seen_ids[child_id].add(phone)

        if any(
            len(seen_ids[child_id]) != int(provider_by_child[child_id].raw_successful)
            for child_id in submitted_ids
        ):
            return {**base, "status": "PROVIDER_SCOPE_MISMATCH"}

        successful_phones = set().union(*(seen_ids[child_id] for child_id in submitted_ids))
        if len(successful_phones) > _MAX_SUCCESSFUL_PHONES:
            return {**base, "status": "SCOPE_TOO_LARGE"}

        latest_sent = max(_utc(entry.submitted_at) for entry in scope.submitted)
        latest_local_date = max(sent_local.values()).date()
        first_local_date = min(sent_local.values()).date()
        venta = (
            session.query(VentaTotalSnapshotORM)
            .filter(
                VentaTotalSnapshotORM.report_type_key == "venta_total",
                VentaTotalSnapshotORM.snapshot_kind == "daily",
                VentaTotalSnapshotORM.is_canonical.is_(True),
                VentaTotalSnapshotORM.business_date >= latest_local_date,
                VentaTotalSnapshotORM.business_date < _commercial_month_end_exclusive(
                    first_local_date
                ),
                VentaTotalSnapshotORM.captured_at >= latest_sent,
            )
            .order_by(
                VentaTotalSnapshotORM.business_date.desc(),
                VentaTotalSnapshotORM.captured_at.desc(),
                VentaTotalSnapshotORM.id.desc(),
            )
            .first()
        )
        if venta is None:
            return {**base, "status": "NO_CANONICAL_VENTA_TOTAL"}

        aliases = (
            session.query(TrackBranchAliasORM, TrackBranchCatalogORM)
            .join(
                TrackBranchCatalogORM,
                TrackBranchCatalogORM.sucursal_canon
                == TrackBranchAliasORM.sucursal_canon,
            )
            .filter(
                TrackBranchAliasORM.source_family == "gasca_family",
                TrackBranchAliasORM.is_active.is_(True),
                TrackBranchCatalogORM.is_track_active.is_(True),
                TrackBranchCatalogORM.sucursal_id.isnot(None),
            ).all()
        )
        alias_map = {
            _normalize_text(alias.raw_branch_name): int(catalog.sucursal_id)
            for alias, catalog in aliases
        }
        phones_by_child = {
            entry.child_id: seen_ids[entry.child_id] for entry in scope.submitted
        }
        phone_to_child = {
            phone: entry.child_id
            for entry in scope.submitted
            for phone in phones_by_child[entry.child_id]
        }
        rows_by_child = defaultdict(list)
        if successful_phones:
            # Bounded streaming over a single cumulative snapshot. No huge
            # IN(phone) parameter arrays or one Gasca query per child.
            sale_rows = (
                session.query(VentaTotalSnapshotRowORM)
                .filter(VentaTotalSnapshotRowORM.snapshot_id == venta.id)
                .yield_per(1000)
            )
            matched = 0
            for row in sale_rows:
                phone = normalize_phone(row.telefono)
                child_id = phone_to_child.get(phone)
                if child_id is None:
                    continue
                matched += 1
                if matched > _MAX_MATCHED_ROWS:
                    return {**base, "status": "SCOPE_TOO_LARGE"}
                rows_by_child[child_id].append(row)

        metrics = _summarize_campaign_v2_multichild_membership_movements(
            required_sale_kind=required_commercial_sale_kind(
                purpose=campaign.purpose, source=campaign.source,
            ),
            expected_submitted_child_ids=submitted_ids,
            child_inputs=[
                {
                    "child_id": entry.child_id,
                    "branch_id": entry.sucursal_id,
                    "sent_local": sent_local[entry.child_id],
                    "successful_phones": phones_by_child[entry.child_id],
                    "rows": rows_by_child[entry.child_id],
                }
                for entry in scope.submitted
            ],
            alias_map=alias_map,
        )
        return {
            **base,
            "status": "READY",
            "attribution_rule_version": COMMERCIAL_SALE_KIND_RULE_VERSION,
            "coverage": "ALL_PROVEN_SUBMITTED_CHILDREN",
            "submitted_child_count": len(scope.submitted),
            "submitted_child_ids": sorted(submitted_ids),
            "not_sent_child_count": len(scope.not_sent_child_ids),
            "provider_snapshot_ids": sorted(snapshot_id_to_child),
            "venta_total_snapshot_id": int(venta.id),
            "venta_total_cutoff": venta.business_date.isoformat(),
            **metrics,
        }


def run_multichild_commercial_materialization_cycle(
    *,
    now: datetime,
    max_campaigns: int = 3,
    session: Any | None = None,
) -> dict[str, int]:
    """Rotate through multi-child campaigns; isolate errors and persist even PENDING."""
    if max_campaigns <= 0:
        raise ValueError("max_campaigns debe ser positivo")
    active = session if session is not None else db.session
    candidates = (
        active.query(MarketingCampaignV2ProviderCampaignORM.campaign_v2_id)
        .group_by(MarketingCampaignV2ProviderCampaignORM.campaign_v2_id)
        .having(func.count(MarketingCampaignV2ProviderCampaignORM.id) >= 2)
        .all()
    )
    ids = [int(row[0]) for row in candidates]
    cache_rows = active.query(MarketingCampaignV2CommercialResultORM).filter(
        MarketingCampaignV2CommercialResultORM.campaign_v2_id.in_(ids)
    ).all() if ids else []
    cache_by_id = {int(row.campaign_v2_id): row for row in cache_rows}
    ids.sort(key=lambda campaign_id: (
        cache_by_id[campaign_id].checked_at is not None if campaign_id in cache_by_id else False,
        _utc(cache_by_id[campaign_id].checked_at)
        if campaign_id in cache_by_id else datetime.min.replace(tzinfo=timezone.utc),
        -campaign_id,
    ))
    result = {"selected": min(len(ids), max_campaigns), "ready": 0,
              "pending": 0, "failed": 0}
    for campaign_id in ids[:max_campaigns]:
        try:
            payload = reconcile_multichild_campaign(
                campaign_id=campaign_id, session=active,
            )
            record = active.get(MarketingCampaignV2CommercialResultORM, campaign_id)
            if record is None:
                record = MarketingCampaignV2CommercialResultORM(
                    campaign_v2_id=campaign_id,
                )
                active.add(record)
            record.status = payload["status"]
            record.result_json = payload
            record.checked_at = _utc(now)
            active.commit()
            result["ready" if payload["status"] == "READY" else "pending"] += 1
        except Exception:  # noqa: BLE001
            active.rollback()
            result["failed"] += 1
            LOGGER.exception(
                "Commercial Campaign V2 materialization failed. campaign_id=%s",
                campaign_id,
            )
        finally:
            if session is None:
                db.session.remove()
    return result
