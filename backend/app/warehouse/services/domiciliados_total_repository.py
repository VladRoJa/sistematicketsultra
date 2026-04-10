#   backend\app\warehouse\services\domiciliados_total_repository.py


from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.extensions import db
from app.models.warehouse import (
    DomiciliadosTotalSnapshotORM,
    DomiciliadosTotalSnapshotRowORM,
)


DOMICILIADOS_TOTAL_REPORT_TYPE_KEY = "domiciliados_total"


class DomiciliadosTotalRepositoryError(RuntimeError):
    """Error base del repository de domiciliados total."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    raise DomiciliadosTotalRepositoryError(
        "Se esperaba dict o dataclass serializable."
    )


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise DomiciliadosTotalRepositoryError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise DomiciliadosTotalRepositoryError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _ensure_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception as exc:
            raise DomiciliadosTotalRepositoryError(
                f"No se pudo convertir a datetime el campo {field_name!r}: {value!r}"
            ) from exc

    raise DomiciliadosTotalRepositoryError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _ensure_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise DomiciliadosTotalRepositoryError(
            f"El campo {field_name!r} no puede ser bool."
        )

    try:
        return int(value)
    except Exception as exc:
        raise DomiciliadosTotalRepositoryError(
            f"No se pudo convertir a int el campo {field_name!r}: {value!r}"
        ) from exc


def _ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise DomiciliadosTotalRepositoryError(
            f"El campo {field_name!r} es obligatorio."
        )
    return normalized


def persist_domiciliados_total_snapshot(
    *,
    warehouse_upload_id: Any,
    business_date: Any,
    captured_at: Any,
    snapshot_kind: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if snapshot_kind != "daily":
        raise DomiciliadosTotalRepositoryError(
            f"snapshot_kind inválido para domiciliados_total: {snapshot_kind!r}"
        )

    if not isinstance(rows, list) or not rows:
        raise DomiciliadosTotalRepositoryError(
            "rows debe ser una lista no vacía."
        )

    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )
    normalized_captured_at = _ensure_datetime(
        captured_at,
        field_name="captured_at",
    )
    normalized_upload_id = _ensure_int(
        warehouse_upload_id,
        field_name="warehouse_upload_id",
    )

    existing_by_upload = DomiciliadosTotalSnapshotORM.query.filter_by(
        warehouse_upload_id=normalized_upload_id
    ).first()

    if existing_by_upload is not None:
        return {
            "status": "already_ingested",
            "snapshot_id": existing_by_upload.id,
            "business_date": existing_by_upload.business_date.isoformat(),
            "is_canonical": existing_by_upload.is_canonical,
        }

    existing_canonical = DomiciliadosTotalSnapshotORM.query.filter_by(
        business_date=normalized_business_date,
        snapshot_kind=snapshot_kind,
        is_canonical=True,
    ).order_by(DomiciliadosTotalSnapshotORM.id.desc()).first()

    row_count_detected = len(rows)
    row_count_valid = len(rows)
    row_count_rejected = 0
    now = _utc_now()

    snapshot = DomiciliadosTotalSnapshotORM(
        warehouse_upload_id=normalized_upload_id,
        report_type_key=DOMICILIADOS_TOTAL_REPORT_TYPE_KEY,
        business_date=normalized_business_date,
        captured_at=normalized_captured_at,
        snapshot_kind=snapshot_kind,
        is_canonical=(existing_canonical is None),
        row_count_detected=row_count_detected,
        row_count_valid=row_count_valid,
        row_count_rejected=row_count_rejected,
        created_at=now,
        updated_at=now,
    )
    db.session.add(snapshot)
    db.session.flush()

    for raw_row in rows:
        row = _as_dict(raw_row)
        db.session.add(
            DomiciliadosTotalSnapshotRowORM(
                snapshot_id=snapshot.id,
                row_index=_ensure_int(row.get("row_index"), field_name="row_index"),
                sucursal=_ensure_text(row.get("sucursal"), field_name="sucursal"),
                general=_ensure_int(row.get("general"), field_name="general"),
                created_at=now,
                updated_at=now,
            )
        )

    db.session.commit()

    return {
        "status": "ingested",
        "snapshot_id": snapshot.id,
        "business_date": snapshot.business_date.isoformat(),
        "is_canonical": snapshot.is_canonical,
        "row_count_detected": snapshot.row_count_detected,
        "row_count_valid": snapshot.row_count_valid,
        "row_count_rejected": snapshot.row_count_rejected,
    }