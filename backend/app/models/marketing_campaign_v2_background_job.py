"""Issue #1129 M1a: durable background dispatch mandates and audit events.

Schema only. This module never stores credentials or invokes iVentas.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utc_now():
    return datetime.now(timezone.utc)


class MarketingCampaignV2BackgroundJobORM(db.Model):
    __tablename__ = "marketing_campaign_v2_background_jobs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_v2_id = db.Column(
        db.BigInteger, db.ForeignKey("marketing_campaign_v2_campaigns.id", ondelete="RESTRICT"),
        nullable=False)
    approval_id = db.Column(
        db.BigInteger, db.ForeignKey("marketing_campaign_v2_dispatch_approvals.id", ondelete="RESTRICT"),
        nullable=False)
    execution_id = db.Column(
        db.BigInteger, db.ForeignKey("marketing_campaign_v2_governed_executions.id", ondelete="RESTRICT"),
        nullable=False)
    operator_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    # Idempotency is an identifier, never an authorization credential.
    request_key = db.Column(db.String(64), nullable=False)
    manifest_digest = db.Column(db.String(64), nullable=False)
    pending_child_ids = db.Column(db.JSON, nullable=False)
    pending_children_digest = db.Column(db.String(64), nullable=False)
    initial_pending_count = db.Column(db.Integer, nullable=False)

    status = db.Column(db.String(24), nullable=False, default="QUEUED", server_default="QUEUED")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=_utc_now, server_default=db.text("CURRENT_TIMESTAMP"))
    start_deadline_at = db.Column(db.DateTime(timezone=True), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    stop_requested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=_utc_now, server_default=db.text("CURRENT_TIMESTAMP"))
    current_child_id = db.Column(
        db.BigInteger, db.ForeignKey("marketing_campaign_v2_provider_campaigns.id", ondelete="RESTRICT"),
        nullable=True)
    last_accepted_child_id = db.Column(
        db.BigInteger, db.ForeignKey("marketing_campaign_v2_provider_campaigns.id", ondelete="RESTRICT"),
        nullable=True)
    # No worker is registered or started in M1a.
    worker_instance_id = db.Column(db.String(64), nullable=True)
    worker_claim_generation = db.Column(db.Integer, nullable=False,
                                        default=0, server_default="0")
    worker_lease_until = db.Column(db.DateTime(timezone=True), nullable=True)
    stop_reason_code = db.Column(db.String(64), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uq_mkt_v2_bg_jobs_execution"),
        db.UniqueConstraint("approval_id", name="uq_mkt_v2_bg_jobs_approval"),
        db.UniqueConstraint("request_key", name="uq_mkt_v2_bg_jobs_request_key"),
        db.CheckConstraint(
            "status IN ('QUEUED','RUNNING','STOP_REQUESTED','STOPPED','COMPLETED','REVIEW_REQUIRED')",
            name="ck_mkt_v2_bg_jobs_status"),
        db.CheckConstraint("initial_pending_count BETWEEN 1 AND 30",
                           name="ck_mkt_v2_bg_jobs_pending_count"),
        db.CheckConstraint("length(manifest_digest) = 64 AND "
                           "length(pending_children_digest) = 64 AND length(request_key) = 64",
                           name="ck_mkt_v2_bg_jobs_digests"),
        db.CheckConstraint("worker_claim_generation >= 0",
                           name="ck_mkt_v2_bg_jobs_claim_generation"),
        # Also blocks fresh approval when an earlier send is uncertain.
        db.Index("uq_mkt_v2_bg_jobs_campaign_active", "campaign_v2_id", unique=True,
                 postgresql_where=db.text(
                     "status IN ('QUEUED','RUNNING','STOP_REQUESTED','REVIEW_REQUIRED')"),
                 sqlite_where=db.text(
                     "status IN ('QUEUED','RUNNING','STOP_REQUESTED','REVIEW_REQUIRED')")),
        db.Index("ix_mkt_v2_bg_jobs_campaign_created", "campaign_v2_id", "created_at"),
        db.Index("ix_mkt_v2_bg_jobs_status_lease", "status", "worker_lease_until"),
    )


class MarketingCampaignV2BackgroundJobEventORM(db.Model):
    """Append-only audit events (enforced by future service write paths)."""

    __tablename__ = "marketing_campaign_v2_background_job_events"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_id = db.Column(
        db.BigInteger, db.ForeignKey("marketing_campaign_v2_background_jobs.id", ondelete="RESTRICT"),
        nullable=False)
    event_no = db.Column(db.Integer, nullable=False)
    event_kind = db.Column(db.String(30), nullable=False)
    actor_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    child_id = db.Column(
        db.BigInteger, db.ForeignKey("marketing_campaign_v2_provider_campaigns.id", ondelete="RESTRICT"),
        nullable=True)
    reason_code = db.Column(db.String(64), nullable=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False,
                            default=_utc_now, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.UniqueConstraint("job_id", "event_no", name="uq_mkt_v2_bg_job_events_sequence"),
        db.CheckConstraint("event_no > 0", name="ck_mkt_v2_bg_job_events_sequence"),
        db.CheckConstraint(
            "event_kind IN ('ENQUEUED','STARTED','CHILD_ACCEPTED','STOP_REQUESTED',"
            "'STOPPED','COMPLETED','REVIEW_REQUIRED')",
            name="ck_mkt_v2_bg_job_events_kind"),
        db.Index("ix_mkt_v2_bg_job_events_job_time", "job_id", "occurred_at"),
    )
