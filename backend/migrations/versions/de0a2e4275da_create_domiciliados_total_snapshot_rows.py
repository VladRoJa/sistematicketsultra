"""create domiciliados_total_snapshot_rows

Revision ID: de0a2e4275da
Revises: 2f1b9a227af9
Create Date: 2026-04-10 07:08:38.447242

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'de0a2e4275da'
down_revision = '2f1b9a227af9'
branch_labels = None
depends_on = None



def upgrade():
    op.create_table(
        "domiciliados_total_snapshot_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("sucursal", sa.Text(), nullable=False),
        sa.Column("general", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["domiciliados_total_snapshots.id"],
            name="fk_domiciliados_total_snapshot_rows_snapshot_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "uq_domiciliados_total_snapshot_rows_snapshot_row_index",
        "domiciliados_total_snapshot_rows",
        ["snapshot_id", "row_index"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_domiciliados_total_snapshot_rows_snapshot_row_index",
        table_name="domiciliados_total_snapshot_rows",
    )
    op.drop_table("domiciliados_total_snapshot_rows")