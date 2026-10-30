"""E4 Bloque 2: resolución y cierre auditado; no afecta inventario V1.

Revision ID: v2e4b2103026
Revises: n26c10202626
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2e4b2103026"
down_revision = "n26c10202626"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_inv_e4_estado_b1", "inventario_levantamientos", type_="check")
    op.create_check_constraint(
        "ck_inv_e4_estado", "inventario_levantamientos",
        "estado IN ('PREPARATION','IN_PROGRESS','IN_REVIEW','CLOSED')",
    )
    op.create_table(
        "inventario_levantamiento_resoluciones",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("levantamiento_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("importacion_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("caso", sa.String(80), nullable=False),
        sa.Column("accion", sa.String(24), nullable=False),
        sa.Column("solicitud_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_correccion_solicitudes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("inventario_id_resultante", sa.Integer(), sa.ForeignKey(
            "inventario_general.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_usuario_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("creado_en_utc", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("actor_usuario_id", "idempotency_key",
                            name="uq_inv_e4_resolucion_idempotencia"),
        sa.CheckConstraint("accion IN ('E2_APROBADA','REGISTRADO_OFICIAL')",
                           name="ck_inv_e4_resolucion_accion"),
        sa.CheckConstraint("char_length(btrim(motivo)) BETWEEN 20 AND 2000",
                           name="ck_inv_e4_resolucion_motivo"),
    )
    op.create_index("ix_inv_e4_resolucion_version_caso",
                    "inventario_levantamiento_resoluciones", ["importacion_id", "caso", "id"])
    op.create_table(
        "inventario_levantamiento_cierres",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("levantamiento_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("importacion_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_usuario_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cerrado_en_utc", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resumen_cierre", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("actor_usuario_id", "idempotency_key",
                            name="uq_inv_e4_cierre_idempotencia"),
        sa.CheckConstraint("char_length(btrim(motivo)) BETWEEN 20 AND 2000",
                           name="ck_inv_e4_cierre_motivo"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT 1 FROM inventario_levantamiento_resoluciones LIMIT 1"
    )).first() or bind.execute(sa.text(
        "SELECT 1 FROM inventario_levantamiento_cierres LIMIT 1"
    )).first() or bind.execute(sa.text(
        "SELECT 1 FROM inventario_levantamientos WHERE estado IN ('IN_REVIEW','CLOSED') LIMIT 1"
    )).first():
        raise RuntimeError("E4 contiene conciliaciones: downgrade destructivo bloqueado")
    op.drop_table("inventario_levantamiento_cierres")
    op.drop_index("ix_inv_e4_resolucion_version_caso",
                  table_name="inventario_levantamiento_resoluciones")
    op.drop_table("inventario_levantamiento_resoluciones")
    op.drop_constraint("ck_inv_e4_estado", "inventario_levantamientos", type_="check")
    op.create_check_constraint(
        "ck_inv_e4_estado_b1", "inventario_levantamientos",
        "estado IN ('PREPARATION','IN_PROGRESS')",
    )
