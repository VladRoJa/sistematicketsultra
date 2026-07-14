"""add routine control run models

Revision ID: ce7b7ce5ae0e
Revises: 9a2b3c4d5e6f
Create Date: 2026-07-14 07:52:41.302435

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ce7b7ce5ae0e"
down_revision = "9a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "routine_control_pipeline_runs",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column(
            "generation_mode",
            sa.String(length=40),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "trigger_source",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "retry_of_pipeline_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "root_pipeline_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "replaces_pipeline_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "current_stage",
            sa.String(length=80),
            nullable=True,
        ),
        sa.Column(
            "worker_instance_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "heartbeat_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "started_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finished_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cancellation_requested_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cancellation_requested_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "cancellation_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "members_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "members_updated",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "evidences_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "evidences_updated",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "status_changes",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "incidents_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "incidents_reopened",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "records_rejected",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "records_excluded",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "error_code",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            """
            generation_mode IN (
                'SCHEDULED',
                'MANUAL',
                'BACKFILL',
                'RETRY'
            )
            """,
            name="ck_routine_control_pipeline_runs_generation_mode",
        ),
        sa.CheckConstraint(
            """
            status IN (
                'PENDING',
                'RUNNING',
                'SUCCESS',
                'PARTIAL',
                'FAILED',
                'CANCELLED',
                'REPLACED'
            )
            """,
            name="ck_routine_control_pipeline_runs_status",
        ),
        sa.CheckConstraint(
            """
            members_created >= 0
            AND members_updated >= 0
            AND evidences_created >= 0
            AND evidences_updated >= 0
            AND status_changes >= 0
            AND incidents_created >= 0
            AND incidents_reopened >= 0
            AND records_rejected >= 0
            AND records_excluded >= 0
            """,
            name="ck_routine_control_pipeline_runs_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_routine_control_pipeline_runs_attempt_number",
        ),
        sa.CheckConstraint(
            "date_from <= date_to",
            name="ck_routine_control_pipeline_runs_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_rc_pipeline_runs_requested_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cancellation_requested_by_user_id"],
            ["users.id"],
            name="fk_rc_pipeline_runs_cancelled_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_pipeline_run_id"],
            ["routine_control_pipeline_runs.id"],
            name="fk_rc_pipeline_runs_retry_of",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["root_pipeline_run_id"],
            ["routine_control_pipeline_runs.id"],
            name="fk_rc_pipeline_runs_root",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["replaces_pipeline_run_id"],
            ["routine_control_pipeline_runs.id"],
            name="fk_rc_pipeline_runs_replaces",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_routine_control_pipeline_runs",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_routine_control_pipeline_runs_idempotency_key",
        ),
    )

    op.create_index(
        "ix_routine_control_pipeline_runs_business_date_status",
        "routine_control_pipeline_runs",
        ["business_date", "status"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_pipeline_runs_root_pipeline_run_id",
        "routine_control_pipeline_runs",
        ["root_pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_pipeline_runs_status_created_at",
        "routine_control_pipeline_runs",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "routine_control_provider_runs",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "pipeline_run_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "provider_key",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "dataset_key",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "last_attempt_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "next_attempt_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "started_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finished_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "raw_warehouse_upload_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "diagnostic_artifact_path",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "records_received",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "records_valid",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "records_rejected",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "records_excluded",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "records_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "records_updated",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "error_code",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            """
            dataset_key IN (
                'new_members',
                'routine_assignments'
            )
            """,
            name="ck_routine_control_provider_runs_dataset_key",
        ),
        sa.CheckConstraint(
            """
            status IN (
                'PENDING',
                'RUNNING',
                'SUCCESS',
                'SUCCESS_EMPTY',
                'PARTIAL',
                'FAILED',
                'BLOCKED',
                'CANCELLED'
            )
            """,
            name="ck_routine_control_provider_runs_status",
        ),
        sa.CheckConstraint(
            """
            records_received >= 0
            AND records_valid >= 0
            AND records_rejected >= 0
            AND records_excluded >= 0
            AND records_created >= 0
            AND records_updated >= 0
            """,
            name="ck_routine_control_provider_runs_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_routine_control_provider_runs_attempt_count",
        ),
        sa.CheckConstraint(
            "date_from <= date_to",
            name="ck_routine_control_provider_runs_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["routine_control_pipeline_runs.id"],
            name="fk_rc_provider_runs_pipeline_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_warehouse_upload_id"],
            ["warehouse_uploads.id"],
            name="fk_rc_provider_runs_warehouse_upload_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_routine_control_provider_runs",
        ),
        sa.UniqueConstraint(
            "pipeline_run_id",
            "provider_key",
            "dataset_key",
            name="uq_routine_control_provider_runs_pipeline_provider_dataset",
        ),
    )

    op.create_index(
        "ix_routine_control_provider_runs_pipeline_run_id",
        "routine_control_provider_runs",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_provider_runs_provider_dataset_status",
        "routine_control_provider_runs",
        ["provider_key", "dataset_key", "status"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_provider_runs_status_created_at",
        "routine_control_provider_runs",
        ["status", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_routine_control_provider_runs_status_created_at",
        table_name="routine_control_provider_runs",
    )
    op.drop_index(
        "ix_routine_control_provider_runs_provider_dataset_status",
        table_name="routine_control_provider_runs",
    )
    op.drop_index(
        "ix_routine_control_provider_runs_pipeline_run_id",
        table_name="routine_control_provider_runs",
    )
    op.drop_table("routine_control_provider_runs")

    op.drop_index(
        "ix_routine_control_pipeline_runs_status_created_at",
        table_name="routine_control_pipeline_runs",
    )
    op.drop_index(
        "ix_routine_control_pipeline_runs_root_pipeline_run_id",
        table_name="routine_control_pipeline_runs",
    )
    op.drop_index(
        "ix_routine_control_pipeline_runs_business_date_status",
        table_name="routine_control_pipeline_runs",
    )
    op.drop_table("routine_control_pipeline_runs")
