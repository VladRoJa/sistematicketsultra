# backend/app/warehouse/services/agregadoras_consolidado_export_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile
import hashlib
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET

from flask import current_app
from sqlalchemy import and_

from app.models.warehouse import (
    IngresosTotalpassSnapshotORM,
    IngresosTotalpassSnapshotRowORM,
    IngresosWellhubSnapshotORM,
    IngresosWellhubSnapshotRowORM,
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
    WarehouseReportTypeORM,
    WarehouseUploadORM,
)


TEMPLATE_REPORT_TYPE_KEY = "agregadoras_consolidado_template"
GENERATED_RELATIVE_DIR = (
    Path("uploads") / "warehouse" / "generated" / "agregadoras"
)
LATEST_OUTPUT_FILENAME = "agregadoras_consolidado_latest.xlsx"
LATEST_METADATA_FILENAME = "agregadoras_consolidado_latest.json"

SHEET_WELLHUB = "xl/worksheets/sheet1.xml"
SHEET_TOTALPASS = "xl/worksheets/sheet2.xml"
SHEET_TODO = "xl/worksheets/sheet3.xml"
SHEET_CATALOGOS = "xl/worksheets/sheet5.xml"
TABLE_TODO = "xl/tables/table1.xml"
PIVOT_CACHE_DEFINITION = "xl/pivotCache/pivotCacheDefinition1.xml"
SHARED_STRINGS = "xl/sharedStrings.xml"
CALC_CHAIN = "xl/calcChain.xml"
WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"
RENDERER_VERSION = "xlsx_xml_integrity_v2"

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
Q = lambda tag: f"{{{SPREADSHEET_NS}}}{tag}"

XML_NAMESPACES = {
    "": SPREADSHEET_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "x14ac": "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac",
    "xr": "http://schemas.microsoft.com/office/spreadsheetml/2014/revision",
    "xr2": "http://schemas.microsoft.com/office/spreadsheetml/2015/revision2",
    "xr3": "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3",
}

for namespace_prefix, namespace_uri in XML_NAMESPACES.items():
    ET.register_namespace(namespace_prefix, namespace_uri)


class AgregadorasConsolidadoError(RuntimeError):
    """Error base del export acumulado de agregadoras."""


class AgregadorasTemplateMissingError(AgregadorasConsolidadoError):
    """No existe una plantilla activa para el consolidado."""


class AgregadorasTemplateInvalidError(AgregadorasConsolidadoError):
    """La plantilla no conserva el contrato esperado."""


class AgregadorasSourceGapError(AgregadorasConsolidadoError):
    """Falta al menos un snapshot diario canónico requerido."""


class AgregadorasSourceRegressionError(AgregadorasConsolidadoError):
    """Un acumulado MTD retrocedió respecto al día anterior."""


@dataclass(frozen=True, slots=True)
class _AccumulatedBranch:
    visits: int
    amount: Decimal
    raw_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgregadoraDailyRow:
    business_date: date
    branch_name: str
    visits: int
    amount: Decimal


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _uploads_root() -> Path:
    return Path(current_app.root_path).parent.parent.resolve()


def _resolve_upload_file_path(upload: WarehouseUploadORM) -> Path:
    return (
        _uploads_root()
        / Path(upload.stored_path)
        / str(upload.stored_filename)
    ).resolve()


def _generated_dir() -> Path:
    path = (_uploads_root() / GENERATED_RELATIVE_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _output_path() -> Path:
    return _generated_dir() / LATEST_OUTPUT_FILENAME


def _metadata_path() -> Path:
    return _generated_dir() / LATEST_METADATA_FILENAME


def _latest_template_upload() -> WarehouseUploadORM | None:
    return (
        WarehouseUploadORM.query
        .join(
            WarehouseReportTypeORM,
            WarehouseReportTypeORM.id == WarehouseUploadORM.report_type_id,
        )
        .filter(
            WarehouseReportTypeORM.key == TEMPLATE_REPORT_TYPE_KEY,
            WarehouseReportTypeORM.active.is_(True),
            WarehouseUploadORM.status == "ACTIVE",
            WarehouseUploadORM.source_file_deleted_at.is_(None),
            WarehouseUploadORM.extension == "xlsx",
        )
        .order_by(
            WarehouseUploadORM.cutoff_date.desc(),
            WarehouseUploadORM.created_at.desc(),
            WarehouseUploadORM.id.desc(),
        )
        .first()
    )


def _latest_common_canonical_date() -> date | None:
    row = (
        IngresosWellhubSnapshotORM.query
        .with_entities(IngresosWellhubSnapshotORM.business_date)
        .join(
            IngresosTotalpassSnapshotORM,
            and_(
                IngresosTotalpassSnapshotORM.business_date
                == IngresosWellhubSnapshotORM.business_date,
                IngresosTotalpassSnapshotORM.snapshot_kind == "daily",
                IngresosTotalpassSnapshotORM.is_canonical.is_(True),
            ),
        )
        .filter(
            IngresosWellhubSnapshotORM.snapshot_kind == "daily",
            IngresosWellhubSnapshotORM.is_canonical.is_(True),
        )
        .distinct()
        .order_by(IngresosWellhubSnapshotORM.business_date.desc())
        .first()
    )
    return row[0] if row else None


def _canonical_snapshots_by_date(model, start_date: date, end_date: date):
    snapshots = (
        model.query
        .filter(
            model.business_date >= start_date,
            model.business_date <= end_date,
            model.snapshot_kind == "daily",
            model.is_canonical.is_(True),
        )
        .order_by(model.business_date.asc(), model.id.asc())
        .all()
    )

    result = {}
    for snapshot in snapshots:
        business_date = snapshot.business_date
        if business_date in result:
            raise AgregadorasConsolidadoError(
                "Existe más de un snapshot canónico diario para "
                f"{model.__tablename__} en {business_date.isoformat()}."
            )
        result[business_date] = snapshot
    return result


def _expected_dates(start_date: date, end_date: date) -> list[date]:
    days = (end_date - start_date).days
    return [
        start_date + timedelta(days=offset)
        for offset in range(days + 1)
    ]


def _validate_snapshot_continuity(
    *,
    baseline_date: date,
    target_date: date,
    wellhub_snapshots: dict[date, IngresosWellhubSnapshotORM],
    totalpass_snapshots: dict[date, IngresosTotalpassSnapshotORM],
) -> None:
    missing_wellhub = []
    missing_totalpass = []

    for expected_date in _expected_dates(baseline_date, target_date):
        if expected_date not in wellhub_snapshots:
            missing_wellhub.append(expected_date.isoformat())
        if expected_date not in totalpass_snapshots:
            missing_totalpass.append(expected_date.isoformat())

    if missing_wellhub or missing_totalpass:
        details = []
        if missing_wellhub:
            details.append(
                "Wellhub: " + ", ".join(missing_wellhub)
            )
        if missing_totalpass:
            details.append(
                "TotalPass: " + ", ".join(missing_totalpass)
            )
        raise AgregadorasSourceGapError(
            "No se puede reconstruir el diario sin continuidad de snapshots "
            "canónicos. Faltan " + " | ".join(details)
        )


def _normalize_raw_names(values: Iterable[str | None]) -> tuple[str, ...]:
    unique = {
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    }
    return tuple(sorted(unique, key=str.casefold))


def _load_wellhub_state(snapshot_id: int) -> dict[str, _AccumulatedBranch]:
    rows = (
        IngresosWellhubSnapshotRowORM.query
        .filter(
            IngresosWellhubSnapshotRowORM.snapshot_id == snapshot_id
        )
        .all()
    )

    mutable: dict[str, dict] = {}
    for row in rows:
        canon = str(row.sucursal_canon).strip()
        item = mutable.setdefault(
            canon,
            {
                "visits": 0,
                "amount": Decimal("0"),
                "raw_names": [],
            },
        )
        item["visits"] += int(row.total_checkins_mtd or 0)
        item["amount"] += Decimal(row.pago_total_mtd or 0)
        item["raw_names"].append(row.raw_branch_name)

    return {
        canon: _AccumulatedBranch(
            visits=int(item["visits"]),
            amount=Decimal(item["amount"]),
            raw_names=_normalize_raw_names(item["raw_names"]),
        )
        for canon, item in mutable.items()
    }


def _load_totalpass_state(snapshot_id: int) -> dict[str, _AccumulatedBranch]:
    rows = (
        IngresosTotalpassSnapshotRowORM.query
        .filter(
            IngresosTotalpassSnapshotRowORM.snapshot_id == snapshot_id
        )
        .all()
    )

    result: dict[str, _AccumulatedBranch] = {}
    for row in rows:
        canon = str(row.sucursal_canon).strip()
        if canon in result:
            raise AgregadorasConsolidadoError(
                "TotalPass devolvió más de una fila para "
                f"sucursal_canon={canon!r} snapshot_id={snapshot_id}."
            )
        result[canon] = _AccumulatedBranch(
            visits=int(row.usage_count or 0),
            amount=Decimal(row.monto_acumulado_mes or 0),
            raw_names=_normalize_raw_names([row.raw_branch_name]),
        )
    return result


def _normalize_catalog_text(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _shared_strings_from_zip(source_zip: ZipFile) -> list[str]:
    if SHARED_STRINGS not in source_zip.namelist():
        return []

    root = ET.fromstring(source_zip.read(SHARED_STRINGS))
    result = []
    for shared_item in root.findall(Q("si")):
        result.append("".join(shared_item.itertext()))
    return result


def _cell_text(
    cell: ET.Element,
    shared_strings: list[str],
) -> str:
    cell_type = cell.get("t")

    if cell_type == "s":
        value_node = cell.find(Q("v"))
        if value_node is None or value_node.text is None:
            return ""
        index = int(value_node.text)
        return shared_strings[index] if index < len(shared_strings) else ""

    if cell_type == "inlineStr":
        inline = cell.find(Q("is"))
        return "".join(inline.itertext()) if inline is not None else ""

    value_node = cell.find(Q("v"))
    return value_node.text if value_node is not None and value_node.text else ""


def _excel_date_from_cell(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    try:
        serial = int(Decimal(raw))
        return date(1899, 12, 30) + timedelta(days=serial)
    except Exception:
        pass

    for parser in (
        lambda item: date.fromisoformat(item[:10]),
        lambda item: datetime.strptime(item, "%d/%m/%Y").date(),
    ):
        try:
            return parser(raw)
        except (TypeError, ValueError):
            continue

    raise AgregadorasTemplateInvalidError(
        f"No se pudo interpretar fecha Excel de plantilla: {raw!r}."
    )


def _template_month_state(
    template_bytes: bytes,
    *,
    sheet_name: str,
    baseline_date: date,
) -> dict[str, _AccumulatedBranch]:
    with ZipFile(BytesIO(template_bytes), "r") as source_zip:
        if sheet_name not in source_zip.namelist():
            raise AgregadorasTemplateInvalidError(
                f"La plantilla no contiene {sheet_name}."
            )

        shared_strings = _shared_strings_from_zip(source_zip)
        root = ET.fromstring(source_zip.read(sheet_name))
        sheet_data = root.find(Q("sheetData"))
        if sheet_data is None:
            raise AgregadorasTemplateInvalidError(
                f"La hoja {sheet_name} no contiene sheetData."
            )

        mutable: dict[str, dict] = {}

        for row in list(sheet_data)[1:]:
            values: dict[str, str] = {}
            for cell in row.findall(Q("c")):
                ref = cell.get("r") or ""
                if not ref:
                    continue
                values[ref[0]] = _cell_text(
                    cell,
                    shared_strings,
                ).strip()

            row_date = _excel_date_from_cell(values.get("A", ""))
            if row_date is None:
                continue
            if (
                row_date.year != baseline_date.year
                or row_date.month != baseline_date.month
                or row_date > baseline_date
            ):
                continue

            branch_name = values.get("B", "").strip()
            if not branch_name:
                continue

            key = _normalize_catalog_text(branch_name)
            item = mutable.setdefault(
                key,
                {
                    "visits": 0,
                    "amount": Decimal("0"),
                    "raw_names": [],
                },
            )

            visits_raw = values.get("D", "").strip() or "0"
            amount_raw = values.get("E", "").strip() or "0"

            try:
                item["visits"] += int(Decimal(visits_raw))
                item["amount"] += Decimal(amount_raw)
            except Exception as exc:
                raise AgregadorasTemplateInvalidError(
                    "La plantilla contiene visitas/pago inválidos en "
                    f"{sheet_name}, sucursal={branch_name!r}, "
                    f"fecha={row_date.isoformat()}."
                ) from exc

            item["raw_names"].append(branch_name)

        return {
            key: _AccumulatedBranch(
                visits=int(item["visits"]),
                amount=Decimal(item["amount"]),
                raw_names=_normalize_raw_names(item["raw_names"]),
            )
            for key, item in mutable.items()
        }


def _normalize_branch_match_text(value: str) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        str(value or "").casefold(),
    )
    without_accents = "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )
    cleaned = "".join(
        char if char.isalnum() else " "
        for char in without_accents
    )
    return " ".join(cleaned.split())


def _branch_names_match(
    left: str,
    right: str,
) -> bool:
    left_key = _normalize_branch_match_text(left)
    right_key = _normalize_branch_match_text(right)

    if not left_key or not right_key:
        return False

    if left_key == right_key:
        return True

    return (
        left_key.endswith(" " + right_key)
        or right_key.endswith(" " + left_key)
    )


def _track_aliases_by_normalized_raw(
    *,
    source_family: str,
) -> dict[str, str]:
    rows = (
        TrackBranchAliasORM.query
        .filter(
            TrackBranchAliasORM.source_family == source_family,
            TrackBranchAliasORM.is_active.is_(True),
        )
        .all()
    )

    result: dict[str, str] = {}
    for row in rows:
        key = _normalize_catalog_text(row.raw_branch_name)
        canon = str(row.sucursal_canon).strip()

        existing = result.get(key)
        if existing is not None and existing != canon:
            raise AgregadorasTemplateInvalidError(
                "Alias ambiguo en track_branch_aliases para "
                f"{source_family}: {row.raw_branch_name!r}."
            )

        result[key] = canon

    return result


def _canonicalize_template_baseline(
    *,
    template_baseline: dict[str, _AccumulatedBranch],
    aggregator_code: str,
    source_family: str,
    template_catalog: dict[tuple[str, str], str],
    track_labels: dict[str, str],
) -> dict[str, _AccumulatedBranch]:
    alias_map = _track_aliases_by_normalized_raw(
        source_family=source_family,
    )

    origins_by_display: dict[str, set[str]] = {}
    for (origin_key, catalog_aggregator), display_name in (
        template_catalog.items()
    ):
        if catalog_aggregator != aggregator_code:
            continue

        display_key = _normalize_catalog_text(display_name)
        origins_by_display.setdefault(display_key, set()).add(origin_key)

    canons_by_track_label: dict[str, set[str]] = {}
    for canon, label in track_labels.items():
        canons_by_track_label.setdefault(
            _normalize_catalog_text(label),
            set(),
        ).add(canon)

    mutable: dict[str, dict] = {}
    unresolved: list[str] = []

    for template_key, value in template_baseline.items():
        candidate_origins = set(
            origins_by_display.get(template_key, set())
        )
        candidate_origins.add(template_key)

        candidate_canons = {
            alias_map[origin_key]
            for origin_key in candidate_origins
            if origin_key in alias_map
        }

        if not candidate_canons:
            for origin_key, canon in alias_map.items():
                if _branch_names_match(template_key, origin_key):
                    candidate_canons.add(canon)

        if not candidate_canons:
            for label_key, canons in canons_by_track_label.items():
                if _branch_names_match(template_key, label_key):
                    candidate_canons.update(canons)

        if len(candidate_canons) != 1:
            unresolved.append(
                next(iter(value.raw_names), template_key)
            )
            continue

        canon = next(iter(candidate_canons))
        item = mutable.setdefault(
            canon,
            {
                "visits": 0,
                "amount": Decimal("0"),
                "raw_names": [],
            },
        )
        item["visits"] += value.visits
        item["amount"] += value.amount
        item["raw_names"].extend(value.raw_names)

    if unresolved:
        raise AgregadorasTemplateInvalidError(
            f"No se pudo canonizar baseline {aggregator_code}: "
            + ", ".join(sorted(unresolved, key=str.casefold))
        )

    return {
        canon: _AccumulatedBranch(
            visits=int(item["visits"]),
            amount=Decimal(item["amount"]),
            raw_names=_normalize_raw_names(item["raw_names"]),
        )
        for canon, item in mutable.items()
    }


def _classify_snapshot_gaps(
    *,
    baseline_date: date,
    target_date: date,
    snapshots: dict[date, object],
) -> tuple[list[date], list[date]]:
    available_dates = sorted(
        business_date
        for business_date in snapshots
        if baseline_date < business_date <= target_date
    )
    available_set = set(available_dates)

    absorbed: list[date] = []
    unrecoverable: list[date] = []

    for missing_date in _expected_dates(
        baseline_date + timedelta(days=1),
        target_date,
    ):
        if missing_date in available_set:
            continue

        has_later_same_month = any(
            candidate > missing_date
            and candidate.year == missing_date.year
            and candidate.month == missing_date.month
            for candidate in available_dates
        )
        if has_later_same_month:
            absorbed.append(missing_date)
        else:
            unrecoverable.append(missing_date)

    return absorbed, unrecoverable


def _state_by_display_name(
    *,
    state: dict[str, _AccumulatedBranch],
    aggregator_code: str,
    template_catalog: dict[tuple[str, str], str],
    track_labels: dict[str, str],
) -> tuple[dict[str, _AccumulatedBranch], dict[str, str]]:
    mutable: dict[str, dict] = {}
    labels: dict[str, str] = {}

    for canon, value in state.items():
        display_name = _resolve_display_name(
            canon=canon,
            raw_names=value.raw_names,
            aggregator_code=aggregator_code,
            template_catalog=template_catalog,
            track_labels=track_labels,
        )
        key = _normalize_catalog_text(display_name)
        item = mutable.setdefault(
            key,
            {
                "visits": 0,
                "amount": Decimal("0"),
                "raw_names": [],
            },
        )
        item["visits"] += value.visits
        item["amount"] += value.amount
        item["raw_names"].append(display_name)
        labels[key] = display_name

    return (
        {
            key: _AccumulatedBranch(
                visits=int(item["visits"]),
                amount=Decimal(item["amount"]),
                raw_names=_normalize_raw_names(item["raw_names"]),
            )
            for key, item in mutable.items()
        },
        labels,
    )


def _daily_delta_from_template_baseline(
    *,
    previous_canonical: dict[str, _AccumulatedBranch],
    current: dict[str, _AccumulatedBranch],
    business_date: date,
    aggregator_code: str,
    template_catalog: dict[tuple[str, str], str],
    track_labels: dict[str, str],
) -> list[AgregadoraDailyRow]:
    return _daily_delta(
        previous=previous_canonical,
        current=current,
        business_date=business_date,
        aggregator_code=aggregator_code,
        template_catalog=template_catalog,
        track_labels=track_labels,
    )


def _build_daily_rows_from_snapshots(
    *,
    baseline_date: date,
    target_date: date,
    snapshots: dict[date, object],
    template_baseline: dict[str, _AccumulatedBranch],
    state_loader,
    aggregator_code: str,
    template_catalog: dict[tuple[str, str], str],
    track_labels: dict[str, str],
) -> list[AgregadoraDailyRow]:
    available_dates = sorted(
        business_date
        for business_date in snapshots
        if baseline_date < business_date <= target_date
    )
    if target_date > baseline_date and target_date not in snapshots:
        raise AgregadorasSourceGapError(
            f"{aggregator_code} no tiene snapshot canónico en la fecha "
            f"de corte {target_date.isoformat()}."
        )

    rows: list[AgregadoraDailyRow] = []
    previous_state: dict[str, _AccumulatedBranch] | None = None
    previous_date = baseline_date

    for business_date in available_dates:
        current_state = state_loader(
            int(snapshots[business_date].id)
        )

        if (
            business_date.year != previous_date.year
            or business_date.month != previous_date.month
        ):
            rows.extend(
                _daily_delta(
                    previous={},
                    current=current_state,
                    business_date=business_date,
                    aggregator_code=aggregator_code,
                    template_catalog=template_catalog,
                    track_labels=track_labels,
                )
            )
        elif previous_state is None:
            rows.extend(
                _daily_delta_from_template_baseline(
                    previous_canonical=template_baseline,
                    current=current_state,
                    business_date=business_date,
                    aggregator_code=aggregator_code,
                    template_catalog=template_catalog,
                    track_labels=track_labels,
                )
            )
        else:
            rows.extend(
                _daily_delta(
                    previous=previous_state,
                    current=current_state,
                    business_date=business_date,
                    aggregator_code=aggregator_code,
                    template_catalog=template_catalog,
                    track_labels=track_labels,
                )
            )

        previous_state = current_state
        previous_date = business_date

    return rows


def _template_catalog_map(template_bytes: bytes) -> dict[tuple[str, str], str]:
    with ZipFile(BytesIO(template_bytes), "r") as source_zip:
        if SHEET_CATALOGOS not in source_zip.namelist():
            return {}

        shared_strings = _shared_strings_from_zip(source_zip)
        root = ET.fromstring(source_zip.read(SHEET_CATALOGOS))
        sheet_data = root.find(Q("sheetData"))
        if sheet_data is None:
            return {}

        result: dict[tuple[str, str], str] = {}
        for row in list(sheet_data)[1:]:
            values = {}
            for cell in row.findall(Q("c")):
                ref = cell.get("r") or ""
                if not ref:
                    continue
                values[ref[0]] = _cell_text(cell, shared_strings).strip()

            origin = values.get("A", "")
            display = values.get("B", "")
            aggregator = values.get("C", "").upper()

            if origin and display and aggregator:
                result[(_normalize_catalog_text(origin), aggregator)] = display

        return result


def _track_labels() -> dict[str, str]:
    rows = (
        TrackBranchCatalogORM.query
        .with_entities(
            TrackBranchCatalogORM.sucursal_canon,
            TrackBranchCatalogORM.track_label,
        )
        .all()
    )
    return {
        str(canon).strip(): str(label or canon).strip()
        for canon, label in rows
    }


def _resolve_display_name(
    *,
    canon: str,
    raw_names: tuple[str, ...],
    aggregator_code: str,
    template_catalog: dict[tuple[str, str], str],
    track_labels: dict[str, str],
) -> str:
    for raw_name in raw_names:
        mapped = template_catalog.get(
            (_normalize_catalog_text(raw_name), aggregator_code)
        )
        if mapped:
            return mapped

    label = track_labels.get(canon)
    if label:
        return label

    if raw_names:
        return raw_names[0]

    return canon


def _daily_delta(
    *,
    previous: dict[str, _AccumulatedBranch],
    current: dict[str, _AccumulatedBranch],
    business_date: date,
    aggregator_code: str,
    template_catalog: dict[tuple[str, str], str],
    track_labels: dict[str, str],
) -> list[AgregadoraDailyRow]:
    rows: list[AgregadoraDailyRow] = []

    missing_current = [
        canon
        for canon, previous_value in previous.items()
        if canon not in current
        and (
            previous_value.visits != 0
            or previous_value.amount != Decimal("0")
        )
    ]
    if missing_current:
        raise AgregadorasSourceRegressionError(
            f"{aggregator_code} perdió sucursales acumuladas en "
            f"{business_date.isoformat()}: {', '.join(sorted(missing_current))}"
        )

    for canon, current_value in current.items():
        previous_value = previous.get(
            canon,
            _AccumulatedBranch(
                visits=0,
                amount=Decimal("0"),
                raw_names=(),
            ),
        )

        visits = current_value.visits - previous_value.visits
        amount = current_value.amount - previous_value.amount

        if (
            aggregator_code != "WH"
            and (visits < 0 or amount < Decimal("0"))
        ):
            raise AgregadorasSourceRegressionError(
                f"{aggregator_code} presentó retroceso MTD para "
                f"{canon} en {business_date.isoformat()}: "
                f"visits={visits}, amount={amount}."
            )

        if visits == 0 and amount == Decimal("0"):
            continue

        rows.append(
            AgregadoraDailyRow(
                business_date=business_date,
                branch_name=_resolve_display_name(
                    canon=canon,
                    raw_names=current_value.raw_names,
                    aggregator_code=aggregator_code,
                    template_catalog=template_catalog,
                    track_labels=track_labels,
                ),
                visits=visits,
                amount=amount,
            )
        )

    rows.sort(key=lambda row: row.branch_name.casefold())
    return rows


def _excel_serial(value: date) -> int:
    return (value - date(1899, 12, 30)).days


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _append_inline_string(
    row: ET.Element,
    *,
    cell_ref: str,
    value: str,
) -> None:
    cell = ET.SubElement(row, Q("c"), {"r": cell_ref, "t": "inlineStr"})
    inline = ET.SubElement(cell, Q("is"))
    text = ET.SubElement(inline, Q("t"))
    if value != value.strip():
        text.set(f"{{{XML_NS}}}space", "preserve")
    text.text = value


def _append_numeric(
    row: ET.Element,
    *,
    cell_ref: str,
    value: str | int,
    style: str | None = None,
) -> None:
    attrs = {"r": cell_ref}
    if style is not None:
        attrs["s"] = style
    cell = ET.SubElement(row, Q("c"), attrs)
    ET.SubElement(cell, Q("v")).text = str(value)


def _preserve_root_namespace_declarations(
    original_xml: bytes,
    rendered_xml: bytes,
    *,
    root_tag: str,
) -> bytes:
    original_text = original_xml.decode("utf-8")
    rendered_text = rendered_xml.decode("utf-8")

    original_root = re.search(
        rf"<{re.escape(root_tag)}\\b[^>]*>",
        original_text,
    )
    rendered_root = re.search(
        rf"<{re.escape(root_tag)}\\b[^>]*>",
        rendered_text,
    )

    if original_root is None or rendered_root is None:
        raise AgregadorasTemplateInvalidError(
            f"No se pudo preservar namespaces de <{root_tag}>."
        )

    original_declarations = re.findall(
        r'\\s(xmlns(?::[A-Za-z_][\\w.-]*)?="[^"]+")',
        original_root.group(0),
    )
    rendered_root_text = rendered_root.group(0)

    missing_declarations = []
    for declaration in original_declarations:
        attribute_name = declaration.split("=", 1)[0]
        if re.search(
            rf"\\s{re.escape(attribute_name)}=",
            rendered_root_text,
        ):
            continue
        missing_declarations.append(declaration)

    if not missing_declarations:
        return rendered_xml

    insertion = "".join(
        f" {declaration}"
        for declaration in missing_declarations
    )
    insert_at = rendered_root.end() - 1
    patched = (
        rendered_text[:insert_at]
        + insertion
        + rendered_text[insert_at:]
    )
    return patched.encode("utf-8")


def _remove_calc_chain_relationship(
    relationships_xml: bytes,
) -> bytes:
    root = ET.fromstring(relationships_xml)
    removed = False

    for relationship in list(root):
        relationship_type = str(
            relationship.get("Type") or ""
        )
        if relationship_type.endswith("/calcChain"):
            root.remove(relationship)
            removed = True

    if not removed:
        return relationships_xml

    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _remove_calc_chain_content_type(
    content_types_xml: bytes,
) -> bytes:
    root = ET.fromstring(content_types_xml)
    removed = False

    for override in list(root):
        if override.get("PartName") == "/xl/calcChain.xml":
            root.remove(override)
            removed = True

    if not removed:
        return content_types_xml

    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _append_source_rows(
    sheet_xml: bytes,
    rows_to_add: list[AgregadoraDailyRow],
    *,
    aggregator_code: str,
) -> bytes:
    root = ET.fromstring(sheet_xml)
    sheet_data = root.find(Q("sheetData"))
    if sheet_data is None:
        raise AgregadorasTemplateInvalidError(
            "La hoja fuente no contiene sheetData."
        )

    existing_rows = sheet_data.findall(Q("row"))
    if not existing_rows:
        raise AgregadorasTemplateInvalidError(
            "La hoja fuente no contiene filas."
        )

    next_row_number = max(
        int(row.get("r") or 0)
        for row in existing_rows
    ) + 1

    for daily_row in rows_to_add:
        row_number = next_row_number
        next_row_number += 1
        row = ET.SubElement(
            sheet_data,
            Q("row"),
            {"r": str(row_number)},
        )

        _append_numeric(
            row,
            cell_ref=f"A{row_number}",
            value=_excel_serial(daily_row.business_date),
            style="1",
        )
        _append_inline_string(
            row,
            cell_ref=f"B{row_number}",
            value=daily_row.branch_name,
        )
        _append_inline_string(
            row,
            cell_ref=f"C{row_number}",
            value=aggregator_code,
        )
        _append_numeric(
            row,
            cell_ref=f"D{row_number}",
            value=daily_row.visits,
        )
        _append_numeric(
            row,
            cell_ref=f"E{row_number}",
            value=_decimal_text(daily_row.amount),
            style="5",
        )

    last_row = next_row_number - 1
    dimension = root.find(Q("dimension"))
    if dimension is not None:
        dimension.set("ref", f"A1:E{last_row}")

    auto_filter = root.find(Q("autoFilter"))
    if auto_filter is not None:
        auto_filter.set("ref", f"A1:E{last_row}")

    rendered_xml = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    return _preserve_root_namespace_declarations(
        sheet_xml,
        rendered_xml,
        root_tag="worksheet",
    )


def _append_todo_rows(
    sheet_xml: bytes,
    rows_to_add: list[tuple[str, AgregadoraDailyRow]],
) -> tuple[bytes, int]:
    root = ET.fromstring(sheet_xml)
    sheet_data = root.find(Q("sheetData"))
    if sheet_data is None:
        raise AgregadorasTemplateInvalidError(
            "La hoja todo no contiene sheetData."
        )

    existing_rows = sheet_data.findall(Q("row"))
    if not existing_rows:
        raise AgregadorasTemplateInvalidError(
            "La hoja todo no contiene filas."
        )

    next_row_number = max(
        int(row.get("r") or 0)
        for row in existing_rows
    ) + 1

    for aggregator_name, daily_row in rows_to_add:
        row_number = next_row_number
        next_row_number += 1
        row = ET.SubElement(
            sheet_data,
            Q("row"),
            {"r": str(row_number)},
        )

        _append_numeric(
            row,
            cell_ref=f"A{row_number}",
            value=_excel_serial(daily_row.business_date),
            style="7",
        )
        _append_inline_string(
            row,
            cell_ref=f"B{row_number}",
            value=daily_row.branch_name,
        )
        _append_inline_string(
            row,
            cell_ref=f"C{row_number}",
            value=aggregator_name,
        )
        _append_numeric(
            row,
            cell_ref=f"D{row_number}",
            value=daily_row.visits,
        )
        _append_numeric(
            row,
            cell_ref=f"E{row_number}",
            value=_decimal_text(daily_row.amount),
            style="5",
        )

        formula_cell = ET.SubElement(
            row,
            Q("c"),
            {"r": f"F{row_number}", "t": "str"},
        )
        ET.SubElement(formula_cell, Q("f")).text = (
            'TEXT(Tabla1[[#This Row],[Fecha]],"dd")'
        )
        ET.SubElement(formula_cell, Q("v")).text = (
            f"{daily_row.business_date.day:02d}"
        )

    last_row = next_row_number - 1
    dimension = root.find(Q("dimension"))
    if dimension is not None:
        dimension.set("ref", f"A1:F{last_row}")

    rendered_xml = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    return (
        _preserve_root_namespace_declarations(
            sheet_xml,
            rendered_xml,
            root_tag="worksheet",
        ),
        last_row,
    )


def _update_table_ref(table_xml: bytes, last_row: int) -> bytes:
    root = ET.fromstring(table_xml)
    table_ref = f"A1:F{last_row}"
    root.set("ref", table_ref)

    auto_filter = root.find(Q("autoFilter"))
    if auto_filter is not None:
        auto_filter.set("ref", table_ref)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _mark_pivot_refresh(pivot_xml: bytes) -> bytes:
    root = ET.fromstring(pivot_xml)
    root.set("refreshOnLoad", "1")
    root.set("enableRefresh", "1")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _validate_template_parts(names: set[str]) -> None:
    required = {
        SHEET_WELLHUB,
        SHEET_TOTALPASS,
        SHEET_TODO,
        SHEET_CATALOGOS,
        TABLE_TODO,
        PIVOT_CACHE_DEFINITION,
    }
    missing = sorted(required.difference(names))
    if missing:
        raise AgregadorasTemplateInvalidError(
            "La plantilla no conserva las piezas requeridas: "
            + ", ".join(missing)
        )


def _render_workbook(
    *,
    template_bytes: bytes,
    wellhub_rows: list[AgregadoraDailyRow],
    totalpass_rows: list[AgregadoraDailyRow],
) -> bytes:
    source_buffer = BytesIO(template_bytes)
    output_buffer = BytesIO()

    with ZipFile(source_buffer, "r") as source_zip:
        _validate_template_parts(set(source_zip.namelist()))

        replacements: dict[str, bytes] = {}
        replacements[SHEET_WELLHUB] = _append_source_rows(
            source_zip.read(SHEET_WELLHUB),
            wellhub_rows,
            aggregator_code="WH",
        )
        replacements[SHEET_TOTALPASS] = _append_source_rows(
            source_zip.read(SHEET_TOTALPASS),
            totalpass_rows,
            aggregator_code="TP",
        )

        todo_rows = [
            ("Wellhub", row)
            for row in wellhub_rows
        ] + [
            ("Totalpass", row)
            for row in totalpass_rows
        ]
        todo_rows.sort(
            key=lambda item: (
                item[1].business_date,
                item[0],
                item[1].branch_name.casefold(),
            )
        )

        todo_xml, todo_last_row = _append_todo_rows(
            source_zip.read(SHEET_TODO),
            todo_rows,
        )
        replacements[SHEET_TODO] = todo_xml
        replacements[TABLE_TODO] = _update_table_ref(
            source_zip.read(TABLE_TODO),
            todo_last_row,
        )
        replacements[PIVOT_CACHE_DEFINITION] = _mark_pivot_refresh(
            source_zip.read(PIVOT_CACHE_DEFINITION)
        )

        if WORKBOOK_RELS in source_zip.namelist():
            replacements[WORKBOOK_RELS] = _remove_calc_chain_relationship(
                source_zip.read(WORKBOOK_RELS)
            )

        if CONTENT_TYPES in source_zip.namelist():
            replacements[CONTENT_TYPES] = _remove_calc_chain_content_type(
                source_zip.read(CONTENT_TYPES)
            )

        with ZipFile(output_buffer, "w") as output_zip:
            for info in source_zip.infolist():
                if info.filename == CALC_CHAIN:
                    continue

                data = replacements.get(
                    info.filename,
                    source_zip.read(info.filename),
                )
                output_zip.writestr(info, data)

    return output_buffer.getvalue()


def _source_signature(
    *,
    template_upload_id: int,
    baseline_date: date,
    target_date: date,
    wellhub_snapshots: dict[date, IngresosWellhubSnapshotORM],
    totalpass_snapshots: dict[date, IngresosTotalpassSnapshotORM],
) -> str:
    parts = [
        f"template:{template_upload_id}",
        f"baseline:{baseline_date.isoformat()}",
        f"target:{target_date.isoformat()}",
        "gap_policy:absorb_into_next_available_same_month_v1",
        f"renderer:{RENDERER_VERSION}",
    ]

    for business_date, snapshot in sorted(wellhub_snapshots.items()):
        if baseline_date < business_date <= target_date:
            parts.append(
                f"WH:{business_date.isoformat()}:{snapshot.id}"
            )

    for business_date, snapshot in sorted(totalpass_snapshots.items()):
        if baseline_date < business_date <= target_date:
            parts.append(
                f"TP:{business_date.isoformat()}:{snapshot.id}"
            )

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _read_metadata() -> dict | None:
    path = _metadata_path()
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_atomic(path: Path, content: bytes) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_bytes(content)
    os.replace(temp_path, path)


def _write_metadata_atomic(metadata: dict) -> None:
    path = _metadata_path()
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _download_filename(cutoff_date: date) -> str:
    months = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }
    return (
        "Agregadoras 1 enero - "
        f"{cutoff_date.day} {months[cutoff_date.month]} "
        f"{cutoff_date.year}.xlsx"
    )


def generate_agregadoras_consolidado(
    *,
    target_date: date | None = None,
) -> dict:
    template_upload = _latest_template_upload()
    if template_upload is None:
        raise AgregadorasTemplateMissingError(
            "No existe una plantilla activa de consolidado de agregadoras "
            "en Warehouse."
        )

    if template_upload.cutoff_date is None:
        raise AgregadorasTemplateInvalidError(
            "La plantilla debe tener cutoff_date; ese corte define el baseline."
        )

    template_path = _resolve_upload_file_path(template_upload)
    if not template_path.exists():
        raise AgregadorasTemplateMissingError(
            "El upload de plantilla existe en BD pero el archivo físico "
            f"no está disponible: {template_path}"
        )

    baseline_date = template_upload.cutoff_date
    resolved_target_date = target_date or _latest_common_canonical_date()
    if resolved_target_date is None:
        raise AgregadorasSourceGapError(
            "Todavía no existe una fecha con snapshots canónicos de "
            "Wellhub y TotalPass."
        )

    if resolved_target_date < baseline_date:
        resolved_target_date = baseline_date

    wellhub_snapshots = _canonical_snapshots_by_date(
        IngresosWellhubSnapshotORM,
        baseline_date + timedelta(days=1),
        resolved_target_date,
    )
    totalpass_snapshots = _canonical_snapshots_by_date(
        IngresosTotalpassSnapshotORM,
        baseline_date + timedelta(days=1),
        resolved_target_date,
    )

    if resolved_target_date > baseline_date:
        missing_target = []
        if resolved_target_date not in wellhub_snapshots:
            missing_target.append("Wellhub")
        if resolved_target_date not in totalpass_snapshots:
            missing_target.append("TotalPass")
        if missing_target:
            raise AgregadorasSourceGapError(
                "La fecha de corte debe tener snapshot canónico de ambas "
                "agregadoras. Faltan: " + ", ".join(missing_target)
            )

    wellhub_absorbed, wellhub_unrecoverable = _classify_snapshot_gaps(
        baseline_date=baseline_date,
        target_date=resolved_target_date,
        snapshots=wellhub_snapshots,
    )
    totalpass_absorbed, totalpass_unrecoverable = _classify_snapshot_gaps(
        baseline_date=baseline_date,
        target_date=resolved_target_date,
        snapshots=totalpass_snapshots,
    )

    if wellhub_unrecoverable or totalpass_unrecoverable:
        details = []
        if wellhub_unrecoverable:
            details.append(
                "Wellhub: "
                + ", ".join(
                    item.isoformat()
                    for item in wellhub_unrecoverable
                )
            )
        if totalpass_unrecoverable:
            details.append(
                "TotalPass: "
                + ", ".join(
                    item.isoformat()
                    for item in totalpass_unrecoverable
                )
            )
        raise AgregadorasSourceGapError(
            "Hay huecos al final de un mes que no pueden absorberse en "
            "un snapshot posterior del mismo mes. " + " | ".join(details)
        )

    signature = _source_signature(
        template_upload_id=int(template_upload.id),
        baseline_date=baseline_date,
        target_date=resolved_target_date,
        wellhub_snapshots=wellhub_snapshots,
        totalpass_snapshots=totalpass_snapshots,
    )

    existing_metadata = _read_metadata()
    if (
        _output_path().exists()
        and existing_metadata
        and existing_metadata.get("source_signature") == signature
    ):
        return {
            "status": "up_to_date",
            **existing_metadata,
            "output_path": str(_output_path()),
        }

    template_bytes = template_path.read_bytes()
    template_catalog = _template_catalog_map(template_bytes)
    track_labels = _track_labels()

    wellhub_template_baseline = _canonicalize_template_baseline(
        template_baseline=_template_month_state(
            template_bytes,
            sheet_name=SHEET_WELLHUB,
            baseline_date=baseline_date,
        ),
        aggregator_code="WH",
        source_family="wellhub_family",
        template_catalog=template_catalog,
        track_labels=track_labels,
    )
    totalpass_template_baseline = _canonicalize_template_baseline(
        template_baseline=_template_month_state(
            template_bytes,
            sheet_name=SHEET_TOTALPASS,
            baseline_date=baseline_date,
        ),
        aggregator_code="TP",
        source_family="totalpass_family",
        template_catalog=template_catalog,
        track_labels=track_labels,
    )

    wellhub_rows = _build_daily_rows_from_snapshots(
        baseline_date=baseline_date,
        target_date=resolved_target_date,
        snapshots=wellhub_snapshots,
        template_baseline=wellhub_template_baseline,
        state_loader=_load_wellhub_state,
        aggregator_code="WH",
        template_catalog=template_catalog,
        track_labels=track_labels,
    )
    totalpass_rows = _build_daily_rows_from_snapshots(
        baseline_date=baseline_date,
        target_date=resolved_target_date,
        snapshots=totalpass_snapshots,
        template_baseline=totalpass_template_baseline,
        state_loader=_load_totalpass_state,
        aggregator_code="TP",
        template_catalog=template_catalog,
        track_labels=track_labels,
    )

    output_bytes = _render_workbook(
        template_bytes=template_bytes,
        wellhub_rows=wellhub_rows,
        totalpass_rows=totalpass_rows,
    )
    _write_atomic(_output_path(), output_bytes)

    metadata = {
        "status": "generated",
        "template_upload_id": int(template_upload.id),
        "template_cutoff_date": baseline_date.isoformat(),
        "cutoff_date": resolved_target_date.isoformat(),
        "source_signature": signature,
        "generated_at": _utc_now().isoformat(),
        "gap_policy": "absorb_into_next_available_same_month",
        "absorbed_gap_dates_wellhub": [
            item.isoformat()
            for item in wellhub_absorbed
        ],
        "absorbed_gap_dates_totalpass": [
            item.isoformat()
            for item in totalpass_absorbed
        ],
        "wellhub_correction_dates": sorted(
            {
                row.business_date.isoformat()
                for row in wellhub_rows
                if row.visits < 0 or row.amount < Decimal("0")
            }
        ),
        "wellhub_rows_added": len(wellhub_rows),
        "totalpass_rows_added": len(totalpass_rows),
        "todo_rows_added": len(wellhub_rows) + len(totalpass_rows),
        "download_filename": _download_filename(resolved_target_date),
        "file_size_bytes": len(output_bytes),
    }
    _write_metadata_atomic(metadata)

    return {
        **metadata,
        "output_path": str(_output_path()),
    }

def get_agregadoras_consolidado_status() -> dict:
    template_upload = _latest_template_upload()
    latest_ready_date = _latest_common_canonical_date()
    metadata = _read_metadata()
    output_exists = _output_path().exists()

    return {
        "template_ready": bool(template_upload),
        "template_upload_id": (
            int(template_upload.id)
            if template_upload is not None
            else None
        ),
        "template_cutoff_date": (
            template_upload.cutoff_date.isoformat()
            if template_upload is not None
            and template_upload.cutoff_date is not None
            else None
        ),
        "latest_ready_date": (
            latest_ready_date.isoformat()
            if latest_ready_date is not None
            else None
        ),
        "generated": bool(metadata and output_exists),
        "cutoff_date": (
            metadata.get("cutoff_date")
            if metadata
            else None
        ),
        "generated_at": (
            metadata.get("generated_at")
            if metadata
            else None
        ),
        "download_filename": (
            metadata.get("download_filename")
            if metadata
            else None
        ),
        "file_size_bytes": (
            metadata.get("file_size_bytes")
            if metadata
            else None
        ),
        "wellhub_rows_added": (
            metadata.get("wellhub_rows_added")
            if metadata
            else None
        ),
        "totalpass_rows_added": (
            metadata.get("totalpass_rows_added")
            if metadata
            else None
        ),
    }


def get_agregadoras_consolidado_download() -> tuple[Path, str]:
    metadata = _read_metadata()
    path = _output_path()

    if not metadata or not path.exists():
        raise AgregadorasConsolidadoError(
            "Todavía no existe un consolidado generado para descargar."
        )

    filename = metadata.get("download_filename")
    if not filename:
        cutoff_raw = metadata.get("cutoff_date")
        cutoff_date = (
            date.fromisoformat(cutoff_raw)
            if cutoff_raw
            else date.today()
        )
        filename = _download_filename(cutoff_date)

    return path, str(filename)
