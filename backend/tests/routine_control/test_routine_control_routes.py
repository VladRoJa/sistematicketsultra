from __future__ import annotations

import unittest
from importlib.metadata import version
from unittest.mock import patch

import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.routine_control_routes import routine_control_bp
from app.routine_control.queries.operational_service import (
    RoutineControlAuthorizationError,
    RoutineControlValidationError,
)


class FakeService:
    exception = None

    def _result(self, value):
        if self.exception:
            raise self.exception
        return value

    def catalogs(self, _user):
        return self._result({"scope": {"scope_type": "GLOBAL", "allowed_branch_ids": [], "fixed_branch_id": None}, "branches": [], "regions": [], "statuses": [], "assignment_types": []})

    def summary(self, _user, _args):
        return self._result({"total_members": 0})

    def members(self, _user, _args, **_kwargs):
        return self._result({"items": [], "page": 1, "page_size": 25, "total": 0, "total_pages": 0})

    def member_detail(self, _user, member_id):
        return self._result(None if member_id == 404 else {"member": {"id": member_id}})

    def runs(self, _user, _args):
        return self._result({"items": [], "page": 1, "page_size": 25, "total": 0, "total_pages": 0})


class RoutineControlRoutesTest(unittest.TestCase):
    def setUp(self):
        if not hasattr(werkzeug, "__version__"):
            werkzeug.__version__ = version("werkzeug")
        app = Flask(__name__)
        app.config.update(TESTING=True, JWT_SECRET_KEY="test-secret", ROUTINE_CONTROL_EXPORT_MAX_ROWS=10)
        JWTManager(app)
        app.register_blueprint(routine_control_bp, url_prefix="/api/routine-control")
        self.app = app
        with app.app_context():
            token = create_access_token(identity="1")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.fake = FakeService()
        self.service_patch = patch("app.routes.routine_control_routes._service", return_value=self.fake)
        self.user_patch = patch("app.routes.routine_control_routes._current_user", return_value=object())
        self.service_patch.start()
        self.user_patch.start()

    def tearDown(self):
        self.service_patch.stop()
        self.user_patch.stop()

    def test_endpoints_require_jwt(self):
        response = self.app.test_client().get("/api/routine-control/catalogs")
        self.assertEqual(response.status_code, 401)

    def test_catalogs_contract_is_returned(self):
        response = self.app.test_client().get("/api/routine-control/catalogs", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("scope", response.get_json())

    def test_member_not_found_is_404(self):
        response = self.app.test_client().get("/api/routine-control/members/404", headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_out_of_scope_is_403(self):
        self.fake.exception = RoutineControlAuthorizationError("fuera de alcance")
        response = self.app.test_client().get("/api/routine-control/members", headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(response.get_json(), {})

    def test_invalid_filter_is_400(self):
        self.fake.exception = RoutineControlValidationError("filtro inválido")
        response = self.app.test_client().get("/api/routine-control/summary", headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_static_export_route_is_not_consumed_as_member_id(self):
        response = self.app.test_client().get("/api/routine-control/members/export", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    unittest.main()
