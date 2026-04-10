"""create track_monthly_targets

Revision ID: 1478ce6503b9
Revises: f6298f01cfad
Create Date: 2026-04-08 09:28:21.100392

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1478ce6503b9'
down_revision = 'f6298f01cfad'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "track_monthly_targets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("target_month", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),

        sa.Column("m2_sin_circulaciones", sa.Numeric(12, 2), nullable=False),
        sa.Column("usuarios_inicio_mes", sa.Integer(), nullable=False),
        sa.Column("proyeccion_usuarios_cierre_mes", sa.Integer(), nullable=False),

        sa.Column("meta_faycgo_mes", sa.Numeric(14, 2), nullable=False),
        sa.Column("meta_clientes_nuevos_mes", sa.Integer(), nullable=False),
        sa.Column("meta_reactivaciones_mes", sa.Integer(), nullable=False),
        sa.Column("meta_bajas_mes", sa.Integer(), nullable=False),
        sa.Column("meta_nuevos_domiciliados_mes", sa.Integer(), nullable=False),
        sa.Column("meta_arpu_mes", sa.Numeric(14, 2), nullable=False),
        sa.Column("meta_venta_tienda_mes", sa.Numeric(14, 2), nullable=False),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),

        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            name="fk_track_monthly_targets_sucursal_canon",
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "uq_track_monthly_targets_active_month_branch",
        "track_monthly_targets",
        ["target_month", "sucursal_canon"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade():
    op.drop_index(
        "uq_track_monthly_targets_active_month_branch",
        table_name="track_monthly_targets",
    )
    op.drop_table("track_monthly_targets")