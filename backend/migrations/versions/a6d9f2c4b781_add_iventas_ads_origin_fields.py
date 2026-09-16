"""add iVentas ads origin fields

Revision ID: a6d9f2c4b781
Revises: f4c2a8e71b36
Create Date: 2026-09-15

Persist the provider-owned ad-origin evidence returned by
GET /v1/integrations/contacts:

- isFromAds -> marketing_iventas_contacts.is_from_ads
- adsSourceId -> marketing_iventas_contacts.ads_source_id

Historical rows remain NULL because older snapshots did not persist
these provider fields. New sync runs preserve true / false explicitly.
"""

from alembic import op
import sqlalchemy as sa


revision = "a6d9f2c4b781"
down_revision = "f4c2a8e71b36"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_marketing_iventas_contacts_run_ads_first_message"


def upgrade():
    op.add_column(
        "marketing_iventas_contacts",
        sa.Column("is_from_ads", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "marketing_iventas_contacts",
        sa.Column("ads_source_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        INDEX_NAME,
        "marketing_iventas_contacts",
        ["sync_run_id", "is_from_ads", "first_message_date_local"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        INDEX_NAME,
        table_name="marketing_iventas_contacts",
    )
    op.drop_column("marketing_iventas_contacts", "ads_source_id")
    op.drop_column("marketing_iventas_contacts", "is_from_ads")
