"""Motor puro de rachas por MESES DE COBERTURA PAGADA, no por fechas de venta.

El insumo debe estar normalizado desde una fuente que demuestre la vigencia
cubierta. No inferir meses desde tickets, ultimos pagos ni snapshots diarios.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class MemberStreak:
    member_key: str
    sucursal: str
    estado: str
    mejor_racha_observada: int
    racha_vigente_observada: int
    racha_de_entrada: int | None
    calidad: str
    evidencia_meses: int
    racha_reiniciada: bool


@dataclass(frozen=True, slots=True)
class StreakResult:
    members: tuple[MemberStreak, ...]
    coverage_rows: int
    duplicate_months: int
    unmatched_coverage: int
    future_months_ignored: int


def _text(value: object) -> str:
    return str(value or "").strip()


def _yes(value: object) -> bool:
    return _text(value).upper() in {"1", "TRUE", "SI", "SÍ", "YES"}


def _member_key(row: Mapping[str, object]) -> str:
    member_id = _text(row.get("id_socio"))
    branch = _text(row.get("sucursal")).upper()
    pin = _text(row.get("pin"))
    if member_id:
        return f"ID:{member_id}"
    if not branch or not pin:
        raise ValueError("Cada socio requiere id_socio o sucursal + pin.")
    return f"PIN:{branch}:{pin}"


def _pin_alias(row: Mapping[str, object]) -> str | None:
    branch = _text(row.get("sucursal")).upper()
    pin = _text(row.get("pin"))
    return f"PIN:{branch}:{pin}" if branch and pin else None


def _covered_month(value: object) -> int:
    raw = _text(value)
    if len(raw) != 7 or raw[4] != "-" or not (
        raw[:4].isdigit() and raw[5:7].isdigit()
    ):
        raise ValueError(f"mes_cubierto invalido (YYYY-MM): {raw!r}")
    year, month = int(raw[:4]), int(raw[5:7])
    if year < 1900 or not 1 <= month <= 12:
        raise ValueError(f"mes_cubierto fuera de rango: {raw!r}")
    return year * 12 + month - 1


def _longest_run(months: set[int]) -> int:
    longest = current = 0
    previous: int | None = None
    for month in sorted(months):
        current = current + 1 if previous is not None and month == previous + 1 else 1
        longest = max(longest, current)
        previous = month
    return longest


def _current_run(months: set[int], at: int) -> int:
    current = 0
    while at in months:
        current += 1
        at -= 1
    return current


def price_for_streak(
    streak: int | None,
    steps: tuple[tuple[int, int], ...] = ((1, 599), (4, 499), (7, 399), (10, 299)),
) -> int | None:
    if streak is None or streak < 1:
        return None
    if not steps or steps[0][0] != 1:
        raise ValueError("La primera brecha de tarifa debe comenzar en el mes 1.")
    if any(step[0] <= 0 for step in steps) or any(
        steps[i][0] >= steps[i + 1][0] for i in range(len(steps) - 1)
    ):
        raise ValueError("Las brechas deben ser positivas y crecientes.")
    price = steps[0][1]
    for start, candidate in steps:
        if streak >= start:
            price = candidate
        else:
            break
    return price


def reconstruct_member_streaks(
    roster: Iterable[Mapping[str, object]],
    paid_coverage: Iterable[Mapping[str, object]],
    *,
    as_of: date,
) -> StreakResult:
    """Una fila de cobertura = un mes comprobado, no un pago ni un snapshot.

    roster: id_socio,pin,sucursal,estado,historial_completo,reinicio_promocion
    paid_coverage: id_socio,pin,sucursal,mes_cubierto,estado_evidencia,fuente_ref
    estado_evidencia exige PAGADO; otros valores no otorgan meses.
    """
    people: dict[str, Mapping[str, object]] = {}
    aliases: dict[str, str] = {}
    collision: set[str] = set()

    for row in roster:
        key = _member_key(row)
        status = _text(row.get("estado")).upper()
        if status not in {"ACTIVO", "VENCIDO", "NUEVO"}:
            raise ValueError(f"Estado no soportado para {key}: {status!r}")
        if key in people:
            raise ValueError(f"Socio repetido en padrón: {key}")
        people[key] = row
        alias = _pin_alias(row)
        if alias:
            if alias in aliases and aliases[alias] != key:
                collision.add(alias)
            else:
                aliases[alias] = key
    for alias in collision:
        aliases.pop(alias, None)

    covered: dict[str, set[int]] = defaultdict(set)
    duplicates = unmatched = future = count = 0
    cutoff = as_of.year * 12 + as_of.month - 1
    for row in paid_coverage:
        count += 1
        if _text(row.get("estado_evidencia")).upper() != "PAGADO":
            raise ValueError("Solo se acepta evidencia mensual PAGADO, no transacciones sin vigencia.")
        if not _text(row.get("fuente_ref")):
            raise ValueError("Cada mes cubierto necesita fuente_ref auditable.")
        month = _covered_month(row.get("mes_cubierto"))
        if month > cutoff:
            future += 1  # prepagos futuros no otorgan descuento hoy
            continue
        raw_key = _member_key(row)
        alias = _pin_alias(row)
        if alias in collision and raw_key not in people:
            raise ValueError("PIN/sucursal ambiguo en padrón; resolver identidad antes.")
        key = raw_key if raw_key in people else aliases.get(alias or "", raw_key)
        if (raw_key.startswith("ID:") and raw_key not in people
                and key.startswith("ID:") and key != raw_key):
            raise ValueError("ID Socio de cobertura contradice el padrón.")
        if key not in people:
            unmatched += 1
            continue
        if month in covered[key]:
            duplicates += 1
        covered[key].add(month)

    result: list[MemberStreak] = []
    for key, row in sorted(people.items()):
        months = covered[key]
        best = _longest_run(months)
        current = _current_run(months, cutoff)
        status = _text(row.get("estado")).upper()
        reset = _yes(row.get("reinicio_promocion"))
        streak: int | None
        if reset or status == "NUEVO":
            streak = 1
        elif status == "VENCIDO":
            streak = best or None
        else:
            streak = current or None
        if status == "NUEVO" or reset:
            quality = "REINICIO_PROMOCION" if reset else "NUEVO"
        elif not months or streak is None:
            quality = "SIN_EVIDENCIA"
        elif _yes(row.get("historial_completo")):
            quality = "CERTIFICABLE_CON_FUENTE_COMPLETA"
        else:
            quality = "PARCIAL_OBSERVADO"
        result.append(
            MemberStreak(
                member_key=key,
                sucursal=_text(row.get("sucursal")).upper(),
                estado=status,
                mejor_racha_observada=best,
                racha_vigente_observada=current,
                racha_de_entrada=streak,
                calidad=quality,
                evidencia_meses=len(months),
                racha_reiniciada=reset,
            )
        )
    return StreakResult(tuple(result), count, duplicates, unmatched, future)
