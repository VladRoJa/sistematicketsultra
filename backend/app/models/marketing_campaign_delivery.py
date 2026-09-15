from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketingReactivationCampaignBranchSendORM(db.Model):
    __tablename__ = "marketing_reactivation_campaign_branch_sends"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_reactivation_campaigns.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    sucursal = db.Column(db.String(255), nullable=False)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=False)
    sent_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    campaign = db.relationship("MarketingReactivationCampaignORM")
    sent_by_user = db.relationship("UserORM")

    __table_args__ = (
        db.UniqueConstraint(
            "campaign_id",
            "sucursal",
            name="uq_marketing_reactivation_branch_send_campaign_branch",
        ),
        db.Index(
            "ix_marketing_reactivation_branch_send_campaign_id",
            "campaign_id",
        ),
        db.Index(
            "ix_marketing_reactivation_branch_send_sent_at",
            "sent_at",
        ),
    )
