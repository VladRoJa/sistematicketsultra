"""BI Vlad multi-branch ACL and single-ticket API contract."""
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.routes import ticket_routes


def _user(role, branch, username="regional"):
    return SimpleNamespace(
        rol=role, sucursal_id=branch, username=username, department_id=7,
    )


def _catalog_context(department_name="BI Vlad", branches=3):
    from contextlib import ExitStack
    stack = ExitStack()
    dep = stack.enter_context(patch.object(ticket_routes, "Departamento"))
    dep.query.get.return_value = SimpleNamespace(nombre=department_name)
    suc = stack.enter_context(patch.object(ticket_routes, "Sucursal"))
    suc.query.filter.return_value.filter.return_value.count.return_value = branches
    return stack, suc


def test_valid_multiple_branches_regional_scope():
    app = Flask(__name__)
    with app.app_context():
        stack, suc = _catalog_context()
        with stack, patch.object(
            ticket_routes, "get_user_assigned_branch_ids", return_value=(4, 5, 21)
        ):
            branches, error = ticket_routes._validate_bi_vlad_branch_scope(
                42, [4, 5, 21], _user("GERENTE_REGIONAL", 100)
            )
            assert error is None and branches == [4, 5, 21]
            suc.query.filter.return_value.filter.return_value.count.assert_called_once()


def test_regional_cannot_use_first_valid_branch_to_smuggle_other_branches():
    app = Flask(__name__)
    with app.app_context():
        stack, suc = _catalog_context()
        with stack, patch.object(
            ticket_routes, "get_user_assigned_branch_ids", return_value=(4, 5)
        ):
            branches, error = ticket_routes._validate_bi_vlad_branch_scope(
                42, [4, 21], _user("GERENTE_REGIONAL", 100)
            )
            assert branches is None and error[1] == 403
            suc.query.filter.assert_not_called()


def test_regional_with_empty_scope_fails_closed_even_if_corporate():
    app = Flask(__name__)
    with app.app_context():
        stack, _ = _catalog_context()
        with stack, patch.object(
            ticket_routes, "get_user_assigned_branch_ids", return_value=()
        ):
            branches, error = ticket_routes._validate_bi_vlad_branch_scope(
                42, [100], _user("GERENTE_REGIONAL", 100)
            )
            assert branches is None and error[1] == 403


def test_scope_requires_existing_distinct_positive_integer_ids():
    app = Flask(__name__)
    with app.app_context():
        invalid = ([], [4, 4], [4, True], [4, "5"], [0], [4] * 51)
        stack, _ = _catalog_context()
        with stack:
            for scope in invalid:
                branches, error = ticket_routes._validate_bi_vlad_branch_scope(
                    42, scope, _user("ADMINISTRADOR", 1000)
                )
                assert branches is None and error[1] == 400
        stack, _ = _catalog_context(branches=1)
        with stack:
            branches, error = ticket_routes._validate_bi_vlad_branch_scope(
                42, [4, 5], _user("ADMINISTRADOR", 1000)
            )
            assert branches is None and error[1] == 400


def test_other_departments_cannot_accept_branch_scope_field():
    app = Flask(__name__)
    with app.app_context():
        stack, _ = _catalog_context(department_name="Sistemas")
        with stack:
            branches, error = ticket_routes._validate_bi_vlad_branch_scope(
                7, [4, 5], _user("ADMINISTRADOR", 1000)
            )
            assert branches is None and error[1] == 400
            assert ticket_routes._validate_bi_vlad_branch_scope(
                7, None, _user("GERENTE", 4)
            ) == (None, None)


def test_regional_available_branches_are_not_all_physical_branches():
    app = Flask(__name__)
    with app.test_request_context(
        "/api/tickets/bi-vlad/sucursales-disponibles", method="GET"
    ), patch.object(
        ticket_routes, "get_jwt_identity", return_value=88
    ), patch.object(
        ticket_routes.UserORM, "get_by_id",
        return_value=_user("GERENTE_REGIONAL", 100)
    ), patch.object(
        ticket_routes, "get_user_assigned_branch_ids", return_value=(4, 5)
    ), patch.object(ticket_routes, "Sucursal") as suc:
        suc.query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [
            SimpleNamespace(sucursal_id=4, sucursal="Villas del Rey"),
            SimpleNamespace(sucursal_id=5, sucursal="Villa Verde"),
        ]
        response, status = ticket_routes.bi_vlad_available_branches.__wrapped__()
        assert status == 200
        assert [s["sucursal_id"] for s in response.get_json()["sucursales"]] == [4, 5]
        assert suc.query.filter.called
