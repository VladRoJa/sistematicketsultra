"""add warehouse commercial catalog

Revision ID: 9dfa6aad20cb
Revises: 37d51eb7ff9c
Create Date: 2026-05-20 18:43:17.818384

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9dfa6aad20cb'
down_revision = '37d51eb7ff9c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "warehouse_commercial_catalog",
        sa.Column("id", sa.Integer(), nullable=False),

        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("normalized_description", sa.Text(), nullable=False),

        sa.Column("commercial_canon", sa.Text(), nullable=True),
        sa.Column(
            "family",
            sa.Text(),
            server_default=sa.text("'sin_clasificar'"),
            nullable=False,
        ),
        sa.Column("subfamily", sa.Text(), nullable=True),

        sa.Column(
            "is_promo",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_membership",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_retail",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_aggregator",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "needs_business_validation",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),

        sa.Column("notes", sa.Text(), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_warehouse_commercial_catalog_raw_description",
        "warehouse_commercial_catalog",
        ["raw_description"],
        unique=True,
    )
    op.create_index(
        "ix_warehouse_commercial_catalog_normalized_description",
        "warehouse_commercial_catalog",
        ["normalized_description"],
        unique=False,
    )
    op.create_index(
        "ix_warehouse_commercial_catalog_commercial_canon",
        "warehouse_commercial_catalog",
        ["commercial_canon"],
        unique=False,
    )
    op.create_index(
        "ix_warehouse_commercial_catalog_family",
        "warehouse_commercial_catalog",
        ["family"],
        unique=False,
    )
    op.create_index(
        "ix_warehouse_commercial_catalog_is_promo",
        "warehouse_commercial_catalog",
        ["is_promo"],
        unique=False,
    )
    op.create_index(
        "ix_warehouse_commercial_catalog_is_active",
        "warehouse_commercial_catalog",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_warehouse_commercial_catalog_needs_business_validation",
        "warehouse_commercial_catalog",
        ["needs_business_validation"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_warehouse_commercial_catalog_needs_business_validation",
        table_name="warehouse_commercial_catalog",
    )
    op.drop_index(
        "ix_warehouse_commercial_catalog_is_active",
        table_name="warehouse_commercial_catalog",
    )
    op.drop_index(
        "ix_warehouse_commercial_catalog_is_promo",
        table_name="warehouse_commercial_catalog",
    )
    op.drop_index(
        "ix_warehouse_commercial_catalog_family",
        table_name="warehouse_commercial_catalog",
    )
    op.drop_index(
        "ix_warehouse_commercial_catalog_commercial_canon",
        table_name="warehouse_commercial_catalog",
    )
    op.drop_index(
        "ix_warehouse_commercial_catalog_normalized_description",
        table_name="warehouse_commercial_catalog",
    )
    op.drop_index(
        "ix_warehouse_commercial_catalog_raw_description",
        table_name="warehouse_commercial_catalog",
    )

    op.drop_table("warehouse_commercial_catalog")
