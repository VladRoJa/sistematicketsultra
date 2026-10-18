"""Permiso individual de bandeja asignada; ninguna excepción por creador."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import Integer, String, column

from app.utils import ticket_filters


def user(role="SR_MANTENIMIENTO"):
    return SimpleNamespace(
        id=68,
        username="SR_MANT_TIJ",
        rol=role,
        sucursal_id=100,
        department_id=1,
        sucursales_ids=[7, 8, 9],
    )


def fake_query(monkeypatch):
    q = MagicMock()
    fake_ticket = SimpleNamespace(
        query=q,
        departamento_id=column("departamento_id", Integer),
        asignado_a=column("asignado_a", String),
        sucursal_id_destino=column("sucursal_id_destino", Integer),
        sucursal_id=column("sucursal_id", Integer),
        username=column("username", String),
    )
    monkeypatch.setattr(ticket_filters, "Ticket", fake_ticket)
    return q


def compiled_where(query):
    expression = query.filter.call_args.args[0]
    return str(expression.compile(compile_kwargs={"literal_binds": True}))


def test_assigned_only_no_incluye_creador_ni_sucursal(monkeypatch):
    query = fake_query(monkeypatch)
    monkeypatch.setattr(
        ticket_filters,
        "has_assigned_only_maintenance_scope",
        lambda target: True,
    )

    ticket_filters.filtrar_tickets_por_usuario(user())
    sql = compiled_where(query)

    assert "departamento_id = 1" in sql
    assert "lower(asignado_a) = 'sr_mant_tij'" in sql
    assert "sucursal_id_destino" not in sql
    assert "lower(username)" not in sql
    assert " OR " not in sql


def test_otros_supervisores_mantienen_scope_preexistente(monkeypatch):
    query = fake_query(monkeypatch)
    monkeypatch.setattr(
        ticket_filters,
        "has_assigned_only_maintenance_scope",
        lambda target: False,
    )

    ticket_filters.filtrar_tickets_por_usuario(user())
    sql = compiled_where(query)

    assert "departamento_id = 1" in sql
    assert "IN (7, 8, 9)" in sql
    assert "asignado_a" not in sql
    assert " OR " in sql


def test_admin_conserva_lectura_global(monkeypatch):
    query = fake_query(monkeypatch)
    monkeypatch.setattr(
        ticket_filters,
        "has_assigned_only_maintenance_scope",
        lambda target: True,
    )

    result = ticket_filters.filtrar_tickets_por_usuario(user(role="ADMINISTRADOR"))

    assert result is query
    query.filter.assert_not_called()


def test_mutacion_legacy_de_ticket_ajeno_bloqueada(monkeypatch):
    from flask import Blueprint, Flask
    from app.utils import maintenance_ticket_update_guard as guard

    app = Flask(__name__)
    bp = Blueprint("tickets", __name__)

    @bp.route("/cierre/solicitar/<int:ticket_id>", methods=["POST"])
    def cierre_solicitar(ticket_id):
        return "unexpected write", 200

    app.register_blueprint(bp)
    staff = user()
    foreign_ticket = SimpleNamespace(
        id=501, departamento_id=1, asignado_a="OTRO_AUXILIAR"
    )
    monkeypatch.setattr(guard, "verify_jwt_in_request", lambda: None)
    monkeypatch.setattr(guard, "get_jwt_identity", lambda: staff.id)
    monkeypatch.setattr(guard.UserORM, "get_by_id", lambda _id: staff)
    monkeypatch.setattr(
        guard, "Ticket",
        SimpleNamespace(query=SimpleNamespace(get=lambda _id: foreign_ticket))
    )
    monkeypatch.setattr(
        guard, "has_assigned_only_maintenance_scope", lambda _actor: True
    )
    guard.register_maintenance_ticket_update_guard(app)

    response = app.test_client().post("/cierre/solicitar/501")
    assert response.status_code == 403
    assert "que tenga asignados" in response.get_json()["mensaje"]


def test_mutacion_legacy_propia_no_es_bloqueada_por_guard(monkeypatch):
    from flask import Blueprint, Flask
    from app.utils import maintenance_ticket_update_guard as guard

    app = Flask(__name__)
    bp = Blueprint("tickets", __name__)

    @bp.route("/cierre/solicitar/<int:ticket_id>", methods=["POST"])
    def cierre_solicitar(ticket_id):
        return "checked by original endpoint", 200

    app.register_blueprint(bp)
    staff = user()
    owned_ticket = SimpleNamespace(
        id=501, departamento_id=1, asignado_a="sr_mant_tij"
    )
    monkeypatch.setattr(guard, "verify_jwt_in_request", lambda: None)
    monkeypatch.setattr(guard, "get_jwt_identity", lambda: staff.id)
    monkeypatch.setattr(guard.UserORM, "get_by_id", lambda _id: staff)
    monkeypatch.setattr(
        guard, "Ticket",
        SimpleNamespace(query=SimpleNamespace(get=lambda _id: owned_ticket))
    )
    monkeypatch.setattr(
        guard, "has_assigned_only_maintenance_scope", lambda _actor: True
    )
    guard.register_maintenance_ticket_update_guard(app)

    assert app.test_client().post("/cierre/solicitar/501").status_code == 200


def test_reassignment_endpoint_denies_mutating_foreign_assigned_ticket(monkeypatch):
    from flask import Blueprint, Flask
    from app.utils import maintenance_ticket_update_guard as guard

    app = Flask(__name__)
    bp = Blueprint("tickets", __name__)

    @bp.route("/maintenance/<int:ticket_id>/reassign", methods=["PUT"])
    def reassign_maintenance_ticket(ticket_id):
        return "unexpected reassignment", 200

    app.register_blueprint(bp)

    staff = user()
    foreign = SimpleNamespace(
        id=501,
        departamento_id=1,
        asignado_a="SR_MANT_MXL",
    )
    monkeypatch.setattr(guard, "verify_jwt_in_request", lambda: None)
    monkeypatch.setattr(guard, "get_jwt_identity", lambda: staff.id)
    monkeypatch.setattr(guard.UserORM, "get_by_id", lambda _id: staff)
    monkeypatch.setattr(
        guard,
        "Ticket",
        SimpleNamespace(query=SimpleNamespace(get=lambda _id: foreign)),
    )
    monkeypatch.setattr(
        guard, "has_assigned_only_maintenance_scope", lambda _actor: True,
    )
    guard.register_maintenance_ticket_update_guard(app)

    response = app.test_client().put("/maintenance/501/reassign", json={
        "motivo": "Cambio no autorizado",
        "tipo_atencion": "INTERNA",
        "asignado_user_id": 68,
    })
    assert response.status_code == 403
    assert "que tenga asignados" in response.get_json()["mensaje"]
