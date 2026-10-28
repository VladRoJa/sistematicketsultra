"""E4 Bloque 1: persistencia del corte y evidencia de importaciones, sin tocar inventario oficial.
Revision ID: v2e4b1102826
Revises: v2e3a1102626
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2e4b1102826"
down_revision = "v2e3a1102626"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventario_levantamientos",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("cycle_key", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("origen_corte", sa.String(24), nullable=False),
        sa.Column("modalidad", sa.String(16), nullable=False),
        sa.Column("responsable", sa.String(200), nullable=True),
        sa.Column("fecha_corte_local", sa.Date(), nullable=True),
        sa.Column("creado_por_usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("creado_en_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("baseline_sha256", sa.String(64), nullable=True),
        sa.Column("baseline_storage_key", sa.String(250), nullable=True),
        sa.Column("baseline_capturado_en_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("baseline_resumen", postgresql.JSONB(), nullable=False),
        sa.Column("estado", sa.String(24), nullable=False),
        sa.Column("ultima_importacion_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("origen_corte IN ('CSV_HISTORICO','DB_ACTUAL','INICIAL')", name="ck_inv_e4_origen"),
        sa.CheckConstraint("modalidad IN ('VERIFICACION','INICIAL')", name="ck_inv_e4_modalidad"),
        sa.CheckConstraint("estado IN ('PREPARATION','IN_PROGRESS')", name="ck_inv_e4_estado_b1"),
    )
    op.create_index("ix_inv_e4_levantamientos_sucursal_fecha", "inventario_levantamientos", ["sucursal_id","creado_en_utc"])
    op.create_table(
        "inventario_levantamiento_referencias",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("levantamiento_id", sa.BigInteger(), sa.ForeignKey("inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventario_id_original", sa.Integer(), nullable=False),
        sa.Column("codigo_interno_original", sa.String(100), nullable=True),
        sa.Column("stock_original", sa.Integer(), nullable=False),
        sa.Column("datos_originales", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("levantamiento_id","inventario_id_original", name="uq_inv_e4_ref_corte_id"),
        sa.CheckConstraint("stock_original > 0", name="ck_inv_e4_ref_stock_positivo"),
    )
    op.create_index("ix_inv_e4_ref_inventario", "inventario_levantamiento_referencias", ["inventario_id_original"])
    op.create_table(
        "inventario_levantamiento_importaciones",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("levantamiento_id", sa.BigInteger(), sa.ForeignKey("inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(250), nullable=False),
        sa.Column("cargado_por_usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cargado_en_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resultado", sa.String(16), nullable=False),
        sa.Column("control", postgresql.JSONB(), nullable=False),
        sa.Column("resumen", postgresql.JSONB(), nullable=False),
        sa.Column("diagnosticos", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("levantamiento_id","version", name="uq_inv_e4_import_version"),
        sa.UniqueConstraint("levantamiento_id","idempotency_key", name="uq_inv_e4_import_idempotency"),
        sa.UniqueConstraint("levantamiento_id","file_sha256", name="uq_inv_e4_import_hash"),
        sa.CheckConstraint("version >= 1", name="ck_inv_e4_import_version"),
        sa.CheckConstraint("resultado IN ('VALIDATED','INCOMPLETE','INVALID')", name="ck_inv_e4_import_resultado"),
    )
    op.create_index("ix_inv_e4_import_levantamiento_fecha", "inventario_levantamiento_importaciones", ["levantamiento_id","cargado_en_utc"])
    op.create_table(
        "inventario_levantamiento_filas",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("importacion_id", sa.BigInteger(), sa.ForeignKey("inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hoja", sa.String(12), nullable=False),
        sa.Column("fila_excel", sa.Integer(), nullable=False),
        sa.Column("inventario_id_declarado", sa.Integer(), nullable=True),
        sa.Column("codigo_declarado", sa.String(120), nullable=True),
        sa.Column("respuesta", sa.String(12), nullable=True),
        sa.Column("datos_crudos", postgresql.JSONB(), nullable=False),
        sa.Column("diagnosticos", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("importacion_id","hoja","fila_excel", name="uq_inv_e4_fila_ubicacion"),
        sa.CheckConstraint("hoja IN ('APARATOS','HALLAZGOS')", name="ck_inv_e4_fila_hoja"),
        sa.CheckConstraint("respuesta IS NULL OR respuesta IN ('SI','NO','SIN_REVISAR')", name="ck_inv_e4_fila_respuesta"),
    )


def downgrade():
    # Rechazar destrucción de evidencia real y sus versiones.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM inventario_levantamientos LIMIT 1")).first():
        raise RuntimeError("E4 contiene levantamientos: downgrade destructivo bloqueado")
    op.drop_table("inventario_levantamiento_filas")
    op.drop_index("ix_inv_e4_import_levantamiento_fecha", table_name="inventario_levantamiento_importaciones")
    op.drop_table("inventario_levantamiento_importaciones")
    op.drop_index("ix_inv_e4_ref_inventario", table_name="inventario_levantamiento_referencias")
    op.drop_table("inventario_levantamiento_referencias")
    op.drop_index("ix_inv_e4_levantamientos_sucursal_fecha", table_name="inventario_levantamientos")
    op.drop_table("inventario_levantamientos")
