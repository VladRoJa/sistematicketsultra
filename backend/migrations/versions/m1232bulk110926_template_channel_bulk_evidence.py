"""Durable per-channel iVentas template evidence reused across campaigns.

Revision ID: m1232bulk110926
Revises: m1224tmpl110526
"""
from alembic import op
import sqlalchemy as sa

revision = "m1232bulk110926"
down_revision = "m1224tmpl110526"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_template_channel_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey(
            "marketing_campaign_v2_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider_channel_id", sa.String(255), nullable=False),
        sa.Column("sender_binding_id", sa.BigInteger(), sa.ForeignKey(
            "marketing_campaign_v2_channel_bindings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_signature", sa.String(64), nullable=False),
        sa.Column("sender_signature", sa.String(64), nullable=False),
        sa.Column("observed_status", sa.String(40), nullable=False),
        sa.Column("inventory_sha256", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_by_user_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "length(template_signature) = 64 AND length(sender_signature) = 64 "
            "AND length(inventory_sha256) = 64",
            name="ck_mkt_v2_template_channel_evidence_hashes"),
        sa.CheckConstraint("length(trim(observed_status)) > 0",
                           name="ck_mkt_v2_template_channel_evidence_status"),
        sa.CheckConstraint("expires_at > observed_at",
                           name="ck_mkt_v2_template_channel_evidence_period"),
    )
    op.create_index(
        "ix_mkt_v2_template_channel_evidence_lookup",
        "marketing_campaign_v2_template_channel_evidence",
        ["template_id", "provider_channel_id", "id"],
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM marketing_campaign_v2_template_channel_evidence LIMIT 1)"
    )).scalar():
        raise RuntimeError("No se puede eliminar evidencia auditada de plantillas.")
    op.drop_index("ix_mkt_v2_template_channel_evidence_lookup",
                  table_name="marketing_campaign_v2_template_channel_evidence")
    op.drop_table("marketing_campaign_v2_template_channel_evidence")
