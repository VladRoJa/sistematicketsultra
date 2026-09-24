from __future__ import annotations

import argparse
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models.warehouse import (
    VentasNuevosSociosDetalleSnapshotORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
    WarehouseUploadORM,
)
from app.utils.warehouse_audit import log_warehouse_audit
from app.warehouse.services.ventas_nuevos_socios_detalle_branch_resolver import (
    resolve_ventas_nuevos_socios_detalle_branch_id,
)
from app.warehouse.services.ventas_nuevos_socios_detalle_parser import (
    parse_ventas_nuevos_socios_detalle_xlsx,
)
from app.warehouse.services.ventas_nuevos_socios_detalle_repository import (
    _normalize_row,
)
from app.warehouse.services.warehouse_upload_loader import load_warehouse_upload


SNAPSHOT_ID = 156
WAREHOUSE_UPLOAD_ID = 19658
REPORT_TYPE_KEY = "ventas_nuevos_socios_detalle"
DATE_FROM = date(2026, 4, 1)
DATE_TO = date(2026, 4, 30)

EXPECTED_FILE_SHA256 = (
    "8be6d41e063c4c20cd76cb8622cfbe068d9b3df3eee3921acf37965edbf13243"
)

EXPECTED_CURRENT_VALID = 2173
EXPECTED_CURRENT_REJECTED = 1
EXPECTED_CURRENT_DETECTED = 2174

EXPECTED_REPAIRED_VALID = 2174
EXPECTED_REPAIRED_REJECTED = 0
EXPECTED_REPAIRED_DETECTED = 2174

TARGET_MEMBER_ID = "357378"
TARGET_FOLIO = "26080524018600006440"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _system_user_id(app) -> int:
    value = app.config.get("WAREHOUSE_INTERNAL_SYSTEM_USER_ID")
    if not isinstance(value, int) or value <= 0:
        raise RuntimeError(
            "WAREHOUSE_INTERNAL_SYSTEM_USER_ID no está configurado con un id válido."
        )
    return value


def _load_and_validate_source() -> tuple[Path, object]:
    upload = WarehouseUploadORM.query.get(WAREHOUSE_UPLOAD_ID)
    if upload is None:
        raise RuntimeError(
            f"No existe warehouse_upload_id={WAREHOUSE_UPLOAD_ID}."
        )

    if str(upload.file_hash_sha256 or "").lower() != EXPECTED_FILE_SHA256:
        raise RuntimeError(
            "El SHA-256 registrado del RAW no coincide con el artifact auditado."
        )

    loaded = load_warehouse_upload(
        warehouse_upload_id=WAREHOUSE_UPLOAD_ID
    )
    if loaded is None:
        raise RuntimeError("El RAW no pudo cargarse desde Warehouse.")

    if loaded.get("report_type_key") != REPORT_TYPE_KEY:
        raise RuntimeError(
            f"report_type_key inesperado: {loaded.get('report_type_key')!r}"
        )

    if loaded.get("date_from") != DATE_FROM:
        raise RuntimeError(
            f"date_from inesperado: {loaded.get('date_from')!r}"
        )

    if loaded.get("date_to") != DATE_TO:
        raise RuntimeError(
            f"date_to inesperado: {loaded.get('date_to')!r}"
        )

    storage_path = loaded.get("storage_path")
    if not storage_path:
        raise RuntimeError("El loader no devolvió storage_path.")

    source_path = Path(str(storage_path))
    if not source_path.is_file():
        raise RuntimeError(
            f"El RAW no existe físicamente: {source_path}"
        )

    actual_sha256 = _sha256(source_path)
    if actual_sha256 != EXPECTED_FILE_SHA256:
        raise RuntimeError(
            "El archivo físico no coincide con el SHA-256 auditado."
        )

    parsed = parse_ventas_nuevos_socios_detalle_xlsx(
        file_path=str(source_path),
        branch_resolver=resolve_ventas_nuevos_socios_detalle_branch_id,
    )

    if parsed.row_count != EXPECTED_REPAIRED_DETECTED:
        raise RuntimeError(
            f"row_count inesperado: {parsed.row_count}."
        )
    if parsed.row_count_valid != EXPECTED_REPAIRED_VALID:
        raise RuntimeError(
            f"row_count_valid inesperado: {parsed.row_count_valid}."
        )
    if parsed.row_count_rejected != EXPECTED_REPAIRED_REJECTED:
        raise RuntimeError(
            f"row_count_rejected inesperado: {parsed.row_count_rejected}."
        )

    target_rows = [
        row
        for row in parsed.rows
        if row.id_socio == TARGET_MEMBER_ID
    ]
    if len(target_rows) != 1:
        raise RuntimeError(
            f"Se esperaba exactamente una fila para IDSocio={TARGET_MEMBER_ID}."
        )

    target = target_rows[0]
    if target.id_folio != TARGET_FOLIO:
        raise RuntimeError(
            f"IDFolio inesperado para socio objetivo: {target.id_folio!r}"
        )
    if target.telefono != "":
        raise RuntimeError(
            f"Telefono del socio objetivo ya no está vacío: {target.telefono!r}"
        )
    if "TELEFONO_MISSING" not in target.quality_flags:
        raise RuntimeError(
            "La fila objetivo no contiene TELEFONO_MISSING."
        )

    return source_path, parsed


def _validate_current_snapshot(
    snapshot: VentasNuevosSociosDetalleSnapshotORM,
) -> int:
    if snapshot.warehouse_upload_id != WAREHOUSE_UPLOAD_ID:
        raise RuntimeError(
            f"snapshot {SNAPSHOT_ID} apunta a upload inesperado "
            f"{snapshot.warehouse_upload_id}."
        )
    if snapshot.report_type_key != REPORT_TYPE_KEY:
        raise RuntimeError("report_type_key del snapshot no coincide.")
    if snapshot.business_date != DATE_TO:
        raise RuntimeError(
            f"business_date inesperado: {snapshot.business_date}."
        )
    if snapshot.date_from != DATE_FROM or snapshot.date_to != DATE_TO:
        raise RuntimeError(
            "El rango de fechas del snapshot no corresponde a abril 2026."
        )
    if not snapshot.is_canonical:
        raise RuntimeError("El snapshot 156 ya no es canónico.")

    current_count = (
        VentasNuevosSociosDetalleSnapshotRowORM.query
        .filter_by(snapshot_id=SNAPSHOT_ID)
        .count()
    )

    expected_counts = (
        snapshot.row_count_detected == EXPECTED_CURRENT_DETECTED
        and snapshot.row_count_valid == EXPECTED_CURRENT_VALID
        and snapshot.row_count_rejected == EXPECTED_CURRENT_REJECTED
        and current_count == EXPECTED_CURRENT_VALID
    )

    repaired_counts = (
        snapshot.row_count_detected == EXPECTED_REPAIRED_DETECTED
        and snapshot.row_count_valid == EXPECTED_REPAIRED_VALID
        and snapshot.row_count_rejected == EXPECTED_REPAIRED_REJECTED
        and current_count == EXPECTED_REPAIRED_VALID
    )

    if repaired_counts:
        return current_count

    if not expected_counts:
        raise RuntimeError(
            "El estado actual del snapshot no coincide con el esperado "
            f"(header={snapshot.row_count_detected}/"
            f"{snapshot.row_count_valid}/"
            f"{snapshot.row_count_rejected}, rows={current_count})."
        )

    return current_count


def _already_repaired(
    snapshot: VentasNuevosSociosDetalleSnapshotORM,
    current_count: int,
) -> bool:
    return (
        snapshot.row_count_detected == EXPECTED_REPAIRED_DETECTED
        and snapshot.row_count_valid == EXPECTED_REPAIRED_VALID
        and snapshot.row_count_rejected == EXPECTED_REPAIRED_REJECTED
        and current_count == EXPECTED_REPAIRED_VALID
    )


def _normalized_rows(parsed) -> list[dict[str, object]]:
    rows = [_normalize_row(row) for row in parsed.rows]

    if len(rows) != EXPECTED_REPAIRED_VALID:
        raise RuntimeError(
            f"Repository normalizó {len(rows)} filas; "
            f"se esperaban {EXPECTED_REPAIRED_VALID}."
        )

    return rows


def run(*, commit: bool, app) -> None:
    source_path, parsed = _load_and_validate_source()
    normalized_rows = _normalized_rows(parsed)

    snapshot = db.session.get(
        VentasNuevosSociosDetalleSnapshotORM,
        SNAPSHOT_ID,
    )
    if snapshot is None:
        raise RuntimeError(f"No existe snapshot_id={SNAPSHOT_ID}.")

    current_count = _validate_current_snapshot(snapshot)

    if _already_repaired(snapshot, current_count):
        print(
            f"ALREADY_REPAIRED snapshot_id={SNAPSHOT_ID} "
            f"rows={current_count}"
        )
        return

    print(
        "READY "
        f"snapshot_id={SNAPSHOT_ID} "
        f"upload_id={WAREHOUSE_UPLOAD_ID} "
        f"source={source_path} "
        f"current={snapshot.row_count_valid}/"
        f"{snapshot.row_count_rejected} "
        f"repaired={parsed.row_count_valid}/"
        f"{parsed.row_count_rejected}"
    )

    if not commit:
        return

    locked_snapshot = (
        VentasNuevosSociosDetalleSnapshotORM.query
        .filter_by(id=SNAPSHOT_ID)
        .with_for_update()
        .one()
    )

    locked_count = _validate_current_snapshot(locked_snapshot)
    if _already_repaired(locked_snapshot, locked_count):
        print(
            f"ALREADY_REPAIRED snapshot_id={SNAPSHOT_ID} "
            f"rows={locked_count}"
        )
        return

    (
        VentasNuevosSociosDetalleSnapshotRowORM.query
        .filter_by(snapshot_id=SNAPSHOT_ID)
        .delete(synchronize_session=False)
    )

    now = datetime.now(timezone.utc)
    orm_rows = [
        VentasNuevosSociosDetalleSnapshotRowORM(
            snapshot_id=SNAPSHOT_ID,
            created_at=now,
            updated_at=now,
            **row,
        )
        for row in normalized_rows
    ]
    db.session.add_all(orm_rows)

    previous_metadata = dict(locked_snapshot.metadata_json or {})
    locked_snapshot.row_count_detected = parsed.row_count
    locked_snapshot.row_count_valid = parsed.row_count_valid
    locked_snapshot.row_count_rejected = parsed.row_count_rejected
    locked_snapshot.metadata_json = {
        **previous_metadata,
        **dict(parsed.metadata or {}),
        "quality_flag_counts": dict(parsed.quality_flag_counts),
        "rejected_rows": [
            {
                "row_number": item.row_number,
                "reason_code": item.reason_code,
                "reason_message": item.reason_message,
            }
            for item in parsed.rejected_rows
        ],
        "structured_repair": {
            "reason": "allow_valid_sale_without_phone",
            "source_upload_id": WAREHOUSE_UPLOAD_ID,
            "source_sha256": EXPECTED_FILE_SHA256,
            "previous_row_count_valid": EXPECTED_CURRENT_VALID,
            "previous_row_count_rejected": EXPECTED_CURRENT_REJECTED,
            "repaired_at_utc": now.isoformat(),
        },
    }
    locked_snapshot.updated_at = now

    log_warehouse_audit(
        action="STRUCTURED_REPAIR",
        performed_by_user_id=_system_user_id(app),
        upload_id=WAREHOUSE_UPLOAD_ID,
        details={
            "report_type_key": REPORT_TYPE_KEY,
            "snapshot_id": SNAPSHOT_ID,
            "business_date": DATE_TO.isoformat(),
            "reason": "allow_valid_sale_without_phone",
            "before": {
                "row_count_valid": EXPECTED_CURRENT_VALID,
                "row_count_rejected": EXPECTED_CURRENT_REJECTED,
            },
            "after": {
                "row_count_valid": EXPECTED_REPAIRED_VALID,
                "row_count_rejected": EXPECTED_REPAIRED_REJECTED,
            },
            "target_id_socio": TARGET_MEMBER_ID,
            "target_id_folio": TARGET_FOLIO,
        },
    )

    db.session.commit()

    final_snapshot = db.session.get(
        VentasNuevosSociosDetalleSnapshotORM,
        SNAPSHOT_ID,
    )
    final_count = (
        VentasNuevosSociosDetalleSnapshotRowORM.query
        .filter_by(snapshot_id=SNAPSHOT_ID)
        .count()
    )

    if (
        final_snapshot is None
        or final_snapshot.row_count_valid != EXPECTED_REPAIRED_VALID
        or final_snapshot.row_count_rejected != EXPECTED_REPAIRED_REJECTED
        or final_count != EXPECTED_REPAIRED_VALID
    ):
        raise RuntimeError(
            "La verificación posterior al commit no coincide con el estado esperado."
        )

    print(
        "OK "
        f"snapshot_id={SNAPSHOT_ID} "
        f"rows={final_count} "
        f"valid={final_snapshot.row_count_valid} "
        f"rejected={final_snapshot.row_count_rejected}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reprocesa de forma controlada el snapshot estructurado de "
            "Ventas Nuevos Socios Detalle de abril 2026 usando su RAW original."
        )
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Aplica la reparación. Sin este flag solo valida y muestra el plan."
        ),
    )
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        try:
            run(commit=args.commit, app=app)
        except Exception as exc:
            db.session.rollback()
            print(f"FAILED {type(exc).__name__}: {exc}")
            return 1
        finally:
            db.session.remove()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
