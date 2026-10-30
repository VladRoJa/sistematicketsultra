"""E4 B3: revision logica unica por discrepancia y evidencia versionada.

Revision ID: v2e4b3103026
Revises: v2e4b2103026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2e4b3103026"
down_revision = "v2e4b2103026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventario_levantamiento_revisiones",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("levantamiento_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("logical_key", sa.String(160), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("inventario_id", sa.Integer(), nullable=True),
        sa.Column("codigo_observado", sa.String(120), nullable=True),
        sa.Column("campo", sa.String(64), nullable=True),
        sa.Column("estado", sa.String(30), nullable=False),
        sa.Column("motivo_bloqueo", sa.String(120), nullable=True),
        sa.Column("solicitud_e2_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_correccion_solicitudes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("primera_importacion_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ultima_importacion_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ultimo_valor", postgresql.JSONB(), nullable=False),
        sa.Column("actor_creador_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("creado_en_utc", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("actualizado_en_utc", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("levantamiento_id", "logical_key",
                            name="uq_inv_e4_revision_logica"),
        sa.CheckConstraint(
            "estado IN ('BLOCKED','PENDING','AWAITING_E3','APPROVED','REJECTED','SUPERSEDED')",
            name="ck_inv_e4_revision_estado"),
    )
    op.create_index("ix_inv_e4_revision_bandeja", "inventario_levantamiento_revisiones",
                    ["levantamiento_id", "estado", "id"])
    op.create_index("ix_inv_e4_revision_e2", "inventario_levantamiento_revisiones",
                    ["solicitud_e2_id"])
    op.create_table(
        "inventario_levantamiento_revision_evidencias",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("revision_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamiento_revisiones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("importacion_id", sa.BigInteger(), sa.ForeignKey(
            "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hoja", sa.String(12), nullable=True),
        sa.Column("fila_excel", sa.Integer(), nullable=True),
        sa.Column("valor_observado", postgresql.JSONB(), nullable=False),
        sa.Column("recibido_en_utc", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "importacion_id", "hoja", "fila_excel",
                            name="uq_inv_e4_revision_evidencia_fila"),
    )
    op.create_index("ix_inv_e4_revision_evidencia_version",
                    "inventario_levantamiento_revision_evidencias", ["importacion_id"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT 1 FROM inventario_levantamiento_revisiones LIMIT 1"
    )).first():
        raise RuntimeError("Existen revisiones E4: downgrade destructivo no autorizado")
    op.drop_index("ix_inv_e4_revision_evidencia_version",
                  table_name="inventario_levantamiento_revision_evidencias")
    op.drop_table("inventario_levantamiento_revision_evidencias")
    op.drop_index("ix_inv_e4_revision_e2", table_name="inventario_levantamiento_revisiones")
    op.drop_index("ix_inv_e4_revision_bandeja",
                  table_name="inventario_levantamiento_revisiones")
    op.drop_table("inventario_levantamiento_revisiones")
