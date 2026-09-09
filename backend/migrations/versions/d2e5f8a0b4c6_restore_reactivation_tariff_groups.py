"""restore reactivation tariff groups after BCN rule correction

Revision ID: d2e5f8a0b4c6
Revises: c1d4e7f9a2b3
Create Date: 2026-09-09
"""

from alembic import op


revision: str = "d2e5f8a0b4c6"
down_revision: str = "c1d4e7f9a2b3"
branch_labels = None
depends_on = None


_CONSTRAINT = "ck_marketing_reactivation_tariffs_group"
_TABLE = "marketing_reactivation_tariffs"


def upgrade():
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


def downgrade():
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
