"""backfill sucursales orden apertura

Revision ID: 0e96bf84836b
Revises: f0f20fb8458a
Create Date: 2026-05-25 08:02:30.630133

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0e96bf84836b'
down_revision = 'f0f20fb8458a'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            UPDATE sucursales AS s
            SET orden_apertura = mapping.orden_apertura
            FROM (
                VALUES
                    (1, 1),
                    (2, 2),
                    (3, 3),
                    (4, 4),
                    (5, 5),
                    (6, 6),
                    (7, 7),
                    (8, 8),
                    (9, 9),
                    (10, 10),
                    (11, 11),
                    (12, 12),
                    (13, 13),
                    (14, 14),
                    (15, 15),
                    (16, 16),
                    (17, 17),
                    (18, 18),
                    (19, 19),
                    (20, 20),
                    (21, 21),
                    (22, 22),
                    (24, 23),
                    (25, 24),
                    (23, 25)
            ) AS mapping(sucursal_id, orden_apertura)
            WHERE s.sucursal_id = mapping.sucursal_id;
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            """
            UPDATE sucursales
            SET orden_apertura = NULL
            WHERE sucursal_id IN (
                1, 2, 3, 4, 5,
                6, 7, 8, 9, 10,
                11, 12, 13, 14, 15,
                16, 17, 18, 19, 20,
                21, 22, 23, 24, 25
            );
            """
        )
    )