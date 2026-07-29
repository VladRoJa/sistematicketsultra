from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import werkzeug
from flask import Flask
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
)

from app.routes.marketing_routes import marketing_bp


def _serialized_row():
    return SimpleNamespace(
        id=91,
        month_start=datetime(
            2026,
            7,
            1,
            tzinfo=timezone.utc,
        ).date(),
        sucursal_id=1,
        investment=Decimal("100.00"),
        leads=10,
        notes=None,
        created_by_user_id=1,
        updated_by_user_id=1,
        created_at=datetime(
            2026,
            7,
            1,
            tzinfo=timezone.utc,
        ),
        updated_at=datetime(
            2026,
            7,
            1,
            tzinfo=timezone.utc,
        ),
    )


class TestMarketingRoutes:
    def setup_method(self):
        if not hasattr(werkzeug, "__version__"):
            werkzeug.__version__ = version("werkzeug")

        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="marketing-route-secret",
        )
        JWTManager(self.app)
        self.app.register_blueprint(
            marketing_bp,
            url_prefix="/api/marketing",
        )
        with self.app.app_context():
            token = create_access_token(identity="1")
        self.headers = {
            "Authorization": f"Bearer {token}"
        }
        self.client = self.app.test_client()
        self.admin = SimpleNamespace(
            id=1,
            rol="ADMIN",
            sucursal_id=1000,
            sucursales_ids=[],
        )

    def test_dashboard_endpoint_returns_service_contract(self):
        expected = {
            "month": "2026-07",
            "cohort_mode": "visit_month",
        }
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "build_marketing_dashboard",
                return_value=expected,
            ),
        ):
            response = self.client.get(
                "/api/marketing/dashboard"
                "?month=2026-07",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected

    def test_inputs_endpoint_returns_scoped_rows(self):
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "load_visible_marketing_branches",
                return_value=(
                    [],
                    (1,),
                    {
                        "type": "GLOBAL",
                        "branch_ids": [1],
                    },
                ),
            ),
            patch(
                "app.routes.marketing_routes."
                "list_marketing_inputs",
                return_value=[_serialized_row()],
            ),
        ):
            response = self.client.get(
                "/api/marketing/inputs?month=2026-07",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json()["inputs"][0][
            "sucursal_id"
        ] == 1

    def test_put_input_creates_scoped_input(self):
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "load_visible_marketing_branches",
                return_value=(
                    [],
                    (1,),
                    {
                        "type": "GLOBAL",
                        "branch_ids": [1],
                    },
                ),
            ),
            patch(
                "app.routes.marketing_routes."
                "upsert_marketing_input",
                return_value=(
                    _serialized_row(),
                    True,
                ),
            ),
        ):
            response = self.client.put(
                "/api/marketing/inputs/1",
                json={
                    "month": "2026-07",
                    "investment": 100,
                    "leads": 10,
                    "notes": "Carga sintética",
                },
                headers=self.headers,
            )

        assert response.status_code == 201
        assert response.get_json()["status"] == "created"

    def test_negative_input_is_rejected_by_endpoint(self):
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "load_visible_marketing_branches",
                return_value=(
                    [],
                    (1,),
                    {
                        "type": "GLOBAL",
                        "branch_ids": [1],
                    },
                ),
            ),
        ):
            response = self.client.put(
                "/api/marketing/inputs/1",
                json={
                    "month": "2026-07",
                    "investment": -1,
                    "leads": 10,
                },
                headers=self.headers,
            )

        assert response.status_code == 400

    def test_user_without_edit_permission_receives_403(self):
        manager = SimpleNamespace(
            id=2,
            rol="GERENTE",
            sucursal_id=1,
            sucursales_ids=[1],
        )
        with patch(
            "app.routes.marketing_routes."
            "_get_current_marketing_user",
            return_value=manager,
        ):
            response = self.client.put(
                "/api/marketing/inputs/1",
                json={
                    "month": "2026-07",
                    "investment": 100,
                    "leads": 10,
                },
                headers=self.headers,
            )

        assert response.status_code == 403

    def test_editor_cannot_write_outside_scope(self):
        editor = SimpleNamespace(
            id=3,
            rol="MARKETING",
            sucursal_id=1,
            sucursales_ids=[1],
        )
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=editor,
            ),
            patch(
                "app.routes.marketing_routes."
                "load_visible_marketing_branches",
                return_value=(
                    [],
                    (1,),
                    {
                        "type": "PRIMARY_BRANCH",
                        "branch_ids": [1],
                    },
                ),
            ),
        ):
            response = self.client.put(
                "/api/marketing/inputs/2",
                json={
                    "month": "2026-07",
                    "investment": 100,
                    "leads": 10,
                },
                headers=self.headers,
            )

        assert response.status_code == 403
