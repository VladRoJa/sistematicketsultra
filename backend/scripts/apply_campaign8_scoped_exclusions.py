"""Guarded one-time operation for Campaign V2 #8.

Run from /app in backend container after deploying the migration:
    python scripts/apply_campaign8_scoped_exclusions.py
    python scripts/apply_campaign8_scoped_exclusions.py --apply

No provider API calls. Without --apply, no writes.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.models.user_model import UserORM
from app.services.marketing_campaign_v2_dispatch_exclusion_service import (
    add_campaign_v2_ambiguous_branch_exclusions,
    get_campaign_v2_excluded_recipient_ids,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)

CAMPAIGN_ID = 8
CAMPAIGN_NAME = "Socios activos/venta nueva invita y gana"
FROZEN_COUNT = 14002
EXPECTED = {
    59510: {"INDEPENDENCIA", "SEND MXL"},
    59859: {"INDEPENDENCIA", "TEC MXL"},
    60120: {"INDEPENDENCIA", "TEC MXL"},
}
ACTOR = "admicorp"


def run(*, apply: bool) -> None:
    app = create_app()
    with app.app_context():
        try:
            campaign = db.session.get(MarketingCampaignV2ORM, CAMPAIGN_ID)
            if (
                campaign is None
                or campaign.name != CAMPAIGN_NAME
                or campaign.frozen_at is None
            ):
                raise RuntimeError("Campaign 8 identity/freeze mismatch; abort.")
            all_count = db.session.query(MarketingCampaignV2RecipientORM).filter(
                MarketingCampaignV2RecipientORM.campaign_id == CAMPAIGN_ID
            ).count()
            if all_count != FROZEN_COUNT:
                raise RuntimeError("Frozen cohort no longer equals 14002; abort.")
            has_child = db.session.query(MarketingCampaignV2ProviderCampaignORM.id).filter(
                MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == CAMPAIGN_ID
            ).first()
            if has_child:
                raise RuntimeError("Provider children already exist; abort.")
            existing = get_campaign_v2_excluded_recipient_ids(
                campaign_id=CAMPAIGN_ID, session=db.session,
            )
            if existing - set(EXPECTED):
                raise RuntimeError("Unexpected pre-existing exclusions; abort.")
            for recipient_id, expected_keys in EXPECTED.items():
                row = db.session.query(MarketingCampaignV2RecipientORM).filter(
                    MarketingCampaignV2RecipientORM.id == recipient_id,
                    MarketingCampaignV2RecipientORM.campaign_id == CAMPAIGN_ID,
                ).one()
                if row.sucursal is not None:
                    raise RuntimeError(f"Recipient {recipient_id} has assigned branch; abort.")
                keys = {
                    key
                    for evidence in row.evidence_rows
                    if (key := normalize_socios_vencidos_branch_key(evidence.sucursal_key))
                }
                if keys != expected_keys:
                    raise RuntimeError(f"Evidence changed for recipient {recipient_id}; abort.")

            print("CAMPAIGN_ID =", CAMPAIGN_ID)
            print("FROZEN =", all_count)
            print("EXPECTED_SCOPED_EXCLUSIONS =", len(EXPECTED))
            print("ALREADY_EXCLUDED =", len(existing))
            print("ACTION =", "APPLY" if apply else "DRY_RUN")
            if apply:
                actor = UserORM.get_by_username(ACTOR)
                if actor is None:
                    raise RuntimeError("Actor admicorp not found; abort.")
                result = add_campaign_v2_ambiguous_branch_exclusions(
                    campaign_id=CAMPAIGN_ID,
                    recipient_ids=tuple(sorted(EXPECTED)),
                    actor_user_id=int(actor.id),
                    allowed_sucursal_keys=None,
                    session=db.session,
                )
                db.session.commit()
                print("ADDED =", result["added"])
                print("EXCLUSIONS_AFTER =", len(
                    get_campaign_v2_excluded_recipient_ids(
                        campaign_id=CAMPAIGN_ID, session=db.session,
                    )
                ))
            else:
                db.session.rollback()
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campaign 8 only; does not submit messages")
    parser.add_argument("--apply", action="store_true")
    run(apply=parser.parse_args().apply)
