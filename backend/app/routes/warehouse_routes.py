# app/routes/warehouse_routes.py

from flask import Blueprint, jsonify, request, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from pathlib import Path
from datetime import datetime, date, time, timedelta
from werkzeug.utils import secure_filename
import hashlib
import uuid
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.warehouse import WarehouseUploadORM
from app.utils.warehouse_access import (
    require_warehouse_archive,
    require_warehouse_catalogs,
    require_warehouse_operator,
    require_warehouse_upload,
    require_warehouse_view,
)
from app.models import (
    WarehouseSourceORM,
    WarehouseFamilyORM,
    WarehouseOperationalRoleORM,
    WarehouseReportTypeORM,
    WarehouseUploadORM,
    WarehouseAuditLogORM,
)
from app.utils.warehouse_audit import log_warehouse_audit
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
    _build_upload_display_filename,
    WarehouseDocumentUploadError,
    WarehouseDocumentValidationError,
)
from app.warehouse.services.warehouse_manual_ingestion_dispatcher import (
    WarehouseManualIngestionDispatcherError,
)



warehouse_bp = Blueprint('warehouse', __name__)


ALLOWED_WAREHOUSE_EXTENSIONS = {
    "xlsx",
    "xls",
    "csv",
    "pdf",
    "txt",
    "docx",
    "pptx",
    "png",
    "jpg",
    "jpeg",
}
MAX_WAREHOUSE_FILE_SIZE_BYTES = 70 * 1024 * 1024
WAREHOUSE_LOCAL_TZ = ZoneInfo("America/Tijuana")

def _get_current_user_id() -> int | None:
    current_user_id = get_jwt_identity()
    if current_user_id is None:
        return None

    try:
        return int(current_user_id)
    except (TypeError, ValueError):
        return None


def _calculate_file_sha256(uploaded_file) -> str:
    hasher = hashlib.sha256()

    uploaded_file.stream.seek(0)
    while True:
        chunk = uploaded_file.stream.read(8192)
        if not chunk:
            break
        hasher.update(chunk)

    uploaded_file.stream.seek(0)
    return hasher.hexdigest()


def _build_warehouse_storage_paths(source_key: str, report_type_key: str, anchor_date, stored_filename: str):
    year = anchor_date.strftime('%Y')
    month = anchor_date.strftime('%m')

    relative_dir = Path('uploads') / 'warehouse' / source_key / report_type_key / year / month
    absolute_dir = (Path(current_app.root_path).parent.parent / relative_dir).resolve()
    absolute_dir.mkdir(parents=True, exist_ok=True)

    absolute_file_path = absolute_dir / stored_filename
    return relative_dir, absolute_file_path


@warehouse_bp.route('/access', methods=['GET'])
@jwt_required()
def warehouse_access():
    forbidden = require_warehouse_operator()
    if forbidden:
        return forbidden

    return jsonify({
        "allowed": True,
        "module": "warehouse"
    }), 200
    
    
@warehouse_bp.route('/catalogs', methods=['GET'])
@jwt_required()
def warehouse_catalogs():
    forbidden = require_warehouse_catalogs()
    if forbidden:
        return forbidden

    sources = WarehouseSourceORM.query.filter_by(active=True).order_by(WarehouseSourceORM.key.asc()).all()
    families = WarehouseFamilyORM.query.filter_by(active=True).order_by(WarehouseFamilyORM.key.asc()).all()
    operational_roles = (
        WarehouseOperationalRoleORM.query
        .filter_by(active=True)
        .order_by(WarehouseOperationalRoleORM.key.asc())
        .all()
    )
    report_types = (
        WarehouseReportTypeORM.query
        .filter_by(active=True)
        .order_by(WarehouseReportTypeORM.key.asc())
        .all()
    )

    return jsonify({
        "sources": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
            }
            for item in sources
        ],
        "families": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
            }
            for item in families
        ],
        "operational_roles": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
            }
            for item in operational_roles
        ],
        "report_types": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
                "family_id": item.family_id,
                "default_source_id": item.default_source_id,
                "default_operational_role_id": item.default_operational_role_id,
                "default_period_type": item.default_period_type,
            }
            for item in report_types
        ],
    }), 200
    
    
@warehouse_bp.route('/uploads', methods=['POST'])
@jwt_required()
def warehouse_create_upload():
    forbidden = require_warehouse_upload()
    if forbidden:
        return forbidden

    if 'file' not in request.files:
        return jsonify({
            "error": "Archivo requerido",
            "detail": "Debes enviar un archivo en el campo 'file'."
        }), 400

    uploaded_file = request.files['file']

    if not uploaded_file or not uploaded_file.filename:
        return jsonify({
            "error": "Archivo inválido",
            "detail": "El archivo enviado no tiene nombre válido."
        }), 400

    current_user_id = _get_current_user_id()
    if not current_user_id:
        return jsonify({
            "error": "Sesión inválida",
            "detail": "No se pudo resolver el usuario autenticado actual."
        }), 401

    report_type_key = (request.form.get('report_type_key') or '').strip()
    cutoff_date_raw = (request.form.get('cutoff_date') or '').strip()
    date_from_raw = (request.form.get('date_from') or '').strip()
    date_to_raw = (request.form.get('date_to') or '').strip()
    target_month_raw = (request.form.get('target_month') or '').strip()

    manual_ingestion_result = {
        "ingestion_status": "not_applicable",
        "metadata": {
            "reason": "manual_structured_ingestion_not_attempted",
        },
    }

    result = None

    try:
        file_bytes = uploaded_file.read()

        result = create_warehouse_document_upload(
            report_type_key=report_type_key,
            original_filename=uploaded_file.filename,
            content_type=uploaded_file.mimetype,
            file_bytes=file_bytes,
            uploaded_by_user_id=current_user_id,
            cutoff_date=cutoff_date_raw or None,
            date_from=date_from_raw or None,
            date_to=date_to_raw or None,
            target_month=target_month_raw or None,
            audit_details={
                "upload_origin": "manual_route",
            },
        )

        manual_dispatcher = current_app.config.get(
            "WAREHOUSE_MANUAL_INGESTION_DISPATCHER"
        )
        if callable(manual_dispatcher):
            manual_ingestion_result = manual_dispatcher(
                warehouse_upload_id=result["upload_id"],
                requested_by=str(current_user_id),
                ingestion_source="manual_route",
            )

    except WarehouseDocumentValidationError as exc:
        return jsonify({
            "error": "No se pudo crear el upload",
            "detail": str(exc),
        }), 400

    except WarehouseDocumentUploadError as exc:
        current_app.logger.exception(
            "Error controlado creando upload documental de Warehouse."
        )
        return jsonify({
            "error": "No se pudo crear el upload",
            "detail": str(exc),
        }), 500

    except WarehouseManualIngestionDispatcherError as exc:
        current_app.logger.exception(
            "Error controlado disparando ingesta estructurada manual de Warehouse."
        )

        if result is None:
            return jsonify({
                "error": "No se pudo crear el upload",
                "detail": str(exc),
            }), 500

        manual_ingestion_result = {
            "ingestion_status": "failed",
            "error": "Upload creado pero falló la ingesta estructurada",
            "detail": str(exc),
        }

        return jsonify({
            "message": "Upload creado correctamente",
            "upload_id": result["upload_id"],
            "filename": result["filename"],
            "stored_filename": result["stored_filename"],
            "display_filename": result["display_filename"],
            "stored_path": result["stored_path"],
            "file_size_bytes": result["file_size_bytes"],
            "file_hash_sha256": result["file_hash_sha256"],
            "report_type_key": result["report_type_key"],
            "report_type_id": result["report_type_id"],
            "family_id": result["family_id"],
            "source_id": result["source_id"],
            "operational_role_id": result["operational_role_id"],
            "period_type": result["period_type"],
            "cutoff_date": result["cutoff_date"],
            "date_from": result["date_from"],
            "date_to": result["date_to"],
            "duplicate_detected": result["duplicate_detected"],
            "duplicate_upload_id": result["duplicate_upload_id"],
            "manual_ingestion_status": manual_ingestion_result.get("ingestion_status"),
            "manual_structured_result": manual_ingestion_result,
        }), 201

    except Exception:
        current_app.logger.exception(
            "Error inesperado creando upload documental de Warehouse."
        )
        return jsonify({
            "error": "No se pudo crear el upload",
            "detail": "Ocurrió un error al guardar el archivo y registrar el upload en Warehouse."
        }), 500

    return jsonify({
        "message": "Upload creado correctamente",
        "upload_id": result["upload_id"],
        "filename": result["filename"],
        "stored_filename": result["stored_filename"],
        "stored_path": result["stored_path"],
        "file_size_bytes": result["file_size_bytes"],
        "file_hash_sha256": result["file_hash_sha256"],
        "report_type_key": result["report_type_key"],
        "report_type_id": result["report_type_id"],
        "family_id": result["family_id"],
        "source_id": result["source_id"],
        "operational_role_id": result["operational_role_id"],
        "period_type": result["period_type"],
        "cutoff_date": result["cutoff_date"],
        "date_from": result["date_from"],
        "date_to": result["date_to"],
        "duplicate_detected": result["duplicate_detected"],
        "duplicate_upload_id": result["duplicate_upload_id"],
        "manual_ingestion_status": manual_ingestion_result.get("ingestion_status"),
        "manual_structured_result": manual_ingestion_result,
    }), 201
        
def _parse_positive_int(raw_value, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default

    value = max(value, minimum)

    if maximum is not None:
        value = min(value, maximum)

    return value


def _parse_iso_date(raw_value: str | None) -> date | None:
    value = (raw_value or '').strip()

    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _build_upload_created_at_range(date_preset: str, date_from_raw: str | None, date_to_raw: str | None):
    today = datetime.now(WAREHOUSE_LOCAL_TZ).date()
    normalized_preset = (date_preset or 'today').strip().lower()

    if normalized_preset == 'all':
        return None, None

    if normalized_preset == 'yesterday':
        start_day = today - timedelta(days=1)
        end_day = start_day
    elif normalized_preset == 'last_7_days':
        start_day = today - timedelta(days=6)
        end_day = today
    elif normalized_preset == 'current_month':
        start_day = today.replace(day=1)
        end_day = today
    elif normalized_preset == 'custom':
        start_day = _parse_iso_date(date_from_raw)
        end_day = _parse_iso_date(date_to_raw)

        if start_day is None and end_day is None:
            return None, None

        if start_day is None:
            start_day = end_day

        if end_day is None:
            end_day = start_day
    else:
        start_day = today
        end_day = today

    if end_day < start_day:
        start_day, end_day = end_day, start_day

    start_dt = datetime.combine(start_day, time.min, tzinfo=WAREHOUSE_LOCAL_TZ)
    end_dt = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=WAREHOUSE_LOCAL_TZ)

    return start_dt, end_dt

def _serialize_warehouse_upload_item(item: WarehouseUploadORM) -> dict:
    return {
        "id": item.id,
        "original_filename": item.original_filename,
        "stored_filename": item.stored_filename,
        "display_filename": _build_upload_display_filename(
            report_type_key=item.report_type.key if item.report_type else "",
            period_type=item.period_type,
            cutoff_date=item.cutoff_date,
            date_from=item.date_from,
            date_to=item.date_to,
            original_filename=item.original_filename,
        ),
        "stored_path": item.stored_path,
        "file_size_bytes": item.file_size_bytes,
        "file_hash_sha256": item.file_hash_sha256,
        "mime_type": item.mime_type,
        "extension": item.extension,

        "report_type_id": item.report_type_id,
        "report_type_key": item.report_type.key if item.report_type else None,
        "report_type_label": item.report_type.label if item.report_type else None,

        "source_id": item.source_id,
        "source_key": item.source.key if item.source else None,
        "source_label": item.source.label if item.source else None,

        "family_id": item.family_id,
        "family_key": item.family.key if item.family else None,
        "family_label": item.family.label if item.family else None,

        "operational_role_id": item.operational_role_id,
        "operational_role_key": item.operational_role.key if item.operational_role else None,
        "operational_role_label": item.operational_role.label if item.operational_role else None,

        "period_type": item.period_type,
        "cutoff_date": item.cutoff_date.isoformat() if item.cutoff_date else None,
        "date_from": item.date_from.isoformat() if item.date_from else None,
        "date_to": item.date_to.isoformat() if item.date_to else None,

        "status": item.status,
        "uploaded_by_user_id": item.uploaded_by_user_id,
        "uploaded_by_username": item.uploader.username if item.uploader else None,

        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }        

@warehouse_bp.route('/uploads', methods=['GET'])
@jwt_required()
def warehouse_list_uploads():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    source_key = (request.args.get('source_key') or '').strip()
    report_type_key = (request.args.get('report_type_key') or '').strip()
    status = (request.args.get('status') or 'ALL').strip().upper()
    period_type = (request.args.get('period_type') or '').strip()

    date_preset = (request.args.get('date_preset') or 'today').strip()
    date_from_raw = (request.args.get('date_from') or '').strip()
    date_to_raw = (request.args.get('date_to') or '').strip()
    search = (request.args.get('search') or '').strip()

    page = _parse_positive_int(request.args.get('page'), default=1, minimum=1)
    page_size = _parse_positive_int(
        request.args.get('page_size'),
        default=25,
        minimum=1,
        maximum=100,
    )

    query = (
        WarehouseUploadORM.query
        .options(
            joinedload(WarehouseUploadORM.report_type),
            joinedload(WarehouseUploadORM.source),
            joinedload(WarehouseUploadORM.family),
            joinedload(WarehouseUploadORM.operational_role),
            joinedload(WarehouseUploadORM.uploader),
        )
    )

    if source_key:
        query = query.filter(WarehouseUploadORM.source.has(key=source_key))

    if report_type_key:
        query = query.filter(WarehouseUploadORM.report_type.has(key=report_type_key))

    if status and status != 'ALL':
        query = query.filter(WarehouseUploadORM.status == status)

    if period_type:
        query = query.filter(WarehouseUploadORM.period_type == period_type)

    start_dt, end_dt = _build_upload_created_at_range(
        date_preset=date_preset,
        date_from_raw=date_from_raw,
        date_to_raw=date_to_raw,
    )

    if start_dt is not None:
        query = query.filter(WarehouseUploadORM.created_at >= start_dt)

    if end_dt is not None:
        query = query.filter(WarehouseUploadORM.created_at < end_dt)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                WarehouseUploadORM.original_filename.ilike(search_pattern),
                WarehouseUploadORM.stored_filename.ilike(search_pattern),
            )
        )

    query = query.order_by(WarehouseUploadORM.created_at.desc())

    pagination = query.paginate(
        page=page,
        per_page=page_size,
        error_out=False,
    )

    return jsonify({
        "items": [
            _serialize_warehouse_upload_item(item)
            for item in pagination.items
        ],
        "page": pagination.page,
        "page_size": pagination.per_page,
        "total": pagination.total,
        "total_pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
        "filters": {
            "source_key": source_key or None,
            "report_type_key": report_type_key or None,
            "status": status,
            "period_type": period_type or None,
            "date_preset": date_preset,
            "date_from": date_from_raw or None,
            "date_to": date_to_raw or None,
            "search": search or None,
        }
    }), 200   
@warehouse_bp.route('/uploads/<int:upload_id>', methods=['GET'])
@jwt_required()
def warehouse_get_upload_detail(upload_id: int):
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    upload = (
        WarehouseUploadORM.query
        .options(
            joinedload(WarehouseUploadORM.report_type),
            joinedload(WarehouseUploadORM.source),
            joinedload(WarehouseUploadORM.family),
            joinedload(WarehouseUploadORM.operational_role),
            joinedload(WarehouseUploadORM.uploader),
        )
        .filter_by(id=upload_id)
        .first()
    )

    if not upload:
        return jsonify({
            "error": "Upload no encontrado",
            "detail": f"No existe un upload de Warehouse con id {upload_id}."
        }), 404

    return jsonify({
        "id": upload.id,
        "original_filename": upload.original_filename,
        "stored_filename": upload.stored_filename,
        "stored_path": upload.stored_path,
        "file_size_bytes": upload.file_size_bytes,
        "file_hash_sha256": upload.file_hash_sha256,
        "mime_type": upload.mime_type,
        "extension": upload.extension,

        "report_type_id": upload.report_type_id,
        "report_type_key": upload.report_type.key if upload.report_type else None,
        "report_type_label": upload.report_type.label if upload.report_type else None,

        "source_id": upload.source_id,
        "source_key": upload.source.key if upload.source else None,
        "source_label": upload.source.label if upload.source else None,

        "family_id": upload.family_id,
        "family_key": upload.family.key if upload.family else None,
        "family_label": upload.family.label if upload.family else None,

        "operational_role_id": upload.operational_role_id,
        "operational_role_key": upload.operational_role.key if upload.operational_role else None,
        "operational_role_label": upload.operational_role.label if upload.operational_role else None,

        "period_type": upload.period_type,
        "cutoff_date": upload.cutoff_date.isoformat() if upload.cutoff_date else None,
        "date_from": upload.date_from.isoformat() if upload.date_from else None,
        "date_to": upload.date_to.isoformat() if upload.date_to else None,

        "status": upload.status,
        "uploaded_by_user_id": upload.uploaded_by_user_id,
        "uploaded_by_username": upload.uploader.username if upload.uploader else None,

        "created_at": upload.created_at.isoformat() if upload.created_at else None,
        "updated_at": upload.updated_at.isoformat() if upload.updated_at else None,
    }), 200
    
    
@warehouse_bp.route('/uploads/<int:upload_id>/download', methods=['GET'])
@jwt_required()
def warehouse_download_upload(upload_id: int):
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    upload = (
        WarehouseUploadORM.query
        .options(joinedload(WarehouseUploadORM.report_type))
        .filter_by(id=upload_id)
        .first()
    )

    if not upload:
        return jsonify({
            "error": "Upload no encontrado",
            "detail": f"No existe un upload de Warehouse con id {upload_id}."
        }), 404

    base_dir = Path(current_app.root_path).parent.parent
    file_path = (base_dir / upload.stored_path / upload.stored_filename).resolve()

    if not file_path.exists() or not file_path.is_file():
        return jsonify({
            "error": "Archivo no encontrado",
            "detail": f"No se encontró el archivo físico para el upload {upload_id}."
        }), 404

    current_user_id = _get_current_user_id()
    if not current_user_id:
        return jsonify({
            "error": "Sesión inválida",
            "detail": "No se pudo resolver el usuario autenticado actual."
        }), 401

    log_warehouse_audit(
        action='DOWNLOAD',
        performed_by_user_id=current_user_id,
        upload_id=upload.id,
        details={
            "original_filename": upload.original_filename,
            "stored_filename": upload.stored_filename,
            "report_type_key": upload.report_type.key if upload.report_type else None,
        },
    )
    db.session.commit()

    return send_file(
        file_path,
        as_attachment=True,
        download_name=upload.original_filename,
        mimetype=upload.mime_type or 'application/octet-stream'
    )
    
       
@warehouse_bp.route('/uploads/<int:upload_id>/archive', methods=['PATCH'])
@jwt_required()
def warehouse_archive_upload(upload_id: int):
    forbidden = require_warehouse_archive()
    if forbidden:
        return forbidden

    upload = WarehouseUploadORM.query.filter_by(id=upload_id).first()

    if not upload:
        return jsonify({
            "error": "Upload no encontrado",
            "detail": f"No existe un upload de Warehouse con id {upload_id}."
        }), 404

    if upload.status == 'ARCHIVED':
        return jsonify({
            "error": "Upload ya archivado",
            "detail": f"El upload {upload_id} ya se encuentra en estado ARCHIVED."
        }), 400

    current_user_id = _get_current_user_id()
    if not current_user_id:
        return jsonify({
            "error": "Sesión inválida",
            "detail": "No se pudo resolver el usuario autenticado actual."
        }), 401

    upload.status = 'ARCHIVED'

    log_warehouse_audit(
        action='ARCHIVE',
        performed_by_user_id=current_user_id,
        upload_id=upload.id,
        details={
            "original_filename": upload.original_filename,
            "stored_filename": upload.stored_filename,
            "previous_status": "ACTIVE",
            "new_status": "ARCHIVED",
        },
    )

    db.session.commit()

    return jsonify({
        "message": "Upload archivado correctamente",
        "upload_id": upload.id,
        "status": upload.status
    }), 200
    
@warehouse_bp.route('/uploads/<int:upload_id>/audit', methods=['GET'])
@jwt_required()
def warehouse_get_upload_audit(upload_id: int):
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    upload = WarehouseUploadORM.query.filter_by(id=upload_id).first()
    if not upload:
        return jsonify({
            "error": "Upload no encontrado",
            "detail": f"No existe un upload de Warehouse con id {upload_id}."
        }), 404

    audit_items = (
        WarehouseAuditLogORM.query
        .filter_by(upload_id=upload_id)
        .order_by(WarehouseAuditLogORM.created_at.desc())
        .all()
    )

    return jsonify({
        "items": [
            {
                "id": item.id,
                "upload_id": item.upload_id,
                "action": item.action,
                "performed_by_user_id": item.performed_by_user_id,
                "details": item.details,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in audit_items
        ]
    }), 200