"""WSO-02: mark iVentas COMPLETED superseded runs whose payload was pruned.

Revision ID: wso02ivnt110226
Revises: wso01caja110226

Schema-only, reversible. No data deleted by Alembic.
"""
from alembic import op
import sqlalchemy as sa


revision = "wso02ivnt110226"
down_revision = "wso01caja110226"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marketing_iventas_sync_runs",
        sa.Column("payload_pruned_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )


def downgrade():
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT EXISTS (
          SELECT 1 FROM public.marketing_iventas_sync_runs
          WHERE payload_pruned_at IS NOT NULL
        )
    """)).scalar_one()
    if rows:
        raise RuntimeError(
            "WSO-02 downgrade blocked: run payload was permanently pruned."
        )
    op.drop_column(
        "marketing_iventas_sync_runs", "payload_pruned_at", schema="public"
    )
