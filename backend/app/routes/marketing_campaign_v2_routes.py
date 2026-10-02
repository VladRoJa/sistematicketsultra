from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.services.marketing_access import (
    MarketingAuthorizationError,
    resolve_marketing_access,
)
from app.services.marketing_branch_scope import marketing_branch_keys_by_sucursal_ids
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_tariff_classifier_service as tariff_classifier
from app.services.marketing_campaign_v2_creation_service import (
    MarketingCampaignV2CreationValidationError,
    MarketingCampaignV2EmptyAudienceError,
    MarketingCampaignV2PersistenceError,
    MarketingCampaignV2PreviewMismatchError,
    build_campaign_v2_freeze_preview,
    freeze_campaign_v2,
)
from app.services.marketing_campaign_v2_query_service import (
    CAMPAIGN_V2_PURPOSES,
    MarketingCampaignV2NotFoundError,
    MarketingCampaignV2QueryValidationError,
    get_campaign_v2,
    get_campaign_v2_recipient,
    list_campaign_v2,
    list_campaign_v2_recipients,
    update_campaign_v2_purpose,
)
from app.services.marketing_campaign_v2_provider_binding_service import (
    MarketingCampaignV2ProviderBindingConflictError,
    MarketingCampaignV2ProviderBindingPersistenceError,
    MarketingCampaignV2ProviderBindingValidationError,
    bind_campaign_v2_provider,
)
from app.services.marketing_campaign_v2_provider_stats_service import (
    MarketingCampaignV2ProviderStatsUnboundError,
    MarketingCampaignV2ProviderStatsUnsupportedError,
    MarketingCampaignV2ProviderStatsUpstreamError,
    get_campaign_v2_provider_stats,
)
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    MarketingCampaignV2ProviderStatsSnapshotPersistenceError,
    capture_campaign_v2_provider_stats_snapshot,
    get_latest_campaign_v2_provider_stats_snapshot,
    list_campaign_v2_provider_stats_snapshots,
)
from app.services.marketing_campaign_v2_provider_history_service import (
    MarketingCampaignV2ProviderHistoryValidationError,
    get_provider_history_for_phones,
)


marketing_campaign_v2_bp = Blueprint("marketing_campaign_v2", __name__)


class MarketingCampaignV2RouteValidationError(ValueError):
    pass


@marketing_campaign_v2_bp.get("/campaigns-v2/options")
@jwt_required()
def campaign_v2_options_endpoint():
    try:
        _, access = _resolve_campaign_v2_request()
        allowed = _campaign_v2_allowed_sucursal_keys(access)
        return jsonify(
            {
                "sources": [
                    audience.SOURCE_EXPIRED_MEMBERS,
                    audience.SOURCE_ACTIVE_MEMBERS,
                    audience.SOURCE_FUNNEL_PORTFOLIO,
                ],
                "source_filters": {
                    audience.SOURCE_FUNNEL_PORTFOLIO: {
                        "required": [
                            "funnel_month",
                            "funnel_cutoff_date",
                        ],
                        "not_applicable": [
                            "audience_families",
                            "expiration_date_from",
                            "expiration_date_to",
                            "tarifa",
                            "categoria_tarifa",
                        ],
                        "cutoff_policy": "EXACT_COMPLETE",
                    }
                },
                "selectable_audience_families": list(
                    audience.SELECTABLE_AUDIENCE_FAMILIES
                ),
                "non_selectable_classifications": [
                    "MES",
                    "OUT_OF_SEGMENT",
                    "UNCLASSIFIED",
                ],
                "purposes": list(CAMPAIGN_V2_PURPOSES),
                "tariff_categories": list(
                    tariff_classifier.list_canonical_tariff_categories(
                        session=db.session,
                    )
                ),
                "scope": {
                    "is_global": bool(access.is_global),
                    "allowed_sucursal_keys": (
                        list(allowed) if allowed is not None else None
                    ),
                },
            }
        ), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except Exception:
        return _error("Falló la consulta de opciones de Campaign V2.", 500)


@marketing_campaign_v2_bp.post("/campaigns-v2/preview")
@jwt_required()
def campaign_v2_preview_endpoint():
    try:
        _, access = _resolve_campaign_v2_request()
        payload = _parse_payload(
            {
                "source",
                "audience_families",
                "expiration_date_from",
                "expiration_date_to",
                "history_exclusion",
                "funnel_month",
                "funnel_cutoff_date",
            }
        )
        result = build_campaign_v2_freeze_preview(
            source=payload.get("source"),
            audience_families=payload.get("audience_families"),
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            expiration_date_from=payload.get("expiration_date_from"),
            expiration_date_to=payload.get("expiration_date_to"),
            history_exclusion=payload.get("history_exclusion"),
            funnel_month=payload.get("funnel_month"),
            funnel_cutoff_date=payload.get("funnel_cutoff_date"),
            marketing_access=access,
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except (MarketingCampaignV2RouteValidationError, MarketingCampaignV2CreationValidationError) as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló el Preview de Campaign V2.", 500)

@marketing_campaign_v2_bp.post("/campaigns-v2/preview-detail")
@jwt_required()
def campaign_v2_preview_detail_endpoint():
    try:
        _, access = _resolve_campaign_v2_request()
        payload = _parse_payload(
            {
                "source",
                "audience_families",
                "expiration_date_from",
                "expiration_date_to",
                "bucket",
                "audience_family",
                "page",
                "page_size",
                "history_exclusion",
                "funnel_month",
                "funnel_cutoff_date",
            }
        )
        result = audience.build_campaign_v2_audience_preview_detail(
            source=payload.get("source"),
            audience_families=payload.get("audience_families"),
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            bucket=payload.get("bucket"),
            audience_family=payload.get("audience_family"),
            page=payload.get("page", 1),
            page_size=payload.get("page_size", 50),
            expiration_date_from=payload.get("expiration_date_from"),
            expiration_date_to=payload.get("expiration_date_to"),
            history_exclusion=payload.get("history_exclusion"),
            funnel_month=payload.get("funnel_month"),
            funnel_cutoff_date=payload.get("funnel_cutoff_date"),
            marketing_access=access,
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except (MarketingCampaignV2RouteValidationError, audience.MarketingCampaignV2AudienceValidationError) as exc:
        return _error(str(exc), 400)
    except RuntimeError:
        return _error("El detalle ya no coincide con el Preview de Campaign V2.", 409)
    except Exception:
        return _error("Falló el detalle del Preview de Campaign V2.", 500)

@marketing_campaign_v2_bp.post("/campaigns-v2")
@jwt_required()
def freeze_campaign_v2_endpoint():
    try:
        user, access = _resolve_campaign_v2_request()
        payload = _parse_payload(
            {
                "name",
                "purpose",
                "source",
                "audience_families",
                "expiration_date_from",
                "expiration_date_to",
                "history_exclusion",
                "funnel_month",
                "funnel_cutoff_date",
                "expected_preview_fingerprint",
            }
        )
        result = freeze_campaign_v2(
            name=payload.get("name"),
            purpose=payload.get("purpose"),
            source=payload.get("source"),
            audience_families=payload.get("audience_families"),
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            expected_preview_fingerprint=payload.get("expected_preview_fingerprint"),
            created_by_user_id=int(user.id),
            expiration_date_from=payload.get("expiration_date_from"),
            expiration_date_to=payload.get("expiration_date_to"),
            history_exclusion=payload.get("history_exclusion"),
            funnel_month=payload.get("funnel_month"),
            funnel_cutoff_date=payload.get("funnel_cutoff_date"),
            marketing_access=access,
            session=db.session,
        )
        return jsonify(result), 201
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except (MarketingCampaignV2RouteValidationError, MarketingCampaignV2CreationValidationError) as exc:
        return _error(str(exc), 400)
    except (MarketingCampaignV2PreviewMismatchError, MarketingCampaignV2EmptyAudienceError) as exc:
        return _error(str(exc), 409)
    except MarketingCampaignV2PersistenceError:
        return _error("No fue posible congelar Campaign V2.", 500)
    except Exception:
        return _error("Falló la creación de Campaign V2.", 500)

@marketing_campaign_v2_bp.get("/campaigns-v2/tariffs/unclassified")
@jwt_required()
def list_campaign_v2_unclassified_tariffs_endpoint():
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args(
            {
                "source",
                "expiration_date_from",
                "expiration_date_to",
            }
        )
        result = tariff_classifier.list_unclassified_tariffs(
            source=request.args.get("source"),
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            expiration_date_from=request.args.get("expiration_date_from"),
            expiration_date_to=request.args.get("expiration_date_to"),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except (
        MarketingCampaignV2RouteValidationError,
        audience.MarketingCampaignV2AudienceValidationError,
        tariff_classifier.MarketingCampaignV2TariffClassifierValidationError,
    ) as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la consulta de tarifas sin clasificación.", 500)


@marketing_campaign_v2_bp.put(
    "/campaigns-v2/tariffs/<path:tarifa_key>/classification"
)
@jwt_required()
def classify_campaign_v2_tariff_endpoint(tarifa_key: str):
    try:
        user, access = _resolve_campaign_v2_request()
        _validate_query_args(
            {
                "source",
                "expiration_date_from",
                "expiration_date_to",
            }
        )
        payload = _parse_payload({"categoria_tarifa", "audience_family"})
        source = request.args.get("source")
        date_from = request.args.get("expiration_date_from")
        date_to = request.args.get("expiration_date_to")
        if source is None and (date_from is not None or date_to is not None):
            raise MarketingCampaignV2RouteValidationError(
                "source es obligatorio cuando se envía rango de vencimiento."
            )

        representative_raw = None
        if source is not None:
            representative_raw = tariff_classifier.stable_representative_for_key(
                tarifa_key=tarifa_key,
                source=source,
                allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
                expiration_date_from=date_from,
                expiration_date_to=date_to,
                session=db.session,
            )

        result = tariff_classifier.upsert_tariff_classification(
            tarifa_key=tarifa_key,
            categoria_tarifa=payload.get("categoria_tarifa"),
            audience_family=payload.get("audience_family"),
            user_id=int(user.id),
            representative_raw=representative_raw,
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except (
        MarketingCampaignV2RouteValidationError,
        audience.MarketingCampaignV2AudienceValidationError,
        tariff_classifier.MarketingCampaignV2TariffClassifierValidationError,
    ) as exc:
        return _error(str(exc), 400)
    except tariff_classifier.MarketingCampaignV2TariffClassifierPersistenceError:
        return _error("No fue posible guardar la clasificación de tarifa.", 500)
    except Exception:
        return _error("Falló la clasificación de tarifa Campaign V2.", 500)


@marketing_campaign_v2_bp.get("/campaigns-v2")
@jwt_required()
def list_campaign_v2_endpoint():
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args({"page", "page_size", "purpose", "source"})
        result = list_campaign_v2(
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 50),
            purpose=request.args.get("purpose"),
            source=request.args.get("source"),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except (MarketingCampaignV2RouteValidationError, MarketingCampaignV2QueryValidationError) as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la consulta de Campaign V2.", 500)


@marketing_campaign_v2_bp.post(
    "/campaigns-v2/provider-history/lookup"
)
@jwt_required()
def lookup_campaign_v2_provider_history_endpoint():
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args(set())
        payload = _parse_payload({"phones", "observed_before"})
        observed_before = _parse_optional_iso_datetime(
            payload.get("observed_before")
        )
        result = get_provider_history_for_phones(
            phones=payload.get("phones"),
            observed_before=observed_before,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except (
        MarketingCampaignV2RouteValidationError,
        MarketingCampaignV2ProviderHistoryValidationError,
    ) as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error(
            "Falló la consulta histórica provider de Campaign V2.",
            500,
        )


@marketing_campaign_v2_bp.get("/campaigns-v2/<int:campaign_id>")
@jwt_required()
def get_campaign_v2_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        result = get_campaign_v2(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except MarketingCampaignV2QueryValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la consulta de Campaign V2.", 500)


@marketing_campaign_v2_bp.get(
    "/campaigns-v2/<int:campaign_id>/provider-stats"
)
@jwt_required()
def get_campaign_v2_provider_stats_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args(set())
        result = get_campaign_v2_provider_stats(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except MarketingCampaignV2RouteValidationError as exc:
        return _error(str(exc), 400)
    except MarketingCampaignV2ProviderStatsUnboundError as exc:
        return _error(str(exc), 409)
    except MarketingCampaignV2ProviderStatsUnsupportedError:
        return _error("Campaign provider no soportado.", 422)
    except MarketingCampaignV2ProviderStatsUpstreamError as exc:
        return _provider_stats_upstream_response(exc)
    except Exception:
        return _error(
            "Falló la consulta de provider stats de Campaign V2.",
            500,
        )


@marketing_campaign_v2_bp.post(
    "/campaigns-v2/<int:campaign_id>/provider-stats/snapshots"
)
@jwt_required()
def capture_campaign_v2_provider_stats_snapshot_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args(set())
        payload = request.get_json(silent=True)
        if payload not in (None, {}):
            raise MarketingCampaignV2RouteValidationError(
                "La captura de provider stats no acepta payload."
            )
        result = capture_campaign_v2_provider_stats_snapshot(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except MarketingCampaignV2RouteValidationError as exc:
        return _error(str(exc), 400)
    except MarketingCampaignV2ProviderStatsUnboundError as exc:
        return _error(str(exc), 409)
    except MarketingCampaignV2ProviderStatsUnsupportedError:
        return _error("Campaign provider no soportado.", 422)
    except MarketingCampaignV2ProviderStatsUpstreamError as exc:
        return _provider_stats_upstream_response(exc)
    except MarketingCampaignV2ProviderStatsSnapshotPersistenceError:
        return _error("No fue posible persistir provider stats.", 500)
    except Exception:
        return _error("Falló la captura de provider stats.", 500)


@marketing_campaign_v2_bp.get(
    "/campaigns-v2/<int:campaign_id>/provider-stats/snapshots"
)
@jwt_required()
def list_campaign_v2_provider_stats_snapshots_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args(set())
        result = list_campaign_v2_provider_stats_snapshots(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except MarketingCampaignV2RouteValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la consulta de snapshots provider stats.", 500)


@marketing_campaign_v2_bp.get(
    "/campaigns-v2/<int:campaign_id>/provider-stats/snapshots/latest"
)
@jwt_required()
def latest_campaign_v2_provider_stats_snapshot_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args(set())
        result = get_latest_campaign_v2_provider_stats_snapshot(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        if result is None:
            return _error("No hay snapshots provider stats.", 404)
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except MarketingCampaignV2RouteValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la consulta del último snapshot provider stats.", 500)


@marketing_campaign_v2_bp.get("/campaigns-v2/<int:campaign_id>/recipients")
@jwt_required()
def list_campaign_v2_recipients_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        _validate_query_args({"page", "page_size"})
        result = list_campaign_v2_recipients(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 50),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except (MarketingCampaignV2RouteValidationError, MarketingCampaignV2QueryValidationError) as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la consulta de recipients de Campaign V2.", 500)


@marketing_campaign_v2_bp.get(
    "/campaigns-v2/<int:campaign_id>/recipients/<int:recipient_id>"
)
@jwt_required()
def get_campaign_v2_recipient_endpoint(campaign_id: int, recipient_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        result = get_campaign_v2_recipient(
            campaign_id=campaign_id,
            recipient_id=recipient_id,
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Recipient V2 no encontrado.", 404)
    except MarketingCampaignV2QueryValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la consulta del recipient de Campaign V2.", 500)


@marketing_campaign_v2_bp.patch("/campaigns-v2/<int:campaign_id>/purpose")
@jwt_required()
def update_campaign_v2_purpose_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        payload = _parse_payload({"purpose"})
        result = update_campaign_v2_purpose(
            campaign_id=campaign_id,
            purpose=payload.get("purpose"),
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except (MarketingCampaignV2RouteValidationError, MarketingCampaignV2QueryValidationError) as exc:
        return _error(str(exc), 400)
    except Exception:
        return _error("Falló la actualización de purpose de Campaign V2.", 500)


@marketing_campaign_v2_bp.put(
    "/campaigns-v2/<int:campaign_id>/provider-binding"
)
@jwt_required()
def bind_campaign_v2_provider_endpoint(campaign_id: int):
    try:
        _, access = _resolve_campaign_v2_request()
        payload = _parse_payload(
            {"provider", "provider_campaign_id"}
        )
        result = bind_campaign_v2_provider(
            campaign_id=campaign_id,
            provider=payload.get("provider"),
            provider_campaign_id=payload.get("provider_campaign_id"),
            allowed_sucursal_keys=_campaign_v2_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return _error(str(exc), 403)
    except MarketingCampaignV2NotFoundError:
        return _error("Campaign V2 no encontrada.", 404)
    except (
        MarketingCampaignV2RouteValidationError,
        MarketingCampaignV2ProviderBindingValidationError,
    ) as exc:
        return _error(str(exc), 400)
    except MarketingCampaignV2ProviderBindingConflictError as exc:
        return _error(str(exc), 409)
    except MarketingCampaignV2ProviderBindingPersistenceError:
        return _error("No fue posible guardar el provider binding.", 500)
    except Exception:
        return _error("Falló el provider binding de Campaign V2.", 500)


def _get_current_campaign_v2_user() -> UserORM:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise MarketingAuthorizationError(
            "Identidad de usuario inválida."
        ) from exc
    user = UserORM.get_by_id(user_id)
    if user is None:
        raise MarketingAuthorizationError("Usuario no encontrado.")
    return user


def _resolve_request_access():
    user = _get_current_campaign_v2_user()
    return user, resolve_marketing_access(user)


def _resolve_campaign_v2_request():
    user, access = _resolve_request_access()
    _require_campaign_v2_management(access)
    return user, access


def _require_campaign_v2_management(access) -> None:
    if not getattr(access, "can_edit_inputs", False):
        raise MarketingAuthorizationError(
            "No autorizado para gestionar Campaign V2."
        )


def _campaign_v2_allowed_sucursal_keys(access) -> tuple[str, ...] | None:
    if access.is_global:
        return None
    mapping = marketing_branch_keys_by_sucursal_ids(
        sucursal_ids=access.branch_ids,
        session=db.session,
    )
    keys = tuple(sorted(set(mapping.values())))
    if not keys:
        raise MarketingAuthorizationError(
            "No hay sucursales Campaign V2 dentro del alcance del usuario."
        )
    return keys


def _parse_payload(allowed_fields: set[str]) -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise MarketingCampaignV2RouteValidationError(
            "El payload JSON debe ser un objeto."
        )
    unknown = sorted(set(payload) - allowed_fields)
    if unknown:
        raise MarketingCampaignV2RouteValidationError(
            "Campos no permitidos: " + ", ".join(unknown) + "."
        )
    return payload


def _validate_query_args(allowed_fields: set[str]) -> None:
    unknown = sorted(set(request.args.keys()) - allowed_fields)
    if unknown:
        raise MarketingCampaignV2RouteValidationError(
            "Parámetros no permitidos: " + ", ".join(unknown) + "."
        )


def _parse_optional_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MarketingCampaignV2RouteValidationError(
            "observed_before debe ser fecha ISO con zona horaria."
        )
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MarketingCampaignV2RouteValidationError(
            "observed_before debe ser fecha ISO con zona horaria."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketingCampaignV2RouteValidationError(
            "observed_before debe incluir zona horaria."
        )
    return parsed


def _provider_stats_upstream_response(
    exc: MarketingCampaignV2ProviderStatsUpstreamError,
):
    status = 503 if exc.retryable else 502
    response = jsonify(
        {
            "status": "error",
            "message": "No fue posible obtener stats del provider.",
        }
    )
    if exc.retry_after_seconds is not None:
        response.headers["Retry-After"] = str(
            max(0, int(exc.retry_after_seconds))
        )
    return response, status


def _error(message: str, status: int):
    return jsonify({"status": "error", "message": message}), status
