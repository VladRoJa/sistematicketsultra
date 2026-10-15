"""Detector de diferencias semánticas para KPI Desempeño (M1, solo lectura).

No accede a Warehouse, ORM, jobs, Track ni canonicalidad. Dos reportes
son comparables si pasan el parser existente y tienen identidades únicas.
La selección de fechas y la validación temporal pertenecen a fases
posteriores: este módulo recibe business_date explícita y compara solo contenido.
"""

from __future__ import annotations

import math
import unicodedata
from datetime import date, datetime
from dataclasses import asdict, dataclass, field
from typing import Mapping

from app.warehouse.services.kpi_desempeno_parser import (
    KPI_DESEMPENO_REPORT_TYPE_KEY,
    KpiDesempenoParseResult,
    KpiDesempenoParserError,
    KpiDesempenoParsedRow,
    parse_kpi_desempeno_xlsx,
)


NO_CHANGE = "NO_CHANGE"
DIFFERENCES_DETECTED = "DIFFERENCES_DETECTED"
BLOCKED_BY_VALIDATION = "BLOCKED_BY_VALIDATION"

# Campos completos de negocio; nunca comparar row_index, orden o estilo XLSX.
KPI_METRIC_FIELDS = (
    "socios_activos_inicio_mes",
    "clientes_nuevo_real",
    "reactivaciones",
    "renovaciones",
    "bajas",
    "socios_activos_del_mes",
    "meta_socios_activos_del_mes",
    "alcance_meta",
)


class KpiDesempenoSemanticValidationError(ValueError):
    """No es seguro establecer una comparación de identidades/datos."""


@dataclass(frozen=True, slots=True)
class KpiDesempenoFieldChange:
    field: str
    previous: int | float | None
    current: int | float | None
    delta: int | float | None


@dataclass(frozen=True, slots=True)
class KpiDesempenoBranchDifference:
    branch_key: str
    kind: str  # CHANGED, ADDED, REMOVED
    previous_branch_name: str | None
    current_branch_name: str | None
    fields: tuple[KpiDesempenoFieldChange, ...]


@dataclass(frozen=True, slots=True)
class KpiDesempenoSemanticDiffResult:
    status: str
    business_date: str | None = None
    previous_row_count: int = 0
    current_row_count: int = 0
    differences: tuple[KpiDesempenoBranchDifference, ...] = field(default_factory=tuple)
    validation_errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def requires_identity_review(self) -> bool:
        """Alta/baja de sucursal exige revisión antes de una futura publicación."""
        return any(item.kind in {"ADDED", "REMOVED"} for item in self.differences)

    def to_dict(self) -> dict:
        return {**asdict(self), "requires_identity_review": self.requires_identity_review}


def _normalize_business_date(value: date | str) -> str:
    """Fecha de negocio explícita; no se infiere del XLSX ni del reloj."""
    if isinstance(value, datetime):
        raise KpiDesempenoSemanticValidationError(
            "business_date debe ser fecha de negocio, no datetime."
        )
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise KpiDesempenoSemanticValidationError(
                "business_date inválida; usar YYYY-MM-DD."
            ) from exc
        if parsed.isoformat() == value:
            return value
    raise KpiDesempenoSemanticValidationError(
        "business_date debe ser date o texto ISO YYYY-MM-DD."
    )


def _normalize_branch(value: str) -> str:
    """Normaliza formato, pero NO inventa equivalencias entre sucursales."""
    if not isinstance(value, str):
        raise KpiDesempenoSemanticValidationError("Identidad de sucursal no textual.")
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _validate_aliases(aliases: Mapping[str, str] | None) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for raw, target in (aliases or {}).items():
        key = _normalize_branch(raw)
        canonical = _normalize_branch(target)
        if not key or not canonical:
            raise KpiDesempenoSemanticValidationError("Alias de sucursal vacío.")
        if key in resolved and resolved[key] != canonical:
            raise KpiDesempenoSemanticValidationError(
                f"Alias contradictorio para sucursal: {key!r}."
            )
        resolved[key] = canonical
    return resolved


def _index_rows(
    parsed: KpiDesempenoParseResult, aliases: Mapping[str, str], label: str
) -> dict[str, KpiDesempenoParsedRow]:
    if parsed.report_type_key != KPI_DESEMPENO_REPORT_TYPE_KEY:
        raise KpiDesempenoSemanticValidationError(
            f"{label}: tipo de reporte incorrecto."
        )
    if not parsed.rows or parsed.row_count != len(parsed.rows):
        raise KpiDesempenoSemanticValidationError(
            f"{label}: filas vacías o conteo inconsistente."
        )

    indexed: dict[str, KpiDesempenoParsedRow] = {}
    for row in parsed.rows:
        key = _normalize_branch(row.sucursal_nombre)
        if not key:
            raise KpiDesempenoSemanticValidationError(
                f"{label}: sucursal vacía."
            )
        key = aliases.get(key, key)
        if key in indexed:
            raise KpiDesempenoSemanticValidationError(
                f"{label}: identidad duplicada de sucursal {key!r}."
            )
        for metric in KPI_METRIC_FIELDS:
            value = getattr(row, metric)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise KpiDesempenoSemanticValidationError(
                    f"{label}: valor inválido de {metric} en {key!r}."
                )
            if metric != "alcance_meta" and int(value) != value:
                raise KpiDesempenoSemanticValidationError(
                    f"{label}: valor fraccionario en métrica entera {metric} "
                    f"para sucursal {key!r}."
                )
        indexed[key] = row
    return indexed


def _metric_equal(field_name: str, previous: int | float, current: int | float) -> bool:
    if field_name == "alcance_meta":
        # Ruido binario de representación XLSX no constituye diferencia.
        return math.isclose(previous, current, rel_tol=0.0, abs_tol=1e-9)
    return previous == current


def compare_kpi_desempeno_parsed(
    *,
    previous: KpiDesempenoParseResult,
    current: KpiDesempenoParseResult,
    business_date: date | str,
    sucursal_aliases: Mapping[str, str] | None = None,
) -> KpiDesempenoSemanticDiffResult:
    """Comparación determinista sin E/S, ordenada por identidad y campo.

    `business_date` es contexto obligatorio y no se verifica contra el
    contenido del XLSX. `sucursal_aliases` es opcional y explícito; el
    detector no consulta catálogos ni infiere aliases de Gasca.
    """
    normalized_date = None
    try:
        normalized_date = _normalize_business_date(business_date)
        aliases = _validate_aliases(sucursal_aliases)
        previous_rows = _index_rows(previous, aliases, "previous")
        current_rows = _index_rows(current, aliases, "current")
    except (KpiDesempenoSemanticValidationError, TypeError, AttributeError) as exc:
        return KpiDesempenoSemanticDiffResult(
            status=BLOCKED_BY_VALIDATION,
            business_date=normalized_date,
            previous_row_count=getattr(previous, "row_count", 0),
            current_row_count=getattr(current, "row_count", 0),
            validation_errors=(str(exc),),
        )

    differences: list[KpiDesempenoBranchDifference] = []
    for key in sorted(previous_rows.keys() | current_rows.keys()):
        old = previous_rows.get(key)
        new = current_rows.get(key)
        kind = "ADDED" if old is None else "REMOVED" if new is None else "CHANGED"
        fields = tuple(
            KpiDesempenoFieldChange(
                field=metric,
                previous=getattr(old, metric) if old else None,
                current=getattr(new, metric) if new else None,
                delta=(
                    getattr(new, metric) - getattr(old, metric)
                    if old is not None and new is not None
                    else None
                ),
            )
            for metric in KPI_METRIC_FIELDS
            if old is None
            or new is None
            or not _metric_equal(metric, getattr(old, metric), getattr(new, metric))
        )
        if fields:
            differences.append(
                KpiDesempenoBranchDifference(
                    branch_key=key,
                    kind=kind,
                    previous_branch_name=old.sucursal_nombre if old else None,
                    current_branch_name=new.sucursal_nombre if new else None,
                    fields=fields,
                )
            )
    return KpiDesempenoSemanticDiffResult(
        status=DIFFERENCES_DETECTED if differences else NO_CHANGE,
        business_date=normalized_date,
        previous_row_count=previous.row_count,
        current_row_count=current.row_count,
        differences=tuple(differences),
    )


def compare_kpi_desempeno_xlsx(
    *,
    business_date: date | str,
    previous_file_path: str | None = None,
    previous_file_bytes: bytes | None = None,
    current_file_path: str | None = None,
    current_file_bytes: bytes | None = None,
    sucursal_aliases: Mapping[str, str] | None = None,
) -> KpiDesempenoSemanticDiffResult:
    """Reutiliza el parser canónico en ambos XLSX; jamás ingesta ni publica."""
    try:
        normalized_date = _normalize_business_date(business_date)
    except KpiDesempenoSemanticValidationError as exc:
        return KpiDesempenoSemanticDiffResult(
            status=BLOCKED_BY_VALIDATION, validation_errors=(str(exc),)
        )
    try:
        previous = parse_kpi_desempeno_xlsx(
            file_path=previous_file_path, file_bytes=previous_file_bytes
        )
        current = parse_kpi_desempeno_xlsx(
            file_path=current_file_path, file_bytes=current_file_bytes
        )
    except KpiDesempenoParserError as exc:
        return KpiDesempenoSemanticDiffResult(
            status=BLOCKED_BY_VALIDATION,
            business_date=normalized_date,
            validation_errors=(f"Parser KPI: {exc}",),
        )
    return compare_kpi_desempeno_parsed(
        previous=previous,
        current=current,
        business_date=normalized_date,
        sucursal_aliases=sucursal_aliases,
    )
