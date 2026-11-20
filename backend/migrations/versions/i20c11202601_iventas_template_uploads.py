"""Persist iVentas template upload requests and branch results."""

import sqlalchemy as sa
from alembic import op


revision = "i20c11202601"
down_revision = "i19c11202601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_iventas_template_uploads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("template", sa.JSON(), nullable=False),
        sa.Column("branches", sa.JSON(), nullable=False),
        sa.Column("image", sa.LargeBinary()),
        sa.Column("image_type", sa.String(20)),
    )
    op.create_index(
        "ix_marketing_iventas_template_uploads_status",
        "marketing_iventas_template_uploads",
        ["status"],
    )


def downgrade():
    op.drop_index("ix_marketing_iventas_template_uploads_status", table_name="marketing_iventas_template_uploads")
    op.drop_table("marketing_iventas_template_uploads")
