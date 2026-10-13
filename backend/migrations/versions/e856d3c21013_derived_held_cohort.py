"""Issue #856 D3c2 — permanently link a HELD intent to its frozen derived cohort.

Revision ID: e856d3c21013
Revises: d856d3c01013
"""
from alembic import op
import sqlalchemy as sa

revision = "e856d3c21013"
down_revision = "d856d3c01013"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_held_release_intents"


def upgrade():
    op.add_column(TABLE, sa.Column("derived_campaign_id", sa.BigInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_mkt_v2_held_release_derived_campaign", TABLE,
        "marketing_campaign_v2_campaigns", ["derived_campaign_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_mkt_v2_held_release_derived_campaign", TABLE, ["derived_campaign_id"],
    )
    op.drop_constraint("ck_mkt_v2_held_release_intent_status", TABLE, type_="check")
    op.create_check_constraint(
        "ck_mkt_v2_held_release_intent_status", TABLE,
        "status IN ('PENDING_FRESH_COHORT', 'FROZEN_DERIVED')",
    )
    op.create_check_constraint(
        "ck_mkt_v2_held_release_materialization_state", TABLE,
        "(status = 'PENDING_FRESH_COHORT' AND derived_campaign_id IS NULL "
        "AND materialized_at IS NULL) OR "
        "(status = 'FROZEN_DERIVED' AND derived_campaign_id IS NOT NULL "
        "AND materialized_at IS NOT NULL)",
    )


def downgrade():
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT COUNT(*) FROM " + TABLE +
        " WHERE derived_campaign_id IS NOT NULL OR status <> 'PENDING_FRESH_COHORT'"
    )).scalar()
    if int(result or 0):
        raise RuntimeError("No se puede perder la relación con cohortes derivadas.")
    op.drop_constraint("ck_mkt_v2_held_release_materialization_state", TABLE, type_="check")
    op.drop_constraint("ck_mkt_v2_held_release_intent_status", TABLE, type_="check")
    op.create_check_constraint(
        "ck_mkt_v2_held_release_intent_status", TABLE, "status = 'PENDING_FRESH_COHORT'",
    )
    op.drop_constraint("uq_mkt_v2_held_release_derived_campaign", TABLE, type_="unique")
    op.drop_constraint("fk_mkt_v2_held_release_derived_campaign", TABLE, type_="foreignkey")
    op.drop_column(TABLE, "materialized_at")
    op.drop_column(TABLE, "derived_campaign_id")
