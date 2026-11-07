"""Recupera RAW ORIGINAL Venta Total de Gasca para meses históricos.

Usa la autenticación y los selectores Playwright ya existentes en Suite Ultra.
Por defecto solo imprime el plan: --execute permite descargar. Nunca escribe
en PostgreSQL, promueve snapshots, envía campañas ni altera archivos antiguos.

cd backend
python -m app.warehouse.backfill.redownload_venta_total_history \
  --from-month 2024-12 --to-month 2024-12
python -m app.warehouse.backfill.redownload_venta_total_history \
  --from-month 2024-12 --to-month 2024-12 --execute
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator
from zipfile import BadZipFile, ZipFile

from lxml import etree

from app import create_app
from app.warehouse.services import gasca_single_report_runner_impl as gasca


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REQUIRED_COLUMNS = ("Fecha", "Folio", "PIN", "Tipo", "IDSocio")
DEFAULT_ROOT = Path("data/backfill/gasca_venta_total_enriched")


class HistoricalRawError(RuntimeError):
    pass


def parse_month(value: str) -> date:
    try:
        parsed = date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise ValueError("Mes inválido: formato YYYY-MM requerido.") from exc
    if len(value) != 7 or value[4] != "-":
        raise ValueError("Mes inválido: formato YYYY-MM requerido.")
    return parsed


def iter_month_ends(start: date, end: date) -> Iterator[date]:
    if start > end:
        raise ValueError("from-month no puede ser posterior a to-month.")
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield date(year, month, monthrange(year, month)[1])
        month = month + 1
        if month == 13:
            month = 1
            year += 1


def month_paths(root: Path, end: date) -> tuple[Path, Path]:
    folder = root / f"{end:%Y-%m}"
    stem = f"venta_total_{end:%Y_%m}_gasca_original"
    return folder / (stem + ".xlsx"), folder / (stem + ".json")


def _column_number(address: str) -> int:
    number = 0
    for c in address:
        if not c.isalpha():
            break
        number = number * 26 + ord(c.upper()) - ord("A") + 1
    return number


def _shared_strings(zipped: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zipped.namelist():
        return []
    values: list[str] = []
    with zipped.open("xl/sharedStrings.xml") as stream:
        for _, node in etree.iterparse(stream, events=("end",), tag=NS + "si"):
            values.append("".join(node.itertext()))
            node.clear()
            while node.getprevious() is not None:
                del node.getparent()[0]
    return values


def _cell_value(cell, strings: list[str]) -> str:
    node = cell.find(NS + "v")
    value = node.text if node is not None else None
    kind = cell.get("t")
    if kind == "s" and value is not None:
        return strings[int(value)].strip()
    if kind == "inlineStr":
        return "".join(cell.itertext()).strip()
    return str(value or "").strip()


def _parse_movement_date(value: str) -> date | None:
    for fmt in ("%d-%m-%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def profile_download(path: Path, *, expected_month: date) -> dict[str, object]:
    """Cuenta identidades sin mostrar PII y valida el rango principal del RAW."""
    if not path.is_file() or not path.stat().st_size:
        raise HistoricalRawError("No se recibió un XLSX no vacío.")
    try:
        with ZipFile(path) as zipped:
            if zipped.testzip() is not None:
                raise HistoricalRawError("XLSX corrupto.")
            shared = _shared_strings(zipped)
            if "xl/worksheets/sheet1.xml" not in zipped.namelist():
                raise HistoricalRawError("No existe hoja principal del reporte.")
            columns: dict[str, int] = {}
            n_rows = n_pin = n_member_id = n_both = n_membership = 0
            in_month = out_month = bad_dates = 0
            statuses: dict[str, int] = {}
            seen_header = False
            with zipped.open("xl/worksheets/sheet1.xml") as stream:
                for _, row in etree.iterparse(stream, events=("end",), tag=NS + "row"):
                    index = int(row.get("r") or 0)
                    if index < 1:
                        continue
                    # El XLSX original pone título en fila 1 y encabezados en fila 2.
                    # También tolera la variante sin título, sin convertir ni reescribir.
                    cells: dict[int, str] = {}
                    for cell in row.iterchildren(NS + "c"):
                        column = _column_number(cell.get("r") or "")
                        if not seen_header or column in columns.values():
                            cells[column] = _cell_value(cell, shared)
                    if not seen_header:
                        candidates = {value: col for col, value in cells.items()}
                        if all(name in candidates for name in REQUIRED_COLUMNS):
                            columns = {name: candidates[name] for name in REQUIRED_COLUMNS}
                            seen_header = True
                        elif index >= 4:
                            raise HistoricalRawError(
                                "No encontramos encabezado con Fecha, Folio, PIN, Tipo e IDSocio."
                            )
                    else:
                        value = lambda name: cells.get(columns[name], "")
                        if value("Folio"):
                            n_rows += 1
                            pin, id_socio = value("PIN"), value("IDSocio")
                            n_pin += bool(pin)
                            n_member_id += bool(id_socio)
                            n_both += bool(pin and id_socio)
                            n_membership += bool(pin and id_socio and value("Tipo") in {
                                "Contrato", "Mensual sin contrato",
                                "Bimestral sin contrato", "Trimestral sin contrato",
                                "Semestral sin contrato", "Anualidad sin contrato",
                            })
                            movement_date = _parse_movement_date(value("Fecha"))
                            if movement_date is None:
                                bad_dates += 1
                            elif (movement_date.year, movement_date.month) == (
                                expected_month.year, expected_month.month
                            ):
                                in_month += 1
                            else:
                                out_month += 1
                    row.clear()
                    while row.getprevious() is not None:
                        del row.getparent()[0]
    except (BadZipFile, etree.XMLSyntaxError, OSError, IndexError) as exc:
        raise HistoricalRawError("No se pudo validar XLSX original.") from exc

    if not seen_header or n_rows == 0:
        raise HistoricalRawError("No se encontraron filas válidas.")
    if in_month < n_rows * 0.90:
        raise HistoricalRawError(
            f"Reporte equivocado: {in_month}/{n_rows} movimientos del mes solicitado."
        )
    return {
        "rows": n_rows,
        "rows_with_pin": n_pin,
        "rows_with_idsocio": n_member_id,
        "rows_with_both": n_both,
        "candidate_membership_rows": n_membership,
        "movement_rows_in_month": in_month,
        "movement_rows_out_of_month": out_month,
        "movement_rows_invalid_date": bad_dates,
        "identity_available": bool(n_pin and n_member_id),
        "raw_file_bytes": path.stat().st_size,
    }


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resumable(output: Path, manifest: Path) -> bool:
    if not output.exists() and not manifest.exists():
        return False
    if not output.is_file() or not manifest.is_file():
        raise HistoricalRawError(
            f"Archivos previos incompletos: {output.parent}. Revisar antes de repetir."
        )
    record = json.loads(manifest.read_text(encoding="utf-8"))
    if record.get("sha256") != file_sha256(output):
        raise HistoricalRawError(f"SHA256 diferente en {output}; no se sobrescribió.")
    return True


def download_month(page, *, runtime, end: date, target: Path) -> None:
    """Reutiliza selectores y autenticación actuales; conserva el XLSX original."""
    page.goto(runtime.reportes_url, timeout=120_000)
    page.wait_for_load_state("networkidle")
    gasca._seleccionar_tipo_reporte(page, "Reporte Venta Total")
    gasca._rellenar_fechas_rango_simple(
        page=page,
        fecha_inicio=end.replace(day=1),
        fecha_fin=end,
    )
    with page.expect_response(
        lambda response: "ReporteVentaTotal_Ajax" in response.url,
        timeout=120_000,
    ) as response_info:
        gasca._click_boton_generar(page)
    gasca._validate_venta_total_ajax_response(response_info.value)
    gasca._esperar_fin_carga_venta_total(page=page, timeout_seconds=120)
    page.wait_for_selector("button:has-text('Exportar')", timeout=120_000)
    gasca._descargar_excel_desde_tabla(
        page=page,
        nombre_reporte="Reporte Venta Total",
        destination_path=target,
    )
    # IMPORTANTE: NO llamar _limpiar_excel_inplace: mantiene IDs y folios originales.


def run_backfill(
    *,
    start: date,
    end: date,
    output_root: Path = DEFAULT_ROOT,
    execute: bool = False,
    limit: int | None = None,
    sleep_seconds: float = 3.0,
) -> dict[str, int]:
    if limit is not None and limit < 1:
        raise ValueError("limit debe ser positivo.")
    if sleep_seconds < 2.0:
        raise ValueError("sleep-seconds debe ser >=2 para moderar descargas.")
    dates = list(iter_month_ends(start, end))
    if limit is not None:
        dates = dates[:limit]
    stats = {"planned": len(dates), "downloaded": 0, "skipped": 0, "errors": 0}
    for month in dates:
        path, _ = month_paths(output_root, month)
        print(f"[PLAN] {month:%Y-%m} => {path}")
    if not execute:
        print("[DRY-RUN] Ninguna sesión Gasca fue iniciada.")
        return stats

    # El login solo se realiza una vez por lote y no se conecta PostgreSQL.
    app = create_app()
    with app.app_context():
        runtime = gasca._resolve_runtime_config()
        today = datetime.now(timezone.utc).date()
        if any(day > today for day in dates):
            raise ValueError("No se permite descargar meses futuros.")
        with gasca._authenticated_page(runtime) as page:
            for index, month in enumerate(dates):
                output, manifest = month_paths(output_root, month)
                try:
                    if resumable(output, manifest):
                        stats["skipped"] += 1
                        print(f"[SKIP] {month:%Y-%m} manifest+SHA verificados")
                        continue
                    output.parent.mkdir(parents=True, exist_ok=True)
                    temp = output.with_name(output.stem + ".partial.xlsx")
                    if temp.exists():
                        raise HistoricalRawError(f"Existe descarga parcial: {temp}.")
                    download_month(page, runtime=runtime, end=month, target=temp)
                    profile = profile_download(temp, expected_month=month)
                    file_hash = file_sha256(temp)
                    # No publicar en Warehouse ni sustituir el snapshot anterior.
                    if output.exists():
                        raise HistoricalRawError(f"Ya existe: {output}")
                    temp.rename(output)
                    metadata = {
                        "report_type_key": "venta_total",
                        "source": "Gasca Playwright existing selectors",
                        "year_month": f"{month:%Y-%m}",
                        "date_from": month.replace(day=1).isoformat(),
                        "date_to": month.isoformat(),
                        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                        "original_filename": output.name,
                        "sha256": file_hash,
                        "state": "RAW_ONLY_NON_CANONICAL",
                        **profile,
                    }
                    manifest.write_text(
                        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    stats["downloaded"] += 1
                    print(
                        f"[OK] {month:%Y-%m} rows={profile['rows']} "
                        f"PIN={profile['rows_with_pin']} "
                        f"IDSocio={profile['rows_with_idsocio']} "
                        f"candidate_memberships={profile['candidate_membership_rows']} "
                        f"sha256={file_hash[:12]}..."
                    )
                    if not profile["identity_available"]:
                        print(f"[WARNING] {month:%Y-%m}: no tiene identidades; requiere revisión.")
                except Exception as exc:
                    stats["errors"] += 1
                    print(f"[ERROR] {month:%Y-%m}: {type(exc).__name__}: {exc}")
                    # No borrar parcial; deja evidencia inspeccionable y evita sobrescribir.
                if index < len(dates) - 1:
                    time.sleep(sleep_seconds)
    print(f"[SUMMARY] {stats}")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-month", required=True, type=parse_month)
    parser.add_argument("--to-month", required=True, type=parse_month)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--execute", action="store_true",
                        help="Realiza el scraping; sin este flag solo lista el plan.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=3.0)
    args = parser.parse_args()
    result = run_backfill(
        start=args.from_month, end=args.to_month, output_root=args.output_root,
        execute=args.execute, limit=args.limit, sleep_seconds=args.sleep_seconds,
    )
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
