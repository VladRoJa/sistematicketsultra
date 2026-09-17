from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.sales_composition import (
    SalesCompositionRowORM,
    SalesCompositionSnapshotORM,
)


RESUMEN_VENTAS_REPORT_TYPE_KEY = "resumen_ventas"


class ResumenVentasRepositoryError(RuntimeError):
    pass


def register_resumen_ventas_repository(app) -> None:
    app.config["WAREHOUSE_RESUMEN_VENTAS_REPOSITORY"] = (
        persist_resumen_ventas_snapshot
    )


def persist_resumen_ventas_snapshot(
    *,
    warehouse_upload_id: int,
    report_type_key: str,
    date_from: date | datetime | str,
    date_to: date | datetime | str,
    captured_at: datetime | str,
    parsed_snapshot: Any,
) -> dict[str, Any]:
    upload_id = _positive_int(warehouse_upload_id, "warehouse_upload_id")
    report_type = str(report_type_key or "").strip()
    if report_type != RESUMEN_VENTAS_REPORT_TYPE_KEY:
        raise ValueError("report_type_key no corresponde a resumen_ventas.")

    normalized_date_from = _as_date(date_from)
    normalized_date_to = _as_date(date_to)
    if normalized_date_from > normalized_date_to:
        raise ValueError("date_from no puede ser posterior a date_to.")

    existing = SalesCompositionSnapshotORM.query.filter_by(
        warehouse_upload_id=upload_id
    ).first()
    if existing is not None:
        return _result(
            existing,
            status="already_ingested",
            was_idempotent=True,
            rows_inserted=0,
        )

    payload = _as_dict(parsed_snapshot)
    rows = [
        _normalize_row(_as_dict(row))
        for row in payload.get("rows") or []
    ]
    if not rows:
        raise ValueError("El parser no devolvió filas estructuradas.")

    row_count_valid = int(payload.get("row_count_valid", len(rows)))
    row_count_rejected = int(payload.get("row_count_rejected", 0))
    row_count_detected = int(
        payload.get(
            "row_count_detected",
            row_count_valid + row_count_rejected,
        )
    )
    if row_count_valid != len(rows):
        raise ValueError(
            "row_count_valid no coincide con las filas parseadas."
        )

    now = datetime.now(timezone.utc)
    normalized_captured_at = _as_datetime(captured_at)

    try:
        existing_canonical = (
            SalesCompositionSnapshotORM.query
            .filter_by(
                business_date=normalized_date_to,
                is_canonical=True,
            )
            .with_for_update()
            .all()
        )
        for snapshot in existing_canonical:
            snapshot.is_canonical = False
            snapshot.updated_at = now

        snapshot = SalesCompositionSnapshotORM(
            warehouse_upload_id=upload_id,
            report_type_key=report_type,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
            business_date=normalized_date_to,
            captured_at=normalized_captured_at,
            is_canonical=True,
            current_label=str(payload.get("current_label") or "").strip(),
            comparison_label=str(
                payload.get("comparison_label") or ""
            ).strip(),
            row_count_detected=row_count_detected,
            row_count_valid=row_count_valid,
            row_count_rejected=row_count_rejected,
            summary_totals=_json_safe(payload.get("summary_totals") or {}),
            data_quality=_json_safe(payload.get("data_quality") or {}),
            created_at=now,
            updated_at=now,
        )
        if not snapshot.current_label or not snapshot.comparison_label:
            raise ValueError(
                "El parser no resolvió los periodos comparativos."
            )

        db.session.add(snapshot)
        db.session.flush()
        orm_rows = [
            SalesCompositionRowORM(
                snapshot_id=int(snapshot.id),
                created_at=now,
                updated_at=now,
                **row,
            )
            for row in rows
        ]
        db.session.add_all(orm_rows)
        db.session.commit()
        return _result(
            snapshot,
            status="ingested",
            was_idempotent=False,
            rows_inserted=len(orm_rows),
        )
    except IntegrityError as exc:
        db.session.rollback()
        existing = SalesCompositionSnapshotORM.query.filter_by(
            warehouse_upload_id=upload_id
        ).first()
        if existing is not None:
            return _result(
                existing,
                status="already_ingested",
                was_idempotent=True,
                rows_inserted=0,
            )
        raise ResumenVentasRepositoryError(
            "Falló una restricción de integridad persistiendo Resumen Ventas."
        ) from exc
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, ValueError):
            raise
        raise ResumenVentasRepositoryError(
            "Falló la persistencia transaccional de Resumen Ventas."
        ) from exc


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    row_kind = str(row.get("row_kind") or "").strip().upper()
    sales_mode = str(row.get("sales_mode") or "").strip().upper()
    if row_kind not in {"TARIFF", "BRANCH"}:
        raise ValueError(f"row_kind inválido: {row_kind!r}.")
    if sales_mode not in {"CONTRACT", "NO_CONTRACT"}:
        raise ValueError(f"sales_mode inválido: {sales_mode!r}.")
    return {
        "row_index": int(row["row_index"]),
        "source_sheet": _required_text(
            row.get("source_sheet"),
            "source_sheet",
        ),
        "source_row_number": int(row["source_row_number"]),
        "row_kind": row_kind,
        "tariff_row_index": int(row["tariff_row_index"]),
        "sales_mode": sales_mode,
        "family": _optional_text(row.get("family")),
        "contract_type": _optional_text(row.get("contract_type")),
        "plan_type": _optional_text(row.get("plan_type")),
        "tariff_name": _required_text(
            row.get("tariff_name"),
            "tariff_name",
        ),
        "source_cost": _optional_decimal(row.get("source_cost")),
        "monthly_equivalent": _optional_decimal(
            row.get("monthly_equivalent")
        ),
        "free_months_raw": _optional_text(row.get("free_months_raw")),
        "branch_raw": _optional_text(row.get("branch_raw")),
        "current_quantity": _decimal(row.get("current_quantity")),
        "current_flow": _decimal(row.get("current_flow")),
        "comparison_quantity": _decimal(row.get("comparison_quantity")),
        "comparison_flow": _decimal(row.get("comparison_flow")),
    }


def _result(
    snapshot: SalesCompositionSnapshotORM,
    *,
    status: str,
    was_idempotent: bool,
    rows_inserted: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "was_idempotent": was_idempotent,
        "snapshot_id": int(snapshot.id),
        "warehouse_upload_id": int(snapshot.warehouse_upload_id),
        "report_type_key": snapshot.report_type_key,
        "date_from": snapshot.date_from.isoformat(),
        "date_to": snapshot.date_to.isoformat(),
        "business_date": snapshot.business_date.isoformat(),
        "is_canonical": bool(snapshot.is_canonical),
        "row_count_detected": int(snapshot.row_count_detected),
        "row_count_valid": int(snapshot.row_count_valid),
        "row_count_rejected": int(snapshot.row_count_rejected),
        "rows_inserted": int(rows_inserted),
        "data_quality": dict(snapshot.data_quality or {}),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    raise ValueError("Se esperaba dict o dataclass serializable.")


def _positive_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} debe ser positivo.")
    return parsed


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Fecha inválida: {value!r}.")


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return (
            parsed
            if parsed.tzinfo
            else parsed.replace(tzinfo=timezone.utc)
        )
    raise ValueError(f"captured_at inválido: {value!r}.")


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} es requerido.")
    return text


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
