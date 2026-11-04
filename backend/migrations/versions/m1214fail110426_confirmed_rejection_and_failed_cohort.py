"""Campaign V2: confirmed rejection job events and idempotent failed cohort.

Revision ID: m1214fail110426
Revises: p1181c102030
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "m1214fail110426"
down_revision = "p1181c102030"
branch_labels = None
depends_on = None

OLD_EVENTS = (
    "event_kind IN ('ENQUEUED','STARTED','CHILD_ACCEPTED','STOP_REQUESTED',"
    "'STOPPED','COMPLETED','REVIEW_REQUIRED')"
)
NEW_EVENTS = (
    "event_kind IN ('ENQUEUED','STARTED','CHILD_ACCEPTED','CHILD_REJECTED',"
    "'STOP_REQUESTED','STOPPED','COMPLETED','REVIEW_REQUIRED')"
)


def upgrade():
    op.drop_constraint(
        "ck_mkt_v2_bg_job_events_kind",
        "marketing_campaign_v2_background_job_events",
        schema="public", type_="check",
    )
    op.create_check_constraint(
        "ck_mkt_v2_bg_job_events_kind",
        "marketing_campaign_v2_background_job_events",
        NEW_EVENTS, schema="public",
    )
    op.create_table(
        "marketing_campaign_v2_failed_recoveries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_campaign_id", sa.BigInteger(),
            sa.ForeignKey("public.marketing_campaign_v2_campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "derived_campaign_id", sa.BigInteger(),
            sa.ForeignKey("public.marketing_campaign_v2_campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("failed_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_child_ids_json", sa.JSON(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_user_id", sa.Integer(),
            sa.ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "source_campaign_id", "failed_fingerprint",
            name="uq_mkt_v2_failed_recoveries_source_fingerprint",
        ),
        sa.UniqueConstraint(
            "derived_campaign_id", name="uq_mkt_v2_failed_recoveries_derived_campaign_id",
        ),
        sa.CheckConstraint(
            "recipient_count > 0", name="ck_mkt_v2_failed_recoveries_count",
        ),
        sa.CheckConstraint(
            "length(failed_fingerprint) = 64",
            name="ck_mkt_v2_failed_recoveries_digest",
        ),
        schema="public",
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM public.marketing_campaign_v2_failed_recoveries)")
    ).scalar_one():
        raise RuntimeError("Cannot drop nonempty failed campaign derivation audit.")
    if bind.execute(sa.text("""
        SELECT EXISTS(
          SELECT 1 FROM public.marketing_campaign_v2_background_job_events
          WHERE event_kind='CHILD_REJECTED'
        )
    """)).scalar_one():
        raise RuntimeError("Cannot drop confirmed rejection events.")
    op.drop_table("marketing_campaign_v2_failed_recoveries", schema="public")
    op.drop_constraint(
        "ck_mkt_v2_bg_job_events_kind",
        "marketing_campaign_v2_background_job_events", schema="public",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mkt_v2_bg_job_events_kind",
        "marketing_campaign_v2_background_job_events", OLD_EVENTS,
        schema="public",
    )
