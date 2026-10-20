"""Transición gobernada de la cuenta Yuliana a coordinación de Mantenimiento.

Revision ID: a19c10202601
Revises: c17a10202601
Create Date: 2026-10-19

No se reescriben tickets ni auditorías de nombres históricos.
Solo se migra la identidad de usuario 91 si coincide con la cuenta
COMPRAS_YULIANA, sus grants y sucursales previamente auditadas.
En DBs sin esa cuenta (CI/QA sintético), la migración es no-op.
"""

from alembic import op
import sqlalchemy as sa


revision = "a19c10202601"
down_revision = "c17a10202601"
branch_labels = None
depends_on = None

USER_ID = 91
OLD_USERNAME = "COMPRAS_YULIANA"
NEW_USERNAME = "MANT_YULIANA"
OLD_ROLE = "COMPRAS"
NEW_ROLE = "COORDINADOR_MANTENIMIENTO"
OLD_DEPARTMENT_ID = 6
NEW_DEPARTMENT_ID = 1
EXPECTED_BRANCHES = {7, 8, 9, 10, 11, 12, 13, 19, 21, 22, 23, 25}


def _account(connection, username):
    return connection.execute(
        sa.text(
            "SELECT id, username, rol, department_id "
            "FROM users WHERE lower(username) = lower(:username) FOR UPDATE"
        ),
        {"username": username},
    ).mappings().first()


def _ensure_single_identity(connection, *, source_name, target_name):
    source = _account(connection, source_name)
    target = _account(connection, target_name)

    if target is not None and (source is None or target["id"] != source["id"]):
        # Idempotencia de una cuenta ya migrada, sin aceptar otra identidad.
        if source is None and target["id"] == USER_ID:
            return None, target
        raise RuntimeError("El nombre de destino ya pertenece a otra cuenta.")

    if source is None:
        # Base QA vacía o datos sintéticos sin la identidad corporativa.
        return None, None

    if source["id"] != USER_ID:
        raise RuntimeError("La cuenta origen no corresponde al usuario 91.")

    return source, target


def _assert_grants_and_scope(connection):
    read_grant = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM usuarios_permisos "
            "WHERE user_id = :uid AND departamento_id = 1 AND es_admin = FALSE"
        ), {"uid": USER_ID},
    ).scalar_one()
    if not read_grant:
        raise RuntimeError("Falta el permiso individual de lectura Mantenimiento.")

    effects = connection.execute(
        sa.text(
            "SELECT g.effect FROM permission_grants g "
            "JOIN permission_actions a ON a.id = g.action_id "
            "WHERE g.principal_type = 'user' AND g.principal_user_id = :uid "
            "AND a.full_key = 'tickets.maintenance.coordinate' "
            "AND a.is_active = TRUE AND g.scope_type = 'global' "
            "AND g.is_active = TRUE AND g.deleted_at IS NULL "
            "AND (g.starts_at IS NULL OR g.starts_at <= now()) "
            "AND (g.expires_at IS NULL OR g.expires_at > now())"
        ), {"uid": USER_ID},
    ).scalars().all()
    if "allow" not in effects or "deny" in effects:
        raise RuntimeError("La cuenta no tiene coordinación individual vigente.")

    branches = set(connection.execute(
        sa.text("SELECT sucursal_id FROM usuario_sucursal WHERE user_id = :uid"),
        {"uid": USER_ID},
    ).scalars().all())
    if branches != EXPECTED_BRANCHES:
        raise RuntimeError(
            "El alcance regional cambió desde la auditoría previa: revisar antes."
        )


def upgrade():
    connection = op.get_bind()
    source, target = _ensure_single_identity(
        connection, source_name=OLD_USERNAME, target_name=NEW_USERNAME
    )

    if source is None:
        if target is not None and (
            target["rol"] != NEW_ROLE
            or target["department_id"] != NEW_DEPARTMENT_ID
        ):
            raise RuntimeError("Cuenta destino existente con perfil inesperado.")
        return

    if (
        source["rol"] != OLD_ROLE
        or source["department_id"] != OLD_DEPARTMENT_ID
    ):
        raise RuntimeError("El perfil origen cambió: abortar migración de Yuliana.")

    _assert_grants_and_scope(connection)
    connection.execute(
        sa.text(
            "UPDATE users SET username = :username, rol = :rol, "
            "department_id = :department_id WHERE id = :uid"
        ),
        {
            "username": NEW_USERNAME,
            "rol": NEW_ROLE,
            "department_id": NEW_DEPARTMENT_ID,
            "uid": USER_ID,
        },
    )


def downgrade():
    connection = op.get_bind()
    source, target = _ensure_single_identity(
        connection, source_name=NEW_USERNAME, target_name=OLD_USERNAME
    )
    if source is None:
        if target is not None and (
            target["rol"] != OLD_ROLE
            or target["department_id"] != OLD_DEPARTMENT_ID
        ):
            raise RuntimeError("Cuenta restaurada con perfil inesperado.")
        return

    if (
        source["rol"] != NEW_ROLE
        or source["department_id"] != NEW_DEPARTMENT_ID
    ):
        raise RuntimeError("El perfil cambió desde la transición; rollback manual.")

    connection.execute(
        sa.text(
            "UPDATE users SET username = :username, rol = :rol, "
            "department_id = :department_id WHERE id = :uid"
        ),
        {
            "username": OLD_USERNAME,
            "rol": OLD_ROLE,
            "department_id": OLD_DEPARTMENT_ID,
            "uid": USER_ID,
        },
    )
