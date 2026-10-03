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
            ("get", "/api/marketing/campaigns-v2/tariffs/unclassified"),
            ("put", "/api/marketing/campaigns-v2/tariffs/PLAN%20FAMILIAR/classification"),
            ("get", "/api/marketing/campaigns-v2"),
            ("post", "/api/marketing/campaigns-v2/provider-history/lookup"),
            ("get", "/api/marketing/campaigns-v2/1"),
            ("get", "/api/marketing/campaigns-v2/reporting"),
            ("get", "/api/marketing/campaigns-v2/1/report"),
            ("get", "/api/marketing/campaigns-v2/1/provider-stats"),
            ("post", "/api/marketing/campaigns-v2/1/provider-stats/snapshots"),
            ("get", "/api/marketing/campaigns-v2/1/provider-stats/snapshots"),
            ("get", "/api/marketing/campaigns-v2/1/provider-stats/snapshots/latest"),
            ("get", "/api/marketing/campaigns-v2/1/recipients"),
            ("get", "/api/marketing/campaigns-v2/1/recipients/2"),
            ("patch", "/api/marketing/campaigns-v2/1/purpose"),
            ("put", "/api/marketing/campaigns-v2/1/provider-binding"),
        ]
        for method, path in paths:
            response = getattr(self.client, method)(
                path,
                json={} if method in {"post", "put", "patch"} else None,
            )
            assert response.status_code == 401

    def test_tariff_classifier_reuses_campaign_v2_management_permission(self):
        access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=False,
        )
        with self._auth(access):
            response = self.client.get(
                "/api/marketing/campaigns-v2/tariffs/unclassified?source=ACTIVE_MEMBERS",
                headers=self.headers,
            )
        assert response.status_code == 403

    def test_unclassified_tariff_route_uses_backend_scope_and_source_filters(self):
        expected = {
            "source": "EXPIRED_MEMBERS",
            "total_unique_tariffs": 1,
            "total_unclassified_rows": 12,
            "unkeyed_row_count": 0,
            "rows": [
                {
                    "tarifa_raw": "PLAN X",
                    "tarifa_key": "PLAN X",
                    "source": "EXPIRED_MEMBERS",
                    "row_count": 12,
                }
            ],
        }
        with self._auth(), patch.object(
            routes.tariff_classifier,
            "list_unclassified_tariffs",
            return_value=expected,
        ) as mocked:
            response = self.client.get(
                "/api/marketing/campaigns-v2/tariffs/unclassified"
                "?source=EXPIRED_MEMBERS"
                "&expiration_date_from=2026-08-01"
                "&expiration_date_to=2026-08-31",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json()["rows"][0]["row_count"] == 12
        kwargs = mocked.call_args.kwargs
        assert kwargs["source"] == "EXPIRED_MEMBERS"
        assert kwargs["allowed_sucursal_keys"] is None
        assert kwargs["expiration_date_from"] == "2026-08-01"
        assert kwargs["expiration_date_to"] == "2026-08-31"

    def test_tariff_classification_put_allows_only_category_family_and_uses_jwt_user(self):
        path = (
            "/api/marketing/campaigns-v2/tariffs/PLAN%20FAMILIAR/classification"
            "?source=ACTIVE_MEMBERS"
        )
        with self._auth():
            rejected = self.client.put(
                path,
                headers=self.headers,
                json={
                    "categoria_tarifa": "Domiciliado",
                    "audience_family": "DOMICILIADO",
                    "created_by_user_id": 999,
                },
            )
        assert rejected.status_code == 400

        result = {
            "id": 5,
            "tarifa_key": "PLAN FAMILIAR",
            "tarifa_raw": "Plan Familiar",
            "categoria_tarifa": "Domiciliado",
            "audience_family": "DOMICILIADO",
            "created_by_user_id": 7,
            "updated_by_user_id": 7,
            "created": True,
        }
        with self._auth(), patch.object(
            routes.tariff_classifier,
            "stable_representative_for_key",
            return_value="Plan Familiar",
        ), patch.object(
            routes.tariff_classifier,
            "upsert_tariff_classification",
            return_value=result,
        ) as mocked:
            response = self.client.put(
                path,
                headers=self.headers,
                json={
                    "categoria_tarifa": "Domiciliado",
                    "audience_family": "DOMICILIADO",
                },
            )

        assert response.status_code == 200
        kwargs = mocked.call_args.kwargs
        assert kwargs["tarifa_key"] == "PLAN FAMILIAR"
        assert kwargs["categoria_tarifa"] == "Domiciliado"
        assert kwargs["audience_family"] == "DOMICILIADO"
        assert kwargs["user_id"] == 7
        assert kwargs["representative_raw"] == "Plan Familiar"

    def test_tariff_classification_put_invalid_category_returns_400(self):
        path = (
            "/api/marketing/campaigns-v2/tariffs/PLAN%20FAMILIAR/classification"
            "?source=ACTIVE_MEMBERS"
        )
        with self._auth(), patch.object(
            routes.tariff_classifier,
            "stable_representative_for_key",
            return_value="Plan Familiar",
        ), patch.object(
            routes.tariff_classifier,
            "upsert_tariff_classification",
            side_effect=routes.tariff_classifier.MarketingCampaignV2TariffClassifierValidationError(
                "categoria_tarifa no pertenece al catálogo canónico Campaign V2."
            ),
        ):
            response = self.client.put(
                path,
                headers=self.headers,
                json={
                    "categoria_tarifa": "Dom",
                    "audience_family": "DOMICILIADO",
                },
            )

        assert response.status_code == 400
        assert "catálogo canónico" in response.get_json()["message"]

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

    def test_options_returns_domains_tariff_categories_and_global_scope(self):
        categories = [
            "Agregadora",
            "Anualidad",
            "Beca",
            "Bimestre",
            "Convenio",
            "Diario",
            "Domiciliado",
            "Estudiante",
            "Instructor",
            "Mensualidad",
            "Mes Reward",
            "Pase de Cortesía",
            "Recurrente",
            "Semana",
            "Semestre",
            "Trimestre",
        ]
        with self._auth(), patch.object(
            routes.tariff_classifier,
            "list_canonical_tariff_categories",
            return_value=tuple(categories),
        ) as mocked:
            response = self.client.get(
                "/api/marketing/campaigns-v2/options",
                headers=self.headers,
            )
        assert response.status_code == 200
        body = response.get_json()
        assert body["sources"] == [
            "EXPIRED_MEMBERS",
            "ACTIVE_MEMBERS",
            "FUNNEL_PORTFOLIO",
        ]
        assert body["source_filters"]["FUNNEL_PORTFOLIO"] == {
            "required": ["funnel_month", "funnel_cutoff_date"],
            "not_applicable": [
                "audience_families",
                "expiration_date_from",
                "expiration_date_to",
                "tarifa",
                "categoria_tarifa",
            ],
            "cutoff_policy": "EXACT_COMPLETE",
        }
        assert body["selectable_audience_families"] == [
            "DOMICILIADO", "TRIMESTRAL", "CONVENIO", "SEMESTRE", "ESTUDIANTE"
        ]
        assert body["non_selectable_classifications"] == [
            "MES", "OUT_OF_SEGMENT", "UNCLASSIFIED"
        ]
        assert body["historical_targeting"] == {
            "modes": ["INCLUDE", "EXCLUDE"],
            "matches": ["ALL", "ANY"],
            "delivery_buckets": ["SENT", "DELIVERED", "VIEWED"],
            "outcomes": ["SUCCESSFUL", "FAILED"],
            "button_interaction": True,
            "window_modes": ["ALL_HISTORY", "LOOKBACK_DAYS"],
            "legacy_history_exclusion_supported": True,
        }
        assert body["tariff_categories"] == categories
        mocked.assert_called_once()
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
            ("/api/marketing/campaigns-v2/preview", {"excluded_phones": ["6861000001"]}),
            ("/api/marketing/campaigns-v2/preview-detail", {"excluded_phones": ["6861000001"]}),
            ("/api/marketing/campaigns-v2", {"excluded_phones": ["6861000001"]}),
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
                    "history_exclusion": {
                        "delivery_buckets": ["VIEWED"],
                    },
                },
                headers=self.headers,
            )
        assert response.status_code == 200
        assert response.get_json()["preview_fingerprint"] == "b" * 64
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None
        assert service.call_args.kwargs["history_exclusion"] == {
            "delivery_buckets": ["VIEWED"],
        }

    def test_preview_forwards_canonical_historical_targeting(self):
        expected = {"preview_fingerprint": "9" * 64}
        rule = {
            "mode": "INCLUDE",
            "match": "ALL",
            "delivery_buckets": ["VIEWED"],
            "outcomes": [],
            "button_interacted": True,
            "lookback_days": 90,
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
                    "source": "ACTIVE_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "historical_targeting": rule,
                },
                headers=self.headers,
            )

        assert response.status_code == 200
        assert service.call_args.kwargs["historical_targeting"] == rule
        assert service.call_args.kwargs["history_exclusion"] is None

    def test_preview_detail_forwards_canonical_historical_targeting(self):
        rule = {
            "mode": "EXCLUDE",
            "match": "ANY",
            "outcomes": ["FAILED"],
        }
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.audience.build_campaign_v2_audience_preview_detail",
                return_value={"total": 0, "rows": []},
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/preview-detail",
                json={
                    "source": "ACTIVE_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "bucket": "RECIPIENTS",
                    "page": 1,
                    "page_size": 25,
                    "historical_targeting": rule,
                },
                headers=self.headers,
            )

        assert response.status_code == 200
        assert service.call_args.kwargs["historical_targeting"] == rule
        assert service.call_args.kwargs["history_exclusion"] is None

    def test_preview_detail_accepts_history_included_bucket(self):
        expected = {
            "bucket": "HISTORY_INCLUDED",
            "total": 1,
            "rows": [
                {
                    "phone_mx10": "6861000001",
                    "history_matched": True,
                    "history_decision": "INCLUDED",
                    "history_reasons": ["HISTORY_DELIVERY_VIEWED"],
                }
            ],
        }
        rule = {
            "mode": "INCLUDE",
            "match": "ANY",
            "delivery_buckets": ["VIEWED"],
        }
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
                    "source": "ACTIVE_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "bucket": "HISTORY_INCLUDED",
                    "page": 1,
                    "page_size": 25,
                    "historical_targeting": rule,
                },
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json()["bucket"] == "HISTORY_INCLUDED"
        assert service.call_args.kwargs["bucket"] == "HISTORY_INCLUDED"
        assert service.call_args.kwargs["historical_targeting"] == rule

    def test_freeze_forwards_canonical_historical_targeting(self):
        rule = {
            "mode": "INCLUDE",
            "match": "ANY",
            "delivery_buckets": ["DELIVERED"],
        }
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.freeze_campaign_v2",
                return_value={"campaign_id": 55, "recipient_count": 1},
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2",
                json={
                    "name": "Targeted",
                    "purpose": "ACTIVE_MEMBERS",
                    "source": "ACTIVE_MEMBERS",
                    "audience_families": ["DOMICILIADO"],
                    "historical_targeting": rule,
                    "expected_preview_fingerprint": "8" * 64,
                },
                headers=self.headers,
            )

        assert response.status_code == 201
        assert service.call_args.kwargs["historical_targeting"] == rule
        assert service.call_args.kwargs["history_exclusion"] is None

    @pytest.mark.parametrize(
        ("endpoint", "extra"),
        [
            ("/api/marketing/campaigns-v2/preview", {}),
            (
                "/api/marketing/campaigns-v2/preview-detail",
                {"bucket": "RECIPIENTS", "page": 1, "page_size": 25},
            ),
            (
                "/api/marketing/campaigns-v2",
                {
                    "name": "Ambiguous",
                    "purpose": "ACTIVE_MEMBERS",
                    "expected_preview_fingerprint": "7" * 64,
                },
            ),
        ],
    )
    def test_legacy_and_canonical_history_together_returns_400(
        self,
        endpoint,
        extra,
    ):
        payload = {
            "source": "ACTIVE_MEMBERS",
            "audience_families": ["DOMICILIADO"],
            "history_exclusion": {"delivery_buckets": ["VIEWED"]},
            "historical_targeting": {
                "mode": "INCLUDE",
                "match": "ANY",
                "delivery_buckets": ["VIEWED"],
            },
            **extra,
        }
        with self._auth():
            response = self.client.post(
                endpoint,
                json=payload,
                headers=self.headers,
            )

        assert response.status_code == 400
        assert "no pueden enviarse juntos" in response.get_json()["message"]

    def test_funnel_preview_forwards_backend_access_and_cutoff(self):
        expected = {"preview_fingerprint": "f" * 64}
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value={11: "BRANCH A", 22: "BRANCH B"},
            ),
            patch(
                "app.routes.marketing_campaign_v2_routes.build_campaign_v2_freeze_preview",
                return_value=expected,
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/preview",
                json={
                    "source": "FUNNEL_PORTFOLIO",
                    "funnel_month": "2026-09",
                    "funnel_cutoff_date": "2026-09-30",
                },
                headers=self.headers,
            )

        assert response.status_code == 200
        assert service.call_args.kwargs["funnel_month"] == "2026-09"
        assert service.call_args.kwargs["funnel_cutoff_date"] == "2026-09-30"
        assert service.call_args.kwargs["marketing_access"] is self.partial_access
        assert service.call_args.kwargs["audience_families"] is None

    @pytest.mark.parametrize("field", ["tarifa", "categoria_tarifa"])
    def test_funnel_preview_rejects_tariff_filters_at_route_boundary(self, field):
        with self._auth():
            response = self.client.post(
                "/api/marketing/campaigns-v2/preview",
                json={
                    "source": "FUNNEL_PORTFOLIO",
                    "funnel_month": "2026-09",
                    "funnel_cutoff_date": "2026-09-30",
                    field: "NO_APLICA",
                },
                headers=self.headers,
            )
        assert response.status_code == 400

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
                    "history_exclusion": {
                        "outcomes": ["FAILED"],
                    },
                },
                headers=self.headers,
            )
        assert response.status_code == 200
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None
        assert service.call_args.kwargs["bucket"] == "RECIPIENTS"
        assert service.call_args.kwargs["history_exclusion"] == {
            "outcomes": ["FAILED"],
        }

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
                    "history_exclusion": {
                        "button_interacted": True,
                    },
                    "expected_preview_fingerprint": "c" * 64,
                },
                headers=self.headers,
            )
        assert response.status_code == 201
        assert service.call_args.kwargs["created_by_user_id"] == 7
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None
        assert service.call_args.kwargs["expected_preview_fingerprint"] == "c" * 64
        assert service.call_args.kwargs["history_exclusion"] == {
            "button_interacted": True,
        }

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



    def test_consolidated_reporting_forwards_filters_and_backend_scope(self):
        expected = {
            "filters": {"purpose": "NEW_SALE"},
            "summary": {"campaign_count": 1},
            "campaigns": [],
            "breakdowns": {"branches": [], "audience_families": []},
        }
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value={11: "A", 22: "B"},
            ),
            patch(
                "app.routes.marketing_campaign_v2_routes.build_campaign_v2_consolidated_report",
                return_value=expected,
            ) as service,
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/reporting"
                "?observed_from=2026-10-01T12:00:00Z"
                "&observed_to=2026-10-02T12:00:00Z"
                "&purpose=NEW_SALE"
                "&source=FUNNEL_PORTFOLIO"
                "&provider=IVENTAS"
                "&snapshot_status=WITH_SNAPSHOT",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected
        assert service.call_args.kwargs["allowed_sucursal_keys"] == ("A", "B")
        assert service.call_args.kwargs["filters"] == {
            "observed_from": "2026-10-01T12:00:00Z",
            "observed_to": "2026-10-02T12:00:00Z",
            "purpose": "NEW_SALE",
            "source": "FUNNEL_PORTFOLIO",
            "provider": "IVENTAS",
            "snapshot_status": "WITH_SNAPSHOT",
        }

    def test_consolidated_reporting_reuses_campaign_v2_management_permission(self):
        access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=False,
        )
        with self._auth(access):
            response = self.client.get(
                "/api/marketing/campaigns-v2/reporting",
                headers=self.headers,
            )

        assert response.status_code == 403

    @pytest.mark.parametrize(
        "query",
        [
            "?observed_from=2026-10-01T12:00:00",
            "?observed_to=not-a-date",
            "?observed_from=2026-10-02T00:00:00Z&observed_to=2026-10-01T00:00:00Z",
            "?purpose=BAD",
            "?source=BAD",
            "?provider=" + ("X" * 51),
            "?snapshot_status=BAD",
        ],
    )
    def test_consolidated_reporting_validation_maps_to_400(self, query):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.build_campaign_v2_consolidated_report",
                side_effect=routes.MarketingCampaignV2ReportingValidationError(
                    "invalid reporting filter"
                ),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/reporting" + query,
                headers=self.headers,
            )

        assert response.status_code == 400

    def test_consolidated_reporting_rejects_unknown_refresh_sync_export_params(self):
        with self._auth():
            for query in (
                "?refresh=true",
                "?sync=true",
                "?export=xlsx",
                "?branch=BRANCH%20A",
            ):
                response = self.client.get(
                    "/api/marketing/campaigns-v2/reporting" + query,
                    headers=self.headers,
                )
                assert response.status_code == 400

    def test_individual_report_uses_backend_scope_only(self):
        expected = {
            "campaign": {"id": 1, "name": "Reporte"},
            "audience": {"total_recipients": 10},
        }
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value={11: "A", 22: "B"},
            ),
            patch(
                "app.routes.marketing_campaign_v2_routes.build_campaign_v2_individual_report",
                return_value=expected,
            ) as service,
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/report",
                headers=self.headers,
            )

        assert response.status_code == 200
        assert response.get_json() == expected
        assert service.call_args.kwargs["campaign_id"] == 1
        assert service.call_args.kwargs["allowed_sucursal_keys"] == ("A", "B")

    def test_individual_report_rejects_refresh_sync_or_provider_flags(self):
        with self._auth():
            for query in (
                "?refresh=true",
                "?sync=true",
                "?provider=IVENTAS",
            ):
                response = self.client.get(
                    "/api/marketing/campaigns-v2/1/report" + query,
                    headers=self.headers,
                )
                assert response.status_code == 400

    def test_individual_report_out_of_scope_maps_to_404(self):
        with (
            self._auth(self.partial_access),
            patch(
                "app.routes.marketing_campaign_v2_routes.marketing_branch_keys_by_sucursal_ids",
                return_value={11: "A", 22: "B"},
            ),
            patch(
                "app.routes.marketing_campaign_v2_routes.build_campaign_v2_individual_report",
                side_effect=MarketingCampaignV2NotFoundError("hidden"),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/99/report",
                headers=self.headers,
            )

        assert response.status_code == 404

    def test_individual_report_reuses_campaign_v2_management_permission(self):
        access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=False,
        )
        with self._auth(access):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/report",
                headers=self.headers,
            )

        assert response.status_code == 403

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

    def test_provider_binding_put_accepts_only_identity_and_applies_scope(self):
        expected = {
            "campaign_id": 1,
            "provider": "IVENTAS",
            "provider_campaign_id": "external-1",
            "created": True,
        }
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.bind_campaign_v2_provider",
                return_value=expected,
            ) as service,
        ):
            response = self.client.put(
                "/api/marketing/campaigns-v2/1/provider-binding",
                json={
                    "provider": "IVENTAS",
                    "provider_campaign_id": "external-1",
                },
                headers=self.headers,
            )
        assert response.status_code == 200
        assert response.get_json() == expected
        assert service.call_args.kwargs["campaign_id"] == 1
        assert service.call_args.kwargs["provider"] == "IVENTAS"
        assert service.call_args.kwargs["provider_campaign_id"] == "external-1"
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None

        with self._auth():
            invalid = self.client.put(
                "/api/marketing/campaigns-v2/1/provider-binding",
                json={
                    "provider": "IVENTAS",
                    "provider_campaign_id": "external-1",
                    "stats": {},
                },
                headers=self.headers,
            )
        assert invalid.status_code == 400

    def test_provider_binding_conflict_maps_to_409(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.bind_campaign_v2_provider",
                side_effect=routes.MarketingCampaignV2ProviderBindingConflictError(
                    "conflict"
                ),
            ),
        ):
            response = self.client.put(
                "/api/marketing/campaigns-v2/1/provider-binding",
                json={
                    "provider": "IVENTAS",
                    "provider_campaign_id": "external-1",
                },
                headers=self.headers,
            )
        assert response.status_code == 409

    def test_provider_history_lookup_uses_backend_scope_and_read_only_payload(self):
        expected = {
            "observed_before": "2026-10-01T12:00:00+00:00",
            "phone_count": 1,
            "rows": [
                {
                    "normalized_phone": "mx10:6861111111",
                    "campaign_count": 1,
                }
            ],
        }
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_provider_history_for_phones",
                return_value=expected,
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/provider-history/lookup",
                json={
                    "phones": ["6861111111"],
                    "observed_before": "2026-10-01T12:00:00Z",
                },
                headers=self.headers,
            )
        assert response.status_code == 200
        assert response.get_json() == expected
        assert service.call_args.kwargs["phones"] == ["6861111111"]
        assert (
            service.call_args.kwargs["observed_before"].isoformat()
            == "2026-10-01T12:00:00+00:00"
        )
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None

    def test_provider_history_lookup_rejects_invalid_payload_and_cutoff(self):
        with self._auth():
            unknown = self.client.post(
                "/api/marketing/campaigns-v2/provider-history/lookup",
                json={"phones": ["6861111111"], "provider": "IVENTAS"},
                headers=self.headers,
            )
            invalid_cutoff = self.client.post(
                "/api/marketing/campaigns-v2/provider-history/lookup",
                json={
                    "phones": ["6861111111"],
                    "observed_before": "2026-10-01T12:00:00",
                },
                headers=self.headers,
            )
        assert unknown.status_code == 400
        assert invalid_cutoff.status_code == 400

    def test_provider_history_lookup_validation_error_maps_to_400(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_provider_history_for_phones",
                side_effect=routes.MarketingCampaignV2ProviderHistoryValidationError(
                    "phones admite máximo 100 elementos."
                ),
            ),
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/provider-history/lookup",
                json={"phones": ["6861111111"]},
                headers=self.headers,
            )
        assert response.status_code == 400
        assert "máximo 100" in response.get_json()["message"]

    def test_provider_history_lookup_reuses_campaign_v2_management_permission(self):
        access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=False,
        )
        with self._auth(access):
            response = self.client.post(
                "/api/marketing/campaigns-v2/provider-history/lookup",
                json={"phones": ["6861111111"]},
                headers=self.headers,
            )
        assert response.status_code == 403

    def test_provider_stats_success_uses_backend_scope_only(self):
        expected = {
            "campaign_id": 1,
            "provider": "IVENTAS",
            "provider_campaign_id": "external-1",
            "analytics_status": "ok",
            "raw_counts": {},
            "recipients": {},
            "button_interactions": [],
            "analytics": {},
        }
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_campaign_v2_provider_stats",
                return_value=expected,
            ) as service,
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats",
                headers=self.headers,
            )
        assert response.status_code == 200
        assert response.get_json() == expected
        assert service.call_args.kwargs["campaign_id"] == 1
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None

    def test_provider_stats_rejects_external_id_or_provider_query_override(self):
        with self._auth():
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats"
                "?provider=OTHER&provider_campaign_id=arbitrary",
                headers=self.headers,
            )
        assert response.status_code == 400

    def test_provider_stats_unbound_maps_to_409(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_campaign_v2_provider_stats",
                side_effect=routes.MarketingCampaignV2ProviderStatsUnboundError(
                    "Campaign V2 no tiene provider binding completo."
                ),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats",
                headers=self.headers,
            )
        assert response.status_code == 409

    def test_provider_stats_unsupported_maps_to_422(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_campaign_v2_provider_stats",
                side_effect=routes.MarketingCampaignV2ProviderStatsUnsupportedError(
                    "OTHER"
                ),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats",
                headers=self.headers,
            )
        assert response.status_code == 422
        assert response.get_json()["message"] == "Campaign provider no soportado."

    def test_provider_stats_retryable_upstream_is_sanitized_503(self):
        secret = "provider-secret"
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_campaign_v2_provider_stats",
                side_effect=routes.MarketingCampaignV2ProviderStatsUpstreamError(
                    secret,
                    retryable=True,
                    retry_after_seconds=120.0,
                ),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats",
                headers=self.headers,
            )
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "120"
        assert secret not in response.get_data(as_text=True)
        assert response.get_json()["message"] == (
            "No fue posible obtener stats del provider."
        )

    def test_provider_stats_nonretryable_upstream_is_sanitized_502(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_campaign_v2_provider_stats",
                side_effect=routes.MarketingCampaignV2ProviderStatsUpstreamError(
                    "contract detail",
                    retryable=False,
                ),
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats",
                headers=self.headers,
            )
        assert response.status_code == 502
        assert "contract detail" not in response.get_data(as_text=True)

    def test_provider_stats_reuses_campaign_v2_management_permission(self):
        access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=False,
        )
        with self._auth(access):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats",
                headers=self.headers,
            )
        assert response.status_code == 403

    def test_provider_stats_snapshot_capture_success_and_rejects_payload(self):
        expected = {
            "id": 7,
            "campaign_id": 1,
            "fingerprint": "a" * 64,
            "created": True,
        }
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.capture_campaign_v2_provider_stats_snapshot",
                return_value=expected,
            ) as service,
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/1/provider-stats/snapshots",
                headers=self.headers,
            )
        assert response.status_code == 200
        assert response.get_json() == expected
        assert service.call_args.kwargs["campaign_id"] == 1
        assert service.call_args.kwargs["allowed_sucursal_keys"] is None

        with self._auth():
            invalid = self.client.post(
                "/api/marketing/campaigns-v2/1/provider-stats/snapshots",
                json={"provider_campaign_id": "arbitrary"},
                headers=self.headers,
            )
        assert invalid.status_code == 400

    def test_provider_stats_snapshot_capture_maps_provider_errors(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.capture_campaign_v2_provider_stats_snapshot",
                side_effect=routes.MarketingCampaignV2ProviderStatsUnboundError(
                    "unbound"
                ),
            ),
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/1/provider-stats/snapshots",
                headers=self.headers,
            )
        assert response.status_code == 409

        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.capture_campaign_v2_provider_stats_snapshot",
                side_effect=routes.MarketingCampaignV2ProviderStatsUpstreamError(
                    "secret upstream",
                    retryable=True,
                    retry_after_seconds=30,
                ),
            ),
        ):
            response = self.client.post(
                "/api/marketing/campaigns-v2/1/provider-stats/snapshots",
                headers=self.headers,
            )
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "30"
        assert "secret upstream" not in response.get_data(as_text=True)

    def test_provider_stats_snapshot_history_and_latest_use_scope(self):
        history = {"campaign_id": 1, "rows": [{"id": 2}, {"id": 1}]}
        latest = {"id": 2, "campaign_id": 1}
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.list_campaign_v2_provider_stats_snapshots",
                return_value=history,
            ) as list_service,
            patch(
                "app.routes.marketing_campaign_v2_routes.get_latest_campaign_v2_provider_stats_snapshot",
                return_value=latest,
            ) as latest_service,
        ):
            history_response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats/snapshots",
                headers=self.headers,
            )
            latest_response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats/snapshots/latest",
                headers=self.headers,
            )
        assert history_response.status_code == 200
        assert history_response.get_json() == history
        assert latest_response.status_code == 200
        assert latest_response.get_json() == latest
        assert list_service.call_args.kwargs["allowed_sucursal_keys"] is None
        assert latest_service.call_args.kwargs["allowed_sucursal_keys"] is None

    def test_provider_stats_snapshot_latest_missing_is_404(self):
        with (
            self._auth(),
            patch(
                "app.routes.marketing_campaign_v2_routes.get_latest_campaign_v2_provider_stats_snapshot",
                return_value=None,
            ),
        ):
            response = self.client.get(
                "/api/marketing/campaigns-v2/1/provider-stats/snapshots/latest",
                headers=self.headers,
            )
        assert response.status_code == 404

    def test_provider_stats_snapshot_routes_reuse_management_permission(self):
        access = SimpleNamespace(
            is_global=True,
            branch_ids=(),
            can_edit_inputs=False,
        )
        for method, path in (
            ("post", "/api/marketing/campaigns-v2/1/provider-stats/snapshots"),
            ("get", "/api/marketing/campaigns-v2/1/provider-stats/snapshots"),
            ("get", "/api/marketing/campaigns-v2/1/provider-stats/snapshots/latest"),
        ):
            with self._auth(access):
                response = getattr(self.client, method)(
                    path,
                    headers=self.headers,
                )
            assert response.status_code == 403

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
