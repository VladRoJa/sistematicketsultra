"""Link approved correction case to versioned canonical M6 publication.

Revision ID: c5e7a2d93f10
Revises: ac42e8b9d510
No rewrite of historical metric tables, RAW or publication schema.
"""
from alembic import op
import sqlalchemy as sa

revision = "c5e7a2d93f10"
down_revision = "ac42e8b9d510"
branch_labels = None
depends_on = None

TABLE = "google_ads_m6_correction_promotions"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("publication_id", sa.BigInteger(), nullable=False),
        sa.Column("decision_id", sa.BigInteger(), nullable=False),
        sa.Column("superseded_publication_id", sa.BigInteger(), nullable=True),
        sa.Column("promoted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["case_id"], ["google_ads_m6_correction_cases.id"],
                                name="fk_ga_m6_corr_promotion_case",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["publication_id"], ["google_ads_m6_daily_publications.id"],
                                name="fk_ga_m6_corr_promotion_publication",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decision_id"], ["google_ads_m6_correction_decisions.id"],
                                name="fk_ga_m6_corr_promotion_decision",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["superseded_publication_id"],
                                ["google_ads_m6_daily_publications.id"],
                                name="fk_ga_m6_corr_promotion_prior",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["promoted_by_user_id"], ["users.id"],
                                name="fk_ga_m6_corr_promotion_actor",
                                ondelete="RESTRICT"),
        sa.UniqueConstraint("case_id", name="uq_ga_m6_corr_promotion_case"),
        sa.UniqueConstraint("publication_id", name="uq_ga_m6_corr_promotion_pub"),
        sa.UniqueConstraint("decision_id", name="uq_ga_m6_corr_promotion_decision"),
        sa.CheckConstraint("snapshot_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_promotion_sha"),
        sa.CheckConstraint("publication_id <> superseded_publication_id",
                           name="ck_ga_m6_corr_promotion_distinct"),
    )


def downgrade():
    conn = op.get_bind()
    if conn.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM google_ads_m6_correction_promotions)"
    )).scalar():
        raise RuntimeError("M6 promotion rollback blocked: version evidence exists")
    op.drop_table(TABLE)
