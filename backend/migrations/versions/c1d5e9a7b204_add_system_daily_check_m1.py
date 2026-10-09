"""add system daily check m1 persistence

Revision ID: c1d5e9a7b204
Revises: d8f1c3a9b204
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa


revision = "c1d5e9a7b204"
down_revision = "d8f1c3a9b204"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_daily_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("performed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("general_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="RESTRICT",
            name="fk_system_daily_checks_branch",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_system_daily_checks_actor",
        ),
        sa.UniqueConstraint(
            "sucursal_id",
            "business_date",
            name="uq_system_daily_checks_branch_date",
        ),
        sa.CheckConstraint(
            "general_status IN ('NORMAL', 'MINOR_FAILURE', 'OPERATIONAL_IMPACT')",
            name="ck_system_daily_checks_general_status",
        ),
    )
    op.create_index(
        "ix_system_daily_checks_business_date_status",
        "system_daily_checks",
        ["business_date", "general_status"],
    )

    op.create_table(
        "system_daily_check_answers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("check_id", sa.BigInteger(), nullable=False),
        sa.Column("question_key", sa.String(length=80), nullable=False),
        sa.Column(
            "question_label_snapshot",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("category_key", sa.String(length=80), nullable=True),
        sa.Column("answer", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["system_daily_checks.id"],
            ondelete="CASCADE",
            name="fk_system_daily_check_answers_check",
        ),
        sa.UniqueConstraint(
            "check_id",
            "question_key",
            name="uq_system_daily_check_answers_check_question",
        ),
        sa.CheckConstraint(
            "answer IN ('YES', 'NO', 'NA')",
            name="ck_system_daily_check_answers_value",
        ),
        sa.CheckConstraint(
            "length(trim(question_key)) > 0",
            name="ck_system_daily_check_answers_question_key_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(question_label_snapshot)) > 0",
            name="ck_system_daily_check_answers_label_nonempty",
        ),
    )
    op.create_index(
        "ix_system_daily_check_answers_question_answer",
        "system_daily_check_answers",
        ["question_key", "answer"],
    )

    op.create_table(
        "system_daily_check_issues",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("answer_id", sa.BigInteger(), nullable=False),
        sa.Column("affected_scope", sa.String(length=16), nullable=True),
        sa.Column("reported_to_support", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["system_daily_check_answers.id"],
            ondelete="CASCADE",
            name="fk_system_daily_check_issues_answer",
        ),
        sa.UniqueConstraint(
            "answer_id",
            name="uq_system_daily_check_issues_answer",
        ),
        sa.CheckConstraint(
            "affected_scope IS NULL OR "
            "affected_scope IN ('ONE', 'MULTIPLE')",
            name="ck_system_daily_check_issues_affected_scope",
        ),
        sa.CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_system_daily_check_issues_description_nonempty",
        ),
    )
    op.create_index(
        "ix_system_daily_check_issues_reported",
        "system_daily_check_issues",
        ["reported_to_support"],
    )

    op.create_table(
        "system_daily_check_issue_attachments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["system_daily_check_issues.id"],
            ondelete="CASCADE",
            name="fk_system_daily_check_issue_attachments_issue",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_system_daily_check_issue_attachments_user",
        ),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_system_daily_check_issue_attachments_storage_key",
        ),
        sa.CheckConstraint(
            "length(trim(original_filename)) > 0",
            name="ck_system_daily_check_issue_attachments_filename_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(storage_key)) > 0",
            name="ck_system_daily_check_issue_attachments_storage_key_nonempty",
        ),
        sa.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_system_daily_check_issue_attachments_size_nonnegative",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64",
            name="ck_system_daily_check_issue_attachments_sha256_length",
        ),
    )
    op.create_index(
        "ix_system_daily_check_issue_attachments_issue",
        "system_daily_check_issue_attachments",
        ["issue_id"],
    )

    op.create_table(
        "system_daily_check_prompt_states",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column(
            "postpone_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_postponed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_prompt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mandatory_from_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="RESTRICT",
            name="fk_system_daily_check_prompt_branch",
        ),
        sa.UniqueConstraint(
            "sucursal_id",
            "business_date",
            name="uq_system_daily_check_prompt_branch_date",
        ),
        sa.CheckConstraint(
            "postpone_count >= 0 AND postpone_count <= 2",
            name="ck_system_daily_check_prompt_postpone_count",
        ),
    )
    op.create_index(
        "ix_system_daily_check_prompt_business_date",
        "system_daily_check_prompt_states",
        ["business_date"],
    )


def downgrade():
    op.drop_index(
        "ix_system_daily_check_prompt_business_date",
        table_name="system_daily_check_prompt_states",
    )
    op.drop_table("system_daily_check_prompt_states")

    op.drop_index(
        "ix_system_daily_check_issue_attachments_issue",
        table_name="system_daily_check_issue_attachments",
    )
    op.drop_table("system_daily_check_issue_attachments")

    op.drop_index(
        "ix_system_daily_check_issues_reported",
        table_name="system_daily_check_issues",
    )
    op.drop_table("system_daily_check_issues")

    op.drop_index(
        "ix_system_daily_check_answers_question_answer",
        table_name="system_daily_check_answers",
    )
    op.drop_table("system_daily_check_answers")

    op.drop_index(
        "ix_system_daily_checks_business_date_status",
        table_name="system_daily_checks",
    )
    op.drop_table("system_daily_checks")
