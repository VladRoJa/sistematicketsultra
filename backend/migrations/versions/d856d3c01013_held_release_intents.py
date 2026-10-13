"""Issue #856 D3c1: immutable HELD release intent, not a fresh approval.

Revision ID: d856d3c01013
Revises: c856d3b01013
"""
from alembic import op
import sqlalchemy as sa

revision = "d856d3c01013"
down_revision = "c856d3b01013"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_held_release_intents"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("source_approval_id", sa.BigInteger(), nullable=False),
        sa.Column("source_child_id", sa.BigInteger(), nullable=False),
        sa.Column("source_manifest_digest", sa.String(64), nullable=False),
        sa.Column("candidate_fingerprint", sa.String(64), nullable=False),
        sa.Column("candidate_recipients", sa.Integer(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(35), nullable=False),
        sa.ForeignKeyConstraint(["source_campaign_id"],
            ["marketing_campaign_v2_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_approval_id"],
            ["marketing_campaign_v2_dispatch_approvals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_child_id"],
            ["marketing_campaign_v2_provider_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"],
            ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("source_child_id", name="uq_mkt_v2_held_release_child"),
        sa.CheckConstraint(
            "length(source_manifest_digest) = 64 AND length(candidate_fingerprint) = 64",
            name="ck_mkt_v2_held_release_fingerprints",
        ),
        sa.CheckConstraint("candidate_recipients > 0",
                           name="ck_mkt_v2_held_release_positive"),
        sa.CheckConstraint("status = 'PENDING_FRESH_COHORT'",
                           name="ck_mkt_v2_held_release_intent_status"),
        sa.CheckConstraint(
            "length(trim(source_reference)) > 0 AND length(trim(reason)) > 0",
            name="ck_mkt_v2_held_release_audit",
        ),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + TABLE)).scalar():
        raise RuntimeError("No se borra historial de solicitudes de liberación HELD.")
    op.drop_table(TABLE)
