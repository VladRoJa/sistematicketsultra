"""Seed idempotente de QA para el cierre Tickets V1 Mantenimiento.

SEGURIDAD: únicamente base local PostgreSQL 'suite_ultra_tickets_qa'.
No utiliza datos de producción, ni usuarios/sucursales reales, ni IDs fijos de tickets.

Antes de ejecutar, crear una base separada y aplicar migraciones Alembic.
Ejemplo (PowerShell, usando la configuración local habitual):
  $env:APP_ENV = "local"
  $env:SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://...@127.0.0.1:5432/suite_ultra_tickets_qa"
  $env:SUITE_QA_SEED_ALLOWED = "YES_CREATE_LOCAL_SYNTHETIC_TICKETS"
  $env:SUITE_QA_TEST_PASSWORD = "<contraseña local NO productiva>"
  python -m scripts.seed_maintenance_closure_qa
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.engine import make_url


QA_DB_NAME = "suite_ultra_tickets_qa"
QA_BRANCH_ID = 990101
QA_BRANCH_NAME = "QA CIERRE MANTENIMIENTO"
QA_DEPARTMENT_ID = 1
QA_USERS = {
    "QA_ADMIN_CIERRE": ("ADMINISTRADOR", 1),
    "QA_COORD_CIERRE": ("COMPRAS", 6),
    "QA_TEC_CIERRE": ("SR_MANTENIMIENTO", 1),
    "QA_GERENTE_CIERRE": ("GERENTE", 2),
    "QA_SOLICITANTE_CIERRE": ("RECEPCIONISTA", 3),
}
QA_TICKETS = {
    "INTERNA": "[QA CIERRE V1] Reparación interna sintética",
    "EXTERNA": "[QA CIERRE V1] Servicio externo sintético",
}


def _preflight() -> str:
    """Falla cerrado ANTES de importar la aplicación/abrir la conexión."""

    if os.getenv("SUITE_QA_SEED_ALLOWED") != "YES_CREATE_LOCAL_SYNTHETIC_TICKETS":
        raise RuntimeError("Falta autorización explícita del seed local de QA.")
    if os.getenv("APP_ENV") != "local":
        raise RuntimeError("APP_ENV debe ser exactamente 'local'.")
    password = os.getenv("SUITE_QA_TEST_PASSWORD", "")
    if len(password) < 12:
        raise RuntimeError("SUITE_QA_TEST_PASSWORD debe tener al menos 12 caracteres.")

    uri = os.getenv("SQLALCHEMY_DATABASE_URI", "")
    if not uri:
        raise RuntimeError("Define explícitamente SQLALCHEMY_DATABASE_URI.")
    url = make_url(uri)
    if (
        not url.drivername.startswith("postgresql")
        or url.database != QA_DB_NAME
        or url.host not in {"localhost", "127.0.0.1", "db"}
    ):
        raise RuntimeError(
            "Seed prohibido: exige PostgreSQL local y base 'suite_ultra_tickets_qa'."
        )
    return uri


def seed() -> None:
    expected_uri = _preflight()

    from werkzeug.security import generate_password_hash

    from app import create_app
    from app.extensions import db
    from app.models.departamento_model import Departamento
    from app.models.permiso_model import Permiso
    from app.models.permissions import (
        PermissionActionORM,
        PermissionGrantAuditLogORM,
        PermissionGrantORM,
    )
    from app.models.sucursal_model import Sucursal
    from app.models.ticket_model import Ticket
    from app.models.user_model import UserORM, usuario_sucursal

    app = create_app()
    if make_url(app.config["SQLALCHEMY_DATABASE_URI"]) != make_url(expected_uri):
        raise RuntimeError("La configuración Flask apunta a una base distinta.")

    with app.app_context():
        try:
            department = db.session.get(Departamento, QA_DEPARTMENT_ID)
            if department is None or department.nombre.strip().casefold() != "mantenimiento":
                raise RuntimeError(
                    "Debes cargar previamente el catálogo oficial del departamento Mantenimiento (id 1)."
                )

            branch = db.session.get(Sucursal, QA_BRANCH_ID)
            if branch is None:
                branch = Sucursal(
                    sucursal_id=QA_BRANCH_ID,
                    serie="QA-CLOSE",
                    sucursal=QA_BRANCH_NAME,
                    estado="ACTIVA",
                    operational_status="ACTIVA",
                    is_demo=True,
                    municipio="QA",
                    direccion="SUCURSAL SINTÉTICA - SIN DIRECCIÓN REAL",
                )
                db.session.add(branch)
                db.session.flush()
            elif not branch.is_demo or branch.sucursal != QA_BRANCH_NAME:
                raise RuntimeError("El ID reservado de la sucursal QA está ocupado.")

            qa_users = {}
            for username, (role, department_id) in QA_USERS.items():
                user = UserORM.get_by_username(username)
                if user is None:
                    user = UserORM(
                        username=username,
                        rol=role,
                        department_id=department_id,
                        sucursal_id=QA_BRANCH_ID,
                        password=generate_password_hash(
                            os.environ["SUITE_QA_TEST_PASSWORD"]
                        ),
                    )
                    db.session.add(user)
                    db.session.flush()
                elif (
                    user.rol != role
                    or user.department_id != department_id
                    or user.sucursal_id != QA_BRANCH_ID
                ):
                    raise RuntimeError(f"Identidad QA existente incompatible: {username}")
                qa_users[username] = user

                existing_scope = db.session.execute(
                    db.select(usuario_sucursal.c.user_id).where(
                        usuario_sucursal.c.user_id == user.id,
                        usuario_sucursal.c.sucursal_id == QA_BRANCH_ID,
                    )
                ).first()
                if existing_scope is None:
                    db.session.execute(
                        usuario_sucursal.insert().values(
                            user_id=user.id, sucursal_id=QA_BRANCH_ID,
                        )
                    )

            coordinator = qa_users["QA_COORD_CIERRE"]
            technician = qa_users["QA_TEC_CIERRE"]
            admin = qa_users["QA_ADMIN_CIERRE"]
            if Permiso.query.filter_by(
                user_id=coordinator.id,
                departamento_id=QA_DEPARTMENT_ID,
                es_admin=False,
            ).first() is None:
                db.session.add(Permiso(
                    user_id=coordinator.id,
                    departamento_id=QA_DEPARTMENT_ID,
                    es_admin=False,
                ))

            for username, action_key in (
                ("QA_COORD_CIERRE", "tickets.maintenance.coordinate"),
                ("QA_TEC_CIERRE", "tickets.maintenance.read_assigned_only"),
            ):
                actor = qa_users[username]
                action = PermissionActionORM.query.filter_by(
                    full_key=action_key, is_active=True,
                ).one_or_none()
                if action is None:
                    raise RuntimeError(
                        f"Falta acción {action_key}; aplica las migraciones Alembic de QA."
                    )

                active = PermissionGrantORM.query.filter(
                    PermissionGrantORM.principal_type == "user",
                    PermissionGrantORM.principal_user_id == actor.id,
                    PermissionGrantORM.action_id == action.id,
                    PermissionGrantORM.is_active.is_(True),
                    PermissionGrantORM.deleted_at.is_(None),
                ).all()
                if any(grant.effect == "deny" for grant in active):
                    raise RuntimeError(f"Permiso QA denegado explícitamente: {action_key}")
                if active:
                    continue

                reason = "Datos sintéticos exclusivos de QA local Tickets V1"
                grant = PermissionGrantORM(
                    principal_type="user",
                    principal_user_id=actor.id,
                    module_id=action.module_id,
                    action_id=action.id,
                    effect="allow",
                    scope_type="global",
                    reason=reason,
                    is_active=True,
                    created_by_user_id=admin.id,
                    updated_by_user_id=admin.id,
                )
                db.session.add(grant)
                db.session.flush()
                db.session.add(PermissionGrantAuditLogORM(
                    grant_id=grant.id,
                    event_type="created",
                    before_payload=None,
                    after_payload={
                        "principal_user_id": actor.id,
                        "action_key": action_key,
                        "effect": "allow",
                        "scope_type": "global",
                        "qa_seed": True,
                    },
                    changed_by_user_id=admin.id,
                    reason=reason,
                    user_agent="qa_local_seed",
                ))

            now = datetime.now(timezone.utc)
            created_ids = {}
            for mode, description in QA_TICKETS.items():
                record = Ticket.query.filter_by(
                    username=qa_users["QA_SOLICITANTE_CIERRE"].username,
                    descripcion=description,
                    sucursal_id_destino=QA_BRANCH_ID,
                    departamento_id=QA_DEPARTMENT_ID,
                ).one_or_none()
                if record is None:
                    record = Ticket(
                        username=qa_users["QA_SOLICITANTE_CIERRE"].username,
                        descripcion=description,
                        sucursal_id=QA_BRANCH_ID,
                        sucursal_id_destino=QA_BRANCH_ID,
                        departamento_id=QA_DEPARTMENT_ID,
                        estado="en progreso",
                        tipo_atencion=mode,
                        asignado_a=technician.username if mode == "INTERNA" else None,
                        fecha_creacion=now,
                        fecha_en_progreso=now,
                        fecha_solucion=now + timedelta(days=7),
                        criticidad=2,
                        historial_fechas=[],
                        necesita_refaccion=False,
                        requiere_aprobacion=False,
                    )
                    db.session.add(record)
                    db.session.flush()
                created_ids[mode] = record.id

            db.session.commit()
            print("QA_DATABASE =", QA_DB_NAME)
            print("QA_BRANCH_ID =", QA_BRANCH_ID)
            print("QA_INTERNAL_TICKET_ID =", created_ids["INTERNA"])
            print("QA_EXTERNAL_TICKET_ID =", created_ids["EXTERNA"])
            print("QA_USERS =", ", ".join(QA_USERS))
            print("SEED_RESULT = PASS (idempotent)")
        except Exception:
            db.session.rollback()
            raise


if __name__ == "__main__":
    seed()
