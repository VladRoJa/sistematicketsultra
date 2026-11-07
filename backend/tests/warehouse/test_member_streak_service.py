from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.warehouse.services.member_streak_service import (
    price_for_streak,
    reconstruct_member_streaks,
)
from scripts.ops.export_member_streaks import export_workbook


def _person(id_socio="10", estado="VENCIDO", **kwargs):
    return {
        "id_socio": id_socio, "pin": "101", "sucursal": "VILLAS DEL REY",
        "estado": estado, "historial_completo": "NO",
        "reinicio_promocion": "NO", **kwargs,
    }


def _month(month, id_socio="10", **kwargs):
    return {
        "id_socio": id_socio, "pin": "101", "sucursal": "VILLAS DEL REY",
        "mes_cubierto": month, "estado_evidencia": "PAGADO",
        "fuente_ref": f"folio-{month}", **kwargs,
    }


def test_vencido_usa_mejor_racha_historica_no_total_de_pagos():
    months = [
        _month("2020-01"), _month("2020-02"),
        *[_month(f"2021-{n:02d}") for n in range(1, 11)],
    ]
    member = reconstruct_member_streaks(
        [_person()], months, as_of=date(2026, 11, 7)
    ).members[0]
    assert member.mejor_racha_observada == 10
    assert member.racha_vigente_observada == 0
    assert member.racha_de_entrada == 10
    assert price_for_streak(member.racha_de_entrada) == 299
    assert member.calidad == "PARCIAL_OBSERVADO"


def test_activo_usa_racha_vigente_no_historica():
    months = [
        *[_month(f"2020-{n:02d}") for n in range(1, 12)],
        _month("2026-10"), _month("2026-11"),
    ]
    member = reconstruct_member_streaks(
        [_person(estado="ACTIVO")], months, as_of=date(2026, 11, 7)
    ).members[0]
    assert member.mejor_racha_observada == 11
    assert member.racha_vigente_observada == 2
    assert member.racha_de_entrada == 2
    assert price_for_streak(member.racha_de_entrada) == 599


def test_reinicio_promocional_no_recupera_maximo_antiguo():
    months = [_month(f"2025-{n:02d}") for n in range(1, 12)]
    member = reconstruct_member_streaks(
        [_person(reinicio_promocion="SI")], months, as_of=date(2026, 11, 7)
    ).members[0]
    assert member.mejor_racha_observada == 11
    assert member.racha_de_entrada == 1
    assert member.calidad == "REINICIO_PROMOCION"


def test_months_duplicated_and_unmatched_do_not_inflate():
    orphan = _month("2026-04", id_socio="999")
    orphan["pin"] = "999"
    result = reconstruct_member_streaks(
        [_person()], [_month("2026-01"), _month("2026-01"),
                    _month("2026-03"), _month("2026-04"), orphan],
        as_of=date(2026, 11, 7),
    )
    assert result.duplicate_months == 1
    assert result.unmatched_coverage == 1
    assert result.members[0].mejor_racha_observada == 2


def test_active_without_cobertura_cannot_get_automatic_price():
    member = reconstruct_member_streaks(
        [_person(estado="ACTIVO")], [], as_of=date(2026, 11, 7)
    ).members[0]
    assert member.racha_de_entrada is None
    assert member.calidad == "SIN_EVIDENCIA"


def test_new_starts_at_month_one():
    member = reconstruct_member_streaks(
        [_person(estado="NUEVO")], [], as_of=date(2026, 11, 7)
    ).members[0]
    assert member.racha_de_entrada == 1


def test_rejects_transaction_without_paid_coverage():
    row = _month("2026-01")
    row["estado_evidencia"] = "VENTA_TOTAL"
    with pytest.raises(ValueError, match="Solo se acepta"):
        reconstruct_member_streaks([_person()], [row], as_of=date(2026, 11, 7))


def test_prepaid_future_months_are_not_counted_as_history():
    result = reconstruct_member_streaks(
        [_person(estado="ACTIVO")], [_month("2026-11"), _month("2026-12")],
        as_of=date(2026, 11, 7),
    )
    assert result.future_months_ignored == 1
    assert result.members[0].mejor_racha_observada == 1


def test_invalid_month_rejected():
    for value in ("2026-13", "noviembre"):
        with pytest.raises(ValueError):
            reconstruct_member_streaks(
                [_person()], [_month(value)], as_of=date(2026, 11, 7)
            )


def test_same_pin_in_two_members_requires_explicit_id():
    people = [
        _person(id_socio="1"),
        _person(id_socio="2"),
    ]
    unlinked = _month("2026-11")
    unlinked["id_socio"] = ""
    with pytest.raises(ValueError, match="ambiguo"):
        reconstruct_member_streaks(people, [unlinked], as_of=date(2026, 11, 7))


def test_custom_tiers_and_monotonic_rules():
    assert price_for_streak(5, ((1, 599), (3, 549), (6, 449))) == 549
    with pytest.raises(ValueError):
        price_for_streak(10, ((1, 599), (1, 499)))


def test_workbook_contains_editable_tariffs_and_quality(tmp_path):
    result = reconstruct_member_streaks(
        [_person()], [_month("2026-11")], as_of=date(2026, 11, 7)
    )
    output = tmp_path / "rachas.xlsx"
    export_workbook(output, result, as_of=date(2026, 11, 7))
    book = load_workbook(output)
    assert {"Reglas", "Detalle", "Cohortes_BI", "Calidad"} <= set(book.sheetnames)
    assert book["Reglas"]["B7"].value == 299
    assert book["Detalle"]["F2"].value == 1
    assert book["Detalle"]["G2"].value.startswith("=IF(")
    assert book["Cohortes_BI"]["E2"].value.startswith("=COUNTIFS(")
    assert book["Calidad"]["B2"].value == 1


def test_conflicting_id_is_rejected_even_if_branch_pin_matches():
    with pytest.raises(ValueError, match="contradice"):
        reconstruct_member_streaks(
            [_person()], [_month("2026-11", id_socio="999")],
            as_of=date(2026, 11, 7),
        )
