"""create maintenance reprogram reasons

Revision ID: e5a9c3d7f1b2
Revises: d4f8b2c6e1a3
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "e5a9c3d7f1b2"
down_revision = "d4f8b2c6e1a3"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "maintenance_reprogram_reasons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column(
            "requiere_comentario",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "orden",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "key",
            name="uq_maintenance_reprogram_reasons_key",
        ),
    )

    op.create_index(
        "ix_maintenance_reprogram_reasons_active_order",
        "maintenance_reprogram_reasons",
        ["activo", "orden"],
        unique=False,
    )

    op.bulk_insert(
        table,
        [
            {
                "key": "REFACCION_PENDIENTE",
                "nombre": "Refacción pendiente",
                "requiere_comentario": False,
                "activo": True,
                "orden": 10,
            },
            {
                "key": "PROVEEDOR_EXTERNO",
                "nombre": "Proveedor externo",
                "requiere_comentario": False,
                "activo": True,
                "orden": 20,
            },
            {
                "key": "EQUIPO_NO_DISPONIBLE",
                "nombre": "Equipo no disponible",
                "requiere_comentario": False,
                "activo": True,
                "orden": 30,
            },
            {
                "key": "REPROGRAMACION_OPERATIVA",
                "nombre": "Reprogramación operativa",
                "requiere_comentario": False,
                "activo": True,
                "orden": 40,
            },
            {
                "key": "FALTA_TECNICO",
                "nombre": "Falta de técnico",
                "requiere_comentario": False,
                "activo": True,
                "orden": 50,
            },
            {
                "key": "OTRO",
                "nombre": "Otro",
                "requiere_comentario": True,
                "activo": True,
                "orden": 60,
            },
        ],
    )


def downgrade():
    op.drop_index(
        "ix_maintenance_reprogram_reasons_active_order",
        table_name="maintenance_reprogram_reasons",
    )
    op.drop_table("maintenance_reprogram_reasons")
