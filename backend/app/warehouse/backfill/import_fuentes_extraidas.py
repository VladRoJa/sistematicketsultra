#   backend/app/warehouse/backfill/import_fuentes_extraidas.py


from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)
from app.warehouse.services.reporte_direccion_ingestion_service import (
    ingest_reporte_direccion_upload,
)
from app.warehouse.services.kpi_desempeno_ingestion_service import (
    ingest_kpi_desempeno_upload,
)
from app.warehouse.services.kpi_ventas_nuevos_socios_ingestion_service import (
    ingest_kpi_ventas_nuevos_socios_upload,
)


REQUIRED_REPORT_TYPES = (
    "reporte_direccion",
    "kpi_desempeno",
    "kpi_ventas_nuevos_socios",
)

INGESTORS_BY_REPORT_TYPE: dict[str, Callable[..., dict[str, Any]]] = {
    "reporte_direccion": ingest_reporte_direccion_upload,
    "kpi_desempeno": ingest_kpi_desempeno_upload,
    "kpi_ventas_nuevos_socios": ingest_kpi_ventas_nuevos_socios_upload,
}

SNAPSHOT_TABLE_BY_REPORT_TYPE = {
    "reporte_direccion": "reporte_direccion_snapshots",
    "kpi_desempeno": "kpi_desempeno_snapshots",
    "kpi_ventas_nuevos_socios": "kpi_ventas_nuevos_socios_snapshots",
}

@dataclass(frozen=True)
class InventoryRow:
    report_type_key: str
    business_date: date
    month: str
    file_name: str
    relative_path: str
    full_path: str
    size_bytes: int
    sha256: str


def _parse_date(value: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(str(value).strip())
    except Exception as exc:
        raise ValueError(f"{field_name} debe tener formato YYYY-MM-DD: {value!r}") from exc


def _load_inventory(csv_path: Path) -> list[InventoryRow]:
    rows: list[InventoryRow] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for raw in reader:
            report_type_key = str(raw.get("report_type_key") or "").strip()

            if report_type_key not in REQUIRED_REPORT_TYPES:
                continue

            business_date = _parse_date(
                str(raw.get("business_date") or "").strip(),
                field_name="business_date",
            )

            rows.append(
                InventoryRow(
                    report_type_key=report_type_key,
                    business_date=business_date,
                    month=str(raw.get("month") or "").strip(),
                    file_name=str(raw.get("file_name") or "").strip(),
                    relative_path=str(raw.get("relative_path") or "").strip(),
                    full_path=str(raw.get("full_path") or "").strip(),
                    size_bytes=int(raw.get("size_bytes") or 0),
                    sha256=str(raw.get("sha256") or "").strip(),
                )
            )

    return rows


def _filter_rows(
    rows: list[InventoryRow],
    *,
    target_date: date | None,
    target_month: str | None,
) -> list[InventoryRow]:
    filtered = rows

    if target_date is not None:
        filtered = [
            row
            for row in filtered
            if row.business_date == target_date
        ]

    if target_month:
        filtered = [
            row
            for row in filtered
            if row.month == target_month
        ]

    return sorted(
        filtered,
        key=lambda row: (
            row.business_date,
            REQUIRED_REPORT_TYPES.index(row.report_type_key),
        ),
    )


def _group_by_date(rows: list[InventoryRow]) -> dict[date, dict[str, InventoryRow]]:
    grouped: dict[date, dict[str, InventoryRow]] = {}

    for row in rows:
        grouped.setdefault(row.business_date, {})[row.report_type_key] = row

    return grouped


def _validate_complete_days(
    grouped: dict[date, dict[str, InventoryRow]],
) -> list[str]:
    issues: list[str] = []

    for business_date, by_report_type in sorted(grouped.items()):
        missing = [
            report_type_key
            for report_type_key in REQUIRED_REPORT_TYPES
            if report_type_key not in by_report_type
        ]

        if missing:
            issues.append(
                f"{business_date.isoformat()} incompleto. Faltan: {', '.join(missing)}"
            )

    return issues


def _resolve_file_path(
    *,
    files_root: Path,
    row: InventoryRow,
) -> Path:
    file_path = files_root / Path(row.relative_path)

    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(
            f"No existe el archivo para {row.report_type_key} {row.business_date}: {file_path}"
        )

    return file_path

def _structured_snapshot_exists(
    *,
    report_type_key: str,
    business_date: date,
    snapshot_kind: str = "daily",
) -> bool:
    table_name = SNAPSHOT_TABLE_BY_REPORT_TYPE.get(report_type_key)

    if not table_name:
        raise RuntimeError(
            f"No hay tabla de snapshots configurada para {report_type_key!r}."
        )

    result = db.session.execute(
        text(
            f"""
            SELECT id
            FROM {table_name}
            WHERE business_date = :business_date
              AND snapshot_kind = :snapshot_kind
              AND is_canonical = true
            LIMIT 1
            """
        ),
        {
            "business_date": business_date,
            "snapshot_kind": snapshot_kind,
        },
    ).first()

    return result is not None

def _upload_and_ingest(
    *,
    row: InventoryRow,
    file_path: Path,
    uploaded_by_user_id: int,
    requested_by: str,
) -> dict[str, Any]:
    upload_result = create_warehouse_document_upload(
        report_type_key=row.report_type_key,
        original_filename=row.file_name,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_path=str(file_path),
        uploaded_by_user_id=uploaded_by_user_id,
        cutoff_date=row.business_date,
        audit_details={
            "upload_origin": "historical_backfill_fuentes_extraidas",
            "source_inventory": "inventario_fuentes_extraidas.csv",
            "inventory_relative_path": row.relative_path,
            "inventory_sha256": row.sha256,
            "business_date": row.business_date.isoformat(),
        },
    )

    warehouse_upload_id = int(upload_result["upload_id"])

    ingestor = INGESTORS_BY_REPORT_TYPE[row.report_type_key]
    ingestion_result = ingestor(
        warehouse_upload_id=warehouse_upload_id,
        snapshot_kind="daily",
        requested_by=requested_by,
        ingestion_source="historical_backfill_fuentes_extraidas",
    )

    return {
        "status": "imported",
        "business_date": row.business_date.isoformat(),
        "report_type_key": row.report_type_key,
        "file_path": str(file_path),
        "warehouse_upload_id": warehouse_upload_id,
        "upload_result": upload_result,
        "ingestion_result": ingestion_result,
    }


def _write_jsonl(output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa fuentes_extraidas históricas al Warehouse y dispara ingesta estructurada."
    )
    parser.add_argument("--inventory", required=True, help="CSV inventario_fuentes_extraidas.csv")
    parser.add_argument("--files-root", required=True, help="Carpeta raíz fuentes_extraidas")
    parser.add_argument("--date", default=None, help="Fecha específica YYYY-MM-DD")
    parser.add_argument("--month", default=None, help="Mes específico YYYY-MM")
    parser.add_argument("--limit-days", type=int, default=None, help="Limita número de días completos")
    parser.add_argument("--uploaded-by-user-id", type=int, default=None)
    parser.add_argument("--requested-by", default="historical_backfill")
    parser.add_argument("--commit", action="store_true", help="Ejecuta cambios reales. Sin esto es dry-run.")
    parser.add_argument(
        "--output",
        default="backfill_fuentes_extraidas_result.jsonl",
        help="Archivo JSONL de resultado.",
    )
    parser.add_argument(
        "--skip-existing-snapshots",
        action="store_true",
        help="Omite fuentes que ya tengan snapshot canónico para la fecha.",
    )

    args = parser.parse_args()

    inventory_path = Path(args.inventory).resolve()
    files_root = Path(args.files_root).resolve()
    target_date = _parse_date(args.date, field_name="date") if args.date else None

    rows = _load_inventory(inventory_path)
    rows = _filter_rows(
        rows,
        target_date=target_date,
        target_month=args.month,
    )

    grouped = _group_by_date(rows)
    issues = _validate_complete_days(grouped)

    if issues:
        raise RuntimeError(
            "Hay días incompletos en el filtro seleccionado:\n"
            + "\n".join(issues)
        )

    selected_dates = sorted(grouped.keys())

    if args.limit_days is not None:
        selected_dates = selected_dates[: args.limit_days]

    planned_rows: list[InventoryRow] = []

    for business_date in selected_dates:
        for report_type_key in REQUIRED_REPORT_TYPES:
            planned_rows.append(grouped[business_date][report_type_key])

    print("Backfill fuentes extraídas")
    print(f"Inventory: {inventory_path}")
    print(f"Files root: {files_root}")
    print(f"Commit: {args.commit}")
    print(f"Días seleccionados: {len(selected_dates)}")
    print(f"Archivos seleccionados: {len(planned_rows)}")

    results: list[dict[str, Any]] = []

    app = create_app()

    with app.app_context():
        for row in planned_rows:
            file_path = _resolve_file_path(
                files_root=files_root,
                row=row,
            )

            if not args.commit:
                result = {
                    "status": "dry_run",
                    "business_date": row.business_date.isoformat(),
                    "report_type_key": row.report_type_key,
                    "file_path": str(file_path),
                    "size_bytes": row.size_bytes,
                    "sha256": row.sha256,
                }
                print(
                    f"DRY-RUN {row.business_date} {row.report_type_key} {file_path.name}"
                )
                results.append(result)
                continue

            if not args.uploaded_by_user_id:
                raise RuntimeError("--uploaded-by-user-id es obligatorio cuando usas --commit.")
            
            if args.commit and args.skip_existing_snapshots:
                if _structured_snapshot_exists(
                    report_type_key=row.report_type_key,
                    business_date=row.business_date,
                    snapshot_kind="daily",
                ):
                    result = {
                        "status": "skipped_existing_snapshot",
                        "business_date": row.business_date.isoformat(),
                        "report_type_key": row.report_type_key,
                        "file_path": str(file_path),
                    }
                    print(
                        f"SKIP {row.business_date} {row.report_type_key} "
                        "snapshot canónico ya existe"
                    )
                    results.append(result)
                    continue   

            try:
                result = _upload_and_ingest(
                    row=row,
                    file_path=file_path,
                    uploaded_by_user_id=args.uploaded_by_user_id,
                    requested_by=args.requested_by,
                )
                db.session.commit()
                print(
                    f"OK {row.business_date} {row.report_type_key} "
                    f"upload_id={result['warehouse_upload_id']}"
                )
                results.append(result)

            except Exception as exc:
                db.session.rollback()
                error_result = {
                    "status": "failed",
                    "business_date": row.business_date.isoformat(),
                    "report_type_key": row.report_type_key,
                    "file_path": str(file_path),
                    "error": str(exc),
                }
                print(
                    f"ERROR {row.business_date} {row.report_type_key}: {exc}"
                )
                results.append(error_result)
                raise

    output_path = Path(args.output).resolve()
    _write_jsonl(output_path, results)

    print(f"Resultado escrito en: {output_path}")


if __name__ == "__main__":
    main()