from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.extensions import db
from app.models.attendance import (
    WarehouseAttendanceRejectionORM,
    WarehouseAttendanceRunORM,
    WarehouseAttendanceVisitORM,
)
from app.routine_control.pipeline.branch_resolver import (
    resolve_gasca_branch_id,
)

from .attendance_mart_service import (
    rebuild_attendance_marts,
)
from .attendance_parser import (
    AttendanceParseResult,
    AttendanceVisitRecord,
    PARSER_VERSION,
    file_sha256,
    parse_attendance_excel,
)


def ingest_attendance_excel(
    path: Path | str,
    *,
    business_date: date,
    trigger_source: str = "MANUAL_FILE",
) -> WarehouseAttendanceRunORM:
    """
    Ingesta un XLSX temporal de Asistencias.

    El archivo sólo es transporte. Este servicio no
    lo conserva ni lo elimina: el capturador/CLI es
    responsable del ciclo de vida del temporal.
    """
    source_path = Path(path)
    digest = file_sha256(source_path)

    run = WarehouseAttendanceRunORM(
        business_date=business_date,
        status="RUNNING",
        trigger_source=(
            _normalize_trigger_source(
                trigger_source
            )
        ),
        source_sha256=digest,
        parser_version=PARSER_VERSION,
    )
    db.session.add(run)
    db.session.commit()

    run_id = int(run.id)

    try:
        result = parse_attendance_excel(
            source_path,
            business_date=business_date,
        )
        (
            inserted_rows,
            updated_rows,
        ) = _persist_visits(
            result,
            run_id=run_id,
        )
        _persist_rejections(
            result,
            run_id=run_id,
        )

        rebuild_attendance_marts(
            business_date=business_date,
            source_run_id=run_id,
        )

        run = db.session.get(
            WarehouseAttendanceRunORM,
            run_id,
        )
        if run is None:
            raise RuntimeError(
                "La ejecución de asistencia "
                "dejó de existir."
            )

        run.status = "SUCCESS"
        run.source_rows = result.source_rows
        run.inserted_rows = inserted_rows
        run.updated_rows = updated_rows
        run.rejected_rows = len(
            result.rejections
        )
        run.finished_at_utc = datetime.now(
            timezone.utc
        )
        run.error_message = None

        db.session.commit()
        return run

    except Exception as exc:
        db.session.rollback()

        failed_run = db.session.get(
            WarehouseAttendanceRunORM,
            run_id,
        )
        if failed_run is not None:
            failed_run.status = "FAILED"
            failed_run.error_message = str(
                exc
            )[:4000]
            failed_run.finished_at_utc = (
                datetime.now(timezone.utc)
            )
            db.session.commit()

        raise


def _persist_visits(
    result: AttendanceParseResult,
    *,
    run_id: int,
) -> tuple[int, int]:
    existing_rows = (
        db.session.query(
            WarehouseAttendanceVisitORM
        )
        .filter(
            WarehouseAttendanceVisitORM
            .business_date
            == result.visits[
                0
            ].business_date
        )
        .all()
        if result.visits
        else []
    )
    existing_by_fingerprint = {
        row.source_fingerprint: row
        for row in existing_rows
    }

    branch_cache: dict[
        str,
        int | None,
    ] = {}
    inserted_rows = 0
    updated_rows = 0

    for record in result.visits:
        branch_id = _resolve_branch_cached(
            record.source_branch_name,
            branch_cache,
        )
        existing = (
            existing_by_fingerprint.get(
                record.source_fingerprint
            )
        )

        if existing is None:
            existing = (
                WarehouseAttendanceVisitORM(
                    source_fingerprint=(
                        record.source_fingerprint
                    )
                )
            )
            db.session.add(existing)
            existing_by_fingerprint[
                record.source_fingerprint
            ] = existing
            inserted_rows += 1
        else:
            updated_rows += 1

        _apply_visit(
            existing,
            record,
            branch_id=branch_id,
            run_id=run_id,
        )

    return inserted_rows, updated_rows


def _persist_rejections(
    result: AttendanceParseResult,
    *,
    run_id: int,
) -> None:
    for rejected in result.rejections:
        db.session.add(
            WarehouseAttendanceRejectionORM(
                run_id=run_id,
                business_date=(
                    rejected.business_date
                ),
                source_row_number=(
                    rejected.source_row_number
                ),
                reason_code=(
                    rejected.reason_code
                ),
                detail=rejected.detail,
                member_pin=(
                    rejected.member_pin
                ),
                source_branch_name=(
                    rejected.source_branch_name
                ),
                entered_at_raw=(
                    rejected.entered_at_raw
                ),
                attendance_type_raw=(
                    rejected.attendance_type_raw
                ),
            )
        )


def _resolve_branch_cached(
    source_branch_name: str,
    cache: dict[str, int | None],
) -> int | None:
    if source_branch_name not in cache:
        cache[
            source_branch_name
        ] = resolve_gasca_branch_id(
            source_branch_name,
            session=db.session,
        )
    return cache[source_branch_name]


def _apply_visit(
    target: WarehouseAttendanceVisitORM,
    record: AttendanceVisitRecord,
    *,
    branch_id: int | None,
    run_id: int,
) -> None:
    target.business_date = (
        record.business_date
    )
    target.sucursal_id = branch_id
    target.source_branch_name = (
        record.source_branch_name
    )
    target.member_pin = record.member_pin
    target.entered_at_utc = (
        record.entered_at_utc
    )
    target.exited_at_utc = (
        record.exited_at_utc
    )
    target.duration_seconds = (
        record.duration_seconds
    )
    target.visit_status = (
        record.visit_status
    )
    target.age = record.age
    target.age_is_valid = (
        record.age_is_valid
    )
    target.city = record.city
    target.postal_code = (
        record.postal_code
    )
    target.member_since = (
        record.member_since
    )
    target.attendance_type = (
        record.attendance_type
    )
    target.has_opening = (
        record.has_opening
    )
    target.source_row_number = (
        record.source_row_number
    )
    target.last_run_id = run_id


def _normalize_trigger_source(
    value: str,
) -> str:
    normalized = str(
        value or ""
    ).strip().upper()
    return (
        normalized[:40]
        or "MANUAL_FILE"
    )
