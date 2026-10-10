"""Selección y ejecución automática de snapshots provider stats Campaign V2."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import and_, func

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
)
from app.services.marketing_campaign_v2_provider_stats_service import (
    MarketingCampaignV2ProviderStatsError,
)
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    MarketingCampaignV2ProviderStatsSnapshotPersistenceError,
    capture_campaign_v2_provider_stats_snapshot,
)


@dataclass(frozen=True)
class CampaignV2ProviderStatsSelection:
    campaign_ids: tuple[int, ...]
    bound_count: int
    eligible_count: int
    skipped_outside_horizon: int
    skipped_by_limit: int
    # Aligned with campaign_ids; None means a legacy parent-bound campaign.
    provider_child_ids: tuple[int | None, ...] = ()


@dataclass(frozen=True)
class CampaignV2ProviderStatsCycleResult:
    selected: int
    attempted: int
    created: int
    unchanged: int
    failed: int
    skipped: int


LOGGER = logging.getLogger(__name__)


CaptureFunc = Callable[..., dict]


def select_campaign_v2_provider_stats_candidates(
    *,
    now: datetime,
    horizon_hours: int,
    max_campaigns: int,
    session=None,
) -> CampaignV2ProviderStatsSelection:
    if horizon_hours <= 0:
        raise ValueError("horizon_hours debe ser positivo.")
    if max_campaigns <= 0:
        raise ValueError("max_campaigns debe ser positivo.")

    active_session = session if session is not None else db.session
    cutoff = _normalize_now(now) - timedelta(hours=horizon_hours)

    # Legacy campaigns only: once provider children exist, do not also
    # capture the parent's historical provider binding.
    parent_history = (
        active_session.query(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id.label(
                "campaign_v2_id"
            ),
            func.min(MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at).label(
                "first_fetched_at"
            ),
            func.max(MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at).label(
                "latest_fetched_at"
            ),
        )
        .group_by(MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id)
        .subquery()
    )
    child_exists = (
        active_session.query(MarketingCampaignV2ProviderCampaignORM.id)
        .filter(
            MarketingCampaignV2ProviderCampaignORM.campaign_v2_id
            == MarketingCampaignV2ORM.id
        )
        .exists()
    )
    # Match historical snapshots by external identity as well: snapshots
    # written before the child FK was introduced may have a NULL child FK.
    child_history = (
        active_session.query(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id.label(
                "campaign_v2_id"
            ),
            MarketingCampaignV2ProviderStatsSnapshotORM.provider.label(
                "provider"
            ),
            MarketingCampaignV2ProviderStatsSnapshotORM.provider_campaign_id.label(
                "provider_campaign_id"
            ),
            func.min(MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at).label(
                "first_fetched_at"
            ),
            func.max(MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at).label(
                "latest_fetched_at"
            ),
        )
        .group_by(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id,
            MarketingCampaignV2ProviderStatsSnapshotORM.provider,
            MarketingCampaignV2ProviderStatsSnapshotORM.provider_campaign_id,
        )
        .subquery()
    )
    with active_session.no_autoflush:
        legacy_rows = (
            active_session.query(
                MarketingCampaignV2ORM.id,
                parent_history.c.first_fetched_at,
                parent_history.c.latest_fetched_at,
            )
            .outerjoin(
                parent_history,
                parent_history.c.campaign_v2_id == MarketingCampaignV2ORM.id,
            )
            .filter(
                MarketingCampaignV2ORM.provider.isnot(None),
                MarketingCampaignV2ORM.provider_campaign_id.isnot(None),
                ~child_exists,
            )
            .all()
        )
        child_rows = (
            active_session.query(
                MarketingCampaignV2ProviderCampaignORM.id.label("child_id"),
                MarketingCampaignV2ProviderCampaignORM.campaign_v2_id.label(
                    "campaign_id"
                ),
                child_history.c.first_fetched_at,
                child_history.c.latest_fetched_at,
            )
            .outerjoin(
                child_history,
                and_(
                    child_history.c.campaign_v2_id
                    == MarketingCampaignV2ProviderCampaignORM.campaign_v2_id,
                    child_history.c.provider
                    == MarketingCampaignV2ProviderCampaignORM.provider,
                    child_history.c.provider_campaign_id
                    == MarketingCampaignV2ProviderCampaignORM.provider_campaign_id,
                ),
            )
            .filter(
                MarketingCampaignV2ProviderCampaignORM.status.in_(
                    ("SUBMITTED", "SCHEDULED")
                ),
                MarketingCampaignV2ProviderCampaignORM.provider.isnot(None),
                MarketingCampaignV2ProviderCampaignORM.provider_campaign_id.isnot(None),
            )
            .all()
        )

    # Each tuple is (campaign_id, provider_child_id, first_fetch, last_fetch).
    targets = [
        (int(row.id), None, row.first_fetched_at, row.latest_fetched_at)
        for row in legacy_rows
    ]
    targets.extend(
        (int(row.campaign_id), int(row.child_id),
         row.first_fetched_at, row.latest_fetched_at)
        for row in child_rows
    )
    bound_count = len(targets)
    eligible: list[tuple[int, int | None, datetime | None]] = []
    skipped_outside_horizon = 0
    for campaign_id, child_id, first_value, latest_value in targets:
        first = _normalize_db_datetime(first_value)
        latest = _normalize_db_datetime(latest_value)
        if first is not None and first < cutoff:
            skipped_outside_horizon += 1
            continue
        eligible.append((campaign_id, child_id, latest))

    eligible.sort(
        key=lambda item: (
            item[2] is not None,
            item[2] or datetime.min.replace(tzinfo=timezone.utc),
            item[0],
            item[1] or 0,
        )
    )
    selected = eligible[:max_campaigns]
    return CampaignV2ProviderStatsSelection(
        campaign_ids=tuple(item[0] for item in selected),
        provider_child_ids=tuple(item[1] for item in selected),
        bound_count=bound_count,
        eligible_count=len(eligible),
        skipped_outside_horizon=skipped_outside_horizon,
        skipped_by_limit=max(0, len(eligible) - len(selected)),
    )


def run_campaign_v2_provider_stats_capture_cycle(
    *,
    now: datetime,
    horizon_hours: int,
    max_campaigns: int,
    session=None,
    capture_func: CaptureFunc = capture_campaign_v2_provider_stats_snapshot,
) -> CampaignV2ProviderStatsCycleResult:
    active_session = session if session is not None else db.session

    selection = select_campaign_v2_provider_stats_candidates(
        now=now,
        horizon_hours=horizon_hours,
        max_campaigns=max_campaigns,
        session=active_session,
    )

    created = 0
    unchanged = 0
    failed = 0
    attempted = 0

    child_ids = selection.provider_child_ids or (None,) * len(selection.campaign_ids)
    if len(child_ids) != len(selection.campaign_ids):
        raise ValueError("La selección de provider children es inconsistente.")

    for campaign_id, child_id in zip(selection.campaign_ids, child_ids):
        attempted += 1
        try:
            capture_kwargs = {
                "campaign_id": campaign_id,
                "allowed_sucursal_keys": None,
                "session": active_session,
                "now": _normalize_now(now),
            }
            if child_id is not None:
                capture_kwargs["provider_campaign_child_id"] = child_id
            result = capture_func(**capture_kwargs)
            if result.get("created"):
                created += 1
            else:
                unchanged += 1
        except (
            MarketingCampaignV2ProviderStatsError,
            MarketingCampaignV2ProviderStatsSnapshotPersistenceError,
        ) as exc:
            failed += 1
            active_session.rollback()
            LOGGER.warning(
                "Captura provider stats falló. "
                "campaign_id=%s child_id=%s error_type=%s",
                campaign_id,
                child_id,
                type(exc).__name__,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            active_session.rollback()
            LOGGER.warning(
                "Captura provider stats falló inesperadamente. "
                "campaign_id=%s child_id=%s error_type=%s",
                campaign_id,
                child_id,
                type(exc).__name__,
            )
        finally:
            if session is None:
                db.session.remove()

    return CampaignV2ProviderStatsCycleResult(
        selected=len(selection.campaign_ids),
        attempted=attempted,
        created=created,
        unchanged=unchanged,
        failed=failed,
        skipped=(
            selection.skipped_outside_horizon
            + selection.skipped_by_limit
        ),
    )


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_db_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
