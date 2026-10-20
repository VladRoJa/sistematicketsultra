"""Scope regional de la cuenta MANTENIMIENTO (user 45).

Revision ID: b20c10202601
Revises: a19c10202601
Create Date: 2026-10-20

Auditoría producción: user 45, rol MANTENIMIENTO, department_id 1,
sucursal_id principal 100 y usuario_sucursal = {100}. Se conservan
la cuenta, departamento, sucursal principal y tickets históricos.
La migración solo sustituye asociaciones M:N de esa identidad.
"""
from alembic import op
import sqlalchemy as sa

revision = "b20c10202601"
down_revision = "a19c10202601"
branch_labels = None
depends_on = None

USER_ID = 45
USERNAME = "MANTENIMIENTO"
ROLE = "MANTENIMIENTO"
DEPARTMENT_ID = 1
PRIMARY_BRANCH_ID = 100
OLD_BRANCH_IDS = {100}
NEW_BRANCH_IDS = {1, 2, 3, 4, 5, 6, 14, 15, 16, 17, 18, 20, 24, 26}


def _account(connection):
    account = connection.execute(sa.text(
        "SELECT id, username, rol, department_id, sucursal_id "
        "FROM users WHERE id = :uid FOR UPDATE"
    ), {"uid": USER_ID}).mappings().first()
    if account is None:
        # Entorno limpio o dataset sintético sin la cuenta de producción.
        other = connection.execute(sa.text(
            "SELECT id FROM users WHERE lower(username) = lower(:name)"
        ), {"name": USERNAME}).scalar()
        if other is not None:
            raise RuntimeError("Identidad MANTENIMIENTO inesperada; abortar migración.")
        return None
    if (
        str(account["username"]).strip().upper() != USERNAME
        or str(account["rol"]).strip().upper() != ROLE
        or account["department_id"] != DEPARTMENT_ID
        or account["sucursal_id"] != PRIMARY_BRANCH_ID
    ):
        raise RuntimeError("Identidad o perfil de MANTENIMIENTO cambió; abortar.")
    return account


def _branches(connection):
    return set(connection.execute(sa.text(
        "SELECT sucursal_id FROM usuario_sucursal WHERE user_id = :uid"
    ), {"uid": USER_ID}).scalars().all())


def _ensure_catalog(connection):
    found = set(connection.execute(sa.text(
        "SELECT sucursal_id FROM sucursales WHERE sucursal_id IN :branch_ids"
    ).bindparams(sa.bindparam("branch_ids", expanding=True)), {
        "branch_ids": tuple(sorted(NEW_BRANCH_IDS)),
    }).scalars().all())
    if found != NEW_BRANCH_IDS:
        raise RuntimeError("Faltan sucursales del alcance de MANTENIMIENTO; abortar.")


def upgrade():
    connection = op.get_bind()
    if _account(connection) is None:
        return
    current = _branches(connection)
    if current == NEW_BRANCH_IDS:
        return
    if current != OLD_BRANCH_IDS:
        raise RuntimeError("usuario_sucursal del jefe cambió; revisar antes de migrar.")
    _ensure_catalog(connection)
    connection.execute(sa.text(
        "DELETE FROM usuario_sucursal WHERE user_id = :uid AND sucursal_id = 100"
    ), {"uid": USER_ID})
    for branch_id in sorted(NEW_BRANCH_IDS):
        connection.execute(sa.text(
            "INSERT INTO usuario_sucursal (user_id, sucursal_id) VALUES (:uid, :sid)"
        ), {"uid": USER_ID, "sid": branch_id})


def downgrade():
    connection = op.get_bind()
    if _account(connection) is None:
        return
    current = _branches(connection)
    if current == OLD_BRANCH_IDS:
        return
    if current != NEW_BRANCH_IDS:
        raise RuntimeError("Alcance regional modificado tras migración; rollback manual.")
    connection.execute(sa.text(
        "DELETE FROM usuario_sucursal WHERE user_id = :uid"
    ), {"uid": USER_ID})
    connection.execute(sa.text(
        "INSERT INTO usuario_sucursal (user_id, sucursal_id) VALUES (:uid, 100)"
    ), {"uid": USER_ID})
