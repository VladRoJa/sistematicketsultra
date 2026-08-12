"""make iventas raw has_more nullable

Revision ID: c42e918f6a31
Revises: fb26a4021f8a
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "c42e918f6a31"
down_revision = "fb26a4021f8a"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "marketing_iventas_raw_pages",
        "has_more",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        nullable=True,
    )


def downgrade():
    bind = op.get_bind()

    null_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM marketing_iventas_raw_pages
            WHERE has_more IS NULL
            """
        )
    ).scalar_one()

    if int(null_count) > 0:
        raise RuntimeError(
            "No se puede restaurar has_more NOT NULL: "
            "existen raw pages todavía sin parsear."
        )

    op.alter_column(
        "marketing_iventas_raw_pages",
        "has_more",
        existing_type=sa.Boolean(),
        existing_nullable=True,
        nullable=False,
    )
