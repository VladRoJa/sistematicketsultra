"""Versioned payment reference for expired members (no PII seeding in migration).

Revision ID: ccpay11232601
Revises: i21c11202601
"""
from alembic import op
import sqlalchemy as sa

revision = "ccpay11232601"
down_revision = "i21c11202601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_center_payment_reference_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("cutoff_date", sa.Date(), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_sha256", name="uq_cc_payment_reference_source_sha256"),
    )
    op.create_index(
        "uq_cc_payment_reference_single_active",
        "contact_center_payment_reference_batches", ["is_active"],
        unique=True, postgresql_where=sa.text("is_active = true"),
    )
    op.create_table(
        "contact_center_payment_reference_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("member_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(255), nullable=False),
        sa.Column("pin", sa.String(64), nullable=False),
        sa.Column("pin_key", sa.String(64), nullable=False),
        sa.Column("branch", sa.String(255), nullable=False),
        sa.Column("status_at_cutoff", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["contact_center_payment_reference_batches.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("batch_id", "member_id", name="uq_cc_payment_reference_member"),
        sa.UniqueConstraint(
            "batch_id", "name_key", "pin_key", name="uq_cc_payment_reference_identity"
        ),
    )
    op.create_index(
        "ix_cc_payment_reference_batch_pin",
        "contact_center_payment_reference_rows", ["batch_id", "pin_key"],
    )
    op.create_index(
        "ix_cc_payment_reference_batch_name",
        "contact_center_payment_reference_rows", ["batch_id", "name_key"],
    )


def downgrade():
    bind = op.get_bind()
    total = bind.execute(
        sa.text("SELECT COUNT(*) FROM contact_center_payment_reference_batches")
    ).scalar_one()
    if total:
        raise RuntimeError(
            "Hay padrones importados; reversión destructiva bloqueada. "
            "Resguardar datos y solicitar procedimiento explícito."
        )
    op.drop_index(
        "ix_cc_payment_reference_batch_name",
        table_name="contact_center_payment_reference_rows",
    )
    op.drop_index(
        "ix_cc_payment_reference_batch_pin",
        table_name="contact_center_payment_reference_rows",
    )
    op.drop_table("contact_center_payment_reference_rows")
    op.drop_index(
        "uq_cc_payment_reference_single_active",
        table_name="contact_center_payment_reference_batches",
    )
    op.drop_table("contact_center_payment_reference_batches")
