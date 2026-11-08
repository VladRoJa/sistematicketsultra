from __future__ import annotations

import json
import sqlite3

import pytest

from scripts.ops.audit_gasca_purchase_cadence import audit
from scripts.ops.consolidate_gasca_member_sales import _db_schema


def _db(path):
    with sqlite3.connect(path) as conn:
        _db_schema(conn)
        rows = [
            ("a1", "2020-01", "2020-01-10", "A", "1", "ID-A", "01",
             "CONTRATO", "12 MESES", "ACTIVO", "599"),
            ("a2", "2020-02", "2020-02-10", "A", "2", "ID-A", "01",
             "CONTRATO", "12 MESES", "ACTIVO", "599"),
            ("a3", "2020-02", "2020-02-10", "A", "3", "ID-A", "01",
             "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("a4", "2020-03", "2020-03-10", "A", "4", "ID-A", "01",
             "MENSUAL SIN CONTRATO", "MENSUAL", "ACTIVO", "599"),
            ("b1", "2020-01", "2020-01-14", "B", "5", "ID-B", "02",
             "ANUALIDAD SIN CONTRATO", "ANUAL", "ACTIVO", "4000"),
            ("c1", "2020-03", "2020-03-10", "C", "6", "ID-C", "03",
             "CONTRATO", "MENSUAL", "CANCELADO", "599"),
        ]
        conn.executemany("""
            INSERT INTO purchase_events
            (fingerprint, source_month, fecha, sucursal, folio, id_socio,
             pin, tipo, descripcion, estatus, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)


def test_audit_cadence_is_read_only_and_never_outputs_ids(tmp_path):
    path = tmp_path / "history.sqlite"
    _db(path)
    result = audit(path)
    assert result["meses_con_fuente"] == 3
    by_kind = {row["tipo"]: row for row in result["por_tipo"]}
    contracts = by_kind["CONTRATO"]
    assert contracts["socio_meses_con_compra_activa"] == 2
    assert contracts["socio_meses_comparables"] == 2
    assert contracts["con_cualquier_compra_al_mes_siguiente"] == 2
    assert contracts["con_compra_del_mismo_tipo_al_mes_siguiente"] == 1
    assert contracts["sin_compra_al_mes_siguiente"] == 0

    monthly = by_kind["MENSUAL SIN CONTRATO"]
    assert monthly["socio_meses_con_compra_activa"] == 2
    assert monthly["socio_meses_comparables"] == 1
    assert monthly["con_cualquier_compra_al_mes_siguiente"] == 1
    assert monthly["sin_mes_siguiente_verificado"] == 1
    annual = by_kind["ANUALIDAD SIN CONTRATO"]
    assert annual["socio_meses_comparables"] == 1
    assert annual["sin_compra_al_mes_siguiente"] == 1
    assert "ID-A" not in json.dumps(result)
    assert "ID-B" not in json.dumps(result)
    assert "01" not in json.dumps(result)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM purchase_events").fetchone()[0] == 6


def test_audit_missing_sqlite_does_not_create_file(tmp_path):
    path = tmp_path / "nonexistent.sqlite"
    with pytest.raises(FileNotFoundError):
        audit(path)
    assert not path.exists()
