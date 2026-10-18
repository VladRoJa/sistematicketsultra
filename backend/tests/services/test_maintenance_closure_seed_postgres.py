"""E2E de persistencia del seed QA en PostgreSQL 16 desechable.

No apunta a producción. Usa un esquema nuevo solo dentro del contenedor de CI.
No sustituye la prueba de upgrade Alembic ni la revisión visual de Angular.
"""

import os

import pytest
from sqlalchemy.engine import make_url


def test_maintenance_closure_seed_persists_and_is_idempotent(monkeypatch):
    uri = os.getenv("PG_QA_SEED_TEST_URL")
    if not uri:
        pytest.skip("Requiere PostgreSQL efímero PG_QA_SEED_TEST_URL.")

    parsed = make_url(uri)
    assert parsed.drivername.startswith("postgresql")
    assert parsed.database == "suite_ultra_tickets_qa"
    assert parsed.host in {"localhost", "127.0.0.1"}

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", uri)
    monkeypatch.setenv(
        "SUITE_QA_SEED_ALLOWED", "YES_CREATE_LOCAL_SYNTHETIC_TICKETS"
    )
    monkeypatch.setenv("SUITE_QA_TEST_PASSWORD", "qa-synthetic-ci-password-2026")

    from app import create_app
    from app.extensions import db
    from app.models.departamento_model import Departamento
    from app.models.permissions import PermissionActionORM, PermissionModuleORM
    from app.models.ticket_model import Ticket
    from app.models.user_model import UserORM
    from scripts.seed_maintenance_closure_qa import QA_TICKETS, QA_USERS, seed

    app = create_app()
    with app.app_context():
        # Exclusivamente el esquema vacío del contenedor PostgreSQL de este job.
        db.create_all()
        db.session.add(Departamento(id=1, nombre="Mantenimiento"))
        module = PermissionModuleORM(
            key="tickets", name="Tickets QA", description="Synthetic CI only"
        )
        db.session.add(module)
        db.session.flush()
        for key, full_key in (
            ("maintenance.coordinate", "tickets.maintenance.coordinate"),
            ("maintenance.read_assigned_only", "tickets.maintenance.read_assigned_only"),
        ):
            db.session.add(PermissionActionORM(
                module_id=module.id,
                key=key,
                full_key=full_key,
                name=key,
                description="Synthetic CI only",
                risk_level="low",
                is_active=True,
            ))
        db.session.commit()

    def assert_persisted():
        with app.app_context():
            rows = Ticket.query.filter(
                Ticket.descripcion.in_(list(QA_TICKETS.values()))
            ).all()
            assert len(rows) == 2
            assert {row.tipo_atencion for row in rows} == {"INTERNA", "EXTERNA"}
            assert all(row.estado == "en progreso" for row in rows)
            internal = next(row for row in rows if row.tipo_atencion == "INTERNA")
            external = next(row for row in rows if row.tipo_atencion == "EXTERNA")
            assert internal.asignado_a == "QA_TEC_CIERRE"
            assert external.asignado_a is None
            users = UserORM.query.filter(UserORM.username.in_(list(QA_USERS))).all()
            assert len(users) == 5
            return sorted(row.id for row in rows)

    seed()
    first_ids = assert_persisted()
    seed()
    assert assert_persisted() == first_ids
