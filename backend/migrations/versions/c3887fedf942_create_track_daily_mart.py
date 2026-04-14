"""create track_daily_mart

Revision ID: c3887fedf942
Revises: e0e4bee0db8c
Create Date: 2026-04-10 10:51:31.255932

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3887fedf942'
down_revision = 'e0e4bee0db8c'
branch_labels = None
depends_on = None



def upgrade():
    op.create_table(
        "track_daily_mart",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),

        # F2 metas / base mensual
        sa.Column("target_month", sa.Date(), nullable=False),
        sa.Column("m2_sin_circulaciones", sa.Numeric(12, 2), nullable=True),
        sa.Column("usuarios_inicio_mes", sa.Integer(), nullable=True),
        sa.Column("proyeccion_usuarios_cierre_mes", sa.Integer(), nullable=True),
        sa.Column("meta_faycgo_mes", sa.Numeric(14, 2), nullable=True),
        sa.Column("meta_clientes_nuevos_mes", sa.Integer(), nullable=True),
        sa.Column("meta_reactivaciones_mes", sa.Integer(), nullable=True),
        sa.Column("meta_bajas_mes", sa.Integer(), nullable=True),
        sa.Column("meta_nuevos_domiciliados_mes", sa.Integer(), nullable=True),
        sa.Column("meta_arpu_mes", sa.Numeric(14, 2), nullable=True),
        sa.Column("meta_venta_tienda_mes", sa.Numeric(14, 2), nullable=True),

        # F3 desempeño
        sa.Column("usuarios_activos_actual", sa.Integer(), nullable=True),
        sa.Column("reactivaciones_real_mtd", sa.Integer(), nullable=True),
        sa.Column("bajas_reales_mtd", sa.Integer(), nullable=True),

        # F4 ingresos
        sa.Column("ingreso_real_mtd", sa.Numeric(14, 2), nullable=True),

        # F5 nuevos
        sa.Column("clientes_nuevos_real_mtd", sa.Integer(), nullable=True),

        # F6 domiciliados efectivos
        sa.Column("nuevos_domiciliados_real_mtd", sa.Integer(), nullable=True),

        # lineage mínimo
        sa.Column("source_snapshot_id_desempeno", sa.BigInteger(), nullable=True),
        sa.Column("source_snapshot_id_ingresos", sa.BigInteger(), nullable=True),
        sa.Column("source_snapshot_id_nuevos", sa.BigInteger(), nullable=True),
        sa.Column("source_snapshot_id_domiciliados", sa.BigInteger(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),

        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            name="fk_track_daily_mart_sucursal_canon",
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "uq_track_daily_mart_date_branch",
        "track_daily_mart",
        ["business_date", "sucursal_canon"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_track_daily_mart_date_branch",
        table_name="track_daily_mart",
    )
    op.drop_table("track_daily_mart")