"""Inventarios V2 E2: persistencia de solicitudes sin modificar stock ni maestro.

Revision ID: v2e2a7c92623
Revises: l23c10202623
Create Date: 2026-10-23

Schema-only. No seed, backfill, permission grant or automatic corrections.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "v2e2a7c92623"
down_revision = "l23c10202623"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventario_correccion_solicitudes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("inventario_id", sa.Integer(), nullable=True),
        sa.Column("campo", sa.String(length=64), nullable=True),
        sa.Column("valor_original", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("valor_propuesto", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("hallazgo_provisional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("baseline_canonico", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fecha_observacion_local", sa.Date(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("evidencia_descriptiva", sa.Text(), nullable=True),
        sa.Column("creado_por_usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "idempotency_key", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_inv_corr_solicitudes"),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            name="fk_inv_corr_solicitudes_sucursal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inventario_id", "sucursal_id"],
            ["inventario_sucursal.inventario_id", "inventario_sucursal.sucursal_id"],
            name="fk_inv_corr_solicitudes_stock_sucursal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["creado_por_usuario_id"],
            ["users.id"],
            name="fk_inv_corr_solicitudes_creador",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "tipo IN ('MASTER_FIELD', 'QUANTITY_DIFFERENCE', "
            "'NOT_LOCATED', 'UNREGISTERED_FIND')",
            name="ck_inv_corr_solicitudes_tipo",
        ),
        sa.CheckConstraint(
            "estado IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_inv_corr_solicitudes_estado",
        ),
        sa.CheckConstraint(
            "("
            "tipo = 'UNREGISTERED_FIND' AND inventario_id IS NULL "
            "AND hallazgo_provisional IS NOT NULL AND campo IS NULL"
            ") OR ("
            "tipo <> 'UNREGISTERED_FIND' AND inventario_id IS NOT NULL "
            "AND hallazgo_provisional IS NULL"
            ")",
            name="ck_inv_corr_solicitudes_identidad",
        ),
        sa.CheckConstraint(
            "(tipo = 'MASTER_FIELD' AND campo IS NOT NULL AND valor_propuesto IS NOT NULL) "
            "OR (tipo <> 'MASTER_FIELD' AND campo IS NULL)",
            name="ck_inv_corr_solicitudes_campo",
        ),
        sa.CheckConstraint(
            "char_length(btrim(motivo)) BETWEEN 10 AND 2000",
            name="ck_inv_corr_solicitudes_motivo",
        ),
        sa.CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="ck_inv_corr_solicitudes_fingerprint",
        ),
        sa.UniqueConstraint(
            "creado_por_usuario_id",
            "idempotency_key",
            name="uq_inv_corr_solicitudes_actor_idempotencia",
        ),
    )
    op.create_index(
        "ix_inv_corr_solicitudes_sucursal_estado_fecha",
        "inventario_correccion_solicitudes",
        ["sucursal_id", "estado", "creado_en_utc"],
    )
    op.create_index(
        "ix_inv_corr_solicitudes_inventario_estado",
        "inventario_correccion_solicitudes",
        ["inventario_id", "estado"],
    )
    op.create_index(
        "ix_inv_corr_solicitudes_creador_fecha",
        "inventario_correccion_solicitudes",
        ["creado_por_usuario_id", "creado_en_utc"],
    )


def downgrade():
    # Nunca destruir solicitudes históricas por accidente.
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM inventario_correccion_solicitudes")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "No se puede retirar Inventarios V2 E2: existen solicitudes. "
            "Resguardar el historial y autorizar migracion de retiro."
        )

    for name in (
        "ix_inv_corr_solicitudes_creador_fecha",
        "ix_inv_corr_solicitudes_inventario_estado",
        "ix_inv_corr_solicitudes_sucursal_estado_fecha",
    ):
        op.drop_index(name, table_name="inventario_correccion_solicitudes")
    op.drop_table("inventario_correccion_solicitudes")
