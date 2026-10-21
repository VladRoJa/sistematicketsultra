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
    # (parent_campaign_id, child_id); None preserves legacy parent-bound capture.
    targets: tuple[tuple[int, int | None], ...] = ()


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
    now_utc = _normalize_now(now)
    cutoff = now_utc - timedelta(hours=horizon_hours)

    # Snapshot identity includes the provider campaign: siblings cannot share
    # the same freshness/horizon state.
    aggregate = (
        active_session.query(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id.label("campaign_v2_id"),
            MarketingCampaignV2ProviderStatsSnapshotORM.provider_campaign_id.label("provider_campaign_id"),
            func.min(MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at).label("first_fetched_at"),
            func.max(MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at).label("latest_fetched_at"),
        )
        .group_by(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id,
            MarketingCampaignV2ProviderStatsSnapshotORM.provider_campaign_id,
        )
        .subquery()
    )
    with active_session.no_autoflush:
        parent_rows = (
            active_session.query(
                MarketingCampaignV2ORM.id,
                aggregate.c.first_fetched_at,
                aggregate.c.latest_fetched_at,
            )
            .outerjoin(aggregate, and_(
                aggregate.c.campaign_v2_id == MarketingCampaignV2ORM.id,
                aggregate.c.provider_campaign_id == MarketingCampaignV2ORM.provider_campaign_id,
            ))
            .filter(
                MarketingCampaignV2ORM.provider.isnot(None),
                MarketingCampaignV2ORM.provider_campaign_id.isnot(None),
            )
            .all()
        )
        child_rows = (
            active_session.query(
                MarketingCampaignV2ProviderCampaignORM.id.label("child_id"),
                MarketingCampaignV2ProviderCampaignORM.campaign_v2_id,
                aggregate.c.first_fetched_at,
                aggregate.c.latest_fetched_at,
            )
            .join(
                MarketingCampaignV2ORM,
                MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == MarketingCampaignV2ORM.id,
            )
            .outerjoin(aggregate, and_(
                aggregate.c.campaign_v2_id == MarketingCampaignV2ProviderCampaignORM.campaign_v2_id,
                aggregate.c.provider_campaign_id == MarketingCampaignV2ProviderCampaignORM.provider_campaign_id,
            ))
            .filter(
                MarketingCampaignV2ORM.provider.is_(None),
                MarketingCampaignV2ORM.provider_campaign_id.is_(None),
                MarketingCampaignV2ProviderCampaignORM.provider == "IVENTAS",
                MarketingCampaignV2ProviderCampaignORM.status == "SUBMITTED",
                MarketingCampaignV2ProviderCampaignORM.provider_campaign_id.isnot(None),
                MarketingCampaignV2ProviderCampaignORM.submitted_at.isnot(None),
                MarketingCampaignV2ProviderCampaignORM.submitted_at <= now_utc,
            )
            .all()
        )

    # max_campaigns is one common outbound provider-fetch budget for both kinds.
    bound_count = len(parent_rows) + len(child_rows)
    eligible: list[tuple[tuple[int, int | None], datetime | None]] = []
    skipped_outside_horizon = 0
    for row in parent_rows:
        first = _normalize_db_datetime(row.first_fetched_at)
        if first is not None and first < cutoff:
            skipped_outside_horizon += 1
            continue
        eligible.append((
            (int(row.id), None), _normalize_db_datetime(row.latest_fetched_at),
        ))
    for row in child_rows:
        first = _normalize_db_datetime(row.first_fetched_at)
        if first is not None and first < cutoff:
            skipped_outside_horizon += 1
            continue
        eligible.append((
            (int(row.campaign_v2_id), int(row.child_id)),
            _normalize_db_datetime(row.latest_fetched_at),
        ))

    eligible.sort(key=lambda item: (
        item[1] is not None,
        item[1] or datetime.min.replace(tzinfo=timezone.utc),
        item[0][0],
        item[0][1] or 0,
    ))
    targets = tuple(key for key, _ in eligible[:max_campaigns])
    return CampaignV2ProviderStatsSelection(
        campaign_ids=tuple(campaign for campaign, child in targets if child is None),
        bound_count=bound_count,
        eligible_count=len(eligible),
        skipped_outside_horizon=skipped_outside_horizon,
        skipped_by_limit=max(0, len(eligible) - len(targets)),
        targets=targets,
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

    # Injected legacy selections without targets remain compatible.
    targets = selection.targets or tuple(
        (campaign_id, None) for campaign_id in selection.campaign_ids
    )
    for campaign_id, child_id in targets:
        attempted += 1
        try:
            kwargs = {
                "campaign_id": campaign_id,
                "allowed_sucursal_keys": None,
                "session": active_session,
                "now": _normalize_now(now),
            }
            if child_id is not None:
                kwargs["child_id"] = child_id
            result = capture_func(**kwargs)
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
        selected=len(targets),
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
