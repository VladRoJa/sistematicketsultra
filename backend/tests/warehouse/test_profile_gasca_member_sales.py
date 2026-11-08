from __future__ import annotations

import json
import sqlite3

import pytest

from scripts.ops.consolidate_gasca_member_sales import _db_schema
from scripts.ops.profile_gasca_member_sales import profile


def _create_test_db(path):
    with sqlite3.connect(path) as conn:
        _db_schema(conn)
        events = [
            ("fp1", "2024-01", "2024-01-02", "CENTRO", "F01",
             "MEMBER-X", "PIN001", "Contrato", "DOMICILIADO 12 MESES",
             "ACTIVO", "599"),
            ("fp2", "2024-01", "2024-01-03", "CENTRO", "F02",
             "MEMBER-X", "PIN001", "Contrato", "RENOVACION RECURRENTE",
             "ACTIVO", "599"),
            ("fp3", "2024-02", "2024-02-03", "NORTE", "F03",
             "MEMBER-X", "PIN002", "Mensual sin contrato", "CONVENIO",
             "CANCELADO", "0"),
            ("fp4", "2024-02", "2024-02-05", "SUR", "F04",
             "MEMBER-Y", "PIN003", "Anualidad sin contrato", "ANUALIDAD",
             "ACTIVO", "1000"),
        ]
        conn.executemany("""
          INSERT INTO purchase_events (
            fingerprint, source_month, fecha, sucursal, folio,
            id_socio, pin, tipo, descripcion, estatus, total
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, events)


def test_profile_aggregates_without_exposing_personal_identifiers(tmp_path):
    db_path = tmp_path / "history.sqlite"
    _create_test_db(db_path)
    original = db_path.read_bytes()
    result = profile(db_path)
    assert result["totales"] == {
        "movimientos": 4,
        "ids_socios_distintos": 2,
        "meses_con_movimientos": 2,
        "movimientos_estatus_activo": 3,
    }
    assert result["repeticiones_mes_de_compra"] == {
        "socio_meses_con_varias_transacciones": 1,
        "transacciones_adicionales": 1,
        "max_movimientos_mismo_socio_mes": 2,
    }
    assert result["movimientos_entre_sucursales"] == {
        "ids_socio_observados_en_varias_sucursales": 1,
    }
    assert result["senales_no_excluyentes_de_duracion_y_producto"][
        "anual_o_12_meses"
    ] == 2
    assert result["senales_no_excluyentes_de_duracion_y_producto"][
        "domiciliado"
    ] == 1
    assert result["senales_no_excluyentes_de_duracion_y_producto"][
        "recurrente"
    ] == 1
    assert result["cruce_tipo_descripcion"][0]["tipo"] == "Contrato"
    assert result["cruce_tipo_descripcion"][0]["movimientos"] == 2
    assert result["cruce_tipo_descripcion"][0]["texto_domiciliado"] == 1
    assert result["cruce_tipo_descripcion"][0]["texto_12_meses_o_anual"] == 1
    assert result["cruce_tipo_descripcion"][0]["texto_recurrente"] == 1
    assert len(result["por_mes"]) == 2
    assert "MEMBER-X" not in json.dumps(result)
    assert "PIN001" not in json.dumps(result)
    assert "F01" not in json.dumps(result)
    assert db_path.read_bytes() == original


def test_profile_missing_file_does_not_create_sqlite(tmp_path):
    absent = tmp_path / "not_created.sqlite"
    with pytest.raises(FileNotFoundError):
        profile(absent)
    assert not absent.exists()
