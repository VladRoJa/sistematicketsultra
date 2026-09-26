from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import math
import unicodedata

import pandas as pd


TIJUANA_TZ = ZoneInfo("America/Tijuana")
PARSER_VERSION = "v1"

REQUIRED_COLUMNS = frozenset(
    {
        "Pin",
        "Entrada",
        "Salida",
        "Edad",
        "Ciudad",
        "Sucursal",
        "CP",
        "Alta",
        "Tipo Asistencia",
        "Tiene Apertura",
    }
)

_OPEN_EXIT_TOKENS = frozenset(
    {
        "",
        "SIN SALIDA",
        "SIN_SALIDA",
        "NAN",
        "NAT",
        "NONE",
        "NULL",
    }
)


class AttendanceParserError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AttendanceVisitRecord:
    business_date: date
    source_row_number: int
    member_pin: str | None
    source_branch_name: str
    entered_at_utc: datetime
    exited_at_utc: datetime | None
    duration_seconds: int | None
    visit_status: str
    age: int | None
    age_is_valid: bool
    city: str | None
    postal_code: str | None
    member_since: date | None
    attendance_type: str
    has_opening: bool | None
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class AttendanceRejectedRecord:
    business_date: date
    source_row_number: int
    reason_code: str
    detail: str | None
    member_pin: str | None
    source_branch_name: str | None
    entered_at_raw: str | None
    attendance_type_raw: str | None


@dataclass(frozen=True, slots=True)
class AttendanceParseResult:
    source_rows: int
    visits: tuple[AttendanceVisitRecord, ...]
    rejections: tuple[AttendanceRejectedRecord, ...]


def file_sha256(path: Path | str) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def parse_attendance_excel(
    path: Path | str,
    *,
    business_date: date,
) -> AttendanceParseResult:
    dataframe = pd.read_excel(
        Path(path),
        header=1,
        dtype=str,
    )
    missing_columns = sorted(
        REQUIRED_COLUMNS - set(dataframe.columns)
    )
    if missing_columns:
        raise AttendanceParserError(
            "Faltan columnas obligatorias: "
            + ", ".join(missing_columns)
        )

    visits: list[AttendanceVisitRecord] = []
    rejections: list[AttendanceRejectedRecord] = []
    source_rows = 0

    for index, row in dataframe.iterrows():
        source_row_number = int(index) + 3

        if _is_footer(row) or _is_empty_row(row):
            continue

        source_rows += 1

        try:
            parsed = _parse_row(
                row,
                source_row_number=source_row_number,
                business_date=business_date,
            )
        except AttendanceParserError as exc:
            rejections.append(
                AttendanceRejectedRecord(
                    business_date=business_date,
                    source_row_number=source_row_number,
                    reason_code=_reason_code(exc),
                    detail=str(exc)[:500],
                    member_pin=_clean_text(
                        row.get("Pin")
                    ),
                    source_branch_name=_clean_text(
                        row.get("Sucursal")
                    ),
                    entered_at_raw=_clean_text(
                        row.get("Entrada")
                    ),
                    attendance_type_raw=_clean_text(
                        row.get("Tipo Asistencia")
                    ),
                )
            )
            continue

        visits.append(parsed)

    return AttendanceParseResult(
        source_rows=source_rows,
        visits=tuple(visits),
        rejections=tuple(rejections),
    )


def _parse_row(
    row: Any,
    *,
    source_row_number: int,
    business_date: date,
) -> AttendanceVisitRecord:
    source_branch_name = _clean_text(
        row.get("Sucursal")
    )
    attendance_type = _clean_text(
        row.get("Tipo Asistencia")
    )
    entered_raw = _clean_text(row.get("Entrada"))

    if not source_branch_name:
        raise AttendanceParserError(
            "BRANCH_REQUIRED: Sucursal vacía."
        )
    if not attendance_type:
        raise AttendanceParserError(
            "ATTENDANCE_TYPE_REQUIRED: "
            "Tipo Asistencia vacío."
        )
    if not entered_raw:
        raise AttendanceParserError(
            "ENTRY_REQUIRED: Entrada vacía."
        )

    entered_local = _parse_local_datetime(
        entered_raw,
        field="Entrada",
    )
    if entered_local.date() != business_date:
        raise AttendanceParserError(
            "BUSINESS_DATE_MISMATCH: "
            f"Entrada {entered_local.date().isoformat()} "
            f"no corresponde a "
            f"{business_date.isoformat()}."
        )

    exited_local = _parse_optional_exit(
        row.get("Salida")
    )

    visit_status = "OPEN"
    duration_seconds: int | None = None

    if exited_local is not None:
        if exited_local < entered_local:
            visit_status = "INVALID_TIME"
        elif (
            exited_local.date()
            != entered_local.date()
        ):
            visit_status = "CROSS_DAY"
            duration_seconds = int(
                (
                    exited_local - entered_local
                ).total_seconds()
            )
        else:
            visit_status = "CLOSED"
            duration_seconds = int(
                (
                    exited_local - entered_local
                ).total_seconds()
            )

    age, age_is_valid = _parse_age(
        row.get("Edad")
    )
    member_pin = _clean_text(row.get("Pin"))
    member_since = _parse_optional_date(
        row.get("Alta")
    )

    entered_utc = entered_local.astimezone(
        timezone.utc
    )

    source_fingerprint = _build_fingerprint(
        business_date=business_date,
        member_pin=member_pin,
        entered_at_utc=entered_utc,
        source_branch_name=source_branch_name,
        attendance_type=attendance_type,
        fallback_name=_clean_text(
            row.get("Nombre")
        ),
        fallback_last_name=_clean_text(
            row.get("Apellido")
        ),
        source_row_number=source_row_number,
    )

    return AttendanceVisitRecord(
        business_date=business_date,
        source_row_number=source_row_number,
        member_pin=member_pin,
        source_branch_name=source_branch_name,
        entered_at_utc=entered_utc,
        exited_at_utc=(
            exited_local.astimezone(timezone.utc)
            if exited_local is not None
            else None
        ),
        duration_seconds=duration_seconds,
        visit_status=visit_status,
        age=age,
        age_is_valid=age_is_valid,
        city=_clean_text(row.get("Ciudad")),
        postal_code=_clean_text(row.get("CP")),
        member_since=member_since,
        attendance_type=(
            attendance_type.strip().upper()
        ),
        has_opening=_parse_optional_bool(
            row.get("Tiene Apertura")
        ),
        source_fingerprint=source_fingerprint,
    )


def _parse_local_datetime(
    value: str,
    *,
    field: str,
) -> datetime:
    parsed = pd.to_datetime(
        value,
        dayfirst=True,
        errors="coerce",
    )
    if pd.isna(parsed):
        raise AttendanceParserError(
            f"{field.upper()}_INVALID: "
            f"{field} inválida: {value!r}."
        )

    if isinstance(parsed, pd.Timestamp):
        parsed_dt = parsed.to_pydatetime()
    elif isinstance(parsed, datetime):
        parsed_dt = parsed
    else:
        raise AttendanceParserError(
            f"{field.upper()}_INVALID: "
            f"{field} inválida: {value!r}."
        )

    if parsed_dt.tzinfo is None:
        return parsed_dt.replace(
            tzinfo=TIJUANA_TZ
        )

    return parsed_dt.astimezone(TIJUANA_TZ)


def _parse_optional_exit(
    value: Any,
) -> datetime | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    token = _normalize_token(cleaned)
    if token in _OPEN_EXIT_TOKENS:
        return None

    return _parse_local_datetime(
        cleaned,
        field="Salida",
    )


def _parse_optional_date(value: Any) -> date | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    parsed = pd.to_datetime(
        cleaned,
        dayfirst=True,
        errors="coerce",
    )
    if pd.isna(parsed):
        return None

    if isinstance(parsed, pd.Timestamp):
        return parsed.date()
    if isinstance(parsed, datetime):
        return parsed.date()
    return None


def _parse_age(value: Any) -> tuple[int | None, bool]:
    cleaned = _clean_text(value)
    if not cleaned:
        return None, False

    try:
        numeric = float(
            cleaned.replace(",", ".")
        )
    except ValueError:
        return None, False

    if not math.isfinite(numeric):
        return None, False

    age = int(numeric)
    if (
        numeric != age
        or age < 0
        or age > 110
    ):
        return None, False

    return age, True


def _parse_optional_bool(
    value: Any,
) -> bool | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    token = _normalize_token(cleaned)
    if token in {
        "SI",
        "S",
        "TRUE",
        "1",
        "YES",
    }:
        return True
    if token in {
        "NO",
        "N",
        "FALSE",
        "0",
    }:
        return False
    return None


def _build_fingerprint(
    *,
    business_date: date,
    member_pin: str | None,
    entered_at_utc: datetime,
    source_branch_name: str,
    attendance_type: str,
    fallback_name: str | None,
    fallback_last_name: str | None,
    source_row_number: int,
) -> str:
    if member_pin:
        identity = f"PIN:{member_pin}"
    else:
        # Nombre/apellido sólo participan dentro del
        # hash para desambiguar filas sin PIN. Nunca
        # se persisten en las tablas de asistencia.
        fallback = "|".join(
            part
            for part in (
                _normalize_token(
                    fallback_name or ""
                ),
                _normalize_token(
                    fallback_last_name or ""
                ),
            )
            if part
        )
        identity = (
            f"NAME:{fallback}"
            if fallback
            else f"ROW:{source_row_number}"
        )

    payload = "|".join(
        (
            business_date.isoformat(),
            identity,
            entered_at_utc.isoformat(),
            _normalize_token(
                source_branch_name
            ),
            _normalize_token(attendance_type),
        )
    )
    return sha256(
        payload.encode("utf-8")
    ).hexdigest()


def _reason_code(
    exc: AttendanceParserError,
) -> str:
    prefix = str(exc).split(":", 1)[0].strip()
    if not prefix:
        return "INVALID_ROW"
    return prefix[:64]


def _is_footer(row: Any) -> bool:
    first_value = _clean_text(
        row.iloc[0] if len(row) else None
    )
    return bool(
        first_value
        and _normalize_token(
            first_value
        ).startswith("REPORTE GENERADO")
    )


def _is_empty_row(row: Any) -> bool:
    return all(
        _clean_text(value) is None
        for value in row.tolist()
    )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    if not text:
        return None
    return text


def _normalize_token(value: str) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value,
    )
    without_accents = "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )
    return " ".join(
        without_accents.upper().split()
    )
