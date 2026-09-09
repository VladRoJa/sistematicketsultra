"""allow borron cuenta nueva reactivation group

Revision ID: c1d4e7f9a2b3
Revises: b9e2f7a4d3c5
Create Date: 2026-09-09
"""

from alembic import op


revision: str = "c1d4e7f9a2b3"
down_revision: str = "b9e2f7a4d3c5"
branch_labels = None
depends_on = None


_CONSTRAINT = "ck_marketing_reactivation_tariffs_group"
_TABLE = "marketing_reactivation_tariffs"


def upgrade():
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "reactivation_group IN ("
        "'REACTIVATE', "
        "'DOMICILIATED_FLOW', "
        "'BORRON_CUENTA_NUEVA', "
        "'EXCLUDE', "
        "'REVIEW'"
        ")",
    )


def downgrade():
    # BCN is a specialized recovery path for former domiciliated members.
    # Map it back before restoring the previous constraint.
    op.execute(
        "UPDATE marketing_reactivation_tariffs "
        "SET reactivation_group = 'DOMICILIATED_FLOW' "
        "WHERE reactivation_group = 'BORRON_CUENTA_NUEVA'"
    )
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "reactivation_group IN ("
        "'REACTIVATE', "
        "'DOMICILIATED_FLOW', "
        "'EXCLUDE', "
        "'REVIEW'"
        ")",
    )
