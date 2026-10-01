from __future__ import annotations

import inspect
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.routes.marketing_campaign_v2_routes import marketing_campaign_v2_bp
from app.services.marketing_access import MarketingAuthorizationError
from app.services.marketing_campaign_v2_creation_service import (
    MarketingCampaignV2CreationValidationError,
    MarketingCampaignV2EmptyAudienceError,
    MarketingCampaignV2PreviewMismatchError,
)
from app.services.marketing_campaign_v2_query_service import (
    MarketingCampaignV2NotFoundError,
    MarketingCampaignV2QueryValidationError,
)


class TestMarketingCampaignV2Routes:
    def setup_method(self):
        if not hasattr(werkzeug, "__version__"):
            werkzeug.__version__ = version("werkzeug")
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="campaign-v2-test")
        JWTManager(self.app)
        self.app.register_blueprint(marketing_campaign_v2_bp, url_prefix="/api/marketing")
        with self.app.app_context():
            token = create_access_token(identity="7")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = self.app.test_client()
        self.user = SimpleNamespace(id=7)
        self.global_access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=True,
        )
        self.partial_access = SimpleNamespace(
            is_global=False,
            branch_ids=(11, 22),
            can_edit_inputs=True,
        )

    def _auth(self, access=None):
        return patch(
            "app.routes.marketing_campaign_v2_routes._resolve_request_access",
            return_value=(self.user, access or self.global_access),
        )

    def test_v2_routes_do_not_depend_on_legacy_reactivation_request_heuristic(self):
        source = inspect.getsource(routes)
        assert "app.routes.marketing_routes" not in source
        assert "_request_targets_reactivation" not in source
        assert "resolve_marketing_access" in source

    def test_all_endpoints_require_jwt(self):
        paths = [
            ("get", "/api/marketing/campaigns-v2/options"),
            ("post", "/api/marketing/campaigns-v2/preview"),
            ("post", "/api/marketing/campaigns-v2/preview-detail"),
            ("post", "/api/marketing/campaigns-v2"),
            ("get", "/api/marketing/campaigns-v2"),
            ("get", "/api/marketing/campaigns-v2/1"),
            ("get", "/api/marketing/campaigns-v2/1/recipients"),
            ("get", "/api/marketing/campaigns-v2/1/recipients/2"),
            ("patch", "/api/marketing/campaigns-v2/1/purpose"),
        ]
        for method, path in paths:
            response = getattr(self.client, method)(path, json={} if method in {"post", "patch"} else None)
            assert response.status_code == 401

    def test_invalid_or_missing_user_is_403(self):
        with patch(
            "app.routes.marketing_campaign_v2_routes._resolve_request_access",
            side_effect=MarketingAuthorizationError("Usuario no encontrado."),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/options",
                headers=self.headers,
            )
        assert response.status_code == 403

    def test_campaign_v2_uses_management_permission_not_reactivation_flag(self):
        access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=False,
            can_view_reactivation=True,
        )
        with self._auth(access):
            response = self.client.get(
                "/api/marketing/campaigns-v2/options",
                headers=self.headers,
            )
        assert response.status_code == 403

    def test_options_returns_domains_and_global_scope(self):
        with self._auth():
            response = self.client.get(
                "/api/marketing/campaigns-v2/options",
                headers=self.headers,
            )
        assert response.status_code == 200
        body = response.get_json()
        assert body["sources"] == ["EXPIRED_MEMBERS", "ACTIVE_MEMBERS"]
        assert body["selectable_audience_families"] == [
            "DOMICILIADO", "TRIMESTRAL", "CONVENIO", "SEMESTRE", "ESTUDIANTE"
        ]
        assert body["non_selectable_classifications"] == [
            "MES", "OUT_OF_SEGMENT", "UNCLASSIFIED"
        ]
        assert body["scope"] == {"is_global": True, "allowed_sucursal_keys": None}

    def test_partial_scope_is_derived_from_backend_branch_ids(self):
        expected = {11: "BRANCH A", 22: "BRANCH B"}
        preview = {"preview_fingerprint": "a" * 64}
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value=expected,
            ) as mapper,
            patch(
                "app.routes.marketing_campaign_v2_routes.build_campaign_v2_freeze_preview",
                return_value=preview,
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/preview",
                json={
                    "source": "ACTIVE_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                },
                headers=self.headers,
            )
        assert response.status_code == 200
        assert mapper.call_args.kwargs["sucursal_ids"] == (11, 22)
        assert service.call_args.kwargs["allowed_sucursal_keys"] == (
            "BRANCH A", "BRANCH B"
        )

    def test_empty_partial_scope_fails_closed(self):
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value={},
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/options",
                headers=self.headers,
            )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "endpoint,extra",
        [
            ("/api/marketing/campaigns-v2/preview", {"allowed_sucursal_keys": ["EXTRA"]}),
            ("/api/marketing/campaigns-v2/preview", {"created_by_user_id": 999}),
            ("/api/marketing/campaigns-v2", {"created_by_user_id": 999}),
            ("/api/marketing/campaigns-v2", {"allowed_sucursal_keys": ["EXTRA"]}),
            ("/api/marketing/campaigns-v2/preview", {"phones": ["6861000001"]}),
            ("/api/marketing/campaigns-v2", {"recipients": [{"phone_mx10": "6861000001"}]}),
            ("/api/marketing/campaigns-v2", {"recipient_ids": [1]}),
            ("/api/marketing/campaigns-v2", {"source_record_ids": [1]}),
            ("/api/marketing/campaigns-v2", {"evidence_rows": [{}]}),
        ],
    )
    def test_payload_cannot_expand_scope_or_supply_cohort(self, endpoint, extra):
        payload = {
            "source": "ACTIVE_MEMBERS",
            "audience_families": ["DOMICILIADO"],
            **extra,
        }
        if endpoint.endswith("campaigns-v2"):
            payload.update(
                {
                    "name": "Test",
                    "purpose": "ACTIVE_MEMBERS",
                    "expected_preview_fingerprint": "a" * 64,
                }
            )
        with self._auth():
            response = self.client.post(endpoint, json=payload, headers=self.headers)
        assert response.status_code == 400

    def test_preview_uses_freeze_preview_and_returns_fingerprint(self):
        expected = {
            "unique_recipient_count": 5,
            "preview_fingerprint_version": "campaign-v2-freeze-v1",
            "preview_fingerprint": "b" * 64,
        }
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.build_campaign_v2_freeze_preview",
                return_value=expected,
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/preview",
                json={
                    "source": "EXPIRED_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "expiration_date_from": "2026-08-01",
                    "expiration_date_to": "2026-08-31",
                },
                headers=self.headers,
            )
        assert response.status_code == 200
        assert response.get_json()["preview_fingerprint"] == "b" * 64
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None

    def test_preview_detail_uses_m3_detail_and_backend_scope(self):
        expected = {"total": 1, "rows": [{"phone_mx10": "6861000001"}]}
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.audience.build_campaign_v2_audience_preview_detail",
                return_value=expected,
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/preview-detail",
                json={
                    "source": "EXPIRED_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "expiration_date_from": "2026-08-01",
                    "expiration_date_to": "2026-08-31",
                    "bucket": "RECIPIENTS",
                    "page": 1,
                    "page_size": 25,
                },
                headers=self.headers,
            )
        assert response.status_code == 200
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None
        assert service.call_args.kwargs["bucket"] == "RECIPIENTS"

    def test_freeze_uses_authenticated_user_and_backend_scope(self):
        expected = {"campaign_id": 44, "recipient_count": 10}
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.freeze_campaign_v2",
                return_value=expected,
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2",
                json={
                    "name": "Activos",
                    "purpose": "ACTIVE_MEMBERS",
                    "source": "ACTIVE_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "expected_preview_fingerprint": "c" * 64,
                },
                headers=self.headers,
            )
        assert response.status_code == 201
        assert service.call_args.kwargs["created_by_user_id"] == 7
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None
        assert service.call_args.kwargs["expected_preview_fingerprint"] == "c" * 64

    @pytest.mark.parametrize(
        "error,status",
        [
            (MarketingCampaignV2CreationValidationError("bad"), 400),
            (MarketingCampaignV2PreviewMismatchError("stale"), 409),
            (MarketingCampaignV2EmptyAudienceError("empty"), 409),
        ],
    )
    def test_freeze_maps_service_errors(self, error, status):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.freeze_campaign_v2",
                side_effect=error,
            ),
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2",
                json={
                    "name": "Test",
                    "purpose": "REACTIVATION",
                    "source": "ACTIVE_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "expected_preview_fingerprint": "d" * 64,
                },
                headers=self.headers,
            )
        assert response.status_code == status

    def test_list_and_reads_receive_backend_scope(self):
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value={11: "A", 22: "B"},
            ),
            patch(
                "app.routes.marketing_campaign_v2_routes.list_campaign_v2",
                return_value={"page": 1, "page_size": 50, "total": 0, "total_pages": 0, "rows": []},
            ) as service,
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2?page=1&page_size=50",
                headers=self.headers,
            )
        assert response.status_code == 200
        assert service.call_args.kwargs["allowed_sucursal_keys"] == ("A", "B")

    def test_out_of_scope_campaign_is_exposed_as_404_not_403(self):
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value={11: "A", 22: "B"},
            ),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_campaign_v2",
                side_effect=MarketingCampaignV2NotFoundError("hidden"),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/99",
                headers=self.headers,
            )
        assert response.status_code == 404

    def test_recipient_detail_does_not_cross_campaign_boundary(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_campaign_v2_recipient",
                side_effect=MarketingCampaignV2NotFoundError("hidden"),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/recipients/999",
                headers=self.headers,
            )
        assert response.status_code == 404

    def test_patch_purpose_accepts_only_purpose_and_applies_scope(self):
        expected = {"id": 1, "purpose": "NEW_SALE"}
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.update_campaign_v2_purpose",
                return_value=expected,
            ) as service,
        ):
            response = self.client.patch(
                "/api/marketing/campaigns-v2/1/purpose",
                json={"purpose": "NEW_SALE"},
                headers=self.headers,
            )
        assert response.status_code == 200
        assert service.call_args.kwargs["purpose"] == "NEW_SALE"
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None

        with self._auth():
            invalid = self.client.patch(
                "/api/marketing/campaigns-v2/1/purpose",
                json={"purpose": "NEW_SALE", "name": "No"},
                headers=self.headers,
            )
        assert invalid.status_code == 400

    def test_query_validation_maps_to_400(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.list_campaign_v2",
                side_effect=MarketingCampaignV2QueryValidationError("page inválida"),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2?page=0",
                headers=self.headers,
            )
        assert response.status_code == 400
