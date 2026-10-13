"""Persist only safe iVentas branch failure classifications per sync run.

Revision ID: f62a1b9d4c07
Revises: e4b856c9170d
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "f62a1b9d4c07"
down_revision = "e4b856c9170d"
branch_labels = None
depends_on = None

TABLE = "marketing_iventas_branch_failures"
ALLOWED_TYPES = (
    "ALIAS_UNRESOLVED",
    "ALIAS_AMBIGUOUS_DESTINATION",
    "MarketingIventasBranchResolutionError",
    "MarketingIventasBranchSyncError",
    "IventasClientError",
    "UNEXPECTED_BRANCH_ABORT",
)


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("sync_run_id", sa.BigInteger(), nullable=False),
        sa.Column("branch_code", sa.String(100), nullable=False),
        sa.Column("error_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("sync_run_id", "branch_code",
                                name="pk_iventas_branch_failures"),
        sa.ForeignKeyConstraint(
            ["sync_run_id"], ["marketing_iventas_sync_runs.id"],
            ondelete="CASCADE",
            name="fk_iventas_branch_failures_run",
        ),
        sa.CheckConstraint(
            "length(trim(branch_code)) BETWEEN 1 AND 100",
            name="ck_iventas_branch_failures_code",
        ),
        sa.CheckConstraint(
            "error_type IN (" + ", ".join("'" + code + "'" for code in ALLOWED_TYPES) + ")",
            name="ck_iventas_branch_failures_type",
        ),
    )


def downgrade():
    # No destruir diagnósticos históricos de forma automática.
    count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM " + TABLE)
    ).scalar()
    if int(count or 0):
        raise RuntimeError(
            "Hay fallos por sucursal guardados; su eliminación requiere "
            "autorización explícita y respaldo."
        )
    op.drop_table(TABLE)
