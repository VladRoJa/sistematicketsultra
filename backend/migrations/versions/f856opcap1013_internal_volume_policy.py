"""Issue 856 operational limits: audited channel/portfolio limits without fake Meta remaining.

Revision ID: f856opcap1013
Revises: e856d3c21013

Existing evidence-backed approvals keep their non-null attestation references.
New internal-limit approvals record null attestation_id with the policy revision
and basis immutably in the approved manifest.
"""
from alembic import op
import sqlalchemy as sa

revision = "f856opcap1013"
down_revision = "e856d3c21013"
branch_labels = None
depends_on = None

POLICY = "marketing_campaign_v2_quota_policy_revisions"
RESERVATION = "marketing_campaign_v2_capacity_reservations"


def upgrade():
    op.add_column(POLICY, sa.Column("operational_channel_cap", sa.Integer(), nullable=True))
    op.add_column(POLICY, sa.Column("operational_portfolio_cap", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_mkt_v2_operational_caps_pair",
        POLICY,
        "(operational_channel_cap IS NULL AND operational_portfolio_cap IS NULL) OR "
        "(operational_channel_cap IS NOT NULL AND operational_portfolio_cap IS NOT NULL AND operational_channel_cap > 0 AND operational_portfolio_cap > 0)",
    )
    op.alter_column(RESERVATION, "attestation_id", existing_type=sa.BigInteger(),
                    existing_nullable=False, nullable=True)


def downgrade():
    conn = op.get_bind()
    configured = conn.execute(sa.text(
        "SELECT COUNT(*) FROM " + POLICY +
        " WHERE operational_channel_cap IS NOT NULL OR operational_portfolio_cap IS NOT NULL"
    )).scalar()
    unattested = conn.execute(sa.text(
        "SELECT COUNT(*) FROM " + RESERVATION + " WHERE attestation_id IS NULL"
    )).scalar()
    if int(configured or 0) or int(unattested or 0):
        raise RuntimeError("No se borra configuración operativa ni reservas sin respaldo.")
    op.alter_column(RESERVATION, "attestation_id", existing_type=sa.BigInteger(),
                    existing_nullable=True, nullable=False)
    op.drop_constraint("ck_mkt_v2_operational_caps_pair", POLICY, type_="check")
    op.drop_column(POLICY, "operational_portfolio_cap")
    op.drop_column(POLICY, "operational_channel_cap")
