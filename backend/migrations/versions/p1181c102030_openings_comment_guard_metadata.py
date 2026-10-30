"""Align openings.comment route metadata with its independent HTTP guard.

Revision ID: p1181c102030
Revises: n26c10202626
Create Date: 2026-10-30

Metadata only. No grants, roles, action enablement or product table changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "p1181c102030"
down_revision = "n26c10202626"
branch_labels = None
depends_on = None

METHOD = "POST"
ROUTE = "/api/openings/<int:opening_id>/tasks/<int:task_id>/comments"
ENDPOINT = "create_task_comment"
ACTION = "openings.comment"
OLD_GUARD = "_require_openings_read"
NEW_GUARD = "_require_openings_comment"
OLD_SCOPE = "openings_read_comment_policy"
NEW_SCOPE = "openings_comment_action_independent"
OLD_REVIEW = "needs_manual_decision"
NEW_REVIEW = "guard_separated_flag_off"


def _find_route(bind):
    rows = bind.execute(
        sa.text("""
            SELECT prm.id, prm.current_guard, prm.current_scope,
                   prm.review_status, pa.full_key AS action_full_key
            FROM permission_route_map prm
            LEFT JOIN permission_actions pa ON pa.id = prm.action_id
            WHERE prm.method = :method AND prm.route = :route
              AND prm.endpoint_function = :endpoint
              AND prm.is_active IS TRUE
        """),
        {"method": METHOD, "route": ROUTE, "endpoint": ENDPOINT},
    ).mappings().all()
    if len(rows) != 1:
        raise RuntimeError(
            f"Esperada una sola ruta activa para {METHOD} {ROUTE}: {len(rows)}"
        )
    row = rows[0]
    if row["action_full_key"] != ACTION:
        raise RuntimeError(
            f"No modificar mapeo inesperado: {row['action_full_key']}"
        )
    return row


def upgrade():
    bind = op.get_bind()
    row = _find_route(bind)
    if (row["current_guard"], row["current_scope"], row["review_status"]) != (
        OLD_GUARD, OLD_SCOPE, OLD_REVIEW,
    ):
        raise RuntimeError("El metadato de guard cambió: revisar antes de migrar")
    bind.execute(
        sa.text("""
            UPDATE permission_route_map
            SET current_guard = :guard,
                current_scope = :scope,
                review_status = :status,
                updated_at = now()
            WHERE id = :id AND current_guard = :expected
        """),
        {
            "id": row["id"], "guard": NEW_GUARD, "scope": NEW_SCOPE,
            "status": NEW_REVIEW, "expected": OLD_GUARD,
        },
    )


def downgrade():
    bind = op.get_bind()
    row = _find_route(bind)
    if (row["current_guard"], row["current_scope"], row["review_status"]) != (
        NEW_GUARD, NEW_SCOPE, NEW_REVIEW,
    ):
        raise RuntimeError("El metadato de guard cambió: no revertir a ciegas")
    bind.execute(
        sa.text("""
            UPDATE permission_route_map
            SET current_guard = :guard,
                current_scope = :scope,
                review_status = :status,
                updated_at = now()
            WHERE id = :id AND current_guard = :expected
        """),
        {
            "id": row["id"], "guard": OLD_GUARD, "scope": OLD_SCOPE,
            "status": OLD_REVIEW, "expected": NEW_GUARD,
        },
    )
