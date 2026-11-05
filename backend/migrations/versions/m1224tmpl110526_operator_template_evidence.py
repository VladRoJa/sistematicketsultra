"""Append-only, operator-attested iVentas template evidence for Campaign V2.

Revision ID: m1224tmpl110526
Revises: m1214fail110426
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "m1224tmpl110526"
down_revision = "m1214fail110426"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_template_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "campaign_id", sa.BigInteger(),
            sa.ForeignKey("marketing_campaign_v2_campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "template_id", sa.BigInteger(),
            sa.ForeignKey("marketing_campaign_v2_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("template_name", sa.String(255), nullable=False),
        sa.Column("template_signature", sa.String(64), nullable=False),
        sa.Column("binding_signature", sa.String(64), nullable=False),
        sa.Column("accepted_channel_ids_json", sa.JSON(), nullable=False),
        sa.Column("inventory_sha256", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "captured_by_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "length(template_signature) = 64 AND length(binding_signature) = 64 AND length(inventory_sha256) = 64",
            name="ck_mkt_v2_template_evidence_hashes",
        ),
        sa.CheckConstraint(
            "expires_at > observed_at", name="ck_mkt_v2_template_evidence_period",
        ),
    )
    op.create_index(
        "ix_mkt_v2_template_evidence_lookup",
        "marketing_campaign_v2_template_evidence",
        ["campaign_id", "template_id", "id"],
    )


def downgrade():
    bind = op.get_bind()
    existing = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM marketing_campaign_v2_template_evidence LIMIT 1)"
    )).scalar()
    if existing:
        raise RuntimeError("No se puede eliminar evidencia auditada de plantillas.")
    op.drop_index(
        "ix_mkt_v2_template_evidence_lookup",
        table_name="marketing_campaign_v2_template_evidence",
    )
    op.drop_table("marketing_campaign_v2_template_evidence")
