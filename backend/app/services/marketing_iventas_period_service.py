"""Identidad de períodos canónicos para Marketing / iVentas."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MarketingIventasMonthPeriod:
    period_key: str
    date_from: date
    date_to: date


def build_iventas_month_period_key(
    month_date: date,
) -> str:
    """Construye la clave canónica mensual de iVentas."""

    if not isinstance(month_date, date):
        raise TypeError(
            "month_date debe ser date."
        )

    return (
        f"IVENTAS-{month_date.year:04d}-"
        f"{month_date.month:02d}"
    )


def build_iventas_month_date_range(
    *,
    month_date: date,
    today: date,
) -> tuple[date, date]:
    """Construye el rango canónico mensual de iVentas."""

    if not isinstance(month_date, date):
        raise TypeError(
            "month_date debe ser date."
        )

    if not isinstance(today, date):
        raise TypeError(
            "today debe ser date."
        )

    month_start = date(
        month_date.year,
        month_date.month,
        1,
    )

    current_month_start = date(
        today.year,
        today.month,
        1,
    )

    if month_start > current_month_start:
        raise ValueError(
            "No se puede construir un rango iVentas "
            "para un mes futuro."
        )

    if month_start == current_month_start:
        return month_start, today

    last_day = monthrange(
        month_start.year,
        month_start.month,
    )[1]

    return (
        month_start,
        date(
            month_start.year,
            month_start.month,
            last_day,
        ),
    )


def resolve_iventas_month_period(
    *,
    month_date: date,
    today: date,
) -> MarketingIventasMonthPeriod:
    """Resuelve identidad y rango del snapshot mensual iVentas."""

    period_key = build_iventas_month_period_key(
        month_date
    )

    date_from, date_to = build_iventas_month_date_range(
        month_date=month_date,
        today=today,
    )

    return MarketingIventasMonthPeriod(
        period_key=period_key,
        date_from=date_from,
        date_to=date_to,
    )
