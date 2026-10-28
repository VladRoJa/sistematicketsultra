"""Fixture CAP-V1 Tapizado para PostgreSQL LOCAL, nunca producción.

Depende del seed oficial de cierre local para catálogo, usuarios demo, permisos
trazables y sucursal. No altera el frontend, rutas ni control de permisos.

Uso desde backend/:
  APP_ENV=local SQLALCHEMY_DATABASE_URI=postgresql+psycopg2://...@127.0.0.1:5432/suite_ultra_tickets_qa \
  SUITE_QA_SEED_ALLOWED=YES_CREATE_LOCAL_SYNTHETIC_TICKETS \
  SUITE_QA_TEST_PASSWORD=... python -m scripts.seed_training_tapizado_qa

Exige la base local vacía ya migrada; una segunda ejecución solo verifica
integridad, nunca revierte o borra automáticamente trazabilidad existente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from os import environ

from scripts.seed_maintenance_closure_qa import (
    QA_BRANCH_ID,
    QA_BRANCH_NAME,
    QA_DB_NAME,
    QA_DEPARTMENT_ID,
    _preflight as validate_qa_database,
    seed as seed_maintenance_qa,
)

TRAINING_DESCRIPTION = "[CAP-V1] Tapizado multiaparato sintético"
TRAINING_CODES = ("CAPV1-TPZ-01", "CAPV1-TPZ-02", "CAPV1-TPZ-03")
ACTOR_USERNAME = "QA_COORD_CIERRE"
REVIEWER_USERNAME = "QA_GERENTE_CIERRE"


def seed() -> None:
    expected_uri = validate_qa_database()  # antes de importar app ni acceder a DB
    if environ.get("TICKETS_TAPIZADO_MULTI_ENABLED", "").lower() not in ("1", "true"):
        raise RuntimeError("CAP-V1 exige TICKETS_TAPIZADO_MULTI_ENABLED=true en QA local.")
    if environ.get("TICKETS_TAPIZADO_RECEPCION_ENABLED", "").lower() not in ("1", "true"):
        raise RuntimeError("CAP-V1 exige TICKETS_TAPIZADO_RECEPCION_ENABLED=true en QA local.")

    # Aprovecha el seed local existente: roles, privilegios auditables y sucursal.
    # Solo queda habilitado después de las comprobaciones estrictas de entorno.
    seed_maintenance_qa()

    from sqlalchemy.engine import make_url
    from app import create_app
    from app.extensions import db
    from app.models.inventario import InventarioGeneral, InventarioSucursal
    from app.models.ticket_model import Ticket
    from app.models.user_model import UserORM
    from app.services.ticket_tapizado_service import registrar_vinculos_tapizado

    app = create_app()
    if make_url(app.config["SQLALCHEMY_DATABASE_URI"]) != make_url(expected_uri):
        raise RuntimeError("Flask cambió de BD tras verificar el seed: operación cancelada.")

    with app.app_context():
        try:
            # Sin IDs fijos para inventarios o tickets; buscar por código sintético.
            ids = []
            for offset, code in enumerate(TRAINING_CODES, 1):
                matches = InventarioGeneral.query.filter_by(codigo_interno=code).all()
                if len(matches) > 1:
                    raise RuntimeError(f"Código QA duplicado: {code}")
                if matches:
                    item = matches[0]
                    if item.nombre != f"Banco de demostración {offset}":
                        raise RuntimeError(f"El código {code} no pertenece al dataset CAP-V1.")
                else:
                    item = InventarioGeneral(
                        tipo="Aparato",
                        nombre=f"Banco de demostración {offset}",
                        descripcion="Activo sintético exclusivo de QA local; sin valor comercial",
                        marca="ULTRA QA",
                        categoria="Aparatos",
                        codigo_interno=code,
                    )
                    db.session.add(item)
                    db.session.flush()
                allocation = InventarioSucursal.query.filter_by(
                    inventario_id=item.id, sucursal_id=QA_BRANCH_ID,
                ).one_or_none()
                if allocation is None:
                    db.session.add(InventarioSucursal(
                        inventario_id=item.id, sucursal_id=QA_BRANCH_ID, stock=1,
                    ))
                elif allocation.stock != 1:
                    raise RuntimeError(f"Stock QA inesperado para {code}")
                ids.append(item.id)

            creator = UserORM.get_by_username(REVIEWER_USERNAME)
            actor = UserORM.get_by_username(ACTOR_USERNAME)
            if not creator or not actor:
                raise RuntimeError("No se encontraron los dos usuarios autorizados de QA.")
            if creator.rol.upper() != "GERENTE" or creator.sucursal_id != QA_BRANCH_ID:
                raise RuntimeError("El revisor no corresponde al gerente de sucursal QA.")
            if actor.sucursal_id != QA_BRANCH_ID:
                raise RuntimeError("El operador no corresponde a la sucursal QA.")

            records = Ticket.query.filter_by(
                descripcion=TRAINING_DESCRIPTION,
                sucursal_id_destino=QA_BRANCH_ID,
                departamento_id=QA_DEPARTMENT_ID,
            ).all()
            if len(records) > 1:
                raise RuntimeError("Fixture CAP-V1 duplicado; no elegir arbitrariamente.")
            if records:
                ticket = records[0]
                existing_ids = [link.inventario_id for link in ticket.aparatos_asociados]
                if (ticket.tipo_trabajo != "TAPIZADO"
                    or ticket.username != creator.username
                    or ticket.tipo_atencion != "EXTERNA"
                    or ticket.estado != "en progreso"
                    or ticket.estado_cierre is not None
                    or set(existing_ids) != set(ids)
                    or any(link.recibido_en_utc is not None or link.recibido_por is not None
                           for link in ticket.aparatos_asociados)):
                    raise RuntimeError(
                        "El ticket CAP-V1 ya se utilizó o difiere de 0/N. "
                        "Restaura únicamente la BD sintética antes de regenerar video."
                    )
            else:
                now = datetime.now(timezone.utc)
                ticket = Ticket(
                    username=creator.username,
                    descripcion=TRAINING_DESCRIPTION,
                    sucursal_id=QA_BRANCH_ID,
                    sucursal_id_destino=QA_BRANCH_ID,
                    departamento_id=QA_DEPARTMENT_ID,
                    estado="en progreso",
                    tipo_trabajo="TAPIZADO",
                    tipo_atencion="EXTERNA",
                    asignado_a=None,
                    aparato_id=ids[0],
                    categoria="Aparatos",
                    problema_detectado="Tapicería por renovar (ejercicio CAP-V1)",
                    fecha_creacion=now,
                    fecha_en_progreso=now,
                    fecha_solucion=now + timedelta(days=7),
                    criticidad=2,
                    historial_fechas=[],
                    necesita_refaccion=False,
                    requiere_aprobacion=False,
                )
                db.session.add(ticket)
                db.session.flush()
                registrar_vinculos_tapizado(
                    ticket=ticket, aparatos_ids=ids, actor=creator.username,
                )

            db.session.commit()
            print("CAP_V1_QA_DATABASE =", QA_DB_NAME)
            print("CAP_V1_BRANCH =", QA_BRANCH_NAME)
            print("CAP_V1_TICKET_ID =", ticket.id)
            print("CAP_V1_CODES =", " ".join(TRAINING_CODES))
            print("CAP_V1_ACTOR_USER =", ACTOR_USERNAME)
            print("CAP_V1_REVIEWER_USER =", REVIEWER_USERNAME)
            print("CAP_V1_SEED = PASS (estado 0/N verificable)")
        except Exception:
            db.session.rollback()
            raise


if __name__ == "__main__":
    seed()
