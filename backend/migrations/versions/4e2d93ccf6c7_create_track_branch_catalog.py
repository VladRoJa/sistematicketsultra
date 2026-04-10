"""create track_branch_catalog

Revision ID: 4e2d93ccf6c7
Revises: 03dba6aef03f
Create Date: 2026-04-08 08:40:45.395698

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4e2d93ccf6c7'
down_revision = '03dba6aef03f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "track_branch_catalog",
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("track_label", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_track_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("sucursal_canon", name="pk_track_branch_catalog"),
    )

    op.create_index(
        "uq_track_branch_catalog_active_label",
        "track_branch_catalog",
        ["track_label"],
        unique=True,
        postgresql_where=sa.text("is_track_active = true"),
    )

    op.create_index(
        "uq_track_branch_catalog_active_display_order",
        "track_branch_catalog",
        ["display_order"],
        unique=True,
        postgresql_where=sa.text("is_track_active = true"),
    )


def downgrade():
    op.drop_index("uq_track_branch_catalog_active_display_order", table_name="track_branch_catalog")
    op.drop_index("uq_track_branch_catalog_active_label", table_name="track_branch_catalog")
    op.drop_table("track_branch_catalog")