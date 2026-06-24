"""drop legacy horarios asistencia tables

Revision ID: ca315822669e
Revises: 1f0f74cb05c8
Create Date: 2026-06-24 11:35:00.853051

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ca315822669e'
down_revision = '1f0f74cb05c8'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("registro_asistencia")
    op.drop_table("empleado_horario_asignado")
    op.drop_table("bloques_horario")
    op.drop_table("horarios_generales")


def downgrade():
    op.create_table(
        "horarios_generales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=50), nullable=True),
        sa.Column("ciclo", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bloques_horario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("horario_general_id", sa.Integer(), nullable=False),
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("es_descanso", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["horario_general_id"], ["horarios_generales.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "empleado_horario_asignado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("horario_general_id", sa.Integer(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["horario_general_id"], ["horarios_generales.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "registro_asistencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("tipo_marcado", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("estatus", sa.String(length=20), nullable=True),
        sa.Column("observacion", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
