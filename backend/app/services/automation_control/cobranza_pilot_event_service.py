"""Read-only operator event from durable Campaign V2 data; no extra event table."""
from __future__ import annotations

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2ProviderCampaignORM as Child,
)
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as Job,
)


def read_cobranza_pilot_event() -> dict | None:
    # Deliberately only the single approved pilot; no historical branch disclosure.
    candidates = (
        db.session.query(Campaign)
        .filter(Campaign.name == "COBRANZA RECURRENTE RECHAZADOS - 2026-11-12")
        .order_by(Campaign.id.desc()).limit(3).all()
    )
    for campaign in candidates:
        meta = (campaign.audience_definition_json or {}).get("source_metadata") or {}
        if (
            meta.get("automation_job") != "cobranza_recurrente_rechazados"
            or meta.get("pilot_branch_key") != "VILLAS_DEL_REY"
            or meta.get("auto_pilot_date") != "2026-11-12"
        ):
            continue
        job = (
            db.session.query(Job).filter(Job.campaign_v2_id == campaign.id)
            .order_by(Job.id.desc()).first()
        )
        children = (
            db.session.query(Child).filter(Child.campaign_v2_id == campaign.id).all()
        )
        recipients = db.session.query(Recipient.id).filter(
            Recipient.campaign_id == campaign.id
        ).count()
        accepted = sum(int(child.recipient_count) for child in children
                       if child.status == "SUBMITTED" and child.provider_campaign_id)
        stage = ("AUTO_SEND_BLOCKED" if meta.get("auto_pilot_blocked") else "PREPARED") if job is None else job.status
        return {
            "event_id": f"cobranza:{campaign.id}:{stage}:{accepted}",
            "campaign_id": int(campaign.id),
            "business_date": "2026-11-12",
            "branch": "VILLAS_DEL_REY",
            "recipient_count": int(recipients),
            "accepted_count": accepted,
            "stage": stage,
            "has_job": job is not None,
        }
    return None
