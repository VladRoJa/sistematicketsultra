from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.models.sales_composition import (
    SalesCompositionRowORM,
    SalesCompositionSnapshotORM,
)


class SalesCompositionAnalysisError(RuntimeError):
    pass


class SalesCompositionNotFoundError(SalesCompositionAnalysisError):
    pass


def list_sales_composition_snapshots(
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 100))
    snapshots = (
        SalesCompositionSnapshotORM.query
        .order_by(
            SalesCompositionSnapshotORM.business_date.desc(),
            SalesCompositionSnapshotORM.captured_at.desc(),
            SalesCompositionSnapshotORM.id.desc(),
        )
        .limit(normalized_limit)
        .all()
    )
    return [_serialize_snapshot(snapshot) for snapshot in snapshots]


def build_sales_composition_analysis(
    *,
    snapshot_id: int | None = None,
) -> dict[str, Any]:
    snapshot = _resolve_snapshot(snapshot_id=snapshot_id)
    rows = (
        SalesCompositionRowORM.query
        .filter_by(snapshot_id=snapshot.id)
        .order_by(SalesCompositionRowORM.row_index.asc())
        .all()
    )
    if not rows:
        raise SalesCompositionNotFoundError(
            "El snapshot de Composición de Venta no contiene filas estructuradas."
        )
    return _build_analysis(snapshot=snapshot, rows=rows)


def _resolve_snapshot(
    *,
    snapshot_id: int | None,
) -> SalesCompositionSnapshotORM:
    if snapshot_id is not None:
        try:
            normalized_id = int(snapshot_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("snapshot_id inválido.") from exc
        if normalized_id <= 0:
            raise ValueError("snapshot_id inválido.")
        snapshot = SalesCompositionSnapshotORM.query.filter_by(
            id=normalized_id
        ).first()
    else:
        snapshot = (
            SalesCompositionSnapshotORM.query
            .filter_by(is_canonical=True)
            .order_by(
                SalesCompositionSnapshotORM.business_date.desc(),
                SalesCompositionSnapshotORM.captured_at.desc(),
                SalesCompositionSnapshotORM.id.desc(),
            )
            .first()
        )
    if snapshot is None:
        raise SalesCompositionNotFoundError(
            "No existe un snapshot de Composición de Venta disponible."
        )
    return snapshot


def _build_analysis(
    *,
    snapshot: Any,
    rows: list[Any],
) -> dict[str, Any]:
    tariff_rows = [
        row
        for row in rows
        if str(row.row_kind).upper() == "TARIFF"
    ]
    branch_rows = [
        row
        for row in rows
        if str(row.row_kind).upper() == "BRANCH"
    ]
    if not tariff_rows:
        raise SalesCompositionNotFoundError(
            "El snapshot no contiene tarifas analíticas."
        )

    current_total = _sum_decimal(
        row.current_flow for row in tariff_rows
    )
    comparison_total = _sum_decimal(
        row.comparison_flow for row in tariff_rows
    )
    current_quantity = _sum_decimal(
        row.current_quantity for row in tariff_rows
    )
    comparison_quantity = _sum_decimal(
        row.comparison_quantity for row in tariff_rows
    )
    delta_flow = current_total - comparison_total
    delta_quantity = current_quantity - comparison_quantity

    contract_current = _sum_decimal(
        row.current_flow
        for row in tariff_rows
        if str(row.sales_mode).upper() == "CONTRACT"
    )
    contract_comparison = _sum_decimal(
        row.comparison_flow
        for row in tariff_rows
        if str(row.sales_mode).upper() == "CONTRACT"
    )
    contract_mix_current = _ratio_pct(
        contract_current,
        current_total,
    )
    contract_mix_comparison = _ratio_pct(
        contract_comparison,
        comparison_total,
    )

    groups = _build_groups(
        tariff_rows,
        current_total=current_total,
        comparison_total=comparison_total,
    )
    tariffs = _build_tariffs(
        tariff_rows,
        current_total=current_total,
        comparison_total=comparison_total,
    )
    branches = _build_branches(
        branch_rows,
        current_total=current_total,
        comparison_total=comparison_total,
    )

    top3_current = _sum_decimal(
        Decimal(str(group["current_flow"]))
        for group in groups[:3]
    )
    largest_mix_shift = max(
        groups,
        key=lambda group: abs(float(group["mix_delta_pp"])),
        default=None,
    )
    positive_drivers = sorted(
        (group for group in groups if group["delta_flow"] > 0),
        key=lambda group: group["delta_flow"],
        reverse=True,
    )
    negative_drivers = sorted(
        (group for group in groups if group["delta_flow"] < 0),
        key=lambda group: group["delta_flow"],
    )

    return {
        "contract_version": "sales-composition.v1",
        "source": _serialize_snapshot(snapshot),
        "summary": {
            "current_flow": _float(current_total),
            "comparison_flow": _float(comparison_total),
            "delta_flow": _float(delta_flow),
            "growth_pct": _growth_pct(
                current_total,
                comparison_total,
            ),
            "current_quantity": _float(current_quantity),
            "comparison_quantity": _float(comparison_quantity),
            "delta_quantity": _float(delta_quantity),
            "quantity_growth_pct": _growth_pct(
                current_quantity,
                comparison_quantity,
            ),
            "contract_mix_pct": contract_mix_current,
            "comparison_contract_mix_pct": contract_mix_comparison,
            "contract_mix_delta_pp": (
                contract_mix_current - contract_mix_comparison
            ),
            "top3_concentration_pct": _ratio_pct(
                top3_current,
                current_total,
            ),
            "largest_mix_shift": largest_mix_shift,
        },
        "groups": groups,
        "drivers": {
            "positive": positive_drivers[:5],
            "negative": negative_drivers[:5],
        },
        "branches": branches,
        "tariffs": tariffs,
        "signals": _build_signals(
            delta_flow=delta_flow,
            growth_pct=_growth_pct(
                current_total,
                comparison_total,
            ),
            contract_mix_delta_pp=(
                contract_mix_current - contract_mix_comparison
            ),
            largest_mix_shift=largest_mix_shift,
            positive_drivers=positive_drivers,
            negative_drivers=negative_drivers,
            branches=branches,
            data_quality=dict(snapshot.data_quality or {}),
        ),
        "data_quality": dict(snapshot.data_quality or {}),
    }


def _build_groups(
    tariff_rows: list[Any],
    *,
    current_total: Decimal,
    comparison_total: Decimal,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in tariff_rows:
        mode = str(row.sales_mode or "").upper()
        label = (
            str(
                row.contract_type or "Contrato sin clasificar"
            ).strip()
            if mode == "CONTRACT"
            else str(row.family or "Sin familia").strip()
        )
        key = (mode, label)
        bucket = buckets.setdefault(
            key,
            {
                "key": f"{mode}:{label}",
                "sales_mode": mode,
                "label": label,
                "current_flow": Decimal("0"),
                "comparison_flow": Decimal("0"),
                "current_quantity": Decimal("0"),
                "comparison_quantity": Decimal("0"),
                "tariff_count": 0,
            },
        )
        bucket["current_flow"] += _decimal(row.current_flow)
        bucket["comparison_flow"] += _decimal(row.comparison_flow)
        bucket["current_quantity"] += _decimal(row.current_quantity)
        bucket["comparison_quantity"] += _decimal(
            row.comparison_quantity
        )
        bucket["tariff_count"] += 1

    result: list[dict[str, Any]] = []
    absolute_movement = _sum_decimal(
        abs(bucket["current_flow"] - bucket["comparison_flow"])
        for bucket in buckets.values()
    )
    for bucket in buckets.values():
        current_flow = bucket["current_flow"]
        comparison_flow = bucket["comparison_flow"]
        current_quantity = bucket["current_quantity"]
        comparison_quantity = bucket["comparison_quantity"]
        delta = current_flow - comparison_flow
        current_mix = _ratio_pct(current_flow, current_total)
        comparison_mix = _ratio_pct(
            comparison_flow,
            comparison_total,
        )
        result.append(
            {
                "key": bucket["key"],
                "sales_mode": bucket["sales_mode"],
                "label": bucket["label"],
                "current_flow": _float(current_flow),
                "comparison_flow": _float(comparison_flow),
                "delta_flow": _float(delta),
                "growth_pct": _growth_pct(
                    current_flow,
                    comparison_flow,
                ),
                "current_quantity": _float(current_quantity),
                "comparison_quantity": _float(comparison_quantity),
                "delta_quantity": _float(
                    current_quantity - comparison_quantity
                ),
                "quantity_growth_pct": _growth_pct(
                    current_quantity,
                    comparison_quantity,
                ),
                "current_mix_pct": current_mix,
                "comparison_mix_pct": comparison_mix,
                "mix_delta_pp": current_mix - comparison_mix,
                "movement_share_pct": _ratio_pct(
                    abs(delta),
                    absolute_movement,
                ),
                "tariff_count": int(bucket["tariff_count"]),
            }
        )
    return sorted(
        result,
        key=lambda item: item["current_flow"],
        reverse=True,
    )


def _build_tariffs(
    tariff_rows: list[Any],
    *,
    current_total: Decimal,
    comparison_total: Decimal,
) -> list[dict[str, Any]]:
    result = []
    for row in tariff_rows:
        current_flow = _decimal(row.current_flow)
        comparison_flow = _decimal(row.comparison_flow)
        current_mix = _ratio_pct(current_flow, current_total)
        comparison_mix = _ratio_pct(
            comparison_flow,
            comparison_total,
        )
        result.append(
            {
                "row_index": int(row.row_index),
                "sales_mode": str(row.sales_mode),
                "group_label": str(
                    row.contract_type
                    or row.family
                    or "Sin clasificar"
                ),
                "family": row.family,
                "contract_type": row.contract_type,
                "plan_type": row.plan_type,
                "tariff_name": str(row.tariff_name),
                "source_cost": _optional_float(row.source_cost),
                "monthly_equivalent": _optional_float(
                    row.monthly_equivalent
                ),
                "free_months_raw": row.free_months_raw,
                "current_quantity": _float(row.current_quantity),
                "comparison_quantity": _float(
                    row.comparison_quantity
                ),
                "delta_quantity": _float(
                    _decimal(row.current_quantity)
                    - _decimal(row.comparison_quantity)
                ),
                "current_flow": _float(current_flow),
                "comparison_flow": _float(comparison_flow),
                "delta_flow": _float(
                    current_flow - comparison_flow
                ),
                "growth_pct": _growth_pct(
                    current_flow,
                    comparison_flow,
                ),
                "current_mix_pct": current_mix,
                "comparison_mix_pct": comparison_mix,
                "mix_delta_pp": current_mix - comparison_mix,
            }
        )
    return sorted(
        result,
        key=lambda item: item["current_flow"],
        reverse=True,
    )


def _build_branches(
    branch_rows: list[Any],
    *,
    current_total: Decimal,
    comparison_total: Decimal,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "current_flow": Decimal("0"),
            "comparison_flow": Decimal("0"),
            "current_quantity": Decimal("0"),
            "comparison_quantity": Decimal("0"),
        }
    )
    for row in branch_rows:
        branch = str(row.branch_raw or "").strip()
        if not branch:
            continue
        bucket = buckets[branch]
        bucket["current_flow"] += _decimal(row.current_flow)
        bucket["comparison_flow"] += _decimal(row.comparison_flow)
        bucket["current_quantity"] += _decimal(row.current_quantity)
        bucket["comparison_quantity"] += _decimal(
            row.comparison_quantity
        )

    absolute_movement = _sum_decimal(
        abs(bucket["current_flow"] - bucket["comparison_flow"])
        for bucket in buckets.values()
    )
    result = []
    for branch, bucket in buckets.items():
        current_flow = bucket["current_flow"]
        comparison_flow = bucket["comparison_flow"]
        delta = current_flow - comparison_flow
        result.append(
            {
                "branch": branch,
                "current_flow": _float(current_flow),
                "comparison_flow": _float(comparison_flow),
                "delta_flow": _float(delta),
                "growth_pct": _growth_pct(
                    current_flow,
                    comparison_flow,
                ),
                "current_quantity": _float(
                    bucket["current_quantity"]
                ),
                "comparison_quantity": _float(
                    bucket["comparison_quantity"]
                ),
                "delta_quantity": _float(
                    bucket["current_quantity"]
                    - bucket["comparison_quantity"]
                ),
                "current_mix_pct": _ratio_pct(
                    current_flow,
                    current_total,
                ),
                "comparison_mix_pct": _ratio_pct(
                    comparison_flow,
                    comparison_total,
                ),
                "movement_share_pct": _ratio_pct(
                    abs(delta),
                    absolute_movement,
                ),
            }
        )
    return sorted(
        result,
        key=lambda item: abs(item["delta_flow"]),
        reverse=True,
    )


def _build_signals(
    *,
    delta_flow: Decimal,
    growth_pct: float | None,
    contract_mix_delta_pp: float,
    largest_mix_shift: dict[str, Any] | None,
    positive_drivers: list[dict[str, Any]],
    negative_drivers: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    data_quality: dict[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = [
        {
            "key": "membership_change",
            "type": "change",
            "tone": (
                "positive"
                if delta_flow > 0
                else "attention"
                if delta_flow < 0
                else "neutral"
            ),
            "metric": "flow",
            "delta_flow": _float(delta_flow),
            "growth_pct": growth_pct,
        },
        {
            "key": "contract_mix",
            "type": "mix",
            "tone": "neutral",
            "metric": "contract_mix",
            "delta_pp": contract_mix_delta_pp,
        },
    ]
    if largest_mix_shift is not None:
        signals.append(
            {
                "key": "largest_mix_shift",
                "type": "mix",
                "tone": "neutral",
                "label": largest_mix_shift["label"],
                "delta_pp": largest_mix_shift["mix_delta_pp"],
            }
        )
    if positive_drivers:
        signals.append(
            {
                "key": "top_positive_driver",
                "type": "driver",
                "tone": "positive",
                "label": positive_drivers[0]["label"],
                "delta_flow": positive_drivers[0]["delta_flow"],
                "movement_share_pct": positive_drivers[0][
                    "movement_share_pct"
                ],
            }
        )
    if negative_drivers:
        signals.append(
            {
                "key": "top_negative_driver",
                "type": "driver",
                "tone": "attention",
                "label": negative_drivers[0]["label"],
                "delta_flow": negative_drivers[0]["delta_flow"],
                "movement_share_pct": negative_drivers[0][
                    "movement_share_pct"
                ],
            }
        )
    if branches:
        signals.append(
            {
                "key": "largest_branch_movement",
                "type": "location",
                "tone": "neutral",
                "label": branches[0]["branch"],
                "delta_flow": branches[0]["delta_flow"],
                "movement_share_pct": branches[0][
                    "movement_share_pct"
                ],
            }
        )
    if (
        str(
            data_quality.get("reconciliation_status") or ""
        ).lower()
        != "ok"
    ):
        signals.insert(
            0,
            {
                "key": "data_quality_warning",
                "type": "quality",
                "tone": "critical",
            },
        )
    return signals


def _serialize_snapshot(snapshot: Any) -> dict[str, Any]:
    return {
        "snapshot_id": int(snapshot.id),
        "warehouse_upload_id": int(snapshot.warehouse_upload_id),
        "business_date": snapshot.business_date.isoformat(),
        "date_from": snapshot.date_from.isoformat(),
        "date_to": snapshot.date_to.isoformat(),
        "captured_at": snapshot.captured_at.isoformat(),
        "is_canonical": bool(snapshot.is_canonical),
        "current_label": str(snapshot.current_label),
        "comparison_label": str(snapshot.comparison_label),
        "row_count_valid": int(snapshot.row_count_valid),
        "data_quality": dict(snapshot.data_quality or {}),
    }


def _decimal(value: Any) -> Decimal:
    return (
        value
        if isinstance(value, Decimal)
        else Decimal(str(value or 0))
    )


def _sum_decimal(values: Any) -> Decimal:
    return sum(
        (_decimal(value) for value in values),
        Decimal("0"),
    )


def _float(value: Any) -> float:
    return float(_decimal(value))


def _optional_float(value: Any) -> float | None:
    return None if value is None else _float(value)


def _ratio_pct(numerator: Any, denominator: Any) -> float:
    denominator_decimal = _decimal(denominator)
    if denominator_decimal == 0:
        return 0.0
    return float(
        (_decimal(numerator) / denominator_decimal)
        * Decimal("100")
    )


def _growth_pct(
    current: Any,
    comparison: Any,
) -> float | None:
    comparison_decimal = _decimal(comparison)
    if comparison_decimal == 0:
        return None
    return float(
        (
            (_decimal(current) - comparison_decimal)
            / comparison_decimal
        )
        * Decimal("100")
    )
