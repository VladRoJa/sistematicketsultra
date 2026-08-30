"""add tornillo danado to peso integrado

Revision ID: c8e3a1b64d95
Revises: b7d2f0a53c84
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = "c8e3a1b64d95"
down_revision = "b7d2f0a53c84"
branch_labels = None
depends_on = None


FAMILY_KEY = "PESO_INTEGRADO"
FAILURE_KEY = "TORNILLO_DANADO"
FAILURE_NAME = "Tornillo dañado"


def upgrade():
    bind = op.get_bind()

    family_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM familia_equipo
            WHERE key = :family_key
              AND activo = TRUE
            """
        ),
        {"family_key": FAMILY_KEY},
    ).scalar()

    if family_id is None:
        raise RuntimeError(f"No existe la familia activa {FAMILY_KEY}")

    bind.execute(
        sa.text(
            """
            INSERT INTO falla_mantenimiento (
                familia_equipo_id,
                key,
                nombre,
                activo,
                orden
            )
            SELECT
                :family_id,
                :failure_key,
                :failure_name,
                TRUE,
                COALESCE(MAX(orden), 0) + 1
            FROM falla_mantenimiento
            WHERE familia_equipo_id = :family_id
              AND NOT EXISTS (
                  SELECT 1
                  FROM falla_mantenimiento
                  WHERE familia_equipo_id = :family_id
                    AND key = :failure_key
              )
            """
        ),
        {
            "family_id": family_id,
            "failure_key": FAILURE_KEY,
            "failure_name": FAILURE_NAME,
        },
    )


def downgrade():
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            DELETE FROM falla_mantenimiento
            WHERE key = :failure_key
              AND familia_equipo_id = (
                  SELECT id
                  FROM familia_equipo
                  WHERE key = :family_key
              )
            """
        ),
        {
            "family_key": FAMILY_KEY,
            "failure_key": FAILURE_KEY,
        },
    )
