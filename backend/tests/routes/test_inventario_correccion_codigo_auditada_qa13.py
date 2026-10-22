"""QA-13: corrección de códigos mantiene audit trail y es atómica."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import column

from app.routes import inventarios as routes


def _cliente():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa13-test")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)
    with app.app_context():
        token = create_access_token(identity="91")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _datos(nuevo="01PIELF08", anterior="01PIELF07", motivo="Corrección por etiqueta física"):
    return {"codigo_anterior": anterior, "codigo_nuevo": nuevo, "motivo": motivo}


class AuditFake:
    ocurrido_en_utc = Mock()
    ocurrencias = []

    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.id = 1
        AuditFake.ocurrencias.append(self)


def _fixture():
    row = SimpleNamespace(
        id=427, codigo_interno="01PIELF07", nombre="Escalera",
        marca="Matrix", stock=1,
    )
    query = Mock()
    query.filter_by.return_value.with_for_update.return_value.first.return_value = row
    query.filter.return_value.first.return_value = None
    model = SimpleNamespace(
        query=query, codigo_interno=column("codigo_interno"), id=column("id"),
    )
    session = Mock()
    audit_query = Mock()
    audit_query.filter_by.return_value.order_by.return_value.all.return_value = []
    AuditFake.ocurrencias = []
    return row, query, model, session, audit_query


def _corregir(body, *, mutate=None, forbidden=None, commit_failure=None):
    client, headers = _cliente()
    row, query, model, session, audit_query = _fixture()
    if mutate:
        mutate(row, query)
    if commit_failure is not None:
        session.commit.side_effect = commit_failure
    with patch.object(routes, "_require_inventory_global_write", return_value=forbidden), \
         patch.object(routes, "_get_current_user_id_required", return_value=(91, None)), \
         patch.object(routes, "_bloquear_escritura_codigos") as lock, \
         patch.object(routes, "InventarioGeneral", model), \
         patch.object(routes, "InventarioCodigoCorreccionORM", AuditFake), \
         patch.object(routes, "db", SimpleNamespace(session=session)):
        res = client.post(
            "/api/inventario/427/corregir-codigo", headers=headers, json=body
        )
    return res, row, query, session, lock


def test_correccion_persiste_valor_e_historial_en_un_commit():
    res, row, query, session, lock = _corregir(_datos())
    assert res.status_code == 200
    assert row.codigo_interno == "01PIELF08"
    assert len(AuditFake.ocurrencias) == 1
    evento = AuditFake.ocurrencias[0]
    assert evento.inventario_id == 427
    assert evento.actor_usuario_id == 91
    assert evento.codigo_anterior == "01PIELF07"
    assert evento.codigo_nuevo == "01PIELF08"
    assert evento.motivo == "Corrección por etiqueta física"
    session.add.assert_called_once_with(evento)
    session.commit.assert_called_once()
    lock.assert_called_once()
    query.filter_by.assert_called_once_with(id=427)
    query.filter_by.return_value.with_for_update.assert_called_once()


def test_rechaza_codigo_duplicado_409_y_no_modifica_registro():
    def duplicate(_, query):
        query.filter.return_value.first.return_value = SimpleNamespace(id=717)
    res, row, _, session, _ = _corregir(_datos("02PLST20"), mutate=duplicate)
    assert res.status_code == 409
    assert row.codigo_interno == "01PIELF07"
    assert not AuditFake.ocurrencias
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_conflicto_optimista_409():
    res, row, _, session, _ = _corregir(_datos(anterior="01PIELF00"))
    assert res.status_code == 409
    assert row.codigo_interno == "01PIELF07"
    session.commit.assert_not_called()
    assert not AuditFake.ocurrencias


def test_codigo_igual_y_motivo_corto_son_rechazados():
    res, _, _, session, _ = _corregir(_datos(nuevo="01PIELF07"))
    assert res.status_code == 400
    session.commit.assert_not_called()
    res, _, _, session, _ = _corregir(_datos(motivo="ok"))
    assert res.status_code == 400
    session.commit.assert_not_called()


def test_commit_fallido_revierte_transaccion():
    res, _, _, session, _ = _corregir(
        _datos(), commit_failure=RuntimeError("db connection error")
    )
    assert res.status_code == 500
    session.rollback.assert_called_once()
    session.add.assert_called_once()


def test_la_edicion_generica_no_puede_cambiar_codigo():
    client, headers = _cliente()
    row = SimpleNamespace(id=427, codigo_interno="01PIELF07", tipo="Aparatos")
    query = Mock()
    query.get.return_value = row
    session = Mock()
    with patch.object(routes, "_require_inventory_global_write", return_value=None), \
         patch.object(routes, "InventarioGeneral", SimpleNamespace(query=query)), \
         patch.object(routes, "db", SimpleNamespace(session=session)):
        res = client.put(
            "/api/inventario/427", headers=headers,
            json={"codigo_interno": "01PIELF08"},
        )
    assert res.status_code == 409
    assert row.codigo_interno == "01PIELF07"
    session.commit.assert_not_called()


def test_historial_es_de_lectura_y_muestra_actor_motivo_y_fecha():
    client, headers = _cliente()
    query = Mock()
    row = SimpleNamespace(
        id=1, actor_usuario_id=91,
        codigo_anterior="01PIELF07", codigo_nuevo="01PIELF08",
        motivo="Corrección por etiqueta física",
        ocurrido_en_utc=datetime(2026, 10, 22, 16, 0, tzinfo=timezone.utc),
    )
    query.filter_by.return_value.order_by.return_value.all.return_value = [row]
    audit = SimpleNamespace(query=query, ocurrido_en_utc=Mock())
    with patch.object(routes, "_require_inventory_global_write", return_value=None), \
         patch.object(routes, "InventarioCodigoCorreccionORM", audit):
        res = client.get("/api/inventario/427/historial-codigos", headers=headers)
    assert res.status_code == 200
    assert res.get_json()[0]["usuario_id"] == 91
    assert res.get_json()[0]["codigo_anterior"] == "01PIELF07"
    assert res.get_json()[0]["motivo"] == "Corrección por etiqueta física"


def test_permissions_are_enforced():
    client, headers = _cliente()
    forbidden = ({"error": "Forbidden"}, 403)
    with patch.object(routes, "_require_inventory_global_write", return_value=forbidden):
        write = client.post(
            "/api/inventario/427/corregir-codigo", headers=headers, json=_datos(),
        )
        read = client.get(
            "/api/inventario/427/historial-codigos", headers=headers,
        )
    assert write.status_code == 403
    assert read.status_code == 403


def test_sin_id_o_codigo_nuevo_no_escribe():
    client, headers = _cliente()
    with patch.object(routes, "_require_inventory_global_write", return_value=None):
        res = client.post(
            "/api/inventario/427/corregir-codigo",
            headers=headers, json=_datos(nuevo=""),
        )
    assert res.status_code == 400
