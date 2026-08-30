"""create mantenimiento equipos structure

Revision ID: a6c1e9f42b73
Revises: d4e5f6a7b8c9
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = "a6c1e9f42b73"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "familia_equipo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("categoria_inventario_id", sa.Integer(), nullable=True),
        sa.Column(
            "activo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["categoria_inventario_id"],
            ["catalogo_categoria_inventario.id"],
            name="fk_familia_equipo_categoria_inventario",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_familia_equipo"),
        sa.UniqueConstraint("key", name="uq_familia_equipo_key"),
    )
    op.create_index(
        "ix_familia_equipo_categoria_inventario_id",
        "familia_equipo",
        ["categoria_inventario_id"],
        unique=False,
    )
    op.create_index(
        "ix_familia_equipo_activo",
        "familia_equipo",
        ["activo"],
        unique=False,
    )

    op.add_column(
        "inventario_general",
        sa.Column("familia_equipo_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventario_general_familia_equipo",
        "inventario_general",
        "familia_equipo",
        ["familia_equipo_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_inventario_general_familia_equipo_id",
        "inventario_general",
        ["familia_equipo_id"],
        unique=False,
    )

    op.create_table(
        "falla_mantenimiento",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("familia_equipo_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column(
            "activo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "orden",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["familia_equipo_id"],
            ["familia_equipo.id"],
            name="fk_falla_mantenimiento_familia_equipo",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_falla_mantenimiento"),
        sa.UniqueConstraint(
            "familia_equipo_id",
            "key",
            name="uq_falla_mantenimiento_familia_key",
        ),
    )
    op.create_index(
        "ix_falla_mantenimiento_familia_activo_orden",
        "falla_mantenimiento",
        ["familia_equipo_id", "activo", "orden"],
        unique=False,
    )

    op.add_column(
        "tickets",
        sa.Column("familia_equipo_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("falla_mantenimiento_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("condicion_operativa", sa.String(length=20), nullable=True),
    )
    op.create_foreign_key(
        "fk_tickets_familia_equipo",
        "tickets",
        "familia_equipo",
        ["familia_equipo_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tickets_falla_mantenimiento",
        "tickets",
        "falla_mantenimiento",
        ["falla_mantenimiento_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_tickets_condicion_operativa",
        "tickets",
        "condicion_operativa IS NULL "
        "OR condicion_operativa IN ('TRABAJA', 'NO_TRABAJA')",
    )
    op.create_index(
        "ix_tickets_familia_equipo_id",
        "tickets",
        ["familia_equipo_id"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_falla_mantenimiento_id",
        "tickets",
        ["falla_mantenimiento_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_tickets_falla_mantenimiento_id", table_name="tickets")
    op.drop_index("ix_tickets_familia_equipo_id", table_name="tickets")
    op.drop_constraint(
        "ck_tickets_condicion_operativa",
        "tickets",
        type_="check",
    )
    op.drop_constraint(
        "fk_tickets_falla_mantenimiento",
        "tickets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_tickets_familia_equipo",
        "tickets",
        type_="foreignkey",
    )
    op.drop_column("tickets", "condicion_operativa")
    op.drop_column("tickets", "falla_mantenimiento_id")
    op.drop_column("tickets", "familia_equipo_id")

    op.drop_index(
        "ix_falla_mantenimiento_familia_activo_orden",
        table_name="falla_mantenimiento",
    )
    op.drop_table("falla_mantenimiento")

    op.drop_index(
        "ix_inventario_general_familia_equipo_id",
        table_name="inventario_general",
    )
    op.drop_constraint(
        "fk_inventario_general_familia_equipo",
        "inventario_general",
        type_="foreignkey",
    )
    op.drop_column("inventario_general", "familia_equipo_id")

    op.drop_index("ix_familia_equipo_activo", table_name="familia_equipo")
    op.drop_index(
        "ix_familia_equipo_categoria_inventario_id",
        table_name="familia_equipo",
    )
    op.drop_table("familia_equipo")
