"""Issue #1129 M1a: add durable governed background jobs; never send.

Revision ID: n26c10202626
Revises: v2e3a1102626
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "n26c10202626"
down_revision = "v2e3a1102626"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_background_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("campaign_v2_id", sa.BigInteger(), nullable=False),
        sa.Column("approval_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=False),
        sa.Column("operator_user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("manifest_digest", sa.String(length=64), nullable=False),
        sa.Column("pending_child_ids", sa.JSON(), nullable=False),
        sa.Column("pending_children_digest", sa.String(length=64), nullable=False),
        sa.Column("initial_pending_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("start_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("current_child_id", sa.BigInteger(), nullable=True),
        sa.Column("last_accepted_child_id", sa.BigInteger(), nullable=True),
        sa.Column("worker_instance_id", sa.String(length=64), nullable=True),
        sa.Column("worker_claim_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason_code", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["campaign_v2_id"], ["marketing_campaign_v2_campaigns.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_id"], ["marketing_campaign_v2_dispatch_approvals.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["execution_id"], ["marketing_campaign_v2_governed_executions.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["current_child_id"],
                                ["marketing_campaign_v2_provider_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["last_accepted_child_id"],
                                ["marketing_campaign_v2_provider_campaigns.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("execution_id", name="uq_mkt_v2_bg_jobs_execution"),
        sa.UniqueConstraint("approval_id", name="uq_mkt_v2_bg_jobs_approval"),
        sa.UniqueConstraint("request_key", name="uq_mkt_v2_bg_jobs_request_key"),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','STOP_REQUESTED','STOPPED','COMPLETED','REVIEW_REQUIRED')",
            name="ck_mkt_v2_bg_jobs_status"),
        sa.CheckConstraint("initial_pending_count BETWEEN 1 AND 30",
                           name="ck_mkt_v2_bg_jobs_pending_count"),
        sa.CheckConstraint("length(manifest_digest) = 64 AND "
                           "length(pending_children_digest) = 64 AND length(request_key) = 64",
                           name="ck_mkt_v2_bg_jobs_digests"),
        sa.CheckConstraint("worker_claim_generation >= 0",
                           name="ck_mkt_v2_bg_jobs_claim_generation"),
    )
    op.create_index(
        "uq_mkt_v2_bg_jobs_campaign_active",
        "marketing_campaign_v2_background_jobs", ["campaign_v2_id"], unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING','STOP_REQUESTED','REVIEW_REQUIRED')"),
        sqlite_where=sa.text("status IN ('QUEUED','RUNNING','STOP_REQUESTED','REVIEW_REQUIRED')"))
    op.create_index("ix_mkt_v2_bg_jobs_campaign_created",
                    "marketing_campaign_v2_background_jobs", ["campaign_v2_id", "created_at"])
    op.create_index("ix_mkt_v2_bg_jobs_status_lease",
                    "marketing_campaign_v2_background_jobs", ["status", "worker_lease_until"])

    op.create_table(
        "marketing_campaign_v2_background_job_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("event_no", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("child_id", sa.BigInteger(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["marketing_campaign_v2_background_jobs.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["child_id"],
                                ["marketing_campaign_v2_provider_campaigns.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("job_id", "event_no", name="uq_mkt_v2_bg_job_events_sequence"),
        sa.CheckConstraint("event_no > 0", name="ck_mkt_v2_bg_job_events_sequence"),
        sa.CheckConstraint(
            "event_kind IN ('ENQUEUED','STARTED','CHILD_ACCEPTED','STOP_REQUESTED',"
            "'STOPPED','COMPLETED','REVIEW_REQUIRED')",
            name="ck_mkt_v2_bg_job_events_kind"))
    op.create_index("ix_mkt_v2_bg_job_events_job_time",
                    "marketing_campaign_v2_background_job_events", ["job_id", "occurred_at"])


def downgrade():
    # Never erase provider uncertainty or audit evidence with an automatic rollback.
    bind = op.get_bind()
    for table in (
        "marketing_campaign_v2_background_job_events",
        "marketing_campaign_v2_background_jobs",
    ):
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)")).scalar_one():
            raise RuntimeError("No se puede perder el historial de envíos en segundo plano.")
    op.drop_index("ix_mkt_v2_bg_job_events_job_time",
                  table_name="marketing_campaign_v2_background_job_events")
    op.drop_table("marketing_campaign_v2_background_job_events")
    op.drop_index("uq_mkt_v2_bg_jobs_campaign_active",
                  table_name="marketing_campaign_v2_background_jobs")
    op.drop_index("ix_mkt_v2_bg_jobs_status_lease",
                  table_name="marketing_campaign_v2_background_jobs")
    op.drop_index("ix_mkt_v2_bg_jobs_campaign_created",
                  table_name="marketing_campaign_v2_background_jobs")
    op.drop_table("marketing_campaign_v2_background_jobs")
