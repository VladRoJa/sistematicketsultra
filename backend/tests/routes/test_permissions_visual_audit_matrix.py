"""Auditoría visual V1: paridad entre perspectivas, triestado y seguridad HTTP.

Los fixtures son sintéticos. No se escriben grants ni se accede a producción.
"""
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.models.user_model import UserORM
from app.routes import permissions_catalog_routes as catalog
from app.routes import permissions_visual_audit_routes as visual


def make_user(role="GERENTE", branches=(7,), username="QA_USER"):
    return SimpleNamespace(
        id=77, username=username, rol=role, sucursal_id=7,
        sucursales_ids=list(branches), department_id=1,
    )


def make_action(key, *, is_active=True):
    module_key, action_key = key.split(".", 1)
    return SimpleNamespace(
        id=12, full_key=key, key=action_key, name=key,
        is_active=is_active,
        module=SimpleNamespace(key=module_key, name=module_key, base_action_id=12),
    )


def make_context(user, *, warehouse=None, planning=None):
    return {
        "user": user, "role": user.rol.upper(),
        "sucursal_ids": sorted(set(user.sucursales_ids + [user.sucursal_id])),
        "warehouse_operator": warehouse,
        "planning_operator": planning,
        "pm_scoped_read": False,
        "allow_ticket_delete_all": False,
    }


@pytest.mark.parametrize("role,legacy,catalog_allowed,comparison", [
    ("GERENTE", True, False, "diferencia"),
    ("RECEPCIONISTA", False, False, "coincide"),
    ("ADMINISTRADOR", True, True, "coincide"),
])
def test_track_read_shared_evaluator_detects_gaps(role, legacy, catalog_allowed, comparison):
    user = make_user(role)
    row = visual.evaluate_pair(user, make_action("track.read"), make_context(user))
    assert row["legacy_allowed"] is legacy
    assert row["catalog_allowed"] is catalog_allowed
    assert row["comparison"] == comparison


@pytest.mark.parametrize("view", ["user", "module", "action"])
@pytest.mark.parametrize("branch_id", [None, 7, 15])
def test_one_pair_yields_identical_decision_from_all_views(view, branch_id):
    user = make_user("SISTEMAS")
    action = make_action("warehouse.view")
    operator = SimpleNamespace(can_view=True, can_upload=False, can_archive=False)
    context = make_context(user, warehouse=operator)
    row = visual.evaluate_pair(user, action, context, branch_id=branch_id)
    # Cada perspectiva invoca la misma función, no derivaciones de roles propias.
    assert row["legacy_allowed"] is True
    assert row["catalog_allowed"] is True
    assert row["comparison"] == "coincide"
    assert row["context"]["branch_id"] == branch_id
    assert row["scope"] == "global"


def test_warehouse_denial_and_planning_inactive_operator():
    user = make_user("GERENTE")
    context = make_context(user)
    row = visual.evaluate_pair(user, make_action("warehouse.upload"), context)
    assert row["legacy_allowed"] is False and row["status"] == "denegado"
    planning = SimpleNamespace(is_active=False, can_approve=True)
    context = make_context(user, planning=planning)
    row = visual.evaluate_pair(user, make_action("planning.approve"), context)
    assert row["legacy_allowed"] is False


def test_internal_documents_manager_difference_from_real_pure_guard():
    user = make_user("SISTEMAS", username="SISTEMAS_QA")
    row = visual.evaluate_pair(
        user, make_action("internal_documents.manage"), make_context(user),
    )
    assert row["legacy_allowed"] is True
    assert row["catalog_allowed"] is False
    assert row["comparison"] == "diferencia"


def test_document_scope_without_object_unknown_then_guard_evaluated(monkeypatch):
    user = make_user("RECEPCIONISTA")
    action = make_action("internal_documents.view")
    context = make_context(user)
    unknown = visual.evaluate_pair(user, action, context)
    assert unknown["legacy_allowed"] is None
    assert unknown["comparison"] == "no_concluyente"
    calls = []
    monkeypatch.setattr(visual, "can_view_internal_document",
                        lambda document, doc_context: calls.append(document.id) or False)
    row = visual.evaluate_pair(user, action, context, document=SimpleNamespace(id=999))
    assert calls == [999]
    assert row["legacy_allowed"] is False
    assert row["catalog_allowed"] is None
    assert row["comparison"] == "no_concluyente"
    assert row["catalog_reason"] == "catalogo_no_modela_visibilidad_de_este_documento"
    assert row["scope"] == "documento"


@pytest.mark.parametrize("action_key", [
    "pm.validate", "inventory.movement_write", "tickets.delete_all", "tickets.close",
])
def test_unverified_specific_guards_remain_unknown(action_key):
    user = make_user("ADMINISTRADOR")
    row = visual.evaluate_pair(
        user, make_action(action_key), make_context(user), branch_id=7,
    )
    assert row["legacy_allowed"] is None
    assert row["status"] == "no_concluyente"
    assert row["comparison"] == "no_concluyente"


def test_catalog_unmapped_does_not_count_as_denial():
    user = make_user("ADMINISTRADOR")
    row = visual.evaluate_pair(user, make_action("custom.unknown"), make_context(user))
    assert row["catalog_allowed"] is None
    assert row["legacy_allowed"] is None
    assert row["comparison"] == "no_concluyente"


def test_scoped_or_time_bounded_grants_never_masquerade_as_enforcement():
    user = make_user("GERENTE")
    grant = SimpleNamespace(
        scope_type="branch", starts_at=None, expires_at=None,
        reason="solo sucursal 7", effect="allow",
    )
    row = visual.evaluate_pair(
        user, make_action("warehouse.view"), make_context(user),
        grants={(12, "user", user.id): grant}, branch_id=7,
    )
    assert row["legacy_allowed"] is False
    assert row["catalog_allowed"] is None
    assert row["catalog_source"] == "grant_diagnostico_no_enforcement"
    assert row["comparison"] == "no_concluyente"


@pytest.mark.parametrize("limit,offset", [(0, 0), (51, 0), (1, -1), ("x", 0)])
def test_pagination_rejects_invalid_ranges(limit, offset):
    app = Flask(__name__)
    with app.test_request_context(f"/?limit={limit}&offset={offset}"):
        with pytest.raises(ValueError):
            visual._pagination()


def test_pagination_defaults_and_positive_bounds():
    app = Flask(__name__)
    with app.test_request_context("/"):
        assert visual._pagination() == (25, 0)
    with app.test_request_context("/?limit=50&offset=75"):
        assert visual._pagination() == (50, 75)


def test_search_and_role_are_cumulative_sql_filters():
    app = Flask(__name__)
    with app.test_request_context("/?q=GER&role=GERENTE"):
        sql = str(visual._user_query().statement.compile())
    assert "upper" in sql.lower() and "like" in sql.lower()
    assert "users.rol" in sql.lower()


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = "tests-only-visual-permissions"
    JWTManager(app)
    app.register_blueprint(
        visual.permissions_visual_audit_bp, url_prefix="/api/permissions/catalog/audit",
    )
    monkeypatch.setattr(
        UserORM, "get_by_id", classmethod(
            lambda cls, uid: SimpleNamespace(
                id=uid, rol="ADMINISTRADOR" if uid == 1 else "GERENTE",
            )
        ),
    )
    return app


def test_http_admin_gate_is_enforced_before_fetching_records(app):
    with app.app_context():
        client = app.test_client()
        admin_token = create_access_token(identity="1")
        ordinary_token = create_access_token(identity="2")
        path = "/api/permissions/catalog/audit/matrix?view=user"
        assert client.get(path).status_code == 401
        ordinary = client.get(path, headers={"Authorization": f"Bearer {ordinary_token}"})
        assert ordinary.status_code == 403
        admin = client.get(path, headers={"Authorization": f"Bearer {admin_token}"})
        assert admin.status_code == 400  # admin pasa guard; le falta user_id


def test_route_is_only_get_and_no_mutating_permission_endpoints(app):
    methods = {
        rule.rule: rule.methods for rule in app.url_map.iter_rules()
        if rule.rule.endswith("/audit/matrix")
    }
    assert len(methods) == 1
    assert "GET" in next(iter(methods.values()))
    assert "PUT" not in next(iter(methods.values()))
    assert "POST" not in next(iter(methods.values()))


def test_http_three_perspectives_share_same_user_action_branch(monkeypatch, app):
    """Prueba los tres endpoints HTTP con la misma pareja y paginación ficticia.

    DB aislada por doubles de consulta: no simula enforcement ni escrituras.
    """
    user = make_user("SISTEMAS")
    module = SimpleNamespace(id=99, key="warehouse", name="Warehouse", base_action_id=12)
    action = make_action("warehouse.view")
    action.module = module
    operator = SimpleNamespace(can_view=True, can_upload=False, can_archive=False)
    context = make_context(user, warehouse=operator)

    class FakeQuery:
        def __init__(self, data):
            self.data = data
        def options(self, *args):
            return self
        def filter(self, *args):
            return self
        def filter_by(self, **kwargs):
            return self
        def order_by(self, *args):
            return self
        def offset(self, value):
            return self
        def limit(self, value):
            return self
        def count(self):
            return len(self.data)
        def first(self):
            return self.data[0] if self.data else None
        def all(self):
            return self.data

    class Loader:
        def joinedload(self, _):
            return self

    class Column:
        def is_(self, _):
            return True

    monkeypatch.setattr(visual, "joinedload", lambda _: Loader())
    monkeypatch.setattr(visual, "PermissionActionORM", SimpleNamespace(
        query=FakeQuery([action]), is_active=Column(), full_key=Column(),
        module_id=Column(), module=Column(), id=Column(),
    ))
    monkeypatch.setattr(visual, "PermissionModuleORM", SimpleNamespace(
        query=FakeQuery([module]), base_action=Column(),
    ))
    monkeypatch.setattr(visual, "UserORM", SimpleNamespace(
        query=FakeQuery([user]), username=Column(), id=Column(),
    ))
    monkeypatch.setattr(visual, "_batch_context", lambda users: {user.id: context})
    monkeypatch.setattr(visual, "_bulk_grants", lambda users, actions: {})
    monkeypatch.setattr(catalog, "_current_admin_user_or_error", lambda: (user, None))
    responses = []
    with app.app_context():
        token = create_access_token(identity="1")
        client = app.test_client()
        for view, extra_filters in (
            ("user", "user_id=77"),
            ("module", "module_key=warehouse"),
            ("action", "action_key=warehouse.view"),
        ):
            result = client.get(
                "/api/permissions/catalog/audit/matrix?"
                f"view={view}&branch_id=7&limit=25&offset=0&{extra_filters}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert result.status_code == 200, result.get_json()
            body = result.get_json()
            assert body["summary"]["total"] == 1
            assert body["summary"]["allowed"] == 1
            assert body["summary"]["denied"] == 0
            assert body["summary"]["unknown"] == 0
            assert len(body["rows"]) == 1
            responses.append(body["rows"][0])
    signatures = [
        (
            row["user_id"], row["action_key"], row["context"]["branch_id"],
            row["legacy_allowed"], row["catalog_allowed"], row["comparison"],
            row["legacy_source"], row["module_entry"],
        )
        for row in responses
    ]
    assert signatures[0] == signatures[1] == signatures[2]
    assert signatures[0][3:6] == (True, True, "coincide")


def _sortable_row(uid, username, legacy, catalog_allowed, comparison, module="track"):
    return {
        "user_id": uid, "username": username, "role": "GERENTE",
        "module_key": module, "module_name": module,
        "action_id": 12, "action_key": "track.read", "action_name": "Ver Track",
        "legacy_allowed": legacy, "catalog_allowed": catalog_allowed,
        "comparison": comparison,
        "status": "permitido" if legacy is True else "denegado" if legacy is False
        else "no_concluyente",
    }


def test_sorting_legacy_across_page_boundary_not_only_visible_page():
    # Los primeros 25 registros alfabéticos podrían ser denegados; el permitido
    # al final debe aparecer en la primera página tras el reordenamiento global.
    rows = [
        _sortable_row(index, f"AAA_{index:02d}", False, False, "coincide")
        for index in range(1, 31)
    ]
    rows.append(_sortable_row(31, "ZZZ_PERMITIDO", True, True, "coincide"))
    ordered, groups = visual._prepare_rows(
        rows, "legacy", "asc", "legacy_permitido", "todos",
    )
    assert ordered[0]["username"] == "ZZZ_PERMITIDO"
    assert ordered[0]["group_key"] == "legacy_allowed:permitido"
    assert groups == {
        "legacy_allowed:permitido": 1, "legacy_allowed:denegado": 30,
    }
    assert len(ordered[:25]) == 25
    assert len(ordered[25:]) == 6
    assert len({row["user_id"] for row in ordered}) == 31


def test_group_denied_first_and_keep_legacy_null_distinct():
    rows = [
        _sortable_row(1, "A", True, True, "coincide"),
        _sortable_row(2, "B", None, True, "no_concluyente"),
        _sortable_row(3, "C", False, False, "coincide"),
    ]
    arranged, groups = visual._prepare_rows(
        rows, "user", "asc", "legacy_denegado", "todos",
    )
    assert [row["username"] for row in arranged] == ["C", "A", "B"]
    assert len(groups) == 3
    assert arranged[2]["group_label"] == "Sin comprobar"


def test_global_filters_before_pagination_and_counts_match_filtered_population():
    rows = [
        _sortable_row(index, f"USER_{index:02d}", index % 2 == 0,
                      index % 2 == 0, "coincide")
        for index in range(1, 41)
    ]
    allowed, _ = visual._prepare_rows(rows, "user", "asc", "none", "permitido")
    assert len(allowed) == 20
    assert [row["user_id"] for row in allowed[:5]] == [2, 4, 6, 8, 10]
    assert [row["user_id"] for row in allowed[5:10]] == [12, 14, 16, 18, 20]
    assert all(row["legacy_allowed"] is True for row in allowed)


def test_global_difference_and_comparison_grouping():
    rows = [
        _sortable_row(1, "A", True, False, "diferencia"),
        _sortable_row(2, "B", False, False, "coincide"),
        _sortable_row(3, "C", None, True, "no_concluyente"),
    ]
    arranged, counts = visual._prepare_rows(
        rows, "user", "asc", "comparison_diferencia", "todos",
    )
    assert [r["comparison"] for r in arranged] == [
        "diferencia", "coincide", "no_concluyente",
    ]
    assert counts["comparison:diferencia"] == 1
    differences, _ = visual._prepare_rows(
        rows, "user", "asc", "none", "diferencia",
    )
    assert [row["user_id"] for row in differences] == [1]


@pytest.mark.parametrize("query", [
    "sort_by=no_existe", "sort_dir=invalid", "group_by=invalid",
    "decision=permitido_o_denegado",
])
def test_matrix_controls_fail_closed_on_invalid_values(query):
    app = Flask(__name__)
    with app.test_request_context("/?" + query):
        with pytest.raises(ValueError):
            visual._matrix_controls()


def test_matrix_controls_accept_all_grouping_modes():
    app = Flask(__name__)
    for group in visual.GROUP_MODES:
        with app.test_request_context("/?sort_by=legacy&sort_dir=desc&group_by=" + group):
            sort_by, sort_dir, group_by, decision = visual._matrix_controls()
            assert (sort_by, sort_dir, group_by, decision) == (
                "legacy", "desc", group, "todos",
            )
