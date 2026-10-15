"""Independent M6 correction review decisions; no publication side effects.

Revision ID: ac42e8b9d510
Revises: e8b2c41d7a60
"""
from alembic import op
import sqlalchemy as sa

revision = "ac42e8b9d510"
down_revision = "e8b2c41d7a60"
branch_labels = None
depends_on = None

TABLE = "google_ads_m6_correction_decisions"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["case_id"], ["google_ads_m6_correction_cases.id"],
                                name="fk_ga_m6_corr_decision_case",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"],
                                name="fk_ga_m6_corr_decision_reviewer",
                                ondelete="RESTRICT"),
        sa.UniqueConstraint("case_id", name="uq_ga_m6_corr_one_decision"),
        sa.CheckConstraint("decision IN ('APPROVED', 'REJECTED')",
                           name="ck_ga_m6_corr_decision"),
        sa.CheckConstraint("snapshot_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_decision_sha"),
        sa.CheckConstraint("length(btrim(review_note)) >= 10",
                           name="ck_ga_m6_corr_review_note"),
    )
    op.create_index("ix_ga_m6_corr_decision_reviewer", TABLE,
                    ["reviewed_by_user_id"])


def downgrade():
    conn = op.get_bind()
    if conn.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM google_ads_m6_correction_decisions)"
    )).scalar():
        raise RuntimeError("M6 correction review rollback blocked: decision evidence exists")
    op.drop_index("ix_ga_m6_corr_decision_reviewer", table_name=TABLE)
    op.drop_table(TABLE)
