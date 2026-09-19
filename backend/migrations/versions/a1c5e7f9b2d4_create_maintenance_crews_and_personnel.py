"""create maintenance crews and personnel

Revision ID: a1c5e7f9b2d4
Revises: f8b2d4e6a1c3
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "a1c5e7f9b2d4"
down_revision = "f8b2d4e6a1c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_crews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["suite_regions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "nombre",
            name="uq_maintenance_crews_nombre",
        ),
    )
    op.create_index(
        "ix_maintenance_crews_region_id",
        "maintenance_crews",
        ["region_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_crews_activo_region",
        "maintenance_crews",
        ["activo", "region_id"],
        unique=False,
    )

    op.create_table(
        "maintenance_personnel",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("crew_id", sa.Integer(), nullable=True),
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["crew_id"],
            ["maintenance_crews.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            name="uq_maintenance_personnel_user_id",
        ),
    )
    op.create_index(
        "ix_maintenance_personnel_user_id",
        "maintenance_personnel",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_maintenance_personnel_crew_id",
        "maintenance_personnel",
        ["crew_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_personnel_activo_crew",
        "maintenance_personnel",
        ["activo", "crew_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_maintenance_personnel_activo_crew",
        table_name="maintenance_personnel",
    )
    op.drop_index(
        "ix_maintenance_personnel_crew_id",
        table_name="maintenance_personnel",
    )
    op.drop_index(
        "ix_maintenance_personnel_user_id",
        table_name="maintenance_personnel",
    )
    op.drop_table("maintenance_personnel")

    op.drop_index(
        "ix_maintenance_crews_activo_region",
        table_name="maintenance_crews",
    )
    op.drop_index(
        "ix_maintenance_crews_region_id",
        table_name="maintenance_crews",
    )
    op.drop_table("maintenance_crews")
