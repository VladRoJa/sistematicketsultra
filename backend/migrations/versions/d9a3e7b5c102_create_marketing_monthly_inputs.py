"""create marketing monthly inputs

Revision ID: d9a3e7b5c102
Revises: c4e7f1a2b903
Create Date: 2026-07-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "d9a3e7b5c102"
down_revision = "c4e7f1a2b903"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_monthly_inputs",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "month_start",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "sucursal_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "investment",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "leads",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "month_start = date_trunc('month', month_start)::date",
            name="ck_marketing_monthly_inputs_first_day",
        ),
        sa.CheckConstraint(
            "investment >= 0",
            name=(
                "ck_marketing_monthly_inputs_"
                "investment_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            "leads >= 0",
            name="ck_marketing_monthly_inputs_leads_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_marketing_monthly_inputs_created_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            name="fk_marketing_monthly_inputs_sucursal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_marketing_monthly_inputs_updated_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_monthly_inputs",
        ),
        sa.UniqueConstraint(
            "month_start",
            "sucursal_id",
            name="uq_marketing_monthly_inputs_month_branch",
        ),
    )
    op.create_index(
        "ix_marketing_monthly_inputs_month_start",
        "marketing_monthly_inputs",
        ["month_start"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_monthly_inputs_sucursal_id",
        "marketing_monthly_inputs",
        ["sucursal_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_monthly_inputs_sucursal_id",
        table_name="marketing_monthly_inputs",
    )
    op.drop_index(
        "ix_marketing_monthly_inputs_month_start",
        table_name="marketing_monthly_inputs",
    )
    op.drop_table("marketing_monthly_inputs")
