from datetime import date, datetime, timedelta, timezone
import smtplib

from flask import Flask
from openpyxl import Workbook, load_workbook
import pytest

from app.extensions import db
from app.models.warehouse import (
    TrackDailyVersionORM,
    VentaTotalSnapshotORM,
    WarehouseAuditLogORM,
    WarehouseFamilyORM,
    WarehouseOperationalRoleORM,
    WarehouseReportTypeORM,
    WarehouseSourceORM,
    WarehouseUploadORM,
)
from app.utils.email_sender import EmailDeliveryUncertain
from app.warehouse.jobs import iventas_activity_delivery_job as job
from app.warehouse.scheduler import reports_scheduler_worker as scheduler
from app.warehouse.services.warehouse_upload_loader_sql import load_warehouse_upload_from_db


NOW = datetime(2026, 11, 19, 18, 20, tzinfo=timezone.utc)
NEXT_HOUR = NOW + timedelta(hours=1)
DAY = date(2026, 11, 19)


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    app = Flask(__name__, root_path=str(tmp_path / "backend" / "app"))
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        WAREHOUSE_INTERNAL_SYSTEM_USER_ID=47,
        WAREHOUSE_UPLOAD_LOADER_IMPL=load_warehouse_upload_from_db,
    )
    db.init_app(app)
    with app.app_context():
        for model in (
            WarehouseSourceORM, WarehouseFamilyORM, WarehouseOperationalRoleORM,
            WarehouseReportTypeORM, TrackDailyVersionORM, WarehouseUploadORM,
            VentaTotalSnapshotORM, WarehouseAuditLogORM,
        ):
            model.__table__.create(db.engine)
        db.session.add_all([
            WarehouseSourceORM(id=1, key="suite_auto", label="Suite", active=True),
            WarehouseFamilyORM(id=1, key="reportes_transaccionales", label="Reportes", active=True),
            WarehouseOperationalRoleORM(id=1, key="FUENTE_PRINCIPAL", label="Principal", active=True),
            TrackDailyVersionORM(
                id=8, track_date=DAY, version_type="preview_operativo", status="success",
                trigger_source="scheduler_hourly_preview", started_at_utc=NOW,
                created_at=NOW, updated_at=NOW,
            ),
        ])
        for report_id, key in enumerate(("venta_total", job.REPORT_TYPE_KEY, job.FULL_REPORT_TYPE_KEY), 1):
            db.session.add(WarehouseReportTypeORM(
                id=report_id, key=key, label=key, family_id=1, default_source_id=1,
                default_operational_role_id=1, default_period_type="rango", active=True,
            ))
        db.session.add(WarehouseUploadORM(
            id=50, original_filename="ventas.xlsx", stored_filename="ventas.xlsx",
            stored_path="ventas", file_size_bytes=10, file_hash_sha256="a" * 64,
            extension="xlsx", source_id=1, family_id=1, operational_role_id=1,
            report_type_id=1, period_type="rango", status="ACTIVE",
            date_from=DAY.replace(day=1), date_to=DAY,
            track_daily_version_id=8, uploaded_by_user_id=47,
        ))
        db.session.add(VentaTotalSnapshotORM(
            id=23, warehouse_upload_id=50, report_type_key="venta_total", business_date=DAY,
            captured_at=NOW, snapshot_kind="daily", is_canonical=False, row_count_detected=1,
            row_count_valid=1, row_count_rejected=0, created_at=NOW, updated_at=NOW,
        ))
        db.session.commit()

        calls = []
        movements = {"folio-initial"}

        def write_workbook(path, included):
            book = Workbook()
            book.properties.identifier = path.name
            book.active.append(["Fecha", "Sucursal", "Descripcion", "Telefono", "IDSocio"])
            for movement in included:
                book.active.append(["19-11-26", "TEC", movement, "6860000000", 20])
            book.save(path)

        def generate(*, venta_total_upload_id, output_path, known_movements, baseline_only, full_output_path):
            calls.append((venta_total_upload_id, baseline_only))
            included = sorted(movements - known_movements)
            if not baseline_only and included:
                write_workbook(output_path, included)
            result = {
                "venta_total_cutoff": DAY.isoformat(), "venta_total_snapshot_id": 23,
                "socios_activos_cutoff": DAY.isoformat(), "rows": len(included), "movement_keys": included,
            }
            if full_output_path is not None:
                write_workbook(full_output_path, sorted(movements))
                result["full_rows"] = len(movements)
            return result

        monkeypatch.setattr(job, "generate_xlsx", generate)
        yield tmp_path, calls, movements


def _run(*, now=NOW, email=True):
    return job.deliver_hourly_activity(now=now, email_enabled=email, recipient="import@example.test")


def _next_cut(started_at):
    track = db.session.get(TrackDailyVersionORM, 8)
    track.started_at_utc = started_at
    db.session.commit()


def test_publish_then_retry_smtp_using_identical_warehouse_file(warehouse, monkeypatch):
    tmp_path, generations, movements = warehouse
    messages = []

    def send(to, subject, html, *, attachments, message_id):
        messages.append((to, attachments[0], message_id))
        if len(messages) == 1:
            raise smtplib.SMTPRecipientsRefused({})

    monkeypatch.setattr(job, "send_email_html", send)
    assert _run(email=False) == "baselined"
    assert WarehouseUploadORM.query.filter_by(report_type_id=2).count() == 0
    _next_cut(NEXT_HOUR)
    movements.add("folio-nuevo")
    assert _run(now=NEXT_HOUR, email=False) == "published"
    assert messages == []
    with pytest.raises(RuntimeError, match="reintento"):
        _run(now=NEXT_HOUR)
    # The same stored delta remains deliverable even when that hour is over.
    later = NEXT_HOUR + timedelta(hours=1)
    assert _run(now=later) == "sent"
    assert _run(now=later) == "waiting_for_venta_total"
    assert generations == [(50, True), (50, False)]
    assert len(messages) == 2 and messages[0] == messages[1]

    upload = WarehouseUploadORM.query.filter_by(report_type_id=2).one()
    attachment = messages[1][1]
    saved = tmp_path / upload.stored_path / upload.stored_filename
    assert saved.read_bytes() == attachment.content
    assert attachment.filename == upload.original_filename
    assert upload.date_from == DAY.replace(day=1) and upload.date_to == DAY
    book = load_workbook(saved, read_only=True)
    try:
        assert list(book.active.values) == [
            ("Fecha", "Sucursal", "Descripcion", "Telefono", "IDSocio"),
            ("19-11-26", "TEC", "folio-nuevo", "6860000000", 20),
        ]
    finally:
        book.close()
    assert [audit.action for audit in WarehouseAuditLogORM.query.filter_by(upload_id=upload.id)
            .order_by(WarehouseAuditLogORM.id).all()] == [
        "UPLOAD", job.EMAIL_ATTEMPT, job.EMAIL_FAILED, job.EMAIL_ATTEMPT, job.EMAIL_SENT,
    ]


def test_uncertain_smtp_attempt_is_not_resent(warehouse, monkeypatch):
    _, generations, movements = warehouse
    attempts = []

    def send(*args, **kwargs):
        attempts.append(True)
        raise EmailDeliveryUncertain()

    monkeypatch.setattr(job, "send_email_html", send)
    assert _run() == "baselined"
    _next_cut(NEXT_HOUR)
    movements.add("folio-nuevo")
    assert _run(now=NEXT_HOUR) == "delivery_uncertain"
    assert _run(now=NEXT_HOUR) == "already_processed"
    assert attempts == [True] and generations == [(50, True), (50, False)]


def test_identical_next_cut_keeps_an_hourly_full_but_no_delta_or_email(warehouse, monkeypatch):
    _, generations, _ = warehouse
    monkeypatch.setattr(job, "send_email_html", lambda *a, **kw: pytest.fail("no new movements"))
    assert _run() == "baselined"
    _next_cut(NEXT_HOUR)
    assert _run(now=NEXT_HOUR) == "no_new_movements"
    assert _run(now=NEXT_HOUR) == "already_processed"
    assert WarehouseUploadORM.query.filter_by(report_type_id=2).count() == 0
    full_uploads = WarehouseUploadORM.query.filter_by(report_type_id=3).all()
    assert len(full_uploads) == 2
    assert len({upload.file_hash_sha256 for upload in full_uploads}) == 2
    assert generations == [(50, True), (50, False)]


def test_each_hour_rebuilds_full_and_delta_only_adds_new_movements(warehouse, monkeypatch):
    tmp_path, generations, movements = warehouse
    monkeypatch.setattr(job, "send_email_html", lambda *a, **kw: pytest.fail("email is disabled"))
    four_pm = datetime(2026, 11, 20, 0, 20, tzinfo=timezone.utc)
    five_pm = four_pm + timedelta(hours=1)
    _next_cut(four_pm)
    assert _run(now=four_pm, email=False) == "baselined"
    _next_cut(five_pm)
    movements.add("folio-nuevo")
    assert _run(now=five_pm, email=False) == "published"
    assert _run(now=five_pm, email=False) == "already_processed"
    assert generations == [(50, True), (50, False)]

    uploads = WarehouseUploadORM.query.filter(WarehouseUploadORM.report_type_id.in_((2, 3)))
    uploads = uploads.order_by(WarehouseUploadORM.id).all()
    assert len(uploads) == 3
    for upload, filename_prefix, hour, expected in zip(uploads, (
        "Acumulado_", "Acumulado_", "Delta_",
    ), ("1600", "1700", "1700"), (
        ["folio-initial"], ["folio-initial", "folio-nuevo"], ["folio-nuevo"],
    )):
        assert upload.original_filename.startswith(filename_prefix)
        assert f"2026-11-19_{hour}-0800" in upload.original_filename
        assert upload.date_from == DAY.replace(day=1) and upload.date_to == DAY
        saved = tmp_path / upload.stored_path / upload.stored_filename
        workbook = load_workbook(saved, read_only=True)
        try:
            rows = list(workbook.active.values)
            assert rows[0] == ("Fecha", "Sucursal", "Descripcion", "Telefono", "IDSocio")
            assert [row[2] for row in rows[1:]] == expected
        finally:
            workbook.close()

    queued = job._pending_email()
    assert queued.upload.report_type_id == 2
    assert WarehouseAuditLogORM.query.filter_by(action=job.EMAIL_ATTEMPT).count() == 0


def test_retry_after_delta_upload_failure_reuses_the_full_warehouse_file(warehouse, monkeypatch):
    _, _, movements = warehouse
    assert _run(email=False) == "baselined"
    _next_cut(NEXT_HOUR)
    movements.add("folio-nuevo")
    save_export = job._save_export

    def fail_delta(**kwargs):
        if kwargs["report_type_key"] == job.REPORT_TYPE_KEY:
            raise RuntimeError("delta upload failed")
        save_export(**kwargs)

    monkeypatch.setattr(job, "_save_export", fail_delta)
    with pytest.raises(RuntimeError, match="delta upload failed"):
        _run(now=NEXT_HOUR, email=False)
    assert WarehouseUploadORM.query.filter_by(report_type_id=3).count() == 2
    monkeypatch.setattr(job, "_save_export", save_export)
    assert _run(now=NEXT_HOUR, email=False) == "published"
    assert WarehouseUploadORM.query.filter_by(report_type_id=3).count() == 2
    assert WarehouseUploadORM.query.filter_by(report_type_id=2).count() == 1


def test_waits_for_successful_track_hour(warehouse):
    _, generations, _ = warehouse
    track = db.session.get(TrackDailyVersionORM, 8)
    track.status = "failed"
    db.session.commit()
    assert _run() == "waiting_for_venta_total"
    assert generations == []


def test_reports_scheduler_calls_the_delivery_job_only_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "_IVENTAS_NEXT_RETRY_AT", None)
    monkeypatch.setattr(scheduler, "has_active_track_work", lambda: False)
    monkeypatch.setattr(scheduler, "deliver_hourly_activity",
                        lambda **settings: calls.append(settings) or "published")
    monkeypatch.delenv("IVENTAS_ACTIVITY_EXPORT_ENABLED", raising=False)
    monkeypatch.delenv("IVENTAS_ACTIVITY_EMAIL_ENABLED", raising=False)
    monkeypatch.setenv("IVENTAS_ACTIVITY_EMAIL_TO", "import@example.test")
    scheduler._run_iventas_activity_if_due(NOW)
    assert calls == []
    monkeypatch.setenv("IVENTAS_ACTIVITY_EXPORT_ENABLED", "true")
    scheduler._run_iventas_activity_if_due(NOW)
    assert calls == [{"now": NOW, "email_enabled": False, "recipient": "import@example.test"}]


@pytest.mark.parametrize("disconnect", [False, True])
def test_smtp_attachment_preserves_bytes_and_handles_failed_quit(monkeypatch, disconnect):
    from app.utils import email_sender

    class SMTP:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            raise smtplib.SMTPResponseException(500, b"QUIT rejected")

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            messages.append(message)
            if disconnect:
                raise smtplib.SMTPServerDisconnected("No reply to DATA")

        def set_debuglevel(self, level):
            pytest.fail("El adjunto no debe aparecer en el debug SMTP")

    messages = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", lambda *args, **kwargs: SMTP())
    monkeypatch.setattr(email_sender, "_get_env", lambda: (
        "smtp.example.test", 587, "operator", "synthetic", "tickets@example.test",
        "Ultra Tickets", "tickets@example.test", "starttls",
    ))
    monkeypatch.setenv("SMTP_DEBUG", "1")
    def send():
        email_sender.send_email_html(
            ["import@example.test"], "Prueba", "<p>Prueba</p>",
            attachments=(email_sender.EmailAttachment("report.xlsx", b"xlsx", job.XLSX_CONTENT_TYPE),),
        )

    if disconnect:
        with pytest.raises(EmailDeliveryUncertain):
            send()
    else:
        send()
    attachment, = messages[0].iter_attachments()
    assert attachment.get_filename() == "report.xlsx"
    assert attachment.get_payload(decode=True) == b"xlsx"
