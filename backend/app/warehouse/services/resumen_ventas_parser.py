from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


RESUMEN_VENTAS_REPORT_TYPE_KEY = "resumen_ventas"
SUMMARY_SHEET = "Resumen ventas"
NO_CONTRACT_SHEET = "Tarifas Sin Contrato"
CONTRACT_SHEET = "Tarifas con Contrato"
REQUIRED_SHEETS = (SUMMARY_SHEET, NO_CONTRACT_SHEET, CONTRACT_SHEET)
ROW_KIND_TARIFF = "TARIFF"
ROW_KIND_BRANCH = "BRANCH"
SALES_MODE_CONTRACT = "CONTRACT"
SALES_MODE_NO_CONTRACT = "NO_CONTRACT"


class ResumenVentasParserError(RuntimeError):
    pass


class ResumenVentasLayoutError(ResumenVentasParserError):
    pass


class ResumenVentasContentError(ResumenVentasParserError):
    pass


@dataclass(frozen=True, slots=True)
class ResumenVentasParsedRow:
    row_index: int
    source_sheet: str
    source_row_number: int
    row_kind: str
    tariff_row_index: int
    sales_mode: str
    family: str | None
    contract_type: str | None
    plan_type: str | None
    tariff_name: str
    source_cost: Decimal | None
    monthly_equivalent: Decimal | None
    free_months_raw: str | None
    branch_raw: str | None
    current_quantity: Decimal
    current_flow: Decimal
    comparison_quantity: Decimal
    comparison_flow: Decimal


@dataclass(frozen=True, slots=True)
class ResumenVentasParseResult:
    report_type_key: str = RESUMEN_VENTAS_REPORT_TYPE_KEY
    current_label: str = ""
    comparison_label: str = ""
    rows: tuple[ResumenVentasParsedRow, ...] = field(default_factory=tuple)
    row_count_detected: int = 0
    row_count_valid: int = 0
    row_count_rejected: int = 0
    summary_totals: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)


def register_resumen_ventas_parser(app) -> None:
    app.config["WAREHOUSE_RESUMEN_VENTAS_PARSER"] = parse_resumen_ventas_xlsx


def parse_resumen_ventas_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> ResumenVentasParseResult:
    sheets = _read_sheets(file_path=file_path, file_bytes=file_bytes)
    _validate_required_sheets(sheets)

    current_label, comparison_label = _resolve_period_labels(sheets)
    summary_totals = _parse_summary_totals(sheets[SUMMARY_SHEET])

    rows: list[ResumenVentasParsedRow] = []
    rows.extend(
        _parse_no_contract_sheet(
            sheets[NO_CONTRACT_SHEET],
            start_index=0,
        )
    )
    rows.extend(
        _parse_contract_sheet(
            sheets[CONTRACT_SHEET],
            start_index=len(rows),
        )
    )

    if not rows:
        raise ResumenVentasContentError(
            "El archivo Resumen Ventas no contiene tarifas válidas."
        )

    tariff_rows = [row for row in rows if row.row_kind == ROW_KIND_TARIFF]
    branch_rows = [row for row in rows if row.row_kind == ROW_KIND_BRANCH]

    contract_current = sum(
        (
            row.current_flow
            for row in tariff_rows
            if row.sales_mode == SALES_MODE_CONTRACT
        ),
        Decimal("0"),
    )
    contract_comparison = sum(
        (
            row.comparison_flow
            for row in tariff_rows
            if row.sales_mode == SALES_MODE_CONTRACT
        ),
        Decimal("0"),
    )
    no_contract_current = sum(
        (
            row.current_flow
            for row in tariff_rows
            if row.sales_mode == SALES_MODE_NO_CONTRACT
        ),
        Decimal("0"),
    )
    no_contract_comparison = sum(
        (
            row.comparison_flow
            for row in tariff_rows
            if row.sales_mode == SALES_MODE_NO_CONTRACT
        ),
        Decimal("0"),
    )

    summary_contract_current = (
        summary_totals["first_contract_payment"]["current"]
        + summary_totals["subsequent_contract_payments"]["current"]
    )
    summary_contract_comparison = (
        summary_totals["first_contract_payment"]["comparison"]
        + summary_totals["subsequent_contract_payments"]["comparison"]
    )
    summary_no_contract_current = summary_totals["no_contract_payments"]["current"]
    summary_no_contract_comparison = summary_totals["no_contract_payments"][
        "comparison"
    ]

    tariff_branch_mismatches = _count_tariff_branch_mismatches(
        tariff_rows,
        branch_rows,
    )
    tolerance = Decimal("0.01")
    contract_delta_current = contract_current - summary_contract_current
    contract_delta_comparison = contract_comparison - summary_contract_comparison
    no_contract_delta_current = no_contract_current - summary_no_contract_current
    no_contract_delta_comparison = (
        no_contract_comparison - summary_no_contract_comparison
    )

    reconciliation_ok = all(
        abs(value) <= tolerance
        for value in (
            contract_delta_current,
            contract_delta_comparison,
            no_contract_delta_current,
            no_contract_delta_comparison,
        )
    ) and tariff_branch_mismatches == 0

    data_quality = {
        "reconciliation_status": "ok" if reconciliation_ok else "warning",
        "tariff_rows": len(tariff_rows),
        "branch_rows": len(branch_rows),
        "tariff_branch_mismatch_count": tariff_branch_mismatches,
        "contract_delta_current": contract_delta_current,
        "contract_delta_comparison": contract_delta_comparison,
        "no_contract_delta_current": no_contract_delta_current,
        "no_contract_delta_comparison": no_contract_delta_comparison,
    }

    detected = sum(len(sheet.index) for sheet in sheets.values())
    return ResumenVentasParseResult(
        current_label=current_label,
        comparison_label=comparison_label,
        rows=tuple(rows),
        row_count_detected=detected,
        row_count_valid=len(rows),
        row_count_rejected=0,
        summary_totals=summary_totals,
        data_quality=data_quality,
    )


def _read_sheets(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> dict[str, pd.DataFrame]:
    if not file_path and file_bytes is None:
        raise ResumenVentasParserError("Se requiere 'file_path' o 'file_bytes'.")

    try:
        source = (
            BytesIO(file_bytes)
            if file_bytes is not None
            else Path(file_path)  # type: ignore[arg-type]
        )
        excel_file = pd.ExcelFile(source)
        return {
            sheet_name: pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
                header=None,
            )
            for sheet_name in excel_file.sheet_names
        }
    except Exception as exc:
        raise ResumenVentasLayoutError(
            "No se pudo leer el XLSX Resumen Ventas."
        ) from exc


def _validate_required_sheets(sheets: dict[str, pd.DataFrame]) -> None:
    missing = [name for name in REQUIRED_SHEETS if name not in sheets]
    if missing:
        raise ResumenVentasLayoutError(
            f"Faltan hojas obligatorias en Resumen Ventas: {missing!r}."
        )


def _resolve_period_labels(
    sheets: dict[str, pd.DataFrame],
) -> tuple[str, str]:
    candidates = (
        (
            _text(_cell(sheets[SUMMARY_SHEET], 0, 2)),
            _text(_cell(sheets[SUMMARY_SHEET], 0, 4)),
        ),
        (
            _text(_cell(sheets[NO_CONTRACT_SHEET], 0, 5)),
            _text(_cell(sheets[NO_CONTRACT_SHEET], 0, 7)),
        ),
        (
            _text(_cell(sheets[CONTRACT_SHEET], 0, 4)),
            _text(_cell(sheets[CONTRACT_SHEET], 0, 6)),
        ),
    )
    normalized = [
        (_normalize_label(current), _normalize_label(comparison))
        for current, comparison in candidates
    ]
    if any(not current or not comparison for current, comparison in normalized):
        raise ResumenVentasLayoutError(
            "No se pudieron resolver los periodos comparativos."
        )
    if len(set(normalized)) != 1:
        raise ResumenVentasLayoutError(
            "Las hojas no comparten el mismo periodo comparativo: "
            f"{candidates!r}."
        )
    return candidates[0]


SUMMARY_TOTAL_LABELS = {
    "Total de primer pago contrato": "first_contract_payment",
    "Total Contratos segundo pago en adelante": "subsequent_contract_payments",
    "Total de pagos sin contrato": "no_contract_payments",
    "Total de penalizaciones": "penalties",
    "Total de Inscripciones": "enrollments",
    "Total de agregadoras": "aggregators",
    "Total de lockers": "lockers",
    "Total de tienda": "store",
    "Gran Total": "grand_total",
}


def _parse_summary_totals(
    df: pd.DataFrame,
) -> dict[str, dict[str, Decimal]]:
    found: dict[str, dict[str, Decimal]] = {}
    for row_index in range(len(df.index)):
        label = _text(_cell(df, row_index, 1))
        key = SUMMARY_TOTAL_LABELS.get(label)
        if key is None:
            continue
        found[key] = {
            "current": _decimal(
                _cell(df, row_index, 2),
                default=Decimal("0"),
            ),
            "comparison": _decimal(
                _cell(df, row_index, 4),
                default=Decimal("0"),
            ),
        }

    missing = [key for key in SUMMARY_TOTAL_LABELS.values() if key not in found]
    if missing:
        raise ResumenVentasLayoutError(
            "Resumen ventas no contiene todos los totales contractuales: "
            f"{missing!r}."
        )
    return found


def _parse_no_contract_sheet(
    df: pd.DataFrame,
    *,
    start_index: int,
) -> list[ResumenVentasParsedRow]:
    rows: list[ResumenVentasParsedRow] = []
    family: str | None = None
    tariff_context: ResumenVentasParsedRow | None = None

    for source_idx in range(2, len(df.index)):
        col_a = _text(_cell(df, source_idx, 0))
        col_b = _text(_cell(df, source_idx, 1))
        col_c = _text(_cell(df, source_idx, 2))
        col_d = _optional_decimal(_cell(df, source_idx, 3))
        col_e = _optional_decimal(_cell(df, source_idx, 4))

        if col_b.startswith("Total ") or col_b.startswith("Gran Total"):
            tariff_context = None
            continue

        if col_a:
            family = col_a

        if col_b and col_c and col_d is not None:
            row_index = start_index + len(rows)
            tariff_context = ResumenVentasParsedRow(
                row_index=row_index,
                source_sheet=NO_CONTRACT_SHEET,
                source_row_number=source_idx + 1,
                row_kind=ROW_KIND_TARIFF,
                tariff_row_index=row_index,
                sales_mode=SALES_MODE_NO_CONTRACT,
                family=family,
                contract_type=None,
                plan_type=col_b,
                tariff_name=col_c,
                source_cost=col_d,
                monthly_equivalent=col_e,
                free_months_raw=None,
                branch_raw=None,
                current_quantity=_decimal(
                    _cell(df, source_idx, 5),
                    default=Decimal("0"),
                ),
                current_flow=_decimal(
                    _cell(df, source_idx, 6),
                    default=Decimal("0"),
                ),
                comparison_quantity=_decimal(
                    _cell(df, source_idx, 7),
                    default=Decimal("0"),
                ),
                comparison_flow=_decimal(
                    _cell(df, source_idx, 8),
                    default=Decimal("0"),
                ),
            )
            rows.append(tariff_context)
            continue

        if (
            tariff_context is not None
            and col_c
            and not col_b
            and col_d is None
            and col_e is None
        ):
            rows.append(
                ResumenVentasParsedRow(
                    row_index=start_index + len(rows),
                    source_sheet=NO_CONTRACT_SHEET,
                    source_row_number=source_idx + 1,
                    row_kind=ROW_KIND_BRANCH,
                    tariff_row_index=tariff_context.tariff_row_index,
                    sales_mode=SALES_MODE_NO_CONTRACT,
                    family=tariff_context.family,
                    contract_type=None,
                    plan_type=tariff_context.plan_type,
                    tariff_name=tariff_context.tariff_name,
                    source_cost=tariff_context.source_cost,
                    monthly_equivalent=tariff_context.monthly_equivalent,
                    free_months_raw=None,
                    branch_raw=col_c,
                    current_quantity=_decimal(
                        _cell(df, source_idx, 5),
                        default=Decimal("0"),
                    ),
                    current_flow=_decimal(
                        _cell(df, source_idx, 6),
                        default=Decimal("0"),
                    ),
                    comparison_quantity=_decimal(
                        _cell(df, source_idx, 7),
                        default=Decimal("0"),
                    ),
                    comparison_flow=_decimal(
                        _cell(df, source_idx, 8),
                        default=Decimal("0"),
                    ),
                )
            )

    return rows


def _parse_contract_sheet(
    df: pd.DataFrame,
    *,
    start_index: int,
) -> list[ResumenVentasParsedRow]:
    rows: list[ResumenVentasParsedRow] = []
    contract_type: str | None = None
    tariff_context: ResumenVentasParsedRow | None = None

    for source_idx in range(2, len(df.index)):
        col_a = _text(_cell(df, source_idx, 0))
        col_b = _text(_cell(df, source_idx, 1))
        col_c = _optional_decimal(_cell(df, source_idx, 2))
        col_d_text = _optional_text(_cell(df, source_idx, 3))

        if col_b.startswith("Total ") or col_b.startswith("Gran Total"):
            tariff_context = None
            continue

        if col_a:
            contract_type = col_a

        if col_b and col_c is not None:
            row_index = start_index + len(rows)
            tariff_context = ResumenVentasParsedRow(
                row_index=row_index,
                source_sheet=CONTRACT_SHEET,
                source_row_number=source_idx + 1,
                row_kind=ROW_KIND_TARIFF,
                tariff_row_index=row_index,
                sales_mode=SALES_MODE_CONTRACT,
                family=None,
                contract_type=contract_type,
                plan_type=None,
                tariff_name=col_b,
                source_cost=col_c,
                monthly_equivalent=None,
                free_months_raw=col_d_text,
                branch_raw=None,
                current_quantity=_decimal(
                    _cell(df, source_idx, 4),
                    default=Decimal("0"),
                ),
                current_flow=_decimal(
                    _cell(df, source_idx, 5),
                    default=Decimal("0"),
                ),
                comparison_quantity=_decimal(
                    _cell(df, source_idx, 6),
                    default=Decimal("0"),
                ),
                comparison_flow=_decimal(
                    _cell(df, source_idx, 7),
                    default=Decimal("0"),
                ),
            )
            rows.append(tariff_context)
            continue

        if tariff_context is not None and col_b and col_c is None:
            rows.append(
                ResumenVentasParsedRow(
                    row_index=start_index + len(rows),
                    source_sheet=CONTRACT_SHEET,
                    source_row_number=source_idx + 1,
                    row_kind=ROW_KIND_BRANCH,
                    tariff_row_index=tariff_context.tariff_row_index,
                    sales_mode=SALES_MODE_CONTRACT,
                    family=None,
                    contract_type=tariff_context.contract_type,
                    plan_type=None,
                    tariff_name=tariff_context.tariff_name,
                    source_cost=tariff_context.source_cost,
                    monthly_equivalent=None,
                    free_months_raw=tariff_context.free_months_raw,
                    branch_raw=col_b,
                    current_quantity=_decimal(
                        _cell(df, source_idx, 4),
                        default=Decimal("0"),
                    ),
                    current_flow=_decimal(
                        _cell(df, source_idx, 5),
                        default=Decimal("0"),
                    ),
                    comparison_quantity=_decimal(
                        _cell(df, source_idx, 6),
                        default=Decimal("0"),
                    ),
                    comparison_flow=_decimal(
                        _cell(df, source_idx, 7),
                        default=Decimal("0"),
                    ),
                )
            )

    return rows


def _count_tariff_branch_mismatches(
    tariff_rows: list[ResumenVentasParsedRow],
    branch_rows: list[ResumenVentasParsedRow],
) -> int:
    by_tariff: dict[int, list[ResumenVentasParsedRow]] = {}
    for branch in branch_rows:
        by_tariff.setdefault(branch.tariff_row_index, []).append(branch)

    mismatches = 0
    tolerance = Decimal("0.01")
    for tariff in tariff_rows:
        children = by_tariff.get(tariff.row_index, [])
        if not children:
            continue
        sums = (
            sum((row.current_quantity for row in children), Decimal("0")),
            sum((row.current_flow for row in children), Decimal("0")),
            sum((row.comparison_quantity for row in children), Decimal("0")),
            sum((row.comparison_flow for row in children), Decimal("0")),
        )
        expected = (
            tariff.current_quantity,
            tariff.current_flow,
            tariff.comparison_quantity,
            tariff.comparison_flow,
        )
        if any(
            abs(actual - target) > tolerance
            for actual, target in zip(sums, expected)
        ):
            mismatches += 1
    return mismatches


def _cell(df: pd.DataFrame, row: int, col: int) -> Any:
    if row >= len(df.index) or col >= len(df.columns):
        return None
    return df.iat[row, col]


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _text(value: Any) -> str:
    if value is None or _is_missing(value):
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return None if text in {"", "-"} else text


def _normalize_label(value: str) -> str:
    return " ".join(value.casefold().split())


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or _is_missing(value):
        return None
    if isinstance(value, str) and _text(value) in {"", "-"}:
        return None
    return _decimal(value)


def _decimal(
    value: Any,
    *,
    default: Decimal | None = None,
) -> Decimal:
    if value is None or _is_missing(value):
        if default is not None:
            return default
        raise ResumenVentasContentError("Valor numérico vacío.")
    if isinstance(value, str):
        normalized = _text(value)
        if normalized in {"", "-"}:
            if default is not None:
                return default
            raise ResumenVentasContentError("Valor numérico vacío.")
        normalized = normalized.replace("$", "").replace(",", "")
    else:
        normalized = str(value)
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ResumenVentasContentError(
            f"Valor numérico inválido: {value!r}"
        ) from exc
