"""BI Vlad routing: existing ADMICORP account, no user or role mutation."""

from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.routes import ticket_routes


def _department(name="BI Vlad"):
    return SimpleNamespace(id=42, nombre=name)


def _classification(*, department_id=42, active=True, parent_id=83, level=2):
    return SimpleNamespace(
        id=85, departamento_id=department_id, activo=active,
        parent_id=parent_id, nivel=level,
    )


def _admin(role="ADMINISTRADOR"):
    return SimpleNamespace(username="ADMICORP", rol=role, sucursal_id=1000, email="admin@example.test")


def _creator(role="GERENTE", branch=4):
    return SimpleNamespace(username="gerente_prueba", rol=role, sucursal_id=branch)


def _fake_route_deps(*, department=None, classification=None, admin=None):
    from contextlib import ExitStack
    stack = ExitStack()
    dep = stack.enter_context(patch.object(ticket_routes, "Departamento"))
    cat = stack.enter_context(patch.object(ticket_routes, "CatalogoClasificacion"))
    branch_catalog = stack.enter_context(patch.object(ticket_routes, "Sucursal"))
    branch_catalog.query.filter.return_value.count.return_value = 1
    admin_lookup = stack.enter_context(
        patch.object(ticket_routes.UserORM, "get_by_username")
    )
    dep.query.get.return_value = _department() if department is None else department
    cat.query.get.return_value = _classification() if classification is None else classification
    admin_lookup.return_value = _admin() if admin is None else admin
    return stack, dep, cat, admin_lookup


def test_bi_vlad_assigns_only_existing_admin():
    app = Flask(__name__)
    with app.app_context():
        stack, dep, cat, lookup = _fake_route_deps()
        with stack:
            assigned, error = ticket_routes._resolve_bi_vlad_assignment(
                42, 85, _creator(), 4
            )
            assert assigned == "ADMICORP"
            assert error is None
            lookup.assert_called_once_with("ADMICORP")
            cat.query.get.assert_called_once_with(85)
            dep.query.get.assert_called_once_with(42)


def test_other_departments_keep_unassigned_legacy_behavior():
    app = Flask(__name__)
    with app.app_context():
        stack, dep, cat, lookup = _fake_route_deps(department=_department("Sistemas"))
        with stack:
            assigned, error = ticket_routes._resolve_bi_vlad_assignment(
                7, 99, _creator(), 4
            )
            assert (assigned, error) == (None, None)
            cat.query.get.assert_not_called()
            lookup.assert_not_called()


def test_bi_vlad_denies_wrong_or_inactive_classification():
    app = Flask(__name__)
    with app.app_context():
        for classified in (
            _classification(department_id=7),
            _classification(active=False),
            _classification(parent_id=None, level=1),
        ):
            stack, _, _, lookup = _fake_route_deps(classification=classified)
            with stack:
                assigned, error = ticket_routes._resolve_bi_vlad_assignment(
                    42, 85, _creator(), 4
                )
                assert assigned is None and error[1] == 400
                lookup.assert_not_called()


def test_bi_vlad_regional_cannot_request_outside_assigned_branches():
    app = Flask(__name__)
    with app.app_context():
        stack, _, _, lookup = _fake_route_deps()
        with stack, patch.object(
            ticket_routes, "get_user_assigned_branch_ids", return_value=(4, 21)
        ):
            assigned, error = ticket_routes._resolve_bi_vlad_assignment(
                42, 85, _creator("GERENTE_REGIONAL", branch=100), 25
            )
            assert assigned is None and error[1] == 403
            lookup.assert_not_called()

            assigned, error = ticket_routes._resolve_bi_vlad_assignment(
                42, 85, _creator("GERENTE_REGIONAL", branch=100), 21
            )
            assert (assigned, error) == ("ADMICORP", None)


def test_bi_vlad_fails_closed_if_admin_missing_or_role_changed():
    app = Flask(__name__)
    with app.app_context():
        for fallback in (False, _admin(role="GERENTE")):
            stack, _, _, _ = _fake_route_deps()
            with stack, patch.object(
                ticket_routes.UserORM, "get_by_username", return_value=fallback
            ):
                assigned, error = ticket_routes._resolve_bi_vlad_assignment(
                    42, 85, _creator(), 4
                )
                assert assigned is None and error[1] == 409


def test_bi_vlad_endpoint_overrides_spoofed_assignee_without_new_user():
    app = Flask(__name__)
    request_data = {
        "descripcion": "Reactivación de noviembre",
        "departamento_id": 42,
        "criticidad": 2,
        "clasificacion_id": 85,
        "sucursal_id_destino": 4,
        "asignado_a": "OTRA_CUENTA",
        "sucursales_alcance_ids": [4],
    }
    created = SimpleNamespace(id=9001)
    with app.test_request_context(
        "/api/tickets/create", method="POST", json=request_data
    ), patch.object(
        ticket_routes, "get_jwt_identity", return_value=10
    ), patch.object(
        ticket_routes.UserORM, "get_by_id", return_value=_creator()
    ), patch.object(
        ticket_routes, "is_regional_maintenance_lead", return_value=False
    ), patch.object(
        ticket_routes.Ticket, "create_ticket", return_value=created
    ) as create, patch.object(
        ticket_routes, "pick_recipients", return_value=[]
    ):
        stack, _, _, _ = _fake_route_deps()
        with stack:
            response, code = ticket_routes.create_ticket.__wrapped__()
        assert code == 201
        assert response.get_json()["ticket_id"] == 9001
        assert create.call_args.kwargs["asignado_a"] == "ADMICORP"
        assert create.call_args.kwargs["departamento_id"] == 42
        assert create.call_args.kwargs["sucursal_id_destino"] == 1000
        assert create.call_args.kwargs["sucursales_alcance_ids"] == [4]
