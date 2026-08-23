# backend/app/warehouse/backfill/download_track_history_local.py

from __future__ import annotations

import argparse
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

from playwright.sync_api import sync_playwright

from app import create_app
from app.warehouse.services.gasca_single_report_runner_impl import (
    run_gasca_single_report,
)
from scripts import gasca_legacy_main as gasca


DEFAULT_OUTPUT_ROOT = Path("data/backfill/gasca_history")

REPORT_KPI_DESEMPENO = "kpi_desempeno"
REPORT_KPI_VENTAS_NS = "kpi_ventas_nuevos_socios"
REPORT_VENTA_TOTAL = "venta_total"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_range(start_date: date, end_date: date) -> Iterator[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _destination_path(
    *,
    output_root: Path,
    report_type_key: str,
    business_date: date,
) -> Path:
    report_dir = output_root / report_type_key
    report_dir.mkdir(parents=True, exist_ok=True)

    return report_dir / (
        f"{report_type_key}_{business_date:%Y-%m-%d}.xlsx"
    )


def _launch_browser(playwright):
    launch_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-extensions",
        "--no-zygote",
    ]

    launch_kwargs = {
        "headless": not gasca.SHOW_BROWSER,
        "args": launch_args,
        "chromium_sandbox": False,
    }

    return playwright.chromium.launch(**launch_kwargs)


def _download_kpi_desempeno_for_date(
    *,
    page,
    business_date: date,
    destination_path: Path,
) -> None:
    print(
        f"➡ KPI Desempeño {business_date.isoformat()}"
    )

    page.goto(gasca.KPI_URL, timeout=120_000)
    page.wait_for_load_state("networkidle")

    gasca.seleccionar_tipo_reporte(page, "Desempeño")
    gasca.setear_fecha_kpi(page, business_date)
    gasca.click_boton_generar(page)

    page.wait_for_timeout(1500)

    dataframe = gasca.obtener_tabla_con_sucursal(
        page,
        "KPI Desempeño",
    )

    gasca.guardar_excel_kpi_con_metadata(
        destino=destination_path,
        report_type=REPORT_KPI_DESEMPENO,
        business_date=business_date,
        generated_at=datetime.now(gasca.TZ),
        df=dataframe,
    )

    print(
        f"✔ KPI Desempeño guardado: {destination_path}"
    )


def _download_kpi_ventas_ns_for_date(
    *,
    page,
    business_date: date,
    destination_path: Path,
) -> None:
    print(
        f"➡ KPI Ventas Nuevos Socios "
        f"{business_date.isoformat()}"
    )

    page.goto(gasca.KPI_URL, timeout=120_000)
    page.wait_for_load_state("networkidle")

    gasca.seleccionar_tipo_reporte(
        page,
        "Ventas Nuevas Socios",
    )
    gasca.setear_fecha_kpi(page, business_date)
    gasca.click_boton_generar(page)

    page.wait_for_timeout(1500)

    dataframe = gasca.obtener_tabla_con_sucursal(
        page,
        "KPI Ventas Nuevos Socios",
    )

    # Conservamos el formato que actualmente produce
    # gasca_legacy_main.py para este reporte.
    dataframe.to_excel(
        destination_path,
        index=False,
    )

    print(
        f"✔ KPI Ventas Nuevos Socios guardado: "
        f"{destination_path}"
    )


def _download_venta_total_for_date(
    *,
    app,
    business_date: date,
    destination_path: Path,
) -> None:
    print(
        f"➡ Venta Total {business_date.isoformat()}"
    )

    with app.app_context():
        result = run_gasca_single_report(
            report_type_key=REPORT_VENTA_TOTAL,
            run_mode="manual_retry",
            snapshot_kind="daily",
            requested_by="historical_backfill",
            trigger_source="local_historical_download",
            requested_at=datetime.now(gasca.TZ),
            target_business_date=business_date,
        )

    source_path = Path(
        str(result.get("file_path") or "")
    ).resolve()

    if not source_path.is_file():
        raise RuntimeError(
            "Venta Total no produjo el artifact esperado. "
            f"file_path={source_path}"
        )

    metadata = result.get("metadata") or {}
    expected_date_to = business_date.isoformat()
    actual_date_to = str(
        metadata.get("date_to") or ""
    ).strip()

    if actual_date_to != expected_date_to:
        raise RuntimeError(
            "Venta Total devolvió un corte distinto al solicitado. "
            f"esperado={expected_date_to!r} "
            f"recibido={actual_date_to!r}"
        )

    expected_date_from = business_date.replace(
        day=1
    ).isoformat()
    actual_date_from = str(
        metadata.get("date_from") or ""
    ).strip()

    if actual_date_from != expected_date_from:
        raise RuntimeError(
            "Venta Total devolvió un inicio de rango inesperado. "
            f"esperado={expected_date_from!r} "
            f"recibido={actual_date_from!r}"
        )

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source_path,
        destination_path,
    )

    print(
        f"✔ Venta Total guardado: {destination_path}"
    )


def run_download(
    *,
    start_date: date,
    end_date: date,
    output_root: Path,
    sleep_seconds: float,
    skip_existing: bool,
    stop_on_error: bool,
    limit: int | None,
) -> None:
    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    gasca.validar_config()

    app = create_app()

    selected_dates = list(
        _date_range(
            start_date,
            end_date,
        )
    )

    if limit is not None:
        selected_dates = selected_dates[:limit]

    counters = {
        "dates_processed": len(selected_dates),
        "downloaded": 0,
        "skipped": 0,
        "errors": 0,
    }

    # FASE 1:
    # Los dos KPI comparten una sola sesión Playwright/Gasca.
    #
    # Esta sesión debe cerrarse por completo antes de ejecutar
    # Venta Total, porque su runner administra su propio
    # sync_playwright() internamente.
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        context = browser.new_context()
        page = context.new_page()

        try:
            print("➡ Iniciando sesión Gasca para KPIs...")
            gasca.hacer_login(page)
            print("✔ Sesión KPI lista.")

            for business_date in selected_dates:
                print("=" * 100)
                print(
                    "[TRACK_HISTORY_DOWNLOAD][KPI] "
                    f"business_date={business_date.isoformat()}"
                )

                destinations = {
                    REPORT_KPI_DESEMPENO: _destination_path(
                        output_root=output_root,
                        report_type_key=REPORT_KPI_DESEMPENO,
                        business_date=business_date,
                    ),
                    REPORT_KPI_VENTAS_NS: _destination_path(
                        output_root=output_root,
                        report_type_key=REPORT_KPI_VENTAS_NS,
                        business_date=business_date,
                    ),
                }

                jobs = (
                    (
                        REPORT_KPI_DESEMPENO,
                        lambda: _download_kpi_desempeno_for_date(
                            page=page,
                            business_date=business_date,
                            destination_path=destinations[
                                REPORT_KPI_DESEMPENO
                            ],
                        ),
                    ),
                    (
                        REPORT_KPI_VENTAS_NS,
                        lambda: _download_kpi_ventas_ns_for_date(
                            page=page,
                            business_date=business_date,
                            destination_path=destinations[
                                REPORT_KPI_VENTAS_NS
                            ],
                        ),
                    ),
                )

                for report_type_key, job in jobs:
                    destination_path = destinations[
                        report_type_key
                    ]

                    if (
                        skip_existing
                        and destination_path.is_file()
                    ):
                        counters["skipped"] += 1
                        print(
                            f"[SKIP] {report_type_key}: "
                            f"{destination_path}"
                        )
                        continue

                    try:
                        job()
                        counters["downloaded"] += 1

                    except Exception as exc:
                        counters["errors"] += 1

                        print(
                            f"[ERROR] "
                            f"{business_date.isoformat()} "
                            f"{report_type_key}: "
                            f"{type(exc).__name__}: {exc}"
                        )

                        if stop_on_error:
                            raise

                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)

        finally:
            print("➡ Cerrando navegador KPI...")
            context.close()
            browser.close()

    # FASE 2:
    # Ya fuera del sync_playwright() anterior.
    # Venta Total puede crear su propio Playwright de forma segura.
    for business_date in selected_dates:
        print("=" * 100)
        print(
            "[TRACK_HISTORY_DOWNLOAD][VENTA_TOTAL] "
            f"business_date={business_date.isoformat()}"
        )

        destination_path = _destination_path(
            output_root=output_root,
            report_type_key=REPORT_VENTA_TOTAL,
            business_date=business_date,
        )

        if (
            skip_existing
            and destination_path.is_file()
        ):
            counters["skipped"] += 1
            print(
                f"[SKIP] {REPORT_VENTA_TOTAL}: "
                f"{destination_path}"
            )
            continue

        try:
            _download_venta_total_for_date(
                app=app,
                business_date=business_date,
                destination_path=destination_path,
            )
            counters["downloaded"] += 1

        except Exception as exc:
            counters["errors"] += 1

            print(
                f"[ERROR] "
                f"{business_date.isoformat()} "
                f"{REPORT_VENTA_TOTAL}: "
                f"{type(exc).__name__}: {exc}"
            )

            if stop_on_error:
                raise

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    print("=" * 100)
    print(
        "[SUMMARY] "
        f"dates_processed={counters['dates_processed']} "
        f"downloaded={counters['downloaded']} "
        f"skipped={counters['skipped']} "
        f"errors={counters['errors']}"
    )

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga localmente las fuentes históricas "
            "necesarias para reconstruir Track."
        )
    )

    parser.add_argument(
        "--start-date",
        required=True,
        help="Fecha inicial YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Fecha final YYYY-MM-DD.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de fechas a procesar.",
    )

    args = parser.parse_args()

    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)

    if end_date < start_date:
        raise ValueError(
            "end-date no puede ser menor que start-date."
        )

    if args.limit is not None and args.limit <= 0:
        raise ValueError(
            "limit debe ser mayor que cero."
        )

    run_download(
        start_date=start_date,
        end_date=end_date,
        output_root=Path(args.output_root),
        sleep_seconds=args.sleep_seconds,
        skip_existing=not args.no_skip_existing,
        stop_on_error=args.stop_on_error,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
