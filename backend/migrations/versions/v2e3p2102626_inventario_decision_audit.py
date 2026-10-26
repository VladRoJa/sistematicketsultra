"""Inventarios V2 E3: tablas de decisiones, ajustes y auditoria sin efectos V1.

Revision ID: v2e3p2102626
Revises: m23c10202623
Create Date: 2026-10-26

Solo DDL. Sin permisos, endpoints, backfill ni movimientos automáticos.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2e3p2102626"
down_revision = "m23c10202623"
branch_labels = None
depends_on = None


def _actor_fk(table, name):
    return sa.ForeignKeyConstraint(
        ["actor_usuario_id"], ["users.id"], name=name, ondelete="RESTRICT"
    )


def _decision_pair_fk(label):
    return sa.ForeignKeyConstraint(
        ["decision_id", "solicitud_id"],
        ["inventario_correccion_decisiones.id", "inventario_correccion_decisiones.solicitud_id"],
        name=f"fk_inv_corr_{label}_decision_solicitud", ondelete="RESTRICT",
    )


def _stock_fk(local_inventory, label):
    return sa.ForeignKeyConstraint(
        [local_inventory, "sucursal_id"],
        ["inventario_sucursal.inventario_id", "inventario_sucursal.sucursal_id"],
        name=f"fk_inv_corr_{label}_stock_sucursal", ondelete="RESTRICT",
    )


def _effect_keys(label):
    return (
        sa.UniqueConstraint("decision_id", name=f"uq_inv_corr_{label}_decision"),
        sa.UniqueConstraint("solicitud_id", name=f"uq_inv_corr_{label}_solicitud"),
        _decision_pair_fk(label),
    )


def upgrade():
    # La idempotencia pertenece a la operación completa, incluso en lotes de N solicitudes.
    op.create_table(
        "inventario_correccion_lotes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_usuario_id", sa.Integer(), nullable=False),
        sa.Column("tipo_decision", sa.String(length=16), nullable=False),
        sa.Column(
            "creado_en_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("motivo_lote", sa.Text(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("resultados", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_inv_corr_lote"),
        _actor_fk("inventario_correccion_lotes", "fk_inv_corr_lote_actor"),
        sa.UniqueConstraint(
            "actor_usuario_id", "idempotency_key",
            name="uq_inv_corr_lote_actor_key",
        ),
        sa.CheckConstraint(
            "tipo_decision IN ('APPROVED', 'REJECTED')", name="ck_inv_corr_lote_tipo",
        ),
        sa.CheckConstraint(
            "char_length(btrim(motivo_lote)) BETWEEN 10 AND 2000",
            name="ck_inv_corr_lote_motivo",
        ),
        sa.CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="ck_inv_corr_lote_fingerprint",
        ),
    )
    op.create_index(
        "ix_inv_corr_lote_actor_fecha", "inventario_correccion_lotes",
        ["actor_usuario_id", "creado_en_utc"],
    )

    op.create_table(
        "inventario_correccion_decisiones",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("solicitud_id", sa.BigInteger(), nullable=False),
        sa.Column("lote_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("actor_usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "decidido_en_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("motivo_decision", sa.Text(), nullable=False),
        sa.Column("resolucion", postgresql.JSONB(), nullable=True),
        sa.Column("efecto_anterior", postgresql.JSONB(), nullable=True),
        sa.Column("efecto_posterior", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_inv_corr_decision"),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["inventario_correccion_solicitudes.id"],
            name="fk_inv_corr_decision_solicitud", ondelete="RESTRICT",
        ),
        _actor_fk("inventario_correccion_decisiones", "fk_inv_corr_decision_actor"),
        sa.ForeignKeyConstraint(
            ["lote_id"], ["inventario_correccion_lotes.id"],
            name="fk_inv_corr_decision_lote", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("solicitud_id", name="uq_inv_corr_decision_solicitud"),
        sa.UniqueConstraint("id", "solicitud_id", name="uq_inv_corr_decision_par"),
        sa.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED')",
            name="ck_inv_corr_decision_tipo",
        ),
        sa.CheckConstraint(
            "char_length(btrim(motivo_decision)) BETWEEN 10 AND 2000",
            name="ck_inv_corr_decision_motivo",
        ),
    )
    op.create_index(
        "ix_inv_corr_decision_actor_fecha",
        "inventario_correccion_decisiones",
        ["actor_usuario_id", "decidido_en_utc"],
    )

    op.create_table(
        "inventario_correccion_ajustes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("decision_id", sa.BigInteger(), nullable=False),
        sa.Column("solicitud_id", sa.BigInteger(), nullable=False),
        sa.Column("inventario_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("stock_anterior", sa.Integer(), nullable=False),
        sa.Column("stock_nuevo", sa.Integer(), nullable=False),
        sa.Column("delta_firmada", sa.Integer(), nullable=False),
        sa.Column("actor_usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "ocurrido_en_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_inv_corr_ajuste"),
        *_effect_keys("ajuste"),
        _stock_fk("inventario_id", "ajuste"),
        _actor_fk("inventario_correccion_ajustes", "fk_inv_corr_ajuste_actor"),
        sa.CheckConstraint(
            "stock_anterior >= 0 AND stock_nuevo >= 0",
            name="ck_inv_corr_ajuste_stock_no_negativo",
        ),
        sa.CheckConstraint(
            "stock_anterior + delta_firmada = stock_nuevo",
            name="ck_inv_corr_ajuste_delta",
        ),
        sa.CheckConstraint(
            "char_length(btrim(motivo)) >= 10",
            name="ck_inv_corr_ajuste_motivo",
        ),
    )
    op.create_index(
        "ix_inv_corr_ajuste_referencia_fecha",
        "inventario_correccion_ajustes",
        ["inventario_id", "sucursal_id", "ocurrido_en_utc"],
    )

    op.create_table(
        "inventario_correccion_maestro_auditoria",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("decision_id", sa.BigInteger(), nullable=False),
        sa.Column("solicitud_id", sa.BigInteger(), nullable=False),
        sa.Column("inventario_id", sa.Integer(), nullable=False),
        sa.Column("campo", sa.String(length=64), nullable=False),
        sa.Column("valor_anterior", postgresql.JSONB(), nullable=True),
        sa.Column("valor_nuevo", postgresql.JSONB(), nullable=True),
        sa.Column("actor_usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "ocurrido_en_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_inv_corr_maestro"),
        *_effect_keys("maestro"),
        sa.ForeignKeyConstraint(
            ["inventario_id"], ["inventario_general.id"],
            name="fk_inv_corr_maestro_inventario", ondelete="RESTRICT",
        ),
        _actor_fk("inventario_correccion_maestro_auditoria", "fk_inv_corr_maestro_actor"),
        sa.CheckConstraint(
            "campo IN ('nombre', 'marca', 'codigo_interno', 'no_equipo', "
            "'unidad_medida', 'tipo', 'categoria_inventario_id', 'familia_equipo_id')",
            name="ck_inv_corr_maestro_campo",
        ),
        sa.CheckConstraint(
            "char_length(btrim(motivo)) >= 10",
            name="ck_inv_corr_maestro_motivo",
        ),
    )
    op.create_index(
        "ix_inv_corr_maestro_referencia_fecha",
        "inventario_correccion_maestro_auditoria",
        ["inventario_id", "ocurrido_en_utc"],
    )

    op.create_table(
        "inventario_correccion_altas_auditoria",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("decision_id", sa.BigInteger(), nullable=False),
        sa.Column("solicitud_id", sa.BigInteger(), nullable=False),
        sa.Column("inventario_id_resultante", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("modalidad", sa.String(length=16), nullable=False),
        sa.Column("stock_anterior", sa.Integer(), nullable=False),
        sa.Column("stock_nuevo", sa.Integer(), nullable=False),
        sa.Column("actor_usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "ocurrido_en_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_inv_corr_alta"),
        *_effect_keys("alta"),
        _stock_fk("inventario_id_resultante", "alta"),
        _actor_fk("inventario_correccion_altas_auditoria", "fk_inv_corr_alta_actor"),
        sa.ForeignKeyConstraint(
            ["inventario_id_resultante"], ["inventario_general.id"],
            name="fk_inv_corr_alta_inventario", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "modalidad IN ('CREACION', 'VINCULACION')",
            name="ck_inv_corr_alta_modalidad",
        ),
        sa.CheckConstraint(
            "stock_anterior >= 0 AND stock_nuevo >= 0",
            name="ck_inv_corr_alta_stock",
        ),
        sa.CheckConstraint(
            "char_length(btrim(motivo)) >= 10",
            name="ck_inv_corr_alta_motivo",
        ),
    )
    op.create_index(
        "ix_inv_corr_alta_referencia_fecha",
        "inventario_correccion_altas_auditoria",
        ["inventario_id_resultante", "sucursal_id", "ocurrido_en_utc"],
    )


def downgrade():
    # Este journal nunca se destruye accidentalmente con decisiones existentes.
    bind = op.get_bind()
    for table in (
        "inventario_correccion_altas_auditoria",
        "inventario_correccion_maestro_auditoria",
        "inventario_correccion_ajustes",
        "inventario_correccion_decisiones",
        "inventario_correccion_lotes",
    ):
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(
                "No se puede retirar E3: existen decisiones o auditorias historicas."
            )

    op.drop_index("ix_inv_corr_alta_referencia_fecha", table_name="inventario_correccion_altas_auditoria")
    op.drop_table("inventario_correccion_altas_auditoria")
    op.drop_index("ix_inv_corr_maestro_referencia_fecha", table_name="inventario_correccion_maestro_auditoria")
    op.drop_table("inventario_correccion_maestro_auditoria")
    op.drop_index("ix_inv_corr_ajuste_referencia_fecha", table_name="inventario_correccion_ajustes")
    op.drop_table("inventario_correccion_ajustes")
    op.drop_index("ix_inv_corr_decision_actor_fecha", table_name="inventario_correccion_decisiones")
    op.drop_table("inventario_correccion_decisiones")
    op.drop_index("ix_inv_corr_lote_actor_fecha", table_name="inventario_correccion_lotes")
    op.drop_table("inventario_correccion_lotes")
