"""create track_branch_aliases

Revision ID: 214114c2361e
Revises: 4e2d93ccf6c7
Create Date: 2026-04-08 09:07:46.850908

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '214114c2361e'
down_revision = '4e2d93ccf6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "track_branch_aliases",
        sa.Column("source_family", sa.Text(), nullable=False),
        sa.Column("raw_branch_name", sa.Text(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "source_family",
            "raw_branch_name",
            name="pk_track_branch_aliases",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            name="fk_track_branch_aliases_sucursal_canon",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "source_family IN ('manual_targets', 'gasca_family', 'domiciliados_total', 'domiciliados_recep', 'venta_tienda')",
            name="ck_track_branch_aliases_source_family",
        ),
    )


def downgrade():
    op.drop_table("track_branch_aliases")