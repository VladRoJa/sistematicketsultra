"""add structured attendance and sports analysis marts

Revision ID: d1a7f3c9e5b2
Revises: cca2b3c4d5e6
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa


revision = "d1a7f3c9e5b2"
down_revision = "cca2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "warehouse_attendance_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="RUNNING", nullable=False),
        sa.Column("trigger_source", sa.String(length=40), server_default="MANUAL_FILE", nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=32), server_default="v1", nullable=False),
        sa.Column("source_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("inserted_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCESS', 'FAILED')",
            name="ck_wh_attendance_runs_status",
        ),
        sa.CheckConstraint(
            "source_rows >= 0 AND inserted_rows >= 0 AND updated_rows >= 0 AND rejected_rows >= 0",
            name="ck_wh_attendance_runs_nonnegative_counts",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wh_attendance_runs_date_status",
        "warehouse_attendance_runs",
        ["business_date", "status"],
        unique=False,
    )

    op.create_table(
        "warehouse_attendance_visits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=True),
        sa.Column("source_branch_name", sa.String(length=255), nullable=False),
        sa.Column("member_pin", sa.String(length=64), nullable=True),
        sa.Column("entered_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("visit_status", sa.String(length=24), nullable=False),
        sa.Column("age", sa.SmallInteger(), nullable=True),
        sa.Column("age_is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("city", sa.String(length=160), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("member_since", sa.Date(), nullable=True),
        sa.Column("attendance_type", sa.String(length=100), nullable=False),
        sa.Column("has_opening", sa.Boolean(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("last_run_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "visit_status IN ('CLOSED', 'OPEN', 'INVALID_TIME', 'CROSS_DAY')",
            name="ck_wh_attendance_visits_status",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_wh_attendance_visits_duration",
        ),
        sa.ForeignKeyConstraint(
            ["last_run_id"],
            ["warehouse_attendance_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_fingerprint",
            name="uq_wh_attendance_visits_fingerprint",
        ),
    )
    op.create_index(
        "ix_wh_attendance_visits_date_branch_type",
        "warehouse_attendance_visits",
        ["business_date", "sucursal_id", "attendance_type"],
        unique=False,
    )
    op.create_index(
        "ix_wh_attendance_visits_pin_date",
        "warehouse_attendance_visits",
        ["member_pin", "business_date"],
        unique=False,
    )
    op.create_index(
        "ix_wh_attendance_visits_entered_at",
        "warehouse_attendance_visits",
        ["entered_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_wh_attendance_visits_date_status",
        "warehouse_attendance_visits",
        ["business_date", "visit_status"],
        unique=False,
    )

    op.create_table(
        "warehouse_attendance_rejections",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("member_pin", sa.String(length=64), nullable=True),
        sa.Column("source_branch_name", sa.String(length=255), nullable=True),
        sa.Column("entered_at_raw", sa.String(length=100), nullable=True),
        sa.Column("attendance_type_raw", sa.String(length=100), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["warehouse_attendance_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wh_attendance_rejections_run",
        "warehouse_attendance_rejections",
        ["run_id", "source_row_number"],
        unique=False,
    )

    op.create_table(
        "track_attendance_interval_mart",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("attendance_type", sa.String(length=100), nullable=False),
        sa.Column("bucket_minute", sa.SmallInteger(), nullable=False),
        sa.Column("entries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("exits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("occupancy", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unique_entries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_run_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "bucket_minute >= 0 AND bucket_minute < 1440",
            name="ck_track_att_interval_bucket_minute",
        ),
        sa.CheckConstraint(
            "bucket_minute % 15 = 0",
            name="ck_track_att_interval_bucket_15m",
        ),
        sa.CheckConstraint(
            "entries >= 0 AND exits >= 0 AND occupancy >= 0 AND unique_entries >= 0",
            name="ck_track_att_interval_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["warehouse_attendance_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_date",
            "sucursal_id",
            "attendance_type",
            "bucket_minute",
            name="uq_track_att_interval_date_branch_type_bucket",
        ),
    )
    op.create_index(
        "ix_track_att_interval_date_branch",
        "track_attendance_interval_mart",
        ["business_date", "sucursal_id"],
        unique=False,
    )

    op.create_table(
        "track_attendance_daily_mart",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("attendance_type", sa.String(length=100), nullable=False),
        sa.Column("visits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unique_members", sa.Integer(), server_default="0", nullable=False),
        sa.Column("closed_visits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("open_visits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cross_day_visits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_time_visits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("average_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("median_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("peak_occupancy", sa.Integer(), server_default="0", nullable=False),
        sa.Column("peak_minute", sa.SmallInteger(), nullable=True),
        sa.Column("source_run_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            """
            visits >= 0
            AND unique_members >= 0
            AND closed_visits >= 0
            AND open_visits >= 0
            AND cross_day_visits >= 0
            AND invalid_time_visits >= 0
            AND peak_occupancy >= 0
            """,
            name="ck_track_att_daily_nonnegative",
        ),
        sa.CheckConstraint(
            "peak_minute IS NULL OR (peak_minute >= 0 AND peak_minute < 1440)",
            name="ck_track_att_daily_peak_minute",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["warehouse_attendance_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_date",
            "sucursal_id",
            "attendance_type",
            name="uq_track_att_daily_date_branch_type",
        ),
    )
    op.create_index(
        "ix_track_att_daily_date_branch",
        "track_attendance_daily_mart",
        ["business_date", "sucursal_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_track_att_daily_date_branch",
        table_name="track_attendance_daily_mart",
    )
    op.drop_table("track_attendance_daily_mart")

    op.drop_index(
        "ix_track_att_interval_date_branch",
        table_name="track_attendance_interval_mart",
    )
    op.drop_table("track_attendance_interval_mart")

    op.drop_index(
        "ix_wh_attendance_rejections_run",
        table_name="warehouse_attendance_rejections",
    )
    op.drop_table("warehouse_attendance_rejections")

    op.drop_index(
        "ix_wh_attendance_visits_date_status",
        table_name="warehouse_attendance_visits",
    )
    op.drop_index(
        "ix_wh_attendance_visits_entered_at",
        table_name="warehouse_attendance_visits",
    )
    op.drop_index(
        "ix_wh_attendance_visits_pin_date",
        table_name="warehouse_attendance_visits",
    )
    op.drop_index(
        "ix_wh_attendance_visits_date_branch_type",
        table_name="warehouse_attendance_visits",
    )
    op.drop_table("warehouse_attendance_visits")

    op.drop_index(
        "ix_wh_attendance_runs_date_status",
        table_name="warehouse_attendance_runs",
    )
    op.drop_table("warehouse_attendance_runs")
