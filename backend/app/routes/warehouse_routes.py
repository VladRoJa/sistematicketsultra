# app/routes/warehouse_routes.py

from flask import Blueprint, jsonify, request, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename
import hashlib
import uuid
from sqlalchemy.orm import joinedload


from app.extensions import db
from app.models.warehouse import WarehouseUploadORM
from app.utils.warehouse_access import require_warehouse_operator
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
    WarehouseDocumentUploadError,
    WarehouseDocumentValidationError,
)



warehouse_bp = Blueprint('warehouse', __name__)


ALLOWED_WAREHOUSE_EXTENSIONS = {'xlsx', 'xls', 'csv', 'pdf', 'txt'}
MAX_WAREHOUSE_FILE_SIZE_BYTES = 70 * 1024 * 1024


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


def _resolve_period_data(report_type, cutoff_date_raw: str, date_from_raw: str, date_to_raw: str):
    parsed_cutoff_date = None
    parsed_date_from = None
    parsed_date_to = None

    if report_type.default_period_type == 'diario':
        if not cutoff_date_raw:
            return None, (jsonify({
                "error": "Fecha requerida",
                "detail": "Debes enviar 'cutoff_date' cuando el report_type requiere periodo diario."
            }), 400)

        try:
            parsed_cutoff_date = datetime.strptime(cutoff_date_raw, '%Y-%m-%d').date()
        except ValueError:
            return None, (jsonify({
                "error": "Fecha inválida",
                "detail": "cutoff_date debe tener formato YYYY-MM-DD."
            }), 400)

    if report_type.default_period_type == 'rango':
        if not date_from_raw or not date_to_raw:
            return None, (jsonify({
                "error": "Rango requerido",
                "detail": "Debes enviar 'date_from' y 'date_to' cuando el report_type requiere periodo rango."
            }), 400)

        try:
            parsed_date_from = datetime.strptime(date_from_raw, '%Y-%m-%d').date()
            parsed_date_to = datetime.strptime(date_to_raw, '%Y-%m-%d').date()
        except ValueError:
            return None, (jsonify({
                "error": "Fecha inválida",
                "detail": "date_from y date_to deben tener formato YYYY-MM-DD."
            }), 400)

        if parsed_date_from > parsed_date_to:
            return None, (jsonify({
                "error": "Rango inválido",
                "detail": "date_from no puede ser mayor que date_to."
            }), 400)

    return {
        "cutoff_date": parsed_cutoff_date,
        "date_from": parsed_date_from,
        "date_to": parsed_date_to,
    }, None

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
    forbidden = require_warehouse_operator()
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
    forbidden = require_warehouse_operator()
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
            audit_details={
                "upload_origin": "manual_route",
            },
        )

    except WarehouseDocumentValidationError as exc:
        return jsonify({
            "error": "No se pudo crear el upload",
            "detail": str(exc),
        }), 400

    except WarehouseDocumentUploadError as exc:
        current_app.logger.exception("Error controlado creando upload documental de Warehouse.")
        return jsonify({
            "error": "No se pudo crear el upload",
            "detail": str(exc),
        }), 500

    except Exception:
        current_app.logger.exception("Error inesperado creando upload documental de Warehouse.")
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
    }), 201  
    
@warehouse_bp.route('/uploads', methods=['GET'])
@jwt_required()
def warehouse_list_uploads():
    forbidden = require_warehouse_operator()
    if forbidden:
        return forbidden

    source_key = (request.args.get('source_key') or '').strip()
    report_type_key = (request.args.get('report_type_key') or '').strip()
    status = (request.args.get('status') or '').strip()
    period_type = (request.args.get('period_type') or '').strip()

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

    if status:
        query = query.filter(WarehouseUploadORM.status == status)

    if period_type:
        query = query.filter(WarehouseUploadORM.period_type == period_type)

    uploads = query.order_by(WarehouseUploadORM.created_at.desc()).all()

    return jsonify({
        "items": [
            {
                "id": item.id,
                "original_filename": item.original_filename,
                "stored_filename": item.stored_filename,
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
            for item in uploads
        ]
    }), 200
    
@warehouse_bp.route('/uploads/<int:upload_id>', methods=['GET'])
@jwt_required()
def warehouse_get_upload_detail(upload_id: int):
    forbidden = require_warehouse_operator()
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
    forbidden = require_warehouse_operator()
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
    forbidden = require_warehouse_operator()
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
    forbidden = require_warehouse_operator()
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