# backend/app/warehouse/services/reporte_direccion_advisory_lock.py

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from typing import Any

from flask import current_app
from sqlalchemy import text

from app.extensions import db


REPORTE_DIRECCION_REPORT_TYPE_KEY = "reporte_direccion"


class ReporteDireccionAdvisoryLockError(RuntimeError):
    """Error base del advisory lock de reporte_direccion."""


def register_reporte_direccion_advisory_lock(app) -> None:
    """
    Registra este advisory lock como hook runtime.

    Uso esperado más adelante en init/app factory:
        register_reporte_direccion_advisory_lock(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK"] =
            acquire_reporte_direccion_advisory_lock
    """
    app.config["WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK"] = (
        acquire_reporte_direccion_advisory_lock
    )


def _ensure_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        return date.fromisoformat(value)

    raise ReporteDireccionAdvisoryLockError(
        f"No se pudo convertir business_date a date: {value!r}"
    )


def _stable_lock_key(report_type_key: str, business_date: date) -> int:
    """
    Genera una llave estable bigint para pg_advisory_xact_lock(bigint)
    a partir de:
    - report_type_key
    - business_date

    Usamos sha256 para evitar depender del hash aleatorio de Python.
    """
    raw = f"{report_type_key}|{business_date.isoformat()}".encode("utf-8")
    digest = sha256(raw).digest()

    key = int.from_bytes(digest[:8], byteorder="big", signed=False)

    # PostgreSQL espera bigint signed.
    max_signed_bigint = 2**63 - 1
    key = key % max_signed_bigint

    return key


def acquire_reporte_direccion_advisory_lock(
    *,
    report_type_key: str,
    business_date: date | str,
) -> None:
    """
    Toma un advisory lock transaccional de PostgreSQL por:
    - report_type_key
    - business_date

    Importante:
    - este lock vive solo durante la transacción actual
    - debe llamarse dentro de una transacción ya abierta o reutilizada
    """
    if report_type_key != REPORTE_DIRECCION_REPORT_TYPE_KEY:
        raise ReporteDireccionAdvisoryLockError(
            f"Este advisory lock solo soporta {REPORTE_DIRECCION_REPORT_TYPE_KEY!r}."
        )

    parsed_business_date = _ensure_date(business_date)
    key = _stable_lock_key(report_type_key, parsed_business_date)

    sql = text("SELECT pg_advisory_xact_lock(:key)")

    try:
        db.session().execute(
            sql,
            {
                "key": key,
            },
        )
    except Exception as exc:
        raise ReporteDireccionAdvisoryLockError(
            "No se pudo tomar el advisory lock transaccional para reporte_direccion."
        ) from exc

    current_app.logger.info(
        "Reporte_direccion advisory lock acquired: report_type_key=%s business_date=%s key1=%s key2=%s",
        report_type_key,
        parsed_business_date.isoformat(),
        key
    )