"""Consolida Venta Total histórico en SQLite LOCAL (nunca en PostgreSQL).

NO infiere meses de servicio pagados ni calcula precios/rachas. Cada fila de
'purchase_events' sigue siendo una TRANSACCIÓN, no vigencia.

Ejemplo Windows (PowerShell, desde backend):
  .\\.venv\\Scripts\\python.exe -m scripts.ops.consolidate_gasca_member_sales \\
    --from-month 2020-01 --to-month 2026-10

Salida privada en backend/data/backfill/gasca_venta_total_enriched/consolidated/.
No requiere credenciales de Gasca ni conexión a Warehouse.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from calendar import monthrange
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile

from lxml import etree


SOURCE_ROOT = Path("data/backfill/gasca_venta_total_enriched")
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MEMBERSHIP_TYPES = frozenset({
    "CONTRATO", "MENSUAL SIN CONTRATO", "BIMESTRAL SIN CONTRATO",
    "TRIMESTRAL SIN CONTRATO", "SEMESTRAL SIN CONTRATO",
    "ANUALIDAD SIN CONTRATO", "SEMANAL SIN CONTRATO",
})
COLUMNS = (
    "Fecha", "Sucursal", "Folio", "Clave", "Clave Producto",
    "Descripcion", "Total", "Estatus", "PIN", "Tipo", "IDSocio",
)


def parse_month(text: str) -> date:
    if len(text) != 7 or text[4] != "-":
        raise ValueError("Mes debe tener formato YYYY-MM.")
    return date.fromisoformat(text + "-01")


def months(start: date, end: date) -> Iterator[str]:
    if start > end:
        raise ValueError("from-month posterior a to-month.")
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield f"{year:04d}-{month:02d}"
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def paths(root: Path, month: str) -> tuple[Path, Path]:
    folder = root / month
    stem = "venta_total_" + month.replace("-", "_") + "_gasca_original"
    return folder / (stem + ".xlsx"), folder / (stem + ".json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _column_number(address: str) -> int:
    value = 0
    for char in address:
        if not char.isalpha():
            break
        value = value * 26 + ord(char.upper()) - ord("A") + 1
    return value


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    result: list[str] = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for _, node in etree.iterparse(
            stream, events=("end",), tag=XML_NS + "si"
        ):
            result.append("".join(node.itertext()))
            node.clear()
            while node.getprevious() is not None:
                del node.getparent()[0]
    return result


def _cell_text(cell, shared: list[str]) -> str:
    kind = cell.get("t")
    node = cell.find(XML_NS + "v")
    value = (node.text or "") if node is not None else ""
    if kind == "s":
        return shared[int(value)].strip()
    if kind == "inlineStr":
        return "".join(cell.itertext()).strip()
    return value.strip()


def iter_xlsx_rows(path: Path) -> Iterator[dict[str, str]]:
    """Extrae encabezados por nombre, sin pandas ni pérdida de folios/IDs."""
    with ZipFile(path) as archive:
        shared = _shared_strings(archive)
        if "xl/worksheets/sheet1.xml" not in archive.namelist():
            raise ValueError("Falta hoja principal del XLSX.")
        mapping: dict[str, int] = {}
        important: set[int] = set()
        with archive.open("xl/worksheets/sheet1.xml") as stream:
            for _, row in etree.iterparse(stream, events=("end",), tag=XML_NS + "row"):
                cells = {
                    _column_number(c.get("r", "")): _cell_text(c, shared)
                    for c in row.iterchildren(XML_NS + "c")
                    if not important or _column_number(c.get("r", "")) in important
                }
                if not mapping:
                    headers = {value: index for index, value in cells.items()}
                    if all(name in headers for name in COLUMNS):
                        mapping = {name: headers[name] for name in COLUMNS}
                        important = set(mapping.values())
                    elif int(row.get("r") or 0) > 5:
                        raise ValueError("No se localizaron encabezados de Gasca.")
                else:
                    if cells.get(mapping["Folio"], "").strip():
                        yield {name: cells.get(index, "").strip()
                               for name, index in mapping.items()}
                row.clear()
                while row.getprevious() is not None:
                    del row.getparent()[0]
        if not mapping:
            raise ValueError("No se encontraron encabezados del reporte.")


def _normalize_date(value: str) -> str | None:
    for fmt in ("%d-%m-%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _db_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE purchase_events (
          fingerprint TEXT PRIMARY KEY,
          source_month TEXT NOT NULL,
          fecha TEXT NOT NULL,
          sucursal TEXT NOT NULL,
          folio TEXT NOT NULL,
          id_socio TEXT NOT NULL,
          pin TEXT NOT NULL,
          tipo TEXT NOT NULL,
          descripcion TEXT NOT NULL,
          estatus TEXT NOT NULL,
          total TEXT NOT NULL,
          -- Nunca es evidencia de servicio cubierto por sí misma.
          evidencia TEXT NOT NULL DEFAULT 'MOVIMIENTO_SIN_VIGENCIA'
        );
        CREATE VIEW member_month_sale_signals AS
        SELECT source_month AS mes_movimiento, id_socio, sucursal,
               COUNT(*) AS movimientos_membresia,
               COUNT(DISTINCT folio) AS folios_distintos,
               SUM(CASE WHEN estatus = 'ACTIVO' THEN 1 ELSE 0 END)
                   AS movimientos_activos,
               COUNT(DISTINCT pin) AS pins_distintos
        FROM purchase_events
        GROUP BY source_month, id_socio, sucursal;
    """)


def _write_batch(conn: sqlite3.Connection, batch: list[tuple]) -> int:
    if not batch:
        return 0
    before = conn.total_changes
    conn.executemany("""
        INSERT OR IGNORE INTO purchase_events (
          fingerprint, source_month, fecha, sucursal, folio,
          id_socio, pin, tipo, descripcion, estatus, total
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, batch)
    inserted = conn.total_changes - before
    batch.clear()
    return inserted


def process_month(conn: sqlite3.Connection, *, month: str,
                  path: Path) -> dict[str, object]:
    counter = Counter()
    by_type = Counter()
    by_status = Counter()
    n_inserted = 0
    batch: list[tuple] = []
    conn.execute("SAVEPOINT one_month")
    try:
        for row in iter_xlsx_rows(path):
            counter["filas_con_folio"] += 1
            date_iso = _normalize_date(row["Fecha"])
            if date_iso is None:
                counter["fechas_invalidas"] += 1
                continue
            if date_iso[:7] != month:
                counter["fuera_del_mes"] += 1
                continue
            counter["en_mes"] += 1
            pin = row["PIN"]
            member = row["IDSocio"]
            if pin:
                counter["con_pin"] += 1
            if member:
                counter["con_idsocio"] += 1
            if pin and member:
                counter["con_ambos"] += 1
            kind = row["Tipo"].upper().strip()
            status = row["Estatus"].upper().strip()
            by_type[kind or "SIN TIPO"] += 1
            by_status[status or "SIN ESTATUS"] += 1
            if kind not in MEMBERSHIP_TYPES:
                continue
            counter["tipo_membresia"] += 1
            if not member or not pin:
                counter["tipo_membresia_sin_identidad_completa"] += 1
                continue
            counter["membresia_identificada"] += 1
            normalized = (
                month, date_iso, row["Sucursal"].upper(), row["Folio"],
                row["Clave"], row["Clave Producto"], row["Descripcion"],
                row["Total"], status, member, pin, kind,
            )
            fingerprint = hashlib.sha256(json.dumps(
                normalized, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            batch.append((
                fingerprint, month, date_iso, row["Sucursal"].upper(),
                row["Folio"], member, pin, kind, row["Descripcion"],
                status, row["Total"],
            ))
            if len(batch) >= 1000:
                n_inserted += _write_batch(conn, batch)
        n_inserted += _write_batch(conn, batch)
        if not counter["filas_con_folio"]:
            raise ValueError("XLSX sin movimientos válidos.")
        if counter["en_mes"] < counter["filas_con_folio"] * 0.90:
            raise ValueError("La mayoría de movimientos no corresponde al mes.")
        conn.execute("RELEASE one_month")
    except Exception:
        conn.execute("ROLLBACK TO one_month")
        conn.execute("RELEASE one_month")
        raise
    counter["membresias_unicas"] = n_inserted
    counter["renglones_identicos"] = counter["membresia_identificada"] - n_inserted
    return {
        "estado": "OK",
        "metricas": dict(counter),
        "tipos": dict(by_type.most_common()),
        "estatus": dict(by_status.most_common()),
    }


def _report_missing(path: Path, manifest: Path) -> dict[str, object]:
    partial = path.with_name(path.stem + ".partial.xlsx")
    if partial.exists():
        return {"estado": "DESCARGA_PARCIAL_NO_VALIDADA"}
    if path.exists() != manifest.exists():
        return {"estado": "ARCHIVO_O_MANIFIESTO_INCOMPLETO"}
    return {"estado": "SIN_ARCHIVO_VERIFICADO"}


def consolidate(*, source_root: Path, start: date, end: date,
                output_dir: Path, replace: bool = False) -> dict:
    if output_dir.resolve() == source_root.resolve():
        raise ValueError("Se requiere output_dir separado de los archivos RAW.")
    output_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        output_dir.chmod(0o700)
    filename = f"member_sales_{start:%Y%m}_{end:%Y%m}"
    final_db = output_dir / (filename + ".sqlite")
    report_path = output_dir / (filename + "_quality.json")
    temp_db = output_dir / (filename + ".working.sqlite")
    if temp_db.exists():
        raise RuntimeError("Existe una compilación .working.sqlite sin resolver.")
    if (final_db.exists() or report_path.exists()) and not replace:
        raise FileExistsError(
            f"Ya existe salida {final_db}. Repetir solo con --replace."
        )
    result = {
        "desde": f"{start:%Y-%m}", "hasta": f"{end:%Y-%m}",
        "advertencia": (
            "Son MOVIMIENTOS POR MES DE COMPRA, NO MESES DE SERVICIO PAGADOS. "
            "Nunca enviar este resultado directo al motor de rachas o campañas."
        ),
        "meses": {}, "resumen": {},
    }
    conn = sqlite3.connect(temp_db)
    try:
        _db_schema(conn)
        for month in months(start, end):
            xlsx, manifest = paths(source_root, month)
            if not xlsx.is_file() or not manifest.is_file():
                result["meses"][month] = _report_missing(xlsx, manifest)
                print(f"[MISSING] {month}: {result['meses'][month]['estado']}")
                continue
            try:
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
                if metadata.get("year_month") != month:
                    raise ValueError("Mes del manifiesto diferente.")
                if metadata.get("sha256") != sha256_file(xlsx):
                    raise ValueError("SHA256 no coincide con el manifiesto.")
                profile = process_month(conn, month=month, path=xlsx)
                result["meses"][month] = profile
                count = profile["metricas"]
                print(f"[OK] {month}: movimientos={count.get('filas_con_folio', 0)} "
                      f"identificados={count.get('con_ambos', 0)} "
                      f"membresias_unicas={count.get('membresias_unicas', 0)}")
            except Exception as exc:
                result["meses"][month] = {
                    "estado": "ERROR_LECTURA_O_INTEGRIDAD", "detalle": str(exc),
                }
                print(f"[ERROR] {month}: {type(exc).__name__}: {exc}")
        conn.executescript("""
          CREATE INDEX ix_member_events_member_month
              ON purchase_events (id_socio, source_month);
          CREATE INDEX ix_member_events_folio
              ON purchase_events (source_month, sucursal, folio);
        """)
        result["resumen"] = {
            "meses_solicitados": len(result["meses"]),
            "meses_ok": sum(r["estado"] == "OK" for r in result["meses"].values()),
            "meses_sin_verificar": [
                m for m, r in result["meses"].items() if r["estado"] != "OK"
            ],
            "movimientos_candidatos_distintos": conn.execute(
                "SELECT COUNT(*) FROM purchase_events"
            ).fetchone()[0],
            "ids_socios_distintos": conn.execute(
                "SELECT COUNT(DISTINCT id_socio) FROM purchase_events"
            ).fetchone()[0],
            "socios_mes_sucursal": conn.execute(
                "SELECT COUNT(*) FROM member_month_sale_signals"
            ).fetchone()[0],
            "calidad": "MOVIMIENTOS_SIN_VIGENCIA",
        }
        conn.commit()
    except Exception:
        conn.close()
        # Mantener archivo de trabajo privado para diagnóstico en caso de error.
        raise
    else:
        conn.close()
    if os.name == "posix":
        temp_db.chmod(0o600)
    if final_db.exists():
        final_db.unlink()  # reemplazo explícito --replace, solo SQLite local.
    temp_db.rename(final_db)
    # Escribir reporte después de terminar base; no contiene PIN ni IDs.
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if os.name == "posix":
        report_path.chmod(0o600)
    print("[SUMMARY] " + json.dumps(result["resumen"], ensure_ascii=False))
    print(f"[OUTPUT] SQLite local: {final_db}")
    print(f"[OUTPUT] Calidad agregada: {report_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-month", type=parse_month, required=True)
    parser.add_argument("--to-month", type=parse_month, required=True)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=SOURCE_ROOT / "consolidated")
    parser.add_argument("--replace", action="store_true",
                        help="Sobrescribe solo el consolidado SQLite local previo.")
    args = parser.parse_args()
    consolidate(source_root=args.source_root, start=args.from_month,
                end=args.to_month, output_dir=args.output_dir,
                replace=args.replace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
