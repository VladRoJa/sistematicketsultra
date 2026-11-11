"""Recover missing iVentas stats for one Campaign V2 without dispatching messages.

Preview by default. --execute performs bounded provider GETs and persists
append-only snapshots using the existing child-scoped capture service.
Run on the existing marketing-scheduler container, not on the Flask web workers.
"""
from __future__ import annotations

import argparse
import logging
import time

from app import create_app
from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2ProviderStatsSnapshotORM as Snapshot,
)
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    capture_campaign_v2_provider_stats_snapshot,
)

LOGGER = logging.getLogger(__name__)


def candidate_children(*, campaign_id: int, session) -> list[tuple[int, str, bool]]:
    rows = (
        session.query(Child)
        .filter(
            Child.campaign_v2_id == campaign_id,
            Child.provider == "IVENTAS",
            Child.status == "SUBMITTED",
            Child.submitted_at.isnot(None),
            Child.provider_campaign_id.isnot(None),
        )
        .order_by(Child.id)
        .all()
    )
    result = []
    for child in rows:
        snapshot_exists = session.query(Snapshot.id).filter(
            Snapshot.campaign_v2_id == campaign_id,
            Snapshot.provider == "IVENTAS",
            Snapshot.provider_campaign_id == child.provider_campaign_id,
        ).first() is not None
        result.append((int(child.id), str(child.sucursal_canon), snapshot_exists))
    return result


def run(*, campaign_id: int, execute: bool, max_children: int,
        delay_seconds: float, session, capture=capture_campaign_v2_provider_stats_snapshot,
        sleeper=time.sleep) -> dict:
    if campaign_id <= 0 or not 1 <= max_children <= 25 or not 0 <= delay_seconds <= 30:
        raise ValueError("Parámetros fuera de rango.")
    rows = candidate_children(campaign_id=campaign_id, session=session)
    pending = [(child_id, branch) for child_id, branch, captured in rows if not captured]
    if len(pending) > max_children:
        raise ValueError(
            f"Hay {len(pending)} children sin captura; usa otra ejecución en grupos "
            "o revisa explícitamente el límite máximo (25)."
        )
    result = dict(campaign_id=campaign_id, submitted=len(rows),
                  already_captured=len(rows)-len(pending), pending=len(pending),
                  attempted=0, created=0, unchanged=0, failed=0, dry_run=not execute)
    print(f"Campaign #{campaign_id}: submitted={len(rows)} "
          f"captured={result['already_captured']} pending={len(pending)}")
    for child_id, branch in pending:
        print(f"child={child_id} branch={branch} action={'GET_STATS' if execute else 'PREVIEW_ONLY'}")
    if not execute:
        return result

    for index, (child_id, _) in enumerate(pending):
        try:
            payload = capture(
                campaign_id=campaign_id,
                child_id=child_id,
                allowed_sucursal_keys=None,
                session=session,
            )
            result["created" if payload.get("created") else "unchanged"] += 1
        except Exception as exc:  # No provider error detail / PII in stdout.
            session.rollback()
            result["failed"] += 1
            LOGGER.warning("Snapshot falló: campaign_id=%s child_id=%s error_type=%s",
                           campaign_id, child_id, type(exc).__name__)
        finally:
            result["attempted"] += 1
            session.remove()  # No transaction spans separate external GETs.
        if index + 1 < len(pending):
            sleeper(delay_seconds)
    print(f"capture summary: created={result['created']} "
          f"unchanged={result['unchanged']} failed={result['failed']}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True, type=int)
    parser.add_argument("--execute", action="store_true",
                        help="Allow provider GET stats and append-only snapshots")
    parser.add_argument("--max-children", type=int, default=12)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        outcome = run(
            campaign_id=args.campaign_id, execute=args.execute,
            max_children=args.max_children, delay_seconds=args.delay_seconds,
            session=db.session,
        )
        if outcome["failed"]:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
