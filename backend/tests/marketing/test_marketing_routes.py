from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
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

    def test_reactivation_sources_requires_jwt(self):
        response = self.client.get(
            "/api/marketing/reactivation/sources"
        )

        assert response.status_code == 401

    def test_reactivation_sources_rejects_unauthorized_role(self):
        unauthorized = SimpleNamespace(
            id=8,
            rol="OPERADOR",
            sucursal_id=1,
            sucursales_ids=[1],
        )
        with patch(
            "app.routes.marketing_routes."
            "_get_current_marketing_user",
            return_value=unauthorized,
        ):
            response = self.client.get(
                "/api/marketing/reactivation/sources",
                headers=self.headers,
            )

        assert response.status_code == 403

    def test_reactivation_sources_returns_service_contract(self):
        expected = {
            "vencidos_coverage": {
                "min_date": "2026-08-23",
                "max_date": "2026-08-23",
                "total_rows": 679,
            },
            "iventas_periods": [
                {
                    "period_key": "IVENTAS-2026-08",
                    "sync_run_id": 26,
                    "date_from": "2026-08-01",
                    "date_to": "2026-08-26",
                    "contacts_unique": 51451,
                }
            ],
        }
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "list_marketing_reactivation_sources",
                return_value=expected,
            ) as source_service,
        ):
            response = self.client.get(
                "/api/marketing/reactivation/sources",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected
        assert source_service.call_count == 1

    def test_reactivation_sources_allow_empty_contract(self):
        expected = {
            "vencidos_coverage": {
                "min_date": None,
                "max_date": None,
                "total_rows": 0,
            },
            "iventas_periods": [],
        }
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "list_marketing_reactivation_sources",
                return_value=expected,
            ),
        ):
            response = self.client.get(
                "/api/marketing/reactivation/sources",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected

    @pytest.mark.parametrize(
        "query_string",
        [
            "",
            "?date_from=2026-08-23&date_to=2026-08-23",
            "?iventas_period_key=IVENTAS-2026-08",
            (
                "?date_from=abc&date_to=2026-08-23"
                "&iventas_period_key=IVENTAS-2026-08"
            ),
            (
                "?date_from=2026-08-23&date_to=abc"
                "&iventas_period_key=IVENTAS-2026-08"
            ),
            (
                "?date_from=2026-08-24&date_to=2026-08-23"
                "&iventas_period_key=IVENTAS-2026-08"
            ),
            (
                "?date_from=2026-08-23&date_to=2026-08-23"
                "&iventas_period_key=%20%20"
            ),
        ],
    )
    def test_reactivation_candidates_reject_invalid_params(
        self,
        query_string,
    ):
        with patch(
            "app.routes.marketing_routes."
            "_get_current_marketing_user",
            return_value=self.admin,
        ):
            response = self.client.get(
                "/api/marketing/reactivation/candidates"
                f"{query_string}",
                headers=self.headers,
            )

        assert response.status_code == 400

    def test_reactivation_candidates_returns_complete_contract(self):
        expected = {
            "sources": {
                "date_from": "2026-08-23",
                "date_to": "2026-08-23",
                "activos_snapshot_id": 8,
                "iventas_sync_run_id": 26,
                "iventas_period_key": "IVENTAS-2026-08",
            },
            "summary": {
                "total_rows": 1,
                "status_counts": {"CONTACT_HISTORY_UNKNOWN": 1},
                "reason_counts": {"NO_OUTBOUND_EVIDENCE": 1},
            },
            "rows": [
                {
                    "vencido_row_id": 101,
                    "status": "CONTACT_HISTORY_UNKNOWN",
                    "reason": "NO_OUTBOUND_EVIDENCE",
                }
            ],
        }
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "build_marketing_reactivation_candidates",
                return_value=expected,
            ) as candidate_service,
        ):
            response = self.client.get(
                "/api/marketing/reactivation/candidates"
                "?date_from=2026-08-23"
                "&date_to=2026-08-23"
                "&iventas_period_key=IVENTAS-2026-08",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected
        candidate_service.assert_called_once()
        assert candidate_service.call_args.kwargs["date_from"] == date(
            2026, 8, 23
        )
        assert candidate_service.call_args.kwargs["date_to"] == date(
            2026, 8, 23
        )
        assert candidate_service.call_args.kwargs[
            "iventas_period_key"
        ] == "IVENTAS-2026-08"

    def test_reactivation_canonical_error_is_not_empty_success(self):
        from app.services.marketing_iventas_leads_service import (
            MarketingIventasCanonicalRunRequiredError,
        )

        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "build_marketing_reactivation_candidates",
                side_effect=MarketingIventasCanonicalRunRequiredError(
                    "Sin canonical"
                ),
            ),
        ):
            response = self.client.get(
                "/api/marketing/reactivation/candidates"
                "?date_from=2026-08-23"
                "&date_to=2026-08-23"
                "&iventas_period_key=IVENTAS-2026-08",
                headers=self.headers,
            )

        assert response.status_code == 500
        assert response.get_json()["status"] == "error"

    def test_reactivation_preview_requires_marketing_write_permission(self):
        manager = SimpleNamespace(
            id=2,
            rol="GERENTE",
            sucursal_id=1,
            sucursales_ids=[1],
        )
        with patch(
            "app.routes.marketing_routes._get_current_marketing_user",
            return_value=manager,
        ):
            response = self.client.post(
                "/api/marketing/reactivation/campaigns/preview",
                json={
                    "date_from": "2026-08-23",
                    "date_to": "2026-08-23",
                    "filters": {
                        "iventas_period_key": "IVENTAS-2026-08",
                    },
                },
                headers=self.headers,
            )

        assert response.status_code == 403

    def test_reactivation_preview_returns_shared_engine_contract(self):
        expected = {
            "summary": {
                "total_candidates": 8,
                "eligible": 5,
                "excluded_active": 1,
                "excluded_invalid_phone": 1,
                "review_identity": 1,
                "duplicate_phone": 0,
                "excluded_recent_campaign": 0,
            }
        }
        with (
            patch(
                "app.routes.marketing_routes._get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "preview_marketing_reactivation_campaign",
                return_value=expected,
            ) as preview_service,
        ):
            response = self.client.post(
                "/api/marketing/reactivation/campaigns/preview",
                json={
                    "date_from": "2026-08-23",
                    "date_to": "2026-08-23",
                    "filters": {
                        "iventas_period_key": "IVENTAS-2026-08",
                    },
                },
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected
        assert preview_service.call_args.kwargs["session"] is not None

    def test_reactivation_create_passes_authenticated_user(self):
        expected = {
            "id": 4,
            "name": "Campaña agosto",
            "status": "DRAFT",
            "recipient_count": 5,
        }
        with (
            patch(
                "app.routes.marketing_routes._get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "create_marketing_reactivation_campaign",
                return_value=expected,
            ) as create_service,
        ):
            response = self.client.post(
                "/api/marketing/reactivation/campaigns",
                json={
                    "name": "Campaña agosto",
                    "date_from": "2026-08-23",
                    "date_to": "2026-08-23",
                    "filters": {
                        "iventas_period_key": "IVENTAS-2026-08",
                    },
                },
                headers=self.headers,
            )

        assert response.status_code == 201
        assert response.get_json()["campaign"] == expected
        assert create_service.call_args.kwargs["created_by_user_id"] == 1

    def test_reactivation_campaign_history_returns_service_contract(self):
        expected = {"rows": [{"id": 4, "status": "DRAFT"}], "limit": 50}
        with (
            patch(
                "app.routes.marketing_routes._get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "list_marketing_reactivation_campaigns",
                return_value=expected,
            ),
        ):
            response = self.client.get(
                "/api/marketing/reactivation/campaigns",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected

    def test_reactivation_campaign_detail_returns_404(self):
        from app.services.marketing_reactivation_service import (
            MarketingReactivationNotFoundError,
        )

        with (
            patch(
                "app.routes.marketing_routes._get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "get_marketing_reactivation_campaign",
                side_effect=MarketingReactivationNotFoundError("No existe"),
            ),
        ):
            response = self.client.get(
                "/api/marketing/reactivation/campaigns/999",
                headers=self.headers,
            )

        assert response.status_code == 404

    def test_reactivation_campaign_export_returns_xlsx(self):
        with (
            patch(
                "app.routes.marketing_routes._get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "export_marketing_reactivation_campaign",
                return_value=(b"xlsx-data", "reactivacion_campana_4.xlsx"),
            ),
        ):
            response = self.client.get(
                "/api/marketing/reactivation/campaigns/4/export",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.data == b"xlsx-data"
        assert "reactivacion_campana_4.xlsx" in response.headers[
            "Content-Disposition"
        ]

    def test_reactivation_mark_sent_invalid_transition_returns_409(self):
        from app.services.marketing_reactivation_service import (
            MarketingReactivationInvalidTransitionError,
        )

        with (
            patch(
                "app.routes.marketing_routes._get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "mark_marketing_reactivation_campaign_sent",
                side_effect=MarketingReactivationInvalidTransitionError(
                    "Sólo EXPORTED"
                ),
            ),
        ):
            response = self.client.post(
                "/api/marketing/reactivation/campaigns/4/mark-sent",
                headers=self.headers,
            )

        assert response.status_code == 409

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
                    "notes": "Carga sintética",
                },
                headers=self.headers,
            )

        assert response.status_code == 201
        assert response.get_json()["status"] == "created"
        assert "leads" not in response.get_json()["input"]
        assert "investment" not in response.get_json()["input"]

    def test_deprecated_investment_is_rejected_by_endpoint(self):
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
                    "investment": 100,
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
                    "notes": "Sin autorización",
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
                    "notes": "Fuera de alcance",
                },
                headers=self.headers,
            )

        assert response.status_code == 403

    def test_investment_detail_endpoint_returns_200(self):
        self._assert_detail_endpoint(
            path="investment-detail",
            service_name="build_marketing_investment_detail",
        )

    def test_leads_detail_endpoint_returns_200(self):
        self._assert_detail_endpoint(
            path="leads-detail",
            service_name="build_marketing_leads_detail",
        )

    def test_visitors_detail_endpoint_returns_200(self):
        self._assert_detail_endpoint(
            path="visitors-detail",
            service_name="build_marketing_visitors_detail",
        )

    def _assert_detail_endpoint(
        self,
        *,
        path: str,
        service_name: str,
    ):
        expected = {
            "month": "2026-08",
            "filters": {"sucursal_id": None},
            "rows": [],
        }
        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                f"app.routes.marketing_routes.{service_name}",
                return_value=expected,
            ),
        ):
            response = self.client.get(
                f"/api/marketing/{path}?month=2026-08",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected

    def test_detail_endpoint_rejects_invalid_branch_id(self):
        with patch(
            "app.routes.marketing_routes."
            "_get_current_marketing_user",
            return_value=self.admin,
        ):
            response = self.client.get(
                "/api/marketing/leads-detail"
                "?month=2026-08&sucursal_id=abc",
                headers=self.headers,
            )

        assert response.status_code == 400

    def test_detail_endpoint_returns_403_outside_scope(self):
        from app.services.marketing_access import (
            MarketingAuthorizationError,
        )

        with (
            patch(
                "app.routes.marketing_routes."
                "_get_current_marketing_user",
                return_value=self.admin,
            ),
            patch(
                "app.routes.marketing_routes."
                "build_marketing_visitors_detail",
                side_effect=MarketingAuthorizationError(
                    "La sucursal está fuera del alcance autorizado."
                ),
            ),
        ):
            response = self.client.get(
                "/api/marketing/visitors-detail"
                "?month=2026-08&sucursal_id=999",
                headers=self.headers,
            )

        assert response.status_code == 403

    def test_detail_endpoint_requires_jwt(self):
        response = self.client.get(
            "/api/marketing/investment-detail?month=2026-08"
        )

        assert response.status_code == 401
