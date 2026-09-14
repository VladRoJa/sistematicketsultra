from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketingReactivationCampaignRecipientOutcomeORM(db.Model):
    __tablename__ = "marketing_reactivation_campaign_recipient_outcomes"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_recipient_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_reactivation_campaign_recipients.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )
    status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING",
    )
    reactivated_at_local = db.Column(
        db.DateTime(timezone=False),
        nullable=True,
    )
    active_snapshot_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "socios_activos_snapshots.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    active_snapshot_row_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "socios_activos_snapshot_rows.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    active_id_socio = db.Column(db.String(64), nullable=True)
    active_sucursal = db.Column(db.String(255), nullable=True)
    review_reason = db.Column(db.String(100), nullable=True)
    first_detected_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    last_checked_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    recipient = db.relationship(
        "MarketingReactivationCampaignRecipientORM",
    )
    active_snapshot = db.relationship("SociosActivosSnapshotORM")
    active_snapshot_row = db.relationship("SociosActivosSnapshotRowORM")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('PENDING', 'REACTIVATED', 'REVIEW', 'WINDOW_CLOSED')",
            name="ck_marketing_reactivation_outcomes_status",
        ),
        db.CheckConstraint(
            "status <> 'REACTIVATED' OR ("
            "reactivated_at_local IS NOT NULL "
            "AND active_snapshot_id IS NOT NULL "
            "AND active_snapshot_row_id IS NOT NULL "
            "AND active_id_socio IS NOT NULL"
            ")",
            name="ck_marketing_reactivation_outcomes_evidence",
        ),
        db.Index(
            "ix_marketing_reactivation_outcomes_status",
            "status",
        ),
        db.Index(
            "ix_marketing_reactivation_outcomes_active_id_socio",
            "active_id_socio",
        ),
    )
