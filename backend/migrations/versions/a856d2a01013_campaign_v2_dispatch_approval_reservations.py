"""Issue #856 D2a: audited approval and capacity reservations (no provider sends).

Revision ID: a856d2a01013
Revises: f4d856a1b20c
"""
from alembic import op
import sqlalchemy as sa

revision = "a856d2a01013"
down_revision = "f4d856a1b20c"
branch_labels = None
depends_on = None

APPROVAL = "marketing_campaign_v2_dispatch_approvals"
RESERVATION = "marketing_campaign_v2_capacity_reservations"


def upgrade():
    op.create_table(
        APPROVAL,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("campaign_v2_id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("dispatch_fingerprint", sa.String(64), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("approved_estimated_mxn", sa.Numeric(14, 2), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_v2_id"], ["marketing_campaign_v2_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["marketing_campaign_v2_templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("campaign_v2_id", name="uq_mkt_v2_approval_campaign"),
        sa.CheckConstraint("recipient_count > 0", name="ck_mkt_v2_approval_recipients"),
        sa.CheckConstraint("approved_estimated_mxn >= 0", name="ck_mkt_v2_approval_cost"),
        sa.CheckConstraint("length(dispatch_fingerprint) = 64", name="ck_mkt_v2_approval_fingerprint"),
        sa.CheckConstraint("approved_at < expires_at", name="ck_mkt_v2_approval_window"),
    )
    op.create_table(
        RESERVATION,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("approval_id", sa.BigInteger(), nullable=False),
        sa.Column("attestation_id", sa.BigInteger(), nullable=False),
        sa.Column("scope_kind", sa.String(20), nullable=False),
        sa.Column("scope_key", sa.String(255), nullable=False),
        sa.Column("reserved_messages", sa.Integer(), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["approval_id"], [APPROVAL + ".id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["attestation_id"], ["marketing_campaign_v2_quota_capacity_attestations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("approval_id", "scope_kind", "scope_key", name="uq_mkt_v2_reservation_scope"),
        sa.CheckConstraint("scope_kind IN ('CHANNEL', 'PORTFOLIO')", name="ck_mkt_v2_reservation_kind"),
        sa.CheckConstraint("reserved_messages > 0", name="ck_mkt_v2_reservation_positive"),
        sa.CheckConstraint("length(trim(scope_key)) > 0", name="ck_mkt_v2_reservation_key"),
    )
    op.create_index("ix_mkt_v2_reservation_active", RESERVATION,
                    ["scope_kind", "scope_key", "reserved_until"])


def downgrade():
    for name in (RESERVATION, APPROVAL):
        count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + name)).scalar()
        if int(count or 0):
            raise RuntimeError("No se borra historial de aprobación/reservas sin autorización.")
    op.drop_index("ix_mkt_v2_reservation_active", table_name=RESERVATION)
    op.drop_table(RESERVATION)
    op.drop_table(APPROVAL)
