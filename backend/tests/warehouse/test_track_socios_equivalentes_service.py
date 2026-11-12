"""QA focal de equivalencias: corte común, tarifario, nulos e histórico."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.warehouse.services import track_socios_equivalentes_service as svc


def _snap(snapshot_id: int):
    return SimpleNamespace(id=snapshot_id)


def _sources(monkeypatch, *, wellhub, totalpass, wh_visits, tp_visits):
    def snapshots(model, requested_date):
        if model is svc.IngresosWellhubSnapshotORM:
            return wellhub
        if model is svc.IngresosTotalpassSnapshotORM:
            return totalpass
        raise AssertionError("Fuente no autorizada")

    monkeypatch.setattr(svc, "_snapshots_in_month", snapshots)
    monkeypatch.setattr(svc, "_wellhub_visits", lambda sid: wh_visits[sid])
    monkeypatch.setattr(svc, "_totalpass_visits", lambda sid: tp_visits[sid])


def test_ultimo_corte_comun_no_mezcla_fechas(monkeypatch):
    d8, d10, d11 = date(2026, 11, 8), date(2026, 11, 10), date(2026, 11, 11)
    _sources(
        monkeypatch,
        wellhub={d11: _snap(111), d10: _snap(110), d8: _snap(108)},
        totalpass={d10: _snap(210), d8: _snap(208)},
        wh_visits={110: {"SERRANIA": 200}},
        tp_visits={210: {"SERRANIA": 283}},
    )
    result = svc.socios_equivalentes_por_fecha(date(2026, 11, 12))
    assert result["fecha_corte"] == "2026-11-10"
    assert (result["snapshot_id_wellhub"], result["snapshot_id_totalpass"]) == (110, 210)
    assert result["por_sucursal"]["SERRANIA"]["socios_agregadoras_eq"] == Decimal("48.3")


def test_sin_corte_comun_no_utiliza_un_solo_proveedor(monkeypatch):
    _sources(
        monkeypatch,
        wellhub={date(2026, 6, 3): _snap(3)},
        totalpass={date(2026, 6, 2): _snap(2)},
        wh_visits={},
        tp_visits={},
    )
    result = svc.socios_equivalentes_por_fecha(date(2026, 6, 4))
    assert result["estado"] == "sin_corte"
    assert result["por_sucursal"] == {}


def test_historico_2025_ofrece_wellhub_no_totalpass(monkeypatch):
    # El tabulador 2026 NO puede aplicarse a enero de 2025.
    _sources(
        monkeypatch,
        wellhub={date(2025, 1, 31): _snap(8)},
        totalpass={date(2025, 1, 31): _snap(9)},
        wh_visits={8: {"VILLA_VERDE": 99}},
        tp_visits={},
    )
    result = svc.socios_equivalentes_por_fecha(date(2025, 1, 31))
    assert result["estado"] == "parcial_tarifa_historica"
    assert result["snapshot_id_totalpass"] is None
    branch = result["por_sucursal"]["VILLA_VERDE"]
    assert branch["socios_wellhub_eq"] == Decimal("9.9")
    assert branch["socios_totalpass_eq"] is None
    assert branch["socios_agregadoras_eq"] is None


def test_26_sucursales_reproducen_totalpass_11_noviembre(monkeypatch):
    tp = {
        "AZAHARES_CUL": 367, "CARROUSEL_TJ": 233,
        "INDEPENDENCIA": 139, "INSURGENTES": 864,
        "IXTAPALUCA": 340, "LOMA_BONITA": 104,
        "METEPEC": 1208, "MISION_ENS": 228,
        "PABELLON_RTO": 54, "PAPALOTE_TJ": 147,
        "PASEO_2000": 169, "PASEO_LA_PAZ": 89,
        "SALTILLO_VILLALTA": 802, "SAN_ISIDRO_CUL": 329,
        "SAN_LUIS": 90, "SANTA_FE": 144,
        "SEND_CHIH": 252, "SEND_CUL": 461,
        "SEND_MXL": 266, "SEND_SALTILLO": 316,
        "SERRANIA": 283, "STA_CATARINA": 455,
        "TEC_MXL": 122, "TLALNEPANTLA": 564,
        "VILLAS_DEL_REY": 84, "VILLA_VERDE": 106,
    }
    assert len(tp) == 26 and sum(tp.values()) == 8216
    # Fixture sintética de Wellhub con 10,792 visitas para validar total.
    wh = {branch: 0 for branch in tp}
    wh["AZAHARES_CUL"] = 10792
    _sources(
        monkeypatch,
        wellhub={date(2026, 11, 11): _snap(209)},
        totalpass={date(2026, 11, 11): _snap(209)},
        wh_visits={209: wh},
        tp_visits={209: tp},
    )
    result = svc.socios_equivalentes_por_fecha(date(2026, 11, 12))
    values = result["por_sucursal"]
    tp_total = sum((r["socios_totalpass_eq"] for r in values.values()), Decimal(0))
    general = sum((r["socios_agregadoras_eq"] for r in values.values()), Decimal(0))
    # Decimal(1/12) es periódico: sumas por sucursal pueden diferir en la
    # última cifra de precisión del contexto, sin alterar el resultado útil.
    expected_tp = Decimal(8216 - 1136) / 10 + Decimal(1136) / 12
    assert abs(tp_total - expected_tp) < Decimal("0.0000001")
    assert general.quantize(Decimal("0.1")) == Decimal("1881.9")
    assert values["SERRANIA"]["socios_totalpass_eq"] == Decimal("28.3")
    assert values["SALTILLO_VILLALTA"]["socios_totalpass_eq"] == Decimal("80.2")


def test_fila_faltante_no_equivale_a_cero(monkeypatch):
    _sources(
        monkeypatch,
        wellhub={date(2026, 6, 30): _snap(10)},
        totalpass={date(2026, 6, 30): _snap(11)},
        wh_visits={10: {"VILLA_VERDE": 0, "SERRANIA": 50}},
        tp_visits={11: {"VILLA_VERDE": 0}},
    )
    report = svc.socios_equivalentes_por_fecha(date(2026, 6, 30))
    assert report["por_sucursal"]["VILLA_VERDE"]["socios_agregadoras_eq"] == 0
    assert report["por_sucursal"]["SERRANIA"]["socios_agregadoras_eq"] is None
    rows = [
        {"sucursal_canon": "VILLA_VERDE", "usuarios_activos_actual": 1237, "m2_sin_circulaciones": 810},
        {"sucursal_canon": "SERRANIA", "usuarios_activos_actual": 300, "m2_sin_circulaciones": 500},
    ]
    svc.add_equivalentes_to_mart_rows(rows, report)
    assert rows[0]["socios_totales_eq"] == 1237
    assert rows[0]["ocupacion_total_eq"] == float(Decimal(1237) / 810)
    assert rows[1]["socios_totales_eq"] is None
    assert rows[1]["ocupacion_total_eq"] is None


def test_mes_sin_snapshots_no_muestra_cero(monkeypatch):
    _sources(monkeypatch, wellhub={}, totalpass={}, wh_visits={}, tp_visits={})
    report = svc.socios_equivalentes_por_fecha(date(2026, 8, 1))
    rows = [{"sucursal_canon": "SERRANIA", "usuarios_activos_actual": 200, "m2_sin_circulaciones": 600}]
    svc.add_equivalentes_to_mart_rows(rows, report)
    assert report["estado"] == "sin_corte"
    assert rows[0]["socios_wellhub_eq"] is None
    assert rows[0]["socios_totalpass_eq"] is None
    assert rows[0]["socios_totales_eq"] is None
