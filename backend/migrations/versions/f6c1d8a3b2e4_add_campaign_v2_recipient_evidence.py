"""add Campaign V2 recipient evidence

Revision ID: f6c1d8a3b2e4
Revises: a4d8c2e6f1b5
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "f6c1d8a3b2e4"
down_revision = "a4d8c2e6f1b5"
branch_labels = None
depends_on = None


_AUDIENCE_FAMILY_CHECK = (
    "audience_family IS NULL OR audience_family IN ("
    "'DOMICILIADO', 'TRIMESTRAL', 'CONVENIO', "
    "'SEMESTRE', 'ESTUDIANTE', 'MES', 'OUT_OF_SEGMENT'"
    ")"
)


def upgrade():
    op.add_column(
        "marketing_campaign_v2_recipients",
        sa.Column(
            "conflict_fields_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )

    op.create_table(
        "marketing_campaign_v2_recipient_evidence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_order", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("phone_raw", sa.String(length=64), nullable=True),
        sa.Column("phone_mx10", sa.String(length=10), nullable=False),
        sa.Column("socios_vencidos_cartera_id", sa.BigInteger(), nullable=True),
        sa.Column("socios_activos_snapshot_row_id", sa.BigInteger(), nullable=True),
        sa.Column("socios_activos_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("member_id", sa.String(length=64), nullable=True),
        sa.Column("member_pin", sa.String(length=64), nullable=True),
        sa.Column("member_name", sa.String(length=255), nullable=True),
        sa.Column("sucursal", sa.String(length=255), nullable=True),
        sa.Column("sucursal_key", sa.String(length=255), nullable=True),
        sa.Column("tarifa_raw", sa.String(length=255), nullable=True),
        sa.Column("tarifa_key", sa.String(length=255), nullable=True),
        sa.Column("categoria_tarifa", sa.String(length=100), nullable=True),
        sa.Column("audience_family", sa.String(length=30), nullable=True),
        sa.Column("fecha_vencimiento_date", sa.Date(), nullable=True),
        sa.Column("current_status", sa.String(length=50), nullable=True),
        sa.Column(
            "evidence_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(phone_mx10) = 10",
            name="ck_marketing_campaign_v2_evidence_phone_mx10_length",
        ),
        sa.CheckConstraint(
            _AUDIENCE_FAMILY_CHECK,
            name="ck_marketing_campaign_v2_evidence_audience_family",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["marketing_campaign_v2_recipients.id"],
            name="fk_marketing_campaign_v2_evidence_recipient_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["socios_vencidos_cartera_id"],
            ["socios_vencidos_cartera.id"],
            name="fk_marketing_campaign_v2_evidence_vencidos_cartera_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["socios_activos_snapshot_row_id"],
            ["socios_activos_snapshot_rows.id"],
            name="fk_marketing_campaign_v2_evidence_activos_snapshot_row_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["socios_activos_snapshot_id"],
            ["socios_activos_snapshots.id"],
            name="fk_marketing_campaign_v2_evidence_activos_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_campaign_v2_recipient_evidence",
        ),
        sa.UniqueConstraint(
            "recipient_id",
            "evidence_order",
            name="uq_marketing_campaign_v2_evidence_recipient_order",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_evidence_recipient_id",
        "marketing_campaign_v2_recipient_evidence",
        ["recipient_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_evidence_vencidos_cartera_id",
        "marketing_campaign_v2_recipient_evidence",
        ["socios_vencidos_cartera_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_evidence_activos_snapshot_row_id",
        "marketing_campaign_v2_recipient_evidence",
        ["socios_activos_snapshot_row_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_evidence_activos_snapshot_id",
        "marketing_campaign_v2_recipient_evidence",
        ["socios_activos_snapshot_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_campaign_v2_evidence_activos_snapshot_id",
        table_name="marketing_campaign_v2_recipient_evidence",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_evidence_activos_snapshot_row_id",
        table_name="marketing_campaign_v2_recipient_evidence",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_evidence_vencidos_cartera_id",
        table_name="marketing_campaign_v2_recipient_evidence",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_evidence_recipient_id",
        table_name="marketing_campaign_v2_recipient_evidence",
    )
    op.drop_table("marketing_campaign_v2_recipient_evidence")
    op.drop_column(
        "marketing_campaign_v2_recipients",
        "conflict_fields_json",
    )
