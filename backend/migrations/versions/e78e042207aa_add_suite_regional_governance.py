"""add suite regional governance

Revision ID: e78e042207aa
Revises: 422da9dde3bf
Create Date: 2026-05-25 07:30:07.817387

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e78e042207aa'
down_revision = '422da9dde3bf'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "suite_regions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_key", sa.String(length=80), nullable=False),
        sa.Column("region_label", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_suite_regions_region_key",
        "suite_regions",
        ["region_key"],
        unique=True,
    )

    op.create_table(
        "suite_sucursal_region_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["suite_regions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sucursal_id",
            "region_id",
            "valid_from",
            name="uq_suite_sucursal_region_assignment_period",
        ),
    )

    op.create_index(
        "ix_suite_sucursal_region_assignments_sucursal_id",
        "suite_sucursal_region_assignments",
        ["sucursal_id"],
        unique=False,
    )

    op.create_index(
        "ix_suite_sucursal_region_assignments_region_id",
        "suite_sucursal_region_assignments",
        ["region_id"],
        unique=False,
    )

    op.create_index(
        "ix_suite_sucursal_region_assignments_is_current",
        "suite_sucursal_region_assignments",
        ["is_current"],
        unique=False,
    )

    op.create_index(
        "uq_suite_sucursal_region_current",
        "suite_sucursal_region_assignments",
        ["sucursal_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "suite_region_managers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["suite_regions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region_id",
            "user_id",
            name="uq_suite_region_manager_region_user",
        ),
    )

    op.create_index(
        "ix_suite_region_managers_region_id",
        "suite_region_managers",
        ["region_id"],
        unique=False,
    )

    op.create_index(
        "ix_suite_region_managers_user_id",
        "suite_region_managers",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_suite_region_managers_is_active",
        "suite_region_managers",
        ["is_active"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_suite_region_managers_is_active",
        table_name="suite_region_managers",
    )

    op.drop_index(
        "ix_suite_region_managers_user_id",
        table_name="suite_region_managers",
    )

    op.drop_index(
        "ix_suite_region_managers_region_id",
        table_name="suite_region_managers",
    )

    op.drop_table("suite_region_managers")

    op.drop_index(
        "uq_suite_sucursal_region_current",
        table_name="suite_sucursal_region_assignments",
    )

    op.drop_index(
        "ix_suite_sucursal_region_assignments_is_current",
        table_name="suite_sucursal_region_assignments",
    )

    op.drop_index(
        "ix_suite_sucursal_region_assignments_region_id",
        table_name="suite_sucursal_region_assignments",
    )

    op.drop_index(
        "ix_suite_sucursal_region_assignments_sucursal_id",
        table_name="suite_sucursal_region_assignments",
    )

    op.drop_table("suite_sucursal_region_assignments")

    op.drop_index(
        "ix_suite_regions_region_key",
        table_name="suite_regions",
    )

    op.drop_table("suite_regions")