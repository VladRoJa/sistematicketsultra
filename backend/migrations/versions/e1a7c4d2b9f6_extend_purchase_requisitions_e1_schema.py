"""extend purchase requisitions e1 schema

Revision ID: e1a7c4d2b9f6
Revises: c6f4b9a2d7e1
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = "e1a7c4d2b9f6"
down_revision = "c6f4b9a2d7e1"
branch_labels = None
depends_on = None


_E1_STATUSES = (
    "PENDING_REVIEW",
    "NEEDS_INFO",
    "REJECTED",
    "IN_QUOTATION",
    "QUOTE_PENDING_FINANCE_APPROVAL",
    "PAYMENT_REQUESTED",
    "SHIPPING_IN_PROGRESS",
    "IMPORT_IN_PROGRESS",
    "FINAL_DESTINATION_SHIPMENT",
    "RECEIPT_ISSUE",
    "CLOSED",
)

_M1_STATUSES = (
    "PENDING_REVIEW",
    "NEEDS_INFO",
    "REJECTED",
    "IN_QUOTATION",
    "CLOSED",
)

_E1_EVENT_TYPES = (
    "CREATED",
    "INFO_REQUESTED",
    "RESUBMITTED",
    "APPROVED",
    "REJECTED",
    "ROUTED_TO_MAINTENANCE",
    "ATTACHMENT_ADDED",
    "QUOTE_ADDED",
    "QUOTE_SELECTED",
    "QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL",
    "QUOTE_APPROVED_BY_FINANCE",
    "QUOTE_REJECTED_BY_FINANCE",
    "PAYMENT_REQUESTED",
    "SHIPPING_STARTED",
    "IMPORT_STARTED",
    "IMPORT_NOT_APPLICABLE",
    "FINAL_DESTINATION_SHIPMENT_STARTED",
    "RECEIVED",
    "RECEIPT_ISSUE_REPORTED",
    "RECEIPT_ISSUE_RESOLUTION_STARTED",
    "ADMINISTRATIVE_CORRECTION",
)

_M1_EVENT_TYPES = (
    "CREATED",
    "INFO_REQUESTED",
    "RESUBMITTED",
    "APPROVED",
    "REJECTED",
    "ROUTED_TO_MAINTENANCE",
    "ATTACHMENT_ADDED",
)

_E1_ATTACHMENT_TYPES = (
    "EVIDENCE",
    "QUOTE",
    "OTHER",
    "RECEIPT_EVIDENCE",
    "RECEIPT_ISSUE_EVIDENCE",
)

_M1_ATTACHMENT_TYPES = (
    "EVIDENCE",
    "QUOTE",
    "OTHER",
)

_FINANCE_STATUSES = (
    "DRAFT",
    "PENDING",
    "APPROVED",
    "REJECTED",
)


def _sql_values(values):
    return ", ".join(f"'{value}'" for value in values)


def upgrade():
    op.drop_constraint(
        "ck_purchase_requisitions_status",
        "purchase_requisitions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_purchase_requisitions_status",
        "purchase_requisitions",
        f"status IN ({_sql_values(_E1_STATUSES)})",
    )

    op.drop_constraint(
        "ck_purchase_requisition_events_type",
        "purchase_requisition_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_purchase_requisition_events_from_status",
        "purchase_requisition_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_purchase_requisition_events_to_status",
        "purchase_requisition_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_purchase_requisition_events_type",
        "purchase_requisition_events",
        f"event_type IN ({_sql_values(_E1_EVENT_TYPES)})",
    )
    op.create_check_constraint(
        "ck_purchase_requisition_events_from_status",
        "purchase_requisition_events",
        (
            "from_status IS NULL OR "
            f"from_status IN ({_sql_values(_E1_STATUSES)})"
        ),
    )
    op.create_check_constraint(
        "ck_purchase_requisition_events_to_status",
        "purchase_requisition_events",
        (
            "to_status IS NULL OR "
            f"to_status IN ({_sql_values(_E1_STATUSES)})"
        ),
    )

    op.drop_constraint(
        "ck_purchase_requisition_attachments_type",
        "purchase_requisition_attachments",
        type_="check",
    )
    op.alter_column(
        "purchase_requisition_attachments",
        "attachment_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_purchase_requisition_attachments_type",
        "purchase_requisition_attachments",
        f"attachment_type IN ({_sql_values(_E1_ATTACHMENT_TYPES)})",
    )

    op.create_table(
        "purchase_requisition_quotes",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "requisition_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "supplier_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=8),
            nullable=False,
        ),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column(
            "attachment_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
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
        sa.Column(
            "is_selected",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "selected_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "selected_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finance_status",
            sa.String(length=20),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column(
            "finance_submitted_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "finance_submitted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finance_decided_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "finance_decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finance_comment",
            sa.Text(),
            nullable=True,
        ),
        sa.CheckConstraint(
            "length(trim(supplier_name)) > 0",
            name="ck_purchase_requisition_quotes_supplier_nonempty",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_purchase_requisition_quotes_amount_positive",
        ),
        sa.CheckConstraint(
            "length(trim(currency)) > 0",
            name="ck_purchase_requisition_quotes_currency_nonempty",
        ),
        sa.CheckConstraint(
            f"finance_status IN ({_sql_values(_FINANCE_STATUSES)})",
            name="ck_purchase_requisition_quotes_finance_status",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["purchase_requisition_attachments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["finance_decided_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["finance_submitted_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["purchase_requisitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["selected_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attachment_id",
            name="uq_purchase_requisition_quotes_attachment",
        ),
    )
    op.create_index(
        "ix_purchase_requisition_quotes_requisition_created",
        "purchase_requisition_quotes",
        ["requisition_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_requisition_quotes_requisition_finance",
        "purchase_requisition_quotes",
        ["requisition_id", "finance_status"],
        unique=False,
    )
    op.create_index(
        "uq_purchase_requisition_quotes_one_selected",
        "purchase_requisition_quotes",
        ["requisition_id"],
        unique=True,
        postgresql_where=sa.text("is_selected = true"),
        sqlite_where=sa.text("is_selected = 1"),
    )

    op.create_table(
        "purchase_requisition_finance_approvers",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "added_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            name="uq_purchase_requisition_finance_approvers_user",
        ),
    )
    op.create_index(
        "ix_purchase_requisition_finance_approvers_active",
        "purchase_requisition_finance_approvers",
        ["is_active"],
        unique=False,
    )


def _ensure_downgrade_safe():
    bind = op.get_bind()

    checks = (
        (
            "purchase_requisition_quotes",
            "SELECT COUNT(*) FROM purchase_requisition_quotes",
        ),
        (
            "purchase_requisition_finance_approvers",
            "SELECT COUNT(*) FROM purchase_requisition_finance_approvers",
        ),
        (
            "purchase_requisitions E1 statuses",
            (
                "SELECT COUNT(*) FROM purchase_requisitions "
                f"WHERE status NOT IN ({_sql_values(_M1_STATUSES)})"
            ),
        ),
        (
            "purchase_requisition_events E1 types/statuses",
            (
                "SELECT COUNT(*) FROM purchase_requisition_events "
                f"WHERE event_type NOT IN ({_sql_values(_M1_EVENT_TYPES)}) "
                "OR (from_status IS NOT NULL AND "
                f"from_status NOT IN ({_sql_values(_M1_STATUSES)})) "
                "OR (to_status IS NOT NULL AND "
                f"to_status NOT IN ({_sql_values(_M1_STATUSES)}))"
            ),
        ),
        (
            "purchase_requisition_attachments E1 types",
            (
                "SELECT COUNT(*) FROM purchase_requisition_attachments "
                f"WHERE attachment_type NOT IN "
                f"({_sql_values(_M1_ATTACHMENT_TYPES)})"
            ),
        ),
    )

    populated = []
    for label, sql in checks:
        count = int(bind.execute(sa.text(sql)).scalar_one())
        if count:
            populated.append(f"{label}: {count}")

    if populated:
        raise RuntimeError(
            "Downgrade e1a7c4d2b9f6 blocked to preserve E1 audit data: "
            + "; ".join(populated)
        )


def downgrade():
    _ensure_downgrade_safe()

    op.drop_index(
        "ix_purchase_requisition_finance_approvers_active",
        table_name="purchase_requisition_finance_approvers",
    )
    op.drop_table("purchase_requisition_finance_approvers")

    op.drop_index(
        "uq_purchase_requisition_quotes_one_selected",
        table_name="purchase_requisition_quotes",
    )
    op.drop_index(
        "ix_purchase_requisition_quotes_requisition_finance",
        table_name="purchase_requisition_quotes",
    )
    op.drop_index(
        "ix_purchase_requisition_quotes_requisition_created",
        table_name="purchase_requisition_quotes",
    )
    op.drop_table("purchase_requisition_quotes")

    op.drop_constraint(
        "ck_purchase_requisition_attachments_type",
        "purchase_requisition_attachments",
        type_="check",
    )
    op.alter_column(
        "purchase_requisition_attachments",
        "attachment_type",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_purchase_requisition_attachments_type",
        "purchase_requisition_attachments",
        f"attachment_type IN ({_sql_values(_M1_ATTACHMENT_TYPES)})",
    )

    op.drop_constraint(
        "ck_purchase_requisition_events_to_status",
        "purchase_requisition_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_purchase_requisition_events_from_status",
        "purchase_requisition_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_purchase_requisition_events_type",
        "purchase_requisition_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_purchase_requisition_events_type",
        "purchase_requisition_events",
        f"event_type IN ({_sql_values(_M1_EVENT_TYPES)})",
    )
    op.create_check_constraint(
        "ck_purchase_requisition_events_from_status",
        "purchase_requisition_events",
        (
            "from_status IS NULL OR "
            f"from_status IN ({_sql_values(_M1_STATUSES)})"
        ),
    )
    op.create_check_constraint(
        "ck_purchase_requisition_events_to_status",
        "purchase_requisition_events",
        (
            "to_status IS NULL OR "
            f"to_status IN ({_sql_values(_M1_STATUSES)})"
        ),
    )

    op.drop_constraint(
        "ck_purchase_requisitions_status",
        "purchase_requisitions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_purchase_requisitions_status",
        "purchase_requisitions",
        f"status IN ({_sql_values(_M1_STATUSES)})",
    )
