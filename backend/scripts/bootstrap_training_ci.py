"""Bootstrapping CI sintético CAP-V1: solo PostgreSQL efímero de GitHub Actions.

Este esquema es una copia basada en ORM para una grabación integral de UI,
NO una prueba de Alembic en una base histórica y NO se usa en producción.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from scripts.seed_maintenance_closure_qa import _preflight, QA_DB_NAME


def main() -> None:
    url = _preflight()  # rechaza una base distinta antes de importar Flask
    parsed = make_url(url)
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("CAP_V1_SYNTHETIC_CI") != "YES_TEMPORARY_DB"
            or parsed.host != "127.0.0.1"
            or parsed.database != QA_DB_NAME
            or parsed.username != "cap_v1_ci"):
        raise RuntimeError("CAP-V1: únicamente PostgreSQL efímero del runner autorizado")

    from app import create_app
    from app.extensions import db
    from app.models.departamento_model import Departamento
    from app.models.permissions import PermissionActionORM, PermissionModuleORM
    from app.models.ticket_model import Ticket
    from scripts.seed_training_tapizado_qa import (
        TRAINING_CODES, TRAINING_DESCRIPTION, ACTOR_USERNAME, REVIEWER_USERNAME,
        seed as seed_tapizado,
    )

    app = create_app()
    if make_url(app.config["SQLALCHEMY_DATABASE_URI"]) != parsed:
        raise RuntimeError("CAP-V1: app configurada a otra base")
    with app.app_context():
        if inspect(db.engine).get_table_names():
            raise RuntimeError("CAP-V1: la base no está vacía; no se modifica")
        db.create_all()  # tabla sintética temporal; sin cambios ORM/migraciones
        db.session.add(Departamento(id=1, nombre="Mantenimiento"))
        module = PermissionModuleORM(key="tickets", name="Tickets sintéticos CAP-V1")
        db.session.add(module)
        db.session.flush()
        for key in ("maintenance.coordinate", "maintenance.read_assigned_only"):
            db.session.add(PermissionActionORM(
                module_id=module.id, key=key,
                full_key="tickets." + key, name=key,
                description="Datos sintéticos de grabación", risk_level="low",
                is_active=True,
            ))
        db.session.commit()

    seed_tapizado()  # valida roles, sucursal, catálogo, permisos y 0/N

    with app.app_context():
        ticket = Ticket.query.filter_by(descripcion=TRAINING_DESCRIPTION).one()
        if (ticket.sucursal_id_destino != 990101 or ticket.estado != "en progreso"
                or len(ticket.aparatos_asociados) != 3):
            raise RuntimeError("CAP-V1: fixture inesperado")
        data = {
            "ticket_id": ticket.id,
            "codes": list(TRAINING_CODES),
            "actor": ACTOR_USERNAME,
            "reviewer": REVIEWER_USERNAME,
            "branch_id": ticket.sucursal_id_destino,
            "mode": "EPHEMERAL_SYNTHETIC_UI",
        }
    out = Path("../artifacts/capacitacion/tapizado-full")
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("CAP-V1 CI BOOTSTRAP PASS: " + str(data["ticket_id"]))


if __name__ == "__main__":
    main()
