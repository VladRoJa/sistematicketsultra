from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping


CLIENTES_NUEVOS_WEEKDAY_WEIGHTS: dict[int, Decimal] = {
    0: Decimal("39.353"),
    1: Decimal("20.504"),
    2: Decimal("15.574"),
    3: Decimal("11.104"),
    4: Decimal("7.613"),
    5: Decimal("2.721"),
    6: Decimal("3.130"),
}

REACTIVACIONES_WEEKDAY_WEIGHTS: dict[int, Decimal] = {
    0: Decimal("41.609"),
    1: Decimal("20.866"),
    2: Decimal("14.319"),
    3: Decimal("9.365"),
    4: Decimal("5.290"),
    5: Decimal("3.967"),
    6: Decimal("4.584"),
}


@dataclass(frozen=True)
class TrackRegionalPaceMetric:
    metric_key: str
    actual_mtd: Decimal | None
    monthly_target: Decimal | None
    actual_progress_pct: Decimal | None
    expected_progress_pct: Decimal
    expected_mtd: Decimal | None
    gap_units: Decimal | None
    gap_pct_points: Decimal | None
    remaining_to_target: Decimal | None
    status: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "metric_key": self.metric_key,
            "actual_mtd": _decimal_to_string(self.actual_mtd),
            "monthly_target": _decimal_to_string(self.monthly_target),
            "actual_progress_pct": _decimal_to_string(
                self.actual_progress_pct
            ),
            "expected_progress_pct": _decimal_to_string(
                self.expected_progress_pct
            ),
            "expected_mtd": _decimal_to_string(self.expected_mtd),
            "gap_units": _decimal_to_string(self.gap_units),
            "gap_pct_points": _decimal_to_string(
                self.gap_pct_points
            ),
            "remaining_to_target": _decimal_to_string(
                self.remaining_to_target
            ),
            "status": self.status,
        }


@dataclass(frozen=True)
class TrackRegionalLimitMetric:
    metric_key: str
    actual_mtd: Decimal | None
    monthly_limit: Decimal | None
    limit_usage_pct: Decimal | None
    remaining_margin: Decimal | None
    status: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "metric_key": self.metric_key,
            "actual_mtd": _decimal_to_string(self.actual_mtd),
            "monthly_limit": _decimal_to_string(self.monthly_limit),
            "limit_usage_pct": _decimal_to_string(self.limit_usage_pct),
            "remaining_margin": _decimal_to_string(self.remaining_margin),
            "status": self.status,
        }


@dataclass(frozen=True)
class TrackRegionalTargetMetric:
    metric_key: str
    actual_mtd: Decimal | None
    monthly_target: Decimal | None
    compliance_pct: Decimal | None
    remaining_to_target: Decimal | None
    status: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "metric_key": self.metric_key,
            "actual_mtd": _decimal_to_string(self.actual_mtd),
            "monthly_target": _decimal_to_string(self.monthly_target),
            "compliance_pct": _decimal_to_string(self.compliance_pct),
            "remaining_to_target": _decimal_to_string(
                self.remaining_to_target
            ),
            "status": self.status,
        }


@dataclass(frozen=True)
class TrackRegionalUsersMetric:
    metric_key: str
    current_users: Decimal | None
    projected_close_users: Decimal | None
    users_gap: Decimal | None
    status: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "metric_key": self.metric_key,
            "current_users": _decimal_to_string(self.current_users),
            "projected_close_users": _decimal_to_string(
                self.projected_close_users
            ),
            "users_gap": _decimal_to_string(self.users_gap),
            "status": self.status,
        }


def _to_optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError("Los valores numéricos no pueden ser booleanos.")

    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))

    if not decimal_value.is_finite():
        raise ValueError("Los valores numéricos deben ser finitos.")

    return decimal_value


def _decimal_to_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def build_normalized_monthly_curve(
    *,
    target_month: date,
    weekday_weights: Mapping[int, Decimal],
) -> dict[date, Decimal]:
    month_start = target_month.replace(day=1)
    days_in_month = monthrange(month_start.year, month_start.month)[1]

    if set(weekday_weights) != set(range(7)):
        raise ValueError("weekday_weights debe definir exactamente lunes a domingo.")

    normalized_weights = {
        weekday: Decimal(str(weight))
        for weekday, weight in weekday_weights.items()
    }

    if any(weight <= 0 for weight in normalized_weights.values()):
        raise ValueError("Todos los weekday_weights deben ser mayores a cero.")

    calendar_dates = [
        month_start + timedelta(days=offset)
        for offset in range(days_in_month)
    ]
    monthly_total_weight = sum(
        normalized_weights[calendar_date.weekday()]
        for calendar_date in calendar_dates
    )

    curve: dict[date, Decimal] = {}
    accumulated = Decimal("0")

    for index, calendar_date in enumerate(calendar_dates):
        if index == len(calendar_dates) - 1:
            normalized_day_weight = Decimal("1") - accumulated
        else:
            normalized_day_weight = (
                normalized_weights[calendar_date.weekday()]
                / monthly_total_weight
            )
            accumulated += normalized_day_weight

        curve[calendar_date] = normalized_day_weight

    return curve


def calculate_expected_progress_ratio(
    *,
    cutoff_date: date,
    weekday_weights: Mapping[int, Decimal],
) -> Decimal:
    curve = build_normalized_monthly_curve(
        target_month=cutoff_date,
        weekday_weights=weekday_weights,
    )

    return sum(
        weight
        for calendar_date, weight in curve.items()
        if calendar_date <= cutoff_date
    )


def build_weekday_pace_metric(
    *,
    metric_key: str,
    actual_mtd: Any,
    monthly_target: Any,
    cutoff_date: date,
    weekday_weights: Mapping[int, Decimal],
) -> TrackRegionalPaceMetric:
    actual = _to_optional_decimal(actual_mtd)
    target = _to_optional_decimal(monthly_target)
    expected_progress_ratio = calculate_expected_progress_ratio(
        cutoff_date=cutoff_date,
        weekday_weights=weekday_weights,
    )
    expected_progress_pct = expected_progress_ratio * Decimal("100")

    if target is None or target <= 0:
        return TrackRegionalPaceMetric(
            metric_key=metric_key,
            actual_mtd=actual,
            monthly_target=target,
            actual_progress_pct=None,
            expected_progress_pct=expected_progress_pct,
            expected_mtd=None,
            gap_units=None,
            gap_pct_points=None,
            remaining_to_target=None,
            status="SIN_META",
        )

    if actual is None:
        return TrackRegionalPaceMetric(
            metric_key=metric_key,
            actual_mtd=None,
            monthly_target=target,
            actual_progress_pct=None,
            expected_progress_pct=expected_progress_pct,
            expected_mtd=target * expected_progress_ratio,
            gap_units=None,
            gap_pct_points=None,
            remaining_to_target=None,
            status="DATOS_INSUFICIENTES",
        )

    actual_progress_pct = actual / target * Decimal("100")
    expected_mtd = target * expected_progress_ratio
    gap_units = actual - expected_mtd
    gap_pct_points = actual_progress_pct - expected_progress_pct

    if actual > target:
        status = "META_SUPERADA"
    elif gap_units > 0:
        status = "ADELANTADO"
    elif gap_units < 0:
        status = "DEBAJO_RITMO"
    else:
        status = "EN_RITMO"

    return TrackRegionalPaceMetric(
        metric_key=metric_key,
        actual_mtd=actual,
        monthly_target=target,
        actual_progress_pct=actual_progress_pct,
        expected_progress_pct=expected_progress_pct,
        expected_mtd=expected_mtd,
        gap_units=gap_units,
        gap_pct_points=gap_pct_points,
        remaining_to_target=max(target - actual, Decimal("0")),
        status=status,
    )


def build_clientes_nuevos_metric(
    *,
    actual_mtd: Any,
    monthly_target: Any,
    cutoff_date: date,
) -> TrackRegionalPaceMetric:
    return build_weekday_pace_metric(
        metric_key="clientes_nuevos",
        actual_mtd=actual_mtd,
        monthly_target=monthly_target,
        cutoff_date=cutoff_date,
        weekday_weights=CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    )


def build_reactivaciones_metric(
    *,
    actual_mtd: Any,
    monthly_target: Any,
    cutoff_date: date,
) -> TrackRegionalPaceMetric:
    return build_weekday_pace_metric(
        metric_key="reactivaciones",
        actual_mtd=actual_mtd,
        monthly_target=monthly_target,
        cutoff_date=cutoff_date,
        weekday_weights=REACTIVACIONES_WEEKDAY_WEIGHTS,
    )


def build_bajas_metric(
    *,
    actual_mtd: Any,
    monthly_limit: Any,
) -> TrackRegionalLimitMetric:
    actual = _to_optional_decimal(actual_mtd)
    limit = _to_optional_decimal(monthly_limit)

    if limit is None or limit <= 0:
        return TrackRegionalLimitMetric(
            metric_key="bajas",
            actual_mtd=actual,
            monthly_limit=limit,
            limit_usage_pct=None,
            remaining_margin=None,
            status="SIN_META",
        )

    if actual is None:
        return TrackRegionalLimitMetric(
            metric_key="bajas",
            actual_mtd=None,
            monthly_limit=limit,
            limit_usage_pct=None,
            remaining_margin=None,
            status="DATOS_INSUFICIENTES",
        )

    return TrackRegionalLimitMetric(
        metric_key="bajas",
        actual_mtd=actual,
        monthly_limit=limit,
        limit_usage_pct=actual / limit * Decimal("100"),
        remaining_margin=limit - actual,
        status=(
            "LIMITE_EXCEDIDO"
            if actual > limit
            else "EN_RITMO"
        ),
    )


def build_target_progress_metric(
    *,
    metric_key: str,
    actual_mtd: Any,
    monthly_target: Any,
) -> TrackRegionalTargetMetric:
    actual = _to_optional_decimal(actual_mtd)
    target = _to_optional_decimal(monthly_target)

    if target is None or target <= 0:
        return TrackRegionalTargetMetric(
            metric_key=metric_key,
            actual_mtd=actual,
            monthly_target=target,
            compliance_pct=None,
            remaining_to_target=None,
            status="SIN_META",
        )

    if actual is None:
        return TrackRegionalTargetMetric(
            metric_key=metric_key,
            actual_mtd=None,
            monthly_target=target,
            compliance_pct=None,
            remaining_to_target=None,
            status="DATOS_INSUFICIENTES",
        )

    if actual > target:
        status = "META_SUPERADA"
    elif actual == target:
        status = "EN_RITMO"
    else:
        status = "DEBAJO_META"

    return TrackRegionalTargetMetric(
        metric_key=metric_key,
        actual_mtd=actual,
        monthly_target=target,
        compliance_pct=actual / target * Decimal("100"),
        remaining_to_target=max(target - actual, Decimal("0")),
        status=status,
    )


def build_users_gap_metric(
    *,
    current_users: Any,
    projected_close_users: Any,
) -> TrackRegionalUsersMetric:
    current = _to_optional_decimal(current_users)
    projected_close = _to_optional_decimal(projected_close_users)

    if current is None or projected_close is None:
        return TrackRegionalUsersMetric(
            metric_key="usuarios",
            current_users=current,
            projected_close_users=projected_close,
            users_gap=None,
            status="DATOS_INSUFICIENTES",
        )

    return TrackRegionalUsersMetric(
        metric_key="usuarios",
        current_users=current,
        projected_close_users=projected_close,
        users_gap=current - projected_close,
        status="INFORMATIVO",
    )
