"""Inventarios V2 E3: QA DDL puro en PostgreSQL 16; no endpoint ni cambios V1."""
import importlib.util
import os
import secrets
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.inventario_correccion_decision import (
    InventarioCorreccionDecisionORM, InventarioCorreccionAjusteORM,
    InventarioCorreccionMaestroAuditORM, InventarioCorreccionAltaAuditORM,
)

BASE = Path(__file__).resolve().parents[2]
MIGRATION = BASE / "migrations/versions/v2e3p2102626_inventario_decision_audit.py"
spec = importlib.util.spec_from_file_location("inventario_e3_revision", MIGRATION)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_e3_extiende_cadena_unica_y_no_crea_rutas():
    assert module.revision == "v2e3p2102626"
    assert module.down_revision == "m23c10202623"
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(BASE / "migrations"))
    graph = ScriptDirectory.from_config(cfg)
    assert graph.get_heads() == ["v2e3p2102626"]
    assert len(list(graph.walk_revisions())) > 1


def test_e3_orm_mapea_journal_y_prohibe_desajuste_de_pares():
    classes = (
        InventarioCorreccionDecisionORM, InventarioCorreccionAjusteORM,
        InventarioCorreccionMaestroAuditORM, InventarioCorreccionAltaAuditORM,
    )
    names = (
        "inventario_correccion_decisiones", "inventario_correccion_ajustes",
        "inventario_correccion_maestro_auditoria", "inventario_correccion_altas_auditoria",
    )
    assert tuple(item.__table__.name for item in classes) == names
    assert isinstance(InventarioCorreccionDecisionORM.__table__.c.idempotency_key.type, UUID)
    assert isinstance(InventarioCorreccionMaestroAuditORM.__table__.c.valor_anterior.type, JSONB)
    for klass in classes:
        assert klass.__table__.c.get("actor_usuario_id") is not None
        assert all(
            fk.ondelete == "RESTRICT"
            for fk in klass.__table__.foreign_key_constraints
        )
    for klass in classes[1:]:
        assert any(
            fk.name.endswith("_decision_solicitud")
            and len(fk.elements) == 2
            for fk in klass.__table__.foreign_key_constraints
        )


def test_e3_migration_crea_solo_cuatro_tablas_nuevas(monkeypatch):
    names = []
    indexes = []

    class Recorder:
        def create_table(self, name, *args):
            names.append(name)
        def create_index(self, name, table, columns):
            indexes.append((name, table))

    monkeypatch.setattr(module, "op", Recorder())
    module.upgrade()
    assert names == [
        "inventario_correccion_decisiones",
        "inventario_correccion_ajustes",
        "inventario_correccion_maestro_auditoria",
        "inventario_correccion_altas_auditoria",
    ]
    assert len(indexes) == 4


def test_e3_postgres_fk_decision_ajustes_idempotencia_y_downgrade(monkeypatch):
    url = os.environ.get("INVENTARIO_E2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requiere PostgreSQL efimero para QA E3")

    schema = "inv_v2_e3_" + secrets.token_hex(5)
    engine = sa.create_engine(url, future=True)
    try:
        with engine.begin() as con:
            con.exec_driver_sql(f"CREATE SCHEMA {schema}")
            con.exec_driver_sql(f"SET search_path TO {schema}")
            con.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            con.exec_driver_sql("CREATE TABLE sucursales (sucursal_id INTEGER PRIMARY KEY)")
            con.exec_driver_sql("CREATE TABLE inventario_general (id INTEGER PRIMARY KEY)")
            con.exec_driver_sql(
                "CREATE TABLE inventario_sucursal ("
                "id INTEGER PRIMARY KEY, "
                "inventario_id INTEGER NOT NULL REFERENCES inventario_general(id), "
                "sucursal_id INTEGER NOT NULL REFERENCES sucursales(sucursal_id), "
                "stock INTEGER NOT NULL,"
                "CONSTRAINT uq_inventario_sucursal_activo UNIQUE (inventario_id,sucursal_id))"
            )
            con.exec_driver_sql(
                "CREATE TABLE inventario_correccion_solicitudes (id BIGINT PRIMARY KEY)"
            )
            monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(con)))
            module.upgrade()
            inspector = sa.inspect(con)
            for name in (
                "inventario_correccion_decisiones", "inventario_correccion_ajustes",
                "inventario_correccion_maestro_auditoria",
                "inventario_correccion_altas_auditoria",
            ):
                assert inspector.has_table(name)

            con.exec_driver_sql("INSERT INTO users VALUES (7), (8)")
            con.exec_driver_sql("INSERT INTO sucursales VALUES (1), (2)")
            con.exec_driver_sql("INSERT INTO inventario_general VALUES (501)")
            con.exec_driver_sql(
                "INSERT INTO inventario_sucursal VALUES (10, 501, 1, 3)"
            )
            con.exec_driver_sql(
                "INSERT INTO inventario_correccion_solicitudes VALUES (1001), (1002)"
            )
            insert_decision = sa.text(
                "INSERT INTO inventario_correccion_decisiones "
                "(solicitud_id,decision,actor_usuario_id,motivo_decision,"
                "idempotency_key,request_fingerprint) VALUES "
                "(:solicitud,:decision,7,'Validacion formal con evidencia',"
                "CAST(:key AS uuid),:fingerprint) RETURNING id"
            )
            decision_id = con.execute(insert_decision, {
                "solicitud": 1001, "decision": "APPROVED",
                "key": "11111111-1111-4111-8111-111111111111", "fingerprint": "a" * 64,
            }).scalar_one()

            insert_adjustment = sa.text(
                "INSERT INTO inventario_correccion_ajustes "
                "(decision_id,solicitud_id,inventario_id,sucursal_id,"
                "stock_anterior,stock_nuevo,delta_firmada,"
                "actor_usuario_id,motivo) VALUES "
                "(:decision,:solicitud,501,1,3,2,:delta,7,'Ajuste documentado')"
            )
            con.execute(insert_adjustment, {
                "decision": decision_id, "solicitud": 1001, "delta": -1,
            })
            # Es solo un registro forense: E3 no muta stock mientras no exista servicio.
            assert con.exec_driver_sql(
                "SELECT stock FROM inventario_sucursal WHERE inventario_id=501"
            ).scalar_one() == 3
            assert con.exec_driver_sql(
                "SELECT delta_firmada FROM inventario_correccion_ajustes"
            ).scalar_one() == -1

            for wrong in [
                {"decision": decision_id, "solicitud": 1002, "delta": -1},  # FK compuesta
                {"decision": decision_id, "solicitud": 1001, "delta": -2},  # UNIQUE o delta
            ]:
                with pytest.raises(sa.exc.IntegrityError):
                    with con.begin_nested():
                        con.execute(insert_adjustment, wrong)

            with pytest.raises(sa.exc.IntegrityError):
                with con.begin_nested():
                    con.execute(insert_decision, {
                        "solicitud": 1002, "decision": "REJECTED",
                        "key": "11111111-1111-4111-8111-111111111111",
                        "fingerprint": "b" * 64,  # misma llave actor
                    })

            with pytest.raises(RuntimeError, match="existen decisiones"):
                module.downgrade()
            con.exec_driver_sql("DELETE FROM inventario_correccion_ajustes")
            con.exec_driver_sql("DELETE FROM inventario_correccion_decisiones")
            module.downgrade()
            assert not sa.inspect(con).has_table("inventario_correccion_decisiones")
            assert con.exec_driver_sql(
                "SELECT stock FROM inventario_sucursal WHERE inventario_id=501"
            ).scalar_one() == 3
    finally:
        with engine.begin() as con:
            con.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        engine.dispose()
