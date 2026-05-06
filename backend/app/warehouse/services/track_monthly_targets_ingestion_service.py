#   backend\app\warehouse\services\track_monthly_targets_ingestion_service.py


from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from datetime import date

import pandas as pd

from app.extensions import db
from app.models.warehouse import TrackBranchCatalogORM
from app.models.warehouse import TrackMonthlyTargetORM

class TrackMonthlyTargetsParseError(Exception):
    pass


REQUIRED_COLUMNS = [
    "sucursal_canon",
    "m2_sin_circulaciones",
    "usuarios_inicio_mes",
    "proyeccion_usuarios_cierre_mes",
    "meta_faycgo_mes",
    "meta_clientes_nuevos_mes",
    "meta_reactivaciones_mes",
    "meta_bajas_mes",
    "meta_nuevos_domiciliados_mes",
    "meta_arpu_mes",
    "meta_venta_tienda_mes",
]


@dataclass(frozen=True)
class TrackMonthlyTargetParsedRow:
    sucursal_canon: str
    m2_sin_circulaciones: Decimal
    usuarios_inicio_mes: int
    proyeccion_usuarios_cierre_mes: int
    meta_faycgo_mes: Decimal
    meta_clientes_nuevos_mes: int
    meta_reactivaciones_mes: int
    meta_bajas_mes: int
    meta_nuevos_domiciliados_mes: int
    meta_arpu_mes: Decimal
    meta_venta_tienda_mes: Decimal


def _require_columns(dataframe: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        raise TrackMonthlyTargetsParseError(
            "Faltan columnas requeridas en el archivo de metas: "
            + ", ".join(missing)
        )


def _to_decimal(value: Any, field_name: str) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise TrackMonthlyTargetsParseError(
            f"El campo '{field_name}' no puede venir vacío."
        )

    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception as exc:
        raise TrackMonthlyTargetsParseError(
            f"El campo '{field_name}' debe ser numérico."
        ) from exc


def _to_int(value: Any, field_name: str) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise TrackMonthlyTargetsParseError(
            f"El campo '{field_name}' no puede venir vacío."
        )

    try:
        return int(value)
    except Exception as exc:
        raise TrackMonthlyTargetsParseError(
            f"El campo '{field_name}' debe ser entero."
        ) from exc


def _normalize_row(row: pd.Series, row_number: int) -> TrackMonthlyTargetParsedRow:
    sucursal_canon = str(row["sucursal_canon"] or "").strip()
    if not sucursal_canon:
        raise TrackMonthlyTargetsParseError(
            f"La fila {row_number} no tiene 'sucursal_canon'."
        )

    return TrackMonthlyTargetParsedRow(
        sucursal_canon=sucursal_canon,
        m2_sin_circulaciones=_to_decimal(
            row["m2_sin_circulaciones"],
            "m2_sin_circulaciones",
        ),
        usuarios_inicio_mes=_to_int(
            row["usuarios_inicio_mes"],
            "usuarios_inicio_mes",
        ),
        proyeccion_usuarios_cierre_mes=_to_int(
            row["proyeccion_usuarios_cierre_mes"],
            "proyeccion_usuarios_cierre_mes",
        ),
        meta_faycgo_mes=_to_decimal(
            row["meta_faycgo_mes"],
            "meta_faycgo_mes",
        ),
        meta_clientes_nuevos_mes=_to_int(
            row["meta_clientes_nuevos_mes"],
            "meta_clientes_nuevos_mes",
        ),
        meta_reactivaciones_mes=_to_int(
            row["meta_reactivaciones_mes"],
            "meta_reactivaciones_mes",
        ),
        meta_bajas_mes=_to_int(
            row["meta_bajas_mes"],
            "meta_bajas_mes",
        ),
        meta_nuevos_domiciliados_mes=_to_int(
            row["meta_nuevos_domiciliados_mes"],
            "meta_nuevos_domiciliados_mes",
        ),
        meta_arpu_mes=_to_decimal(
            row["meta_arpu_mes"],
            "meta_arpu_mes",
        ),
        meta_venta_tienda_mes=_to_decimal(
            row["meta_venta_tienda_mes"],
            "meta_venta_tienda_mes",
        ),
    )

def _validate_no_duplicate_branches(
    parsed_rows: list[TrackMonthlyTargetParsedRow],
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()

    for row in parsed_rows:
        key = row.sucursal_canon.strip().upper()

        if key in seen:
            duplicates.add(row.sucursal_canon)
            continue

        seen.add(key)

    if duplicates:
        duplicates_sorted = sorted(duplicates)
        raise TrackMonthlyTargetsParseError(
            "El archivo contiene sucursales duplicadas: "
            + ", ".join(duplicates_sorted)
        )

def _validate_branches_exist_in_catalog(
    parsed_rows: list[TrackMonthlyTargetParsedRow],
) -> None:
    branches_in_file = sorted(
        {
            row.sucursal_canon.strip().upper()
            for row in parsed_rows
        }
    )

    if not branches_in_file:
        return

    existing_rows = (
        db.session.query(TrackBranchCatalogORM.sucursal_canon)
        .filter(TrackBranchCatalogORM.sucursal_canon.in_(branches_in_file))
        .all()
    )

    existing_branches = {
        str(sucursal_canon).strip().upper()
        for (sucursal_canon,) in existing_rows
    }

    missing_branches = [
        branch
        for branch in branches_in_file
        if branch not in existing_branches
    ]

    if missing_branches:
        raise TrackMonthlyTargetsParseError(
            "Las siguientes sucursales no existen en track_branch_catalog: "
            + ", ".join(missing_branches)
        )

def parse_track_monthly_targets_file(file_path: str | Path) -> list[TrackMonthlyTargetParsedRow]:
    dataframe: pd.DataFrame | None = None
    selected_header_row: int | None = None
    last_missing_columns: list[str] = []

    for header_row in range(0, 8):
        candidate_dataframe = pd.read_excel(
            file_path,
            header=header_row,
        )

        candidate_dataframe.columns = [
            str(column).strip()
            for column in candidate_dataframe.columns
        ]

        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in candidate_dataframe.columns
        ]

        if not missing_columns:
            dataframe = candidate_dataframe.dropna(how="all")
            selected_header_row = header_row
            break

        last_missing_columns = missing_columns

    if dataframe is None or selected_header_row is None:
        raise TrackMonthlyTargetsParseError(
            "No se encontró una fila de encabezados válida para metas mensuales. "
            "Faltan columnas requeridas en el archivo de metas: "
            + ", ".join(last_missing_columns)
        )

    _require_columns(dataframe)

    parsed_rows: list[TrackMonthlyTargetParsedRow] = []

    for index, row in dataframe.iterrows():
        row_number = index + selected_header_row + 2
        parsed_rows.append(_normalize_row(row, row_number))

    _validate_no_duplicate_branches(parsed_rows)

    return parsed_rows


def ingest_track_monthly_targets_file(
    *,
    file_path: str | Path,
    target_month: date,
) -> dict[str, Any]:
    parsed_rows = parse_track_monthly_targets_file(file_path)
    _validate_branches_exist_in_catalog(parsed_rows)

    try:
        rows_inserted = _replace_target_month_rows(
            target_month=target_month,
            parsed_rows=parsed_rows,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "ingested",
        "target_month": target_month.isoformat(),
        "row_count": len(parsed_rows),
        "rows_inserted": rows_inserted,
    }
    
def _replace_target_month_rows(
    *,
    target_month: date,
    parsed_rows: list[TrackMonthlyTargetParsedRow],
) -> int:
    (
        db.session.query(TrackMonthlyTargetORM)
        .filter(TrackMonthlyTargetORM.target_month == target_month)
        .delete(synchronize_session=False)
    )

    for row in parsed_rows:
        db.session.add(
            TrackMonthlyTargetORM(
                target_month=target_month,
                sucursal_canon=row.sucursal_canon,
                m2_sin_circulaciones=row.m2_sin_circulaciones,
                usuarios_inicio_mes=row.usuarios_inicio_mes,
                proyeccion_usuarios_cierre_mes=row.proyeccion_usuarios_cierre_mes,
                meta_faycgo_mes=row.meta_faycgo_mes,
                meta_clientes_nuevos_mes=row.meta_clientes_nuevos_mes,
                meta_reactivaciones_mes=row.meta_reactivaciones_mes,
                meta_bajas_mes=row.meta_bajas_mes,
                meta_nuevos_domiciliados_mes=row.meta_nuevos_domiciliados_mes,
                meta_arpu_mes=row.meta_arpu_mes,
                meta_venta_tienda_mes=row.meta_venta_tienda_mes,
                is_active=True,
                notes=None,
            )
        )

    db.session.flush()

    return len(parsed_rows)

def ingest_track_monthly_targets_upload(
    *,
    warehouse_upload_id: int,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    from app.warehouse.services.warehouse_upload_loader_sql import (
        load_warehouse_upload_from_db,
    )

    loaded_upload = load_warehouse_upload_from_db(
        warehouse_upload_id=warehouse_upload_id,
    )
    if loaded_upload is None:
        raise TrackMonthlyTargetsParseError(
            f"No se encontró el warehouse_upload_id={warehouse_upload_id}."
        )

    storage_path = loaded_upload.get("storage_path")
    target_month = loaded_upload.get("cutoff_date")

    if not storage_path:
        raise TrackMonthlyTargetsParseError(
            "El upload de track_monthly_targets no tiene storage_path resolvible."
        )

    if not target_month:
        raise TrackMonthlyTargetsParseError(
            "El upload de track_monthly_targets no tiene cutoff_date/target_month resuelto."
        )

    result = ingest_track_monthly_targets_file(
        file_path=storage_path,
        target_month=target_month,
    )

    return {
        "status": "ingested",
        "warehouse_upload_id": warehouse_upload_id,
        "requested_by": requested_by,
        "ingestion_source": ingestion_source,
        "target_month": result["target_month"],
        "row_count": result["row_count"],
        "rows_inserted": result["rows_inserted"],
    }
    
def register_track_monthly_targets_ingestor(app) -> None:
    """
    Registra el ingestor estructurado de metas mensuales del Track.

    Esto deja disponible:
        app.config["WAREHOUSE_TRACK_MONTHLY_TARGETS_INGESTOR"]
    """
    app.config["WAREHOUSE_TRACK_MONTHLY_TARGETS_INGESTOR"] = (
        ingest_track_monthly_targets_upload
    )