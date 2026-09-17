from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.control_center.access import (
    ControlAuthorizationError,
    ControlValidationError,
    resolve_control_access,
    resolve_effective_scope,
)
from app.control_center.retention import build_retention_summary
from app.control_center.sales_composition import (
    SalesCompositionAnalysisError,
    SalesCompositionNotFoundError,
    build_sales_composition_analysis,
    list_sales_composition_snapshots,
)
from app.models.user_model import UserORM
from app.warehouse.services.resumen_ventas_ingestion_service import (
    ResumenVentasIngestionError,
    ingest_resumen_ventas_upload,
)
from app.warehouse.services.warehouse_document_upload_service import (
    WarehouseDocumentUploadError,
    WarehouseDocumentValidationError,
    create_warehouse_document_upload,
)


control_center_bp = Blueprint("control_center", __name__)
BUSINESS_TZ = ZoneInfo("America/Tijuana")


def _get_current_user() -> UserORM:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise ControlAuthorizationError(
            "No autorizado para consultar el Centro de Control."
        ) from exc

    user = UserORM.get_by_id(user_id)
    if user is None:
        raise ControlAuthorizationError("Usuario no encontrado.")
    return user


def _require_admicorp() -> UserORM:
    user = _get_current_user()
    username = str(
        getattr(user, "username", "") or ""
    ).strip().upper()
    if username != "ADMICORP":
        raise ControlAuthorizationError(
            "El Analizador de Composición está habilitado "
            "temporalmente solo para ADMICORP."
        )
    return user


def _parse_cutoff_date():
    raw_value = str(request.args.get("cutoff_date") or "").strip()
    if not raw_value:
        return datetime.now(BUSINESS_TZ).date()

    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ControlValidationError(
            "cutoff_date inválido. Usa YYYY-MM-DD."
        ) from exc


def _resolve_request_context():
    cutoff_date = _parse_cutoff_date()
    user = _get_current_user()
    access = resolve_control_access(
        user,
        as_of_date=cutoff_date,
    )
    effective_scope = resolve_effective_scope(
        access,
        as_of_date=cutoff_date,
        requested_scope_type=request.args.get("scope_type"),
        region_key=request.args.get("region_key"),
        branch_id=request.args.get("branch_id"),
    )
    return cutoff_date, access, effective_scope


def _parse_optional_positive_int(
    value: object,
    *,
    field_name: str,
) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ControlValidationError(
            f"{field_name} inválido."
        ) from exc
    if parsed <= 0:
        raise ControlValidationError(f"{field_name} inválido.")
    return parsed


@control_center_bp.get("/context")
@jwt_required()
def get_control_context():
    try:
        cutoff_date, access, effective_scope = _resolve_request_context()

        return jsonify(
            {
                "status": "ok",
                "contract_version": "control.v1",
                "cutoff_date": cutoff_date.isoformat(),
                "access": access.to_public_dict(),
                "effective_scope": effective_scope.to_public_dict(),
            }
        ), 200
    except ControlAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ControlValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@control_center_bp.get("/retention")
@jwt_required()
def get_control_retention():
    try:
        cutoff_date, _access, effective_scope = _resolve_request_context()
        generation_mode = str(
            request.args.get("generation_mode") or "manual_preview"
        ).strip()
        if generation_mode not in {
            "manual_preview",
            "official_closed_day",
        }:
            raise ControlValidationError("generation_mode inválido.")

        result = build_retention_summary(
            cutoff_date=cutoff_date,
            effective_scope=effective_scope,
            generation_mode=generation_mode,
        )
        result["contract_version"] = "control.retention.v1"
        result["effective_scope"] = effective_scope.to_public_dict()
        return jsonify(result), 200
    except ControlAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ControlValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta de Retención para Control.",
                "detail": str(exc),
            }
        ), 500


@control_center_bp.get("/sales-composition")
@jwt_required()
def get_sales_composition():
    try:
        _require_admicorp()
        snapshot_id = _parse_optional_positive_int(
            request.args.get("snapshot_id"),
            field_name="snapshot_id",
        )
        result = build_sales_composition_analysis(
            snapshot_id=snapshot_id
        )
        return jsonify({"status": "ok", **result}), 200
    except ControlAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ControlValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except SalesCompositionNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except SalesCompositionAnalysisError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló el Analizador de Composición de Venta.",
                "detail": str(exc),
            }
        ), 500


@control_center_bp.get("/sales-composition/snapshots")
@jwt_required()
def get_sales_composition_snapshots():
    try:
        _require_admicorp()
        limit = _parse_optional_positive_int(
            request.args.get("limit"),
            field_name="limit",
        ) or 24
        return jsonify(
            {
                "status": "ok",
                "contract_version": "sales-composition.snapshots.v1",
                "snapshots": list_sales_composition_snapshots(
                    limit=limit
                ),
            }
        ), 200
    except ControlAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except ControlValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta de cortes de Composición de Venta."
                ),
                "detail": str(exc),
            }
        ), 500


@control_center_bp.post("/sales-composition/upload")
@jwt_required()
def upload_sales_composition():
    try:
        user = _require_admicorp()
        uploaded_file = request.files.get("file")
        if uploaded_file is None or not uploaded_file.filename:
            raise ControlValidationError(
                "Debes seleccionar el XLSX exportado por GASCA."
            )

        date_from = str(
            request.form.get("date_from") or ""
        ).strip()
        date_to = str(
            request.form.get("date_to") or ""
        ).strip()
        if not date_from or not date_to:
            raise ControlValidationError(
                "date_from y date_to son requeridos."
            )

        file_bytes = uploaded_file.read()
        upload_result = create_warehouse_document_upload(
            report_type_key="resumen_ventas",
            original_filename=uploaded_file.filename,
            content_type=uploaded_file.mimetype,
            file_bytes=file_bytes,
            uploaded_by_user_id=int(user.id),
            date_from=date_from,
            date_to=date_to,
            audit_details={
                "upload_origin": "sales_composition_analyzer"
            },
        )
        ingestion_result = ingest_resumen_ventas_upload(
            warehouse_upload_id=int(upload_result["upload_id"]),
            requested_by=str(user.id),
            ingestion_source="sales_composition_analyzer",
        )
        analysis = build_sales_composition_analysis(
            snapshot_id=int(ingestion_result["snapshot_id"]),
        )
        return jsonify(
            {
                "status": "ok",
                "message": (
                    "Resumen Ventas cargado y analizado correctamente."
                ),
                "upload": upload_result,
                "ingestion": ingestion_result,
                "analysis": analysis,
            }
        ), 201
    except ControlAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except (
        ControlValidationError,
        WarehouseDocumentValidationError,
        ResumenVentasIngestionError,
        ValueError,
    ) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except WarehouseDocumentUploadError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la carga del Resumen Ventas.",
                "detail": str(exc),
            }
        ), 500
