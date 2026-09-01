# backend/app/warehouse/backfill/download_kpi_desempeno_weekly.py

from __future__ import annotations

import argparse
import calendar
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.warehouse.backfill import download_track_history_local as history


START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 8, 30)

TARGET_DAYS = (1, 7, 14, 21, 28)

DEFAULT_OUTPUT_DIR = Path(
    "data/kpi_desempeno_semanal"
)


def _target_dates() -> list[date]:
    dates: list[date] = []

    year = START_DATE.year
    month = START_DATE.month

    while (year, month) <= (END_DATE.year, END_DATE.month):

        # ---------------------------------------------------------
        # Cortes fijos:
        # 1, 7, 14, 21 y 28 de cada mes.
        # ---------------------------------------------------------
        for day in TARGET_DAYS:
            business_date = date(
                year,
                month,
                day,
            )

            if START_DATE <= business_date <= END_DATE:
                dates.append(
                    business_date
                )

        # ---------------------------------------------------------
        # Corte final del mes.
        #
        # Ejemplos:
        # enero -> 31
        # abril -> 30
        # febrero -> 28
        #
        # Si END_DATE termina antes del cierre natural del último
        # mes, se utiliza END_DATE.
        #
        # Ejemplo actual:
        # agosto 2026 termina el día 30, por lo que usamos 30
        # aunque agosto naturalmente tenga 31 días.
        # ---------------------------------------------------------
        last_day_number = calendar.monthrange(
            year,
            month,
        )[1]

        month_end_date = date(
            year,
            month,
            last_day_number,
        )

        if (
            year == END_DATE.year
            and month == END_DATE.month
            and END_DATE < month_end_date
        ):
            month_end_date = END_DATE

        # ---------------------------------------------------------
        # Evitar duplicados.
        #
        # Ejemplo:
        # febrero de un año no bisiesto termina el día 28.
        # Como el 28 ya está dentro de TARGET_DAYS,
        # no debe agregarse dos veces.
        # ---------------------------------------------------------
        if (
            START_DATE <= month_end_date <= END_DATE
            and month_end_date not in dates
        ):
            dates.append(
                month_end_date
            )

        # ---------------------------------------------------------
        # Avanzar al siguiente mes.
        # ---------------------------------------------------------
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1

    return sorted(
        dates
    )


def _validate_config() -> None:
    missing: list[str] = []

    if not history.gasca.USER:
        missing.append(
            "DIRECCION_USER"
        )

    if not history.gasca.PASS:
        missing.append(
            "DIRECCION_PASS"
        )

    if not history.gasca.LOGIN_URL:
        missing.append(
            "DIRECCION_LOGIN_URL"
        )

    if missing:
        raise RuntimeError(
            "Faltan variables requeridas: "
            + ", ".join(
                missing
            )
        )


def run(
    *,
    output_dir: Path,
    dry_run: bool,
    limit: int | None,
    overwrite: bool,
    sleep_seconds: float,
) -> int:

    target_dates = _target_dates()

    if limit is not None:
        target_dates = target_dates[:limit]

    print()
    print("=" * 90)
    print(
        "KPI DESEMPEÑO HISTÓRICO"
    )
    print("=" * 90)

    print(
        f"Rango: "
        f"{START_DATE.isoformat()} "
        f"-> "
        f"{END_DATE.isoformat()}"
    )

    print(
        "Cortes fijos: "
        + ", ".join(
            str(day)
            for day in TARGET_DAYS
        )
    )

    print(
        "Corte adicional: "
        "último día disponible de cada mes"
    )

    print(
        f"Total de fechas seleccionadas: "
        f"{len(target_dates)}"
    )

    print("=" * 90)

    for business_date in target_dates:
        print(
            business_date.isoformat()
        )

    # -------------------------------------------------------------
    # Dry run:
    # solamente muestra las fechas.
    # -------------------------------------------------------------
    if dry_run:
        print()
        print("=" * 90)
        print(
            "[DRY-RUN] "
            "No se abrió navegador."
        )
        print(
            "[DRY-RUN] "
            "No se descargó ningún archivo."
        )
        print("=" * 90)

        return 0

    _validate_config()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    downloaded = 0
    skipped = 0
    errors = 0

    failed_dates: list[date] = []

    with sync_playwright() as playwright:

        browser = history._launch_browser(
            playwright
        )

        context = browser.new_context()

        page = context.new_page()

        try:
            print()
            print(
                "➡ Iniciando sesión Gasca..."
            )

            history.gasca.hacer_login(
                page
            )

            print(
                "✔ Sesión Gasca lista."
            )

            for index, business_date in enumerate(
                target_dates,
                start=1,
            ):
                print()
                print("=" * 90)

                print(
                    f"[{index}/"
                    f"{len(target_dates)}] "
                    f"KPI Desempeño "
                    f"{business_date.isoformat()}"
                )

                destination_path = (
                    output_dir
                    / (
                        "kpi_desempeno_"
                        f"{business_date:%Y-%m-%d}"
                        ".xlsx"
                    )
                )

                # -------------------------------------------------
                # No volver a bajar archivos existentes,
                # salvo que se mande --overwrite.
                # -------------------------------------------------
                if (
                    destination_path.is_file()
                    and not overwrite
                ):
                    skipped += 1

                    print(
                        "[SKIP] Ya existe: "
                        f"{destination_path}"
                    )

                    continue

                try:
                    history.gasca.ejecutar_con_reintentos(
                        lambda d=business_date,
                        p=destination_path: (
                            history
                            ._download_kpi_desempeno_for_date(
                                page=page,
                                business_date=d,
                                destination_path=p,
                            )
                        ),
                        (
                            "KPI Desempeño "
                            f"{business_date.isoformat()}"
                        ),
                    )

                    downloaded += 1

                    print(
                        "[OK] Guardado: "
                        f"{destination_path}"
                    )

                except Exception as exc:
                    errors += 1

                    failed_dates.append(
                        business_date
                    )

                    print(
                        "[ERROR] "
                        f"{business_date.isoformat()} "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                if sleep_seconds > 0:
                    time.sleep(
                        sleep_seconds
                    )

        finally:
            print()
            print(
                "➡ Cerrando navegador..."
            )

            context.close()
            browser.close()

    print()
    print("=" * 90)
    print(
        "RESUMEN"
    )
    print("=" * 90)

    print(
        f"Fechas seleccionadas: "
        f"{len(target_dates)}"
    )

    print(
        f"Descargadas: "
        f"{downloaded}"
    )

    print(
        f"Ya existentes: "
        f"{skipped}"
    )

    print(
        f"Errores: "
        f"{errors}"
    )

    if failed_dates:
        print()
        print(
            "FECHAS CON ERROR:"
        )

        for failed_date in failed_dates:
            print(
                f"  - "
                f"{failed_date.isoformat()}"
            )

    print("=" * 90)

    return 1 if failed_dates else 0


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Descarga KPI Desempeño histórico "
            "para los días 1, 7, 14, 21 y 28, "
            "más el último día disponible de "
            "cada mes."
        )
    )

    parser.add_argument(
        "--output-dir",
        default=str(
            DEFAULT_OUTPUT_DIR
        ),
        help=(
            "Carpeta donde se guardarán "
            "los archivos descargados."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Muestra las fechas seleccionadas "
            "sin descargar archivos."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Limita la cantidad de fechas "
            "procesadas. Útil para pruebas."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Vuelve a descargar archivos "
            "aunque ya existan."
        ),
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=2.0,
        help=(
            "Segundos de espera entre "
            "una descarga y la siguiente."
        ),
    )

    args = parser.parse_args()

    if (
        args.limit is not None
        and args.limit <= 0
    ):
        raise ValueError(
            "--limit debe ser mayor que cero."
        )

    if args.sleep_seconds < 0:
        raise ValueError(
            "--sleep-seconds no puede ser negativo."
        )

    exit_code = run(
        output_dir=Path(
            args.output_dir
        ),
        dry_run=args.dry_run,
        limit=args.limit,
        overwrite=args.overwrite,
        sleep_seconds=args.sleep_seconds,
    )

    raise SystemExit(
        exit_code
    )


if __name__ == "__main__":
    main()