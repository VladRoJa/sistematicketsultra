from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.marketing_reactivation_outcome import (
    MarketingReactivationCampaignRecipientOutcomeORM,
)
from app.models.user_model import UserORM
from app.services.marketing_access import (
    MarketingAuthorizationError,
    resolve_marketing_access,
)
from app.services.marketing_campaign_audience_service import region_branches
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_reactivation_outcome_service import (
    OUTCOME_PENDING,
    OUTCOME_WINDOW_CLOSED,
    build_marketing_reactivation_campaign_outcome_detail,
    build_marketing_reactivation_outcome_summary,
    run_marketing_reactivation_outcomes,
)
from app.services.marketing_recovery_business_service import (
    enrich_campaign_outcome_detail_with_business_results,
    enrich_outcome_summary_with_business_results,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


marketing_reactivation_outcome_bp = Blueprint(
    "marketing_reactivation_outcomes",
    __name__,
)
_TZ = ZoneInfo("America/Tijuana")


def _current_user_and_access():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise MarketingAuthorizationError("Identidad de usuario inválida.") from exc
    user = UserORM.get_by_id(user_id)
    if user is None:
        raise MarketingAuthorizationError("Usuario no encontrado.")
    return user, resolve_marketing_access(user)


def _allowed_sucursal_keys(access) -> tuple[str, ...] | None:
    if access.is_global:
        return None
    visible_branches, _, _ = load_visible_marketing_branches(access)
    keys = tuple(
        sorted(
            {
                key
                for key in (
                    normalize_socios_vencidos_branch_key(branch.name)
                    for branch in visible_branches
                )
                if key is not None
            }
        )
    )
    if not keys:
        raise MarketingAuthorizationError(
            "No hay sucursales de Reactivación dentro del alcance del usuario."
        )
    return keys


def _optional_region_id() -> int | None:
    raw = request.args.get("region_id")
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("region_id debe ser un entero válido.") from exc
    if value <= 0:
        raise ValueError("region_id debe ser mayor a cero.")
    return value


def _selected_sucursal_keys(
    *,
    allowed_sucursal_keys: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    selected: set[str] | None = None
    region_id = _optional_region_id()
    if region_id is not None:
        rows = region_branches(
            region_id=region_id,
            today=datetime.now(_TZ).date(),
            session=db.session,
        )
        selected = {
            key
            for key in (
                normalize_socios_vencidos_branch_key(row.sucursal)
                for row in rows
            )
            if key is not None
        }

    raw_sucursal = request.args.get("sucursal")
    if raw_sucursal is not None and raw_sucursal.strip():
        branch_key = normalize_socios_vencidos_branch_key(raw_sucursal)
        if branch_key is None:
            raise ValueError("sucursal no contiene un valor válido.")
        selected = (
            {branch_key}
            if selected is None
            else selected.intersection({branch_key})
        )

    if selected is not None and allowed_sucursal_keys is not None:
        allowed = set(allowed_sucursal_keys)
        forbidden = selected - allowed
        if forbidden:
            raise MarketingAuthorizationError(
                "La selección contiene sucursales fuera del alcance del usuario."
            )
        selected = selected.intersection(allowed)

    return tuple(sorted(selected)) if selected is not None else None


def _reopen_closed_outcomes_for_reconciliation() -> int:
    return int(
        db.session.query(MarketingReactivationCampaignRecipientOutcomeORM)
        .filter(
            MarketingReactivationCampaignRecipientOutcomeORM.status
            == OUTCOME_WINDOW_CLOSED
        )
        .update(
            {MarketingReactivationCampaignRecipientOutcomeORM.status: OUTCOME_PENDING},
            synchronize_session=False,
        )
    )


@marketing_reactivation_outcome_bp.get("/reactivation/outcomes/summary")
@jwt_required()
def get_marketing_reactivation_outcomes_summary():
    try:
        _, access = _current_user_and_access()
        allowed = _allowed_sucursal_keys(access)
        selected = _selected_sucursal_keys(allowed_sucursal_keys=allowed)
        result = build_marketing_reactivation_outcome_summary(
            date_from=request.args.get("date_from"),
            date_to=request.args.get("date_to"),
            allowed_sucursal_keys=allowed,
            selected_sucursal_keys=selected,
            session=db.session,
        )
        result = enrich_outcome_summary_with_business_results(
            result,
            allowed_sucursal_keys=allowed,
            selected_sucursal_keys=selected,
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló el resumen de resultados de Reactivación."}
        ), 500


@marketing_reactivation_outcome_bp.get(
    "/reactivation/outcomes/campaigns/<int:campaign_id>"
)
@jwt_required()
def get_marketing_reactivation_campaign_outcomes(campaign_id: int):
    try:
        _, access = _current_user_and_access()
        allowed = _allowed_sucursal_keys(access)
        result = build_marketing_reactivation_campaign_outcome_detail(
            campaign_id=campaign_id,
            allowed_sucursal_keys=allowed,
            session=db.session,
        )
        result = enrich_campaign_outcome_detail_with_business_results(result)
        if allowed is not None and int((result.get("summary") or {}).get("sent") or 0) == 0:
            raise MarketingAuthorizationError(
                "La campaña no contiene destinatarios dentro del alcance del usuario."
            )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló el detalle de resultados de Reactivación."}
        ), 500


@marketing_reactivation_outcome_bp.post("/reactivation/outcomes/run")
@jwt_required()
def run_marketing_reactivation_outcomes_endpoint():
    try:
        _, access = _current_user_and_access()
        if not access.can_edit_inputs or not access.is_global:
            raise MarketingAuthorizationError(
                "La reconciliación global de Reactivación requiere acceso global de edición."
            )
        reopened = _reopen_closed_outcomes_for_reconciliation()
        result = run_marketing_reactivation_outcomes(session=db.session)
        result["reopened_window_closed"] = reopened
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except Exception:
        db.session.rollback()
        return jsonify(
            {"status": "error", "message": "Falló la actualización de resultados de Reactivación."}
        ), 500
