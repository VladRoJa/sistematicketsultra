"""link track branch catalog to sucursales

Revision ID: 6add09109634
Revises: 99969d5f6a41
Create Date: 2026-05-23 20:24:00.292069

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6add09109634'
down_revision = '99969d5f6a41'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "track_branch_catalog",
        sa.Column(
            "sucursal_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_track_branch_catalog_sucursal_id_sucursales",
        "track_branch_catalog",
        "sucursales",
        ["sucursal_id"],
        ["sucursal_id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_track_branch_catalog_sucursal_id",
        "track_branch_catalog",
        ["sucursal_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_track_branch_catalog_sucursal_id",
        table_name="track_branch_catalog",
    )

    op.drop_constraint(
        "fk_track_branch_catalog_sucursal_id_sucursales",
        "track_branch_catalog",
        type_="foreignkey",
    )

    op.drop_column(
        "track_branch_catalog",
        "sucursal_id",
    )