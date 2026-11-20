from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from email.headerregistry import Address
from email.errors import HeaderParseError
from fcntl import LOCK_EX, LOCK_NB, flock
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import and_, func, or_
from sqlalchemy.engine import Row
from sqlalchemy.orm import aliased
from app.extensions import db
from app.models.warehouse import (
    TrackDailyVersionORM,
    VentaTotalSnapshotORM,
    WarehouseAuditLogORM,
    WarehouseUploadORM,
)
from app.utils.email_sender import EmailAttachment, EmailDeliveryUncertain, send_email_html
from app.utils.warehouse_audit import log_warehouse_audit
from app.warehouse.jobs.iventas_activity_hourly_job import run_job as generate_xlsx
from app.warehouse.services.warehouse_document_upload_service import create_warehouse_document_upload
from app.warehouse.services.warehouse_upload_loader import load_warehouse_upload


REPORT_TYPE_KEY = "iventas_actividad_horaria"
FULL_REPORT_TYPE_KEY = "iventas_actividad_acumulado_horario"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PUBLISHED = "IVENTAS_EXPORT_READY"
PUBLICATION_ACTIONS = ("UPLOAD", PUBLISHED)
BASELINE = "IVENTAS_DELTA_BASELINE"
EMPTY = "IVENTAS_DELTA_EMPTY"
EMAIL_ATTEMPT = "IVENTAS_EMAIL_ATTEMPT"
EMAIL_FAILED = "IVENTAS_EMAIL_FAILED"
EMAIL_SENT = "IVENTAS_EMAIL_SENT"
TIJUANA = ZoneInfo("America/Tijuana")


def _hourly_venta_total(now: datetime) -> tuple[int, int] | None:
    local = now.astimezone(TIJUANA)
    start = local.replace(minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return (
        db.session.query(TrackDailyVersionORM.id, WarehouseUploadORM.id)
        .join(WarehouseUploadORM, WarehouseUploadORM.track_daily_version_id == TrackDailyVersionORM.id)
        .join(VentaTotalSnapshotORM, VentaTotalSnapshotORM.warehouse_upload_id == WarehouseUploadORM.id)
        .filter(
            TrackDailyVersionORM.track_date == local.date(),
            TrackDailyVersionORM.status == "success",
            TrackDailyVersionORM.version_type == "preview_operativo",
            TrackDailyVersionORM.trigger_source == "scheduler_hourly_preview",
            TrackDailyVersionORM.started_at_utc >= start,
            TrackDailyVersionORM.started_at_utc < start + timedelta(hours=1),
            WarehouseUploadORM.status == "ACTIVE",
            WarehouseUploadORM.source_file_deleted_at.is_(None),
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.business_date == local.date(),
        )
        .order_by(TrackDailyVersionORM.id.desc(), VentaTotalSnapshotORM.captured_at.desc())
        .first()
    )


@contextmanager
def _publication_lock():
    lock_path = Path(current_app.root_path).parent.parent / "uploads" / "warehouse" / ".iventas_activity.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        try:
            flock(lock.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def _operator_id() -> int:
    operator_id = current_app.config["WAREHOUSE_INTERNAL_SYSTEM_USER_ID"]
    if operator_id <= 0:
        raise RuntimeError("Configura WAREHOUSE_INTERNAL_SYSTEM_USER_ID para publicar el reporte de iVentas.")
    return operator_id


def _record(*, action: str, operator_id: int, upload_id: int | None, details: dict) -> None:
    log_warehouse_audit(
        action=action, performed_by_user_id=operator_id, upload_id=upload_id, details=details,
    )
    db.session.commit()


def _delta_audits():
    return db.session.query(WarehouseAuditLogORM).filter(
        WarehouseAuditLogORM.details["producer"].as_string() == REPORT_TYPE_KEY,
        WarehouseAuditLogORM.details["export_mode"].as_string() == "delta",
        WarehouseAuditLogORM.action.in_((*PUBLICATION_ACTIONS, BASELINE, EMPTY)),
    )


def _save_export(*, path: Path, report_type_key: str, operator_id: int, result: dict, details: dict) -> None:
    cutoff = date.fromisoformat(result["venta_total_cutoff"])
    details.update({
        "rows": result["rows"],
        "venta_total_snapshot_id": result["venta_total_snapshot_id"],
        "socios_activos_cutoff": result["socios_activos_cutoff"],
    })
    upload = create_warehouse_document_upload(
        report_type_key=report_type_key,
        original_filename=path.name,
        content_type=XLSX_CONTENT_TYPE,
        file_path=str(path),
        uploaded_by_user_id=operator_id,
        date_from=cutoff.replace(day=1),
        date_to=cutoff,
        audit_details=details,
    )
    if upload["upload_status"] == "reused_existing":
        _record(action=PUBLISHED, operator_id=operator_id, upload_id=upload["warehouse_upload_id"], details=details)


def _publish(*, source_id: int, operator_id: int, details: dict, now: datetime) -> str:
    audits = _delta_audits()
    baseline_only = audits.filter(WarehouseAuditLogORM.action == BASELINE).first() is None
    known_movements = {
        key for (evidence,) in audits.with_entities(WarehouseAuditLogORM.details).filter(
            WarehouseAuditLogORM.details["business_month"].as_string() == details["business_month"],
        ) for key in evidence.get("movement_keys", ())
    }
    full_published = db.session.query(WarehouseAuditLogORM.id).filter(
        WarehouseAuditLogORM.action.in_(PUBLICATION_ACTIONS),
        WarehouseAuditLogORM.details["producer"].as_string() == FULL_REPORT_TYPE_KEY,
        WarehouseAuditLogORM.details["cutoff_hour_utc"].as_string() == details["cutoff_hour_utc"],
    ).first() is not None

    with TemporaryDirectory(prefix="iventas-activity-") as workspace:
        cutoff_hour = now.astimezone(TIJUANA).strftime("%Y-%m-%d_%H00%z")
        xlsx = Path(workspace) / f"Delta_pases_recorridos_ventas_iVentas_{cutoff_hour}.xlsx"
        full_path = Path(workspace) / f"Acumulado_pases_recorridos_ventas_iVentas_{cutoff_hour}.xlsx"
        result = generate_xlsx(
            venta_total_upload_id=source_id, output_path=xlsx,
            known_movements=known_movements, baseline_only=baseline_only,
            full_output_path=None if full_published else full_path,
        )
        if not full_published:
            _save_export(
                path=full_path, report_type_key=FULL_REPORT_TYPE_KEY, operator_id=operator_id,
                result={**result, "rows": result["full_rows"]},
                details={**details, "producer": FULL_REPORT_TYPE_KEY, "export_mode": "hourly_full"},
            )
        details["movement_keys"] = result["movement_keys"]
        if baseline_only or result["rows"] == 0:
            details.update({
                "rows": result["rows"],
                "venta_total_snapshot_id": result["venta_total_snapshot_id"],
                "socios_activos_cutoff": result["socios_activos_cutoff"],
            })
            _record(action=BASELINE if baseline_only else EMPTY, operator_id=operator_id,
                    upload_id=None, details=details)
            return "baselined" if baseline_only else "no_new_movements"
        _save_export(
            path=xlsx, report_type_key=REPORT_TYPE_KEY, operator_id=operator_id, result=result, details=details,
        )
    return "published"


def _pending_email() -> Row[tuple[WarehouseAuditLogORM, int]] | None:
    delivery = aliased(WarehouseAuditLogORM)
    delivery_hour = delivery.details["cutoff_hour_utc"].as_string()
    last_attempts = (
        db.session.query(delivery_hour.label("cutoff_hour"), func.max(delivery.id).label("audit_id"))
        .filter(
            delivery.details["producer"].as_string() == REPORT_TYPE_KEY,
            delivery.details["export_mode"].as_string() == "delta",
            delivery.action.in_((EMAIL_ATTEMPT, EMAIL_FAILED, EMAIL_SENT)),
        )
        .group_by(delivery_hour).subquery()
    )
    current_hour = WarehouseAuditLogORM.details["cutoff_hour_utc"].as_string()
    full_export = aliased(WarehouseAuditLogORM)
    full_upload = aliased(WarehouseUploadORM)
    return _delta_audits().add_columns(full_export.upload_id).join(
        full_export,
        and_(
            full_export.details["cutoff_hour_utc"].as_string() == current_hour,
            full_export.details["producer"].as_string() == FULL_REPORT_TYPE_KEY,
            full_export.action.in_(PUBLICATION_ACTIONS),
        ),
    ).join(full_upload, full_upload.id == full_export.upload_id).outerjoin(
        WarehouseUploadORM, WarehouseUploadORM.id == WarehouseAuditLogORM.upload_id,
    ).outerjoin(last_attempts, last_attempts.c.cutoff_hour == current_hour).outerjoin(
        delivery, delivery.id == last_attempts.c.audit_id,
    ).filter(
        full_upload.status == "ACTIVE",
        full_upload.source_file_deleted_at.is_(None),
        or_(
            WarehouseAuditLogORM.action.in_((BASELINE, EMPTY)),
            and_(
                WarehouseUploadORM.status == "ACTIVE",
                WarehouseUploadORM.source_file_deleted_at.is_(None),
            ),
        ),
        or_(delivery.action.is_(None), delivery.action == EMAIL_FAILED),
    ).order_by(WarehouseAuditLogORM.id).first()


def _attachment(upload_id: int, report_type_key: str) -> EmailAttachment:
    metadata = load_warehouse_upload(warehouse_upload_id=upload_id)
    if metadata is None or metadata["report_type_key"] != report_type_key or not metadata["storage_path"]:
        raise RuntimeError("No se pudo recuperar el XLSX de iVentas registrado en Warehouse.")
    stored = db.session.get(WarehouseUploadORM, upload_id)
    content = Path(metadata["storage_path"]).read_bytes()
    if stored is None or stored.status != "ACTIVE" or sha256(content).hexdigest() != stored.file_hash_sha256:
        raise RuntimeError("El XLSX de iVentas no coincide con un upload activo de Warehouse.")
    return EmailAttachment(metadata["original_filename"], content, XLSX_CONTENT_TYPE)


def _email_address(value: str, setting: str) -> str:
    try:
        address = Address(addr_spec=value.strip())
    except (ValueError, HeaderParseError):
        raise RuntimeError(f"Configura {setting} con un correo válido.") from None
    if not address.username or not address.domain:
        raise RuntimeError(f"Configura {setting} con un correo válido.")
    return address.addr_spec


def _send_pending_email(
    completed_cut: WarehouseAuditLogORM,
    full_upload_id: int,
    *,
    operator_id: int,
    recipient: str,
    recipient_cc: str,
) -> str:
    address = _email_address(recipient, "IVENTAS_ACTIVITY_EMAIL_TO")
    cc_addresses = recipient_cc.split(",") if recipient_cc.strip() else ()
    cc = [_email_address(value, "IVENTAS_ACTIVITY_EMAIL_CC") for value in cc_addresses]

    delta_upload_id = completed_cut.upload_id
    attachments = [_attachment(full_upload_id, FULL_REPORT_TYPE_KEY)]
    body = "<p>Adjuntamos el acumulado del mes de pases de cortesía, recorridos y ventas de Ultra Gym."
    if delta_upload_id is not None:
        attachments.append(_attachment(delta_upload_id, REPORT_TYPE_KEY))
        body += " También se adjuntan los movimientos nuevos del corte."
    body += "</p>"

    upload_id = delta_upload_id or full_upload_id
    hour = datetime.fromisoformat(completed_cut.details["cutoff_hour_utc"])
    message_id = f"<iventas-actividad.{hour:%Y%m%d%H}@suiteultragym.com>"
    local_cut = hour.astimezone(TIJUANA).strftime("%d/%m/%Y %H:%M")
    # Preserve the delivery audit key used by earlier versions.
    details = {
        "producer": REPORT_TYPE_KEY, "export_mode": "delta", "cutoff_hour_utc": hour.isoformat(),
        "message_id": message_id, "recipient": address, "cc": cc,
        "full_upload_id": full_upload_id, "delta_upload_id": delta_upload_id,
    }
    _record(action=EMAIL_ATTEMPT, operator_id=operator_id, upload_id=upload_id, details=details)
    try:
        send_email_html(
            [address], f"Ultra Gym | Pases, recorridos y ventas | {local_cut}", body,
            cc_list=cc, attachments=attachments, message_id=message_id,
        )
    except EmailDeliveryUncertain as exc:
        current_app.logger.warning(
            "iVentas SMTP sin confirmación completa: upload_id=%s message_id=%s motivo=%s",
            upload_id, message_id, exc,
        )
        return "delivery_uncertain"
    except Exception as exc:
        _record(action=EMAIL_FAILED, operator_id=operator_id, upload_id=upload_id,
                details={**details, "error_type": type(exc).__name__})
        raise RuntimeError("El envío del reporte iVentas falló. Se conservará el upload para reintento.") from None

    _record(action=EMAIL_SENT, operator_id=operator_id, upload_id=upload_id, details=details)
    return "sent"


def deliver_hourly_activity(*, now: datetime, email_enabled: bool, recipient: str, recipient_cc: str = "") -> str:
    """Publish a full export and at most one delta for each hourly Track cut."""
    with _publication_lock() as acquired:
        if not acquired:
            return "busy"

        operator_id = _operator_id()

        source = _hourly_venta_total(now)
        status = "waiting_for_venta_total"
        if source is not None:
            version_id, source_id = source
            hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
            processed = _delta_audits().filter(
                WarehouseAuditLogORM.details["cutoff_hour_utc"].as_string() == hour.isoformat(),
            ).first()
            status = "already_processed" if processed is not None else _publish(
                source_id=source_id, operator_id=operator_id, now=now,
                details={
                    "producer": REPORT_TYPE_KEY, "export_mode": "delta",
                    "cutoff_hour_utc": hour.isoformat(), "business_month": now.astimezone(TIJUANA).strftime("%Y-%m"),
                    "track_preview_id": version_id, "venta_total_upload_id": source_id,
                },
            )
        if email_enabled:
            pending = _pending_email()
            if pending is not None:
                return _send_pending_email(
                    *pending, operator_id=operator_id, recipient=recipient, recipient_cc=recipient_cc,
                )
        return status
