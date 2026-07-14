"""add routine control members and evidences

Revision ID: f6740e2f5d25
Revises: ce7b7ce5ae0e
Create Date: 2026-07-14 09:44:32.396159

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f6740e2f5d25"
down_revision = "ce7b7ce5ae0e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "routine_control_members",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "source_system",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "source_record_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "source_identity_key",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "external_member_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "external_sale_id",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column(
            "sucursal_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "source_branch_name",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "member_name",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "email_original",
            sa.String(length=320),
            nullable=True,
        ),
        sa.Column(
            "email_normalized",
            sa.String(length=320),
            nullable=True,
        ),
        sa.Column(
            "sale_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "cohort_month",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "classification_status",
            sa.String(length=32),
            server_default="CLASSIFIED",
            nullable=False,
        ),
        sa.Column(
            "current_status",
            sa.String(length=32),
            server_default="SIN_RUTINA",
            nullable=True,
        ),
        sa.Column(
            "status_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "first_routine_at",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "latest_routine_at",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "current_instructor_name",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "routine_assignment_type",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "source_updated_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "payload_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
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
            classification_status IN (
                'CLASSIFIED',
                'INCIDENT'
            )
            """,
            name="ck_routine_control_members_classification_status",
        ),
        sa.CheckConstraint(
            """
            current_status IS NULL
            OR current_status IN (
                'SIN_RUTINA',
                'CON_RUTINA',
                'NO_DESEA_RUTINA'
            )
            """,
            name="ck_routine_control_members_current_status",
        ),
        sa.CheckConstraint(
            """
            (
                classification_status = 'CLASSIFIED'
                AND current_status IS NOT NULL
            )
            OR
            (
                classification_status = 'INCIDENT'
                AND current_status IS NULL
            )
            """,
            name="ck_routine_control_members_status_consistency",
        ),
        sa.CheckConstraint(
            "status_version >= 1",
            name="ck_routine_control_members_status_version",
        ),
        sa.CheckConstraint(
            """
            cohort_month
            = date_trunc('month', cohort_month)::date
            """,
            name="ck_routine_control_members_cohort_month",
        ),
        sa.CheckConstraint(
            """
            routine_assignment_type IS NULL
            OR routine_assignment_type IN (
                'PREEXISTENTE',
                'MISMO_DIA',
                'POSTERIOR'
            )
            """,
            name="ck_routine_control_members_assignment_type",
        ),
        sa.CheckConstraint(
            """
            (
                first_routine_at IS NULL
                AND latest_routine_at IS NULL
                AND routine_assignment_type IS NULL
            )
            OR
            (
                first_routine_at IS NOT NULL
                AND latest_routine_at IS NOT NULL
                AND routine_assignment_type IS NOT NULL
                AND first_routine_at <= latest_routine_at
            )
            """,
            name="ck_routine_control_members_routine_dates",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            name="fk_routine_control_members_sucursal_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_routine_control_members",
        ),
        sa.UniqueConstraint(
            "source_system",
            "source_record_id",
            name="uq_routine_control_members_source_record",
        ),
        sa.UniqueConstraint(
            "source_system",
            "source_identity_key",
            name="uq_routine_control_members_identity_key",
        ),
    )

    op.create_index(
        "ix_routine_control_members_cohort_month",
        "routine_control_members",
        ["cohort_month"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_members_sucursal_cohort",
        "routine_control_members",
        ["sucursal_id", "cohort_month"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_members_status_cohort",
        "routine_control_members",
        ["current_status", "cohort_month"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_members_classification_cohort",
        "routine_control_members",
        ["classification_status", "cohort_month"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_members_email_normalized",
        "routine_control_members",
        ["email_normalized"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_members_branch_status_cohort",
        "routine_control_members",
        ["sucursal_id", "current_status", "cohort_month"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_members_sale_date",
        "routine_control_members",
        ["sale_date"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_members_external_member",
        "routine_control_members",
        ["source_system", "external_member_id"],
        unique=False,
    )

    op.create_table(
        "routine_assignment_evidences",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "provider_key",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "provider_member_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "evidence_identity_key",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "external_member_id",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column(
            "external_routine_id",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column(
            "email_original",
            sa.String(length=320),
            nullable=True,
        ),
        sa.Column(
            "email_normalized",
            sa.String(length=320),
            nullable=True,
        ),
        sa.Column(
            "provider_center_key",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "provider_center_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "sucursal_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "routine_activity_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "instructor_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "instructor_name_normalized",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "routine_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "weighing_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "first_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "first_provider_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "last_provider_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "payload_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "is_valid",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "invalidated_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "invalidated_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "invalidation_reason",
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
            "routine_count > 0",
            name="ck_routine_assignment_evidences_routine_count",
        ),
        sa.CheckConstraint(
            "weighing_count >= 0",
            name="ck_routine_assignment_evidences_weighing_count",
        ),
        sa.CheckConstraint(
            """
            (
                is_valid = true
                AND invalidated_at_utc IS NULL
                AND invalidated_by_user_id IS NULL
                AND invalidation_reason IS NULL
            )
            OR
            (
                is_valid = false
                AND invalidated_at_utc IS NOT NULL
                AND invalidated_by_user_id IS NOT NULL
                AND invalidation_reason IS NOT NULL
            )
            """,
            name="ck_routine_assignment_evidences_invalidation",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            name="fk_routine_assignment_evidences_sucursal_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["first_provider_run_id"],
            ["routine_control_provider_runs.id"],
            name=(
                "fk_routine_assignment_evidences_"
                "first_provider_run_id"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_provider_run_id"],
            ["routine_control_provider_runs.id"],
            name=(
                "fk_routine_assignment_evidences_"
                "last_provider_run_id"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invalidated_by_user_id"],
            ["users.id"],
            name=(
                "fk_routine_assignment_evidences_"
                "invalidated_by_user_id"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_routine_assignment_evidences",
        ),
        sa.UniqueConstraint(
            "provider_key",
            "evidence_identity_key",
            name="uq_routine_assignment_evidences_identity",
        ),
    )

    op.create_index(
        "ix_routine_assignment_evidences_external_member_date",
        "routine_assignment_evidences",
        ["external_member_id", "routine_activity_date"],
        unique=False,
    )
    op.create_index(
        "ix_routine_assignment_evidences_email",
        "routine_assignment_evidences",
        ["email_normalized"],
        unique=False,
    )
    op.create_index(
        "ix_routine_assignment_evidences_provider_date",
        "routine_assignment_evidences",
        ["provider_key", "routine_activity_date"],
        unique=False,
    )
    op.create_index(
        "ix_routine_assignment_evidences_valid_date",
        "routine_assignment_evidences",
        ["is_valid", "routine_activity_date"],
        unique=False,
    )
    op.create_index(
        "ix_routine_assignment_evidences_provider_member_date",
        "routine_assignment_evidences",
        ["provider_member_id", "routine_activity_date"],
        unique=False,
    )
    op.create_index(
        "ix_routine_assignment_evidences_center_date",
        "routine_assignment_evidences",
        ["provider_center_key", "routine_activity_date"],
        unique=False,
    )

    op.create_table(
        "routine_control_member_evidences",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "match_method",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "linked_by_provider_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "linked_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "unlinked_by_provider_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "unlinked_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "unlink_reason",
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
            match_method IN (
                'EXTERNAL_ID',
                'EMAIL'
            )
            """,
            name=(
                "ck_routine_control_member_evidences_"
                "match_method"
            ),
        ),
        sa.CheckConstraint(
            """
            (
                is_active = true
                AND unlinked_at_utc IS NULL
                AND unlink_reason IS NULL
            )
            OR
            (
                is_active = false
                AND unlinked_at_utc IS NOT NULL
                AND unlink_reason IS NOT NULL
            )
            """,
            name="ck_routine_control_member_evidences_active",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["routine_control_members.id"],
            name=(
                "fk_routine_control_member_evidences_"
                "member_id"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["routine_assignment_evidences.id"],
            name=(
                "fk_routine_control_member_evidences_"
                "evidence_id"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["linked_by_provider_run_id"],
            ["routine_control_provider_runs.id"],
            name=(
                "fk_routine_control_member_evidences_"
                "linked_provider_run"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["unlinked_by_provider_run_id"],
            ["routine_control_provider_runs.id"],
            name=(
                "fk_routine_control_member_evidences_"
                "unlinked_provider_run"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_routine_control_member_evidences",
        ),
        sa.UniqueConstraint(
            "member_id",
            "evidence_id",
            name="uq_routine_control_member_evidences_pair",
        ),
    )

    op.create_index(
        "ix_routine_control_member_evidences_member_active",
        "routine_control_member_evidences",
        ["member_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_member_evidences_evidence_active",
        "routine_control_member_evidences",
        ["evidence_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_routine_control_member_evidences_method_active",
        "routine_control_member_evidences",
        ["match_method", "is_active"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_routine_control_member_evidences_method_active",
        table_name="routine_control_member_evidences",
    )
    op.drop_index(
        "ix_routine_control_member_evidences_evidence_active",
        table_name="routine_control_member_evidences",
    )
    op.drop_index(
        "ix_routine_control_member_evidences_member_active",
        table_name="routine_control_member_evidences",
    )
    op.drop_table("routine_control_member_evidences")

    op.drop_index(
        "ix_routine_assignment_evidences_center_date",
        table_name="routine_assignment_evidences",
    )
    op.drop_index(
        "ix_routine_assignment_evidences_provider_member_date",
        table_name="routine_assignment_evidences",
    )
    op.drop_index(
        "ix_routine_assignment_evidences_valid_date",
        table_name="routine_assignment_evidences",
    )
    op.drop_index(
        "ix_routine_assignment_evidences_provider_date",
        table_name="routine_assignment_evidences",
    )
    op.drop_index(
        "ix_routine_assignment_evidences_email",
        table_name="routine_assignment_evidences",
    )
    op.drop_index(
        "ix_routine_assignment_evidences_external_member_date",
        table_name="routine_assignment_evidences",
    )
    op.drop_table("routine_assignment_evidences")

    op.drop_index(
        "ix_routine_control_members_external_member",
        table_name="routine_control_members",
    )
    op.drop_index(
        "ix_routine_control_members_sale_date",
        table_name="routine_control_members",
    )
    op.drop_index(
        "ix_routine_control_members_branch_status_cohort",
        table_name="routine_control_members",
    )
    op.drop_index(
        "ix_routine_control_members_email_normalized",
        table_name="routine_control_members",
    )
    op.drop_index(
        "ix_routine_control_members_classification_cohort",
        table_name="routine_control_members",
    )
    op.drop_index(
        "ix_routine_control_members_status_cohort",
        table_name="routine_control_members",
    )
    op.drop_index(
        "ix_routine_control_members_sucursal_cohort",
        table_name="routine_control_members",
    )
    op.drop_index(
        "ix_routine_control_members_cohort_month",
        table_name="routine_control_members",
    )
    op.drop_table("routine_control_members")
