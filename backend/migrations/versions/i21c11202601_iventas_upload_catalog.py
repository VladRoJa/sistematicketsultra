"""Track iVentas approval checks and catalog templates published from uploads."""

import sqlalchemy as sa
from alembic import op


revision = "i21c11202601"
down_revision = "i20c11202601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("marketing_iventas_template_uploads", sa.Column("next_review_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_marketing_iventas_template_uploads_next_review_at",
        "marketing_iventas_template_uploads",
        ["next_review_at"],
    )
    op.add_column("marketing_campaign_v2_templates", sa.Column("upload_fingerprint", sa.String(64)))


def downgrade():
    op.drop_column("marketing_campaign_v2_templates", "upload_fingerprint")
    op.drop_index("ix_marketing_iventas_template_uploads_next_review_at", table_name="marketing_iventas_template_uploads")
    op.drop_column("marketing_iventas_template_uploads", "next_review_at")
