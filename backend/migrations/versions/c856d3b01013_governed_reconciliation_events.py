"""Issue #856 D3b: append-only governed reconciliation evidence.

Revision ID: c856d3b01013
Revises: b856d2c01013
"""
from alembic import op
import sqlalchemy as sa

revision = "c856d3b01013"
down_revision = "b856d2c01013"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_governed_reconciliation_events"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("execution_id", sa.BigInteger, nullable=False),
        sa.Column("child_id", sa.BigInteger, nullable=False),
        sa.Column("event_kind", sa.String(40), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("evidence_note", sa.Text, nullable=False),
        sa.Column("provider_campaign_id", sa.String(255), nullable=True),
        sa.Column("previous_child_status", sa.String(30), nullable=False),
        sa.Column("next_child_status", sa.String(30), nullable=False),
        sa.Column("previous_execution_status", sa.String(25), nullable=False),
        sa.Column("next_execution_status", sa.String(25), nullable=False),
        sa.Column("actor_user_id", sa.Integer, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_json", sa.JSON, nullable=False),
        sa.ForeignKeyConstraint(["execution_id"],
            ["marketing_campaign_v2_governed_executions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["child_id"],
            ["marketing_campaign_v2_provider_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("execution_id", "child_id", "event_kind",
                            name="uq_mkt_v2_governed_reconcile_event"),
        sa.CheckConstraint(
            "event_kind IN ('STALE_CLAIM_REVIEW','PROVIDER_CAMPAIGN_FOUND',"
            "'NOT_CREATED_CONFIRMED')",
            name="ck_mkt_v2_governed_reconcile_event_kind"),
        sa.CheckConstraint("length(trim(source_reference)) > 0",
                           name="ck_mkt_v2_governed_reconcile_source"),
        sa.CheckConstraint("length(trim(evidence_note)) > 0",
                           name="ck_mkt_v2_governed_reconcile_note"),
    )


def downgrade():
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + TABLE)).scalar()
    if int(count or 0):
        raise RuntimeError("No se borra historial de reconciliaciones gobernadas.")
    op.drop_table(TABLE)
