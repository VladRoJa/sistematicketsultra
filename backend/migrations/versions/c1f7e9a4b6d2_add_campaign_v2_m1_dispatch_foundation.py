"""add Campaign V2 M1 dispatch foundation

Revision ID: c1f7e9a4b6d2
Revises: b9e2f7a4d3c5
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "c1f7e9a4b6d2"
down_revision = "b9e2f7a4d3c5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_channel_bindings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_canon", sa.String(length=100), nullable=False),
        sa.Column("provider_channel_id", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0 AND provider = upper(trim(provider))",
            name="ck_marketing_campaign_v2_channel_provider",
        ),
        sa.CheckConstraint(
            "length(trim(sucursal_canon)) > 0",
            name="ck_marketing_campaign_v2_channel_sucursal_canon",
        ),
        sa.CheckConstraint(
            "length(trim(provider_channel_id)) > 0",
            name="ck_marketing_campaign_v2_channel_provider_channel_id",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_channel_id",
            name="uq_marketing_campaign_v2_channel_provider_identity",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_channel_sucursal",
        "marketing_campaign_v2_channel_bindings",
        ["provider", "sucursal_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "uq_marketing_campaign_v2_channel_default_active",
        "marketing_campaign_v2_channel_bindings",
        ["provider", "sucursal_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND is_default = true"),
        sqlite_where=sa.text("is_active = 1 AND is_default = 1"),
    )

    op.create_table(
        "marketing_campaign_v2_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("template_name", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "purposes_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "variables_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "compatible_channel_ids_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0 AND provider = upper(trim(provider))",
            name="ck_marketing_campaign_v2_template_provider",
        ),
        sa.CheckConstraint(
            "length(trim(template_name)) > 0 AND template_name = trim(template_name)",
            name="ck_marketing_campaign_v2_template_name",
        ),
        sa.CheckConstraint(
            "length(trim(label)) > 0",
            name="ck_marketing_campaign_v2_template_label",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "template_name",
            name="uq_marketing_campaign_v2_template_provider_name",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_template_active",
        "marketing_campaign_v2_templates",
        ["provider", "is_active"],
        unique=False,
    )

    op.create_table(
        "marketing_campaign_v2_provider_campaigns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campaign_v2_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_canon", sa.String(length=100), nullable=False),
        sa.Column("channel_binding_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_channel_id", sa.String(length=255), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("template_name", sa.String(length=255), nullable=False),
        sa.Column(
            "template_snapshot_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("dispatch_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="PREPARED",
            nullable=False,
        ),
        sa.Column("provider_campaign_id", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("support_ref", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "recipient_count >= 0",
            name="ck_marketing_campaign_v2_provider_campaign_recipient_count",
        ),
        sa.CheckConstraint(
            "length(dispatch_fingerprint) = 64 AND length(idempotency_key) = 64",
            name="ck_marketing_campaign_v2_provider_campaign_fingerprints",
        ),
        sa.CheckConstraint(
            "status IN ('PREPARED', 'READY', 'BLOCKED', 'SUBMITTING', "
            "'SUBMITTED', 'PROVIDER_ERROR', 'RECONCILIATION_REQUIRED')",
            name="ck_marketing_campaign_v2_provider_campaign_status",
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0 AND provider = upper(trim(provider))",
            name="ck_marketing_campaign_v2_provider_campaign_provider",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_v2_id"],
            ["marketing_campaign_v2_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["channel_binding_id"],
            ["marketing_campaign_v2_channel_bindings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["marketing_campaign_v2_templates.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_marketing_campaign_v2_provider_campaign_idempotency",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_campaign_id",
            name="uq_marketing_campaign_v2_provider_campaign_external_identity",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_provider_campaign_parent",
        "marketing_campaign_v2_provider_campaigns",
        ["campaign_v2_id", "sucursal_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_provider_campaign_status",
        "marketing_campaign_v2_provider_campaigns",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_campaign_v2_provider_campaign_status",
        table_name="marketing_campaign_v2_provider_campaigns",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_provider_campaign_parent",
        table_name="marketing_campaign_v2_provider_campaigns",
    )
    op.drop_table("marketing_campaign_v2_provider_campaigns")

    op.drop_index(
        "ix_marketing_campaign_v2_template_active",
        table_name="marketing_campaign_v2_templates",
    )
    op.drop_table("marketing_campaign_v2_templates")

    op.drop_index(
        "uq_marketing_campaign_v2_channel_default_active",
        table_name="marketing_campaign_v2_channel_bindings",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_channel_sucursal",
        table_name="marketing_campaign_v2_channel_bindings",
    )
    op.drop_table("marketing_campaign_v2_channel_bindings")
