from __future__ import annotations

import argparse
import calendar
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.warehouse.services.track_source_ingresos_daily_service import (
    refresh_track_source_ingresos_daily_for_date,
)
from app.warehouse.services.track_source_desempeno_daily_service import (
    refresh_track_source_desempeno_daily_for_date,
)
from app.warehouse.services.track_source_nuevos_daily_service import (
    refresh_track_source_nuevos_daily_for_date,
)
from app.warehouse.services.track_daily_version_service import (
    replace_current_track_daily_version,
    mark_track_daily_version_success,
)
from app.warehouse.services.track_daily_mart_service import (
    refresh_track_daily_mart_for_date,
)


REQUIRED_SNAPSHOT_TABLES = {
    "reporte_direccion": "reporte_direccion_snapshots",
    "kpi_desempeno": "kpi_desempeno_snapshots",
    "kpi_ventas_nuevos_socios": "kpi_ventas_nuevos_socios_snapshots",
}


def _parse_date(value: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except Exception as exc:
        raise ValueError(f"{field_name} debe tener formato YYYY-MM-DD: {value!r}") from exc


def _parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.strip().split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except Exception as exc:
        raise ValueError(f"month debe tener formato YYYY-MM: {value!r}") from exc

    if month < 1 or month > 12:
        raise ValueError(f"month inválido: {value!r}")

    return year, month


def _dates_for_month(month_value: str) -> list[date]:
    year, month = _parse_month(month_value)
    _, last_day = calendar.monthrange(year, month)

    return [
        date(year, month, day)
        for day in range(1, last_day + 1)
    ]


def _structured_snapshot_exists(
    *,
    table_name: str,
    business_date: date,
    snapshot_kind: str = "daily",
) -> bool:
    result = db.session.execute(
        text(
            f"""
            SELECT id
            FROM {table_name}
            WHERE business_date = :business_date
              AND snapshot_kind = :snapshot_kind
              AND is_canonical = true
            LIMIT 1
            """
        ),
        {
            "business_date": business_date,
            "snapshot_kind": snapshot_kind,
        },
    ).first()

    return result is not None


def _missing_required_snapshots(business_date: date) -> list[str]:
    missing: list[str] = []

    for report_type_key, table_name in REQUIRED_SNAPSHOT_TABLES.items():
        if not _structured_snapshot_exists(
            table_name=table_name,
            business_date=business_date,
            snapshot_kind="daily",
        ):
            missing.append(report_type_key)

    return missing


def _current_success_version_exists(
    *,
    track_date: date,
    version_type: str,
) -> bool:
    result = db.session.execute(
        text(
            """
            SELECT id
            FROM track_daily_versions
            WHERE track_date = :track_date
              AND version_type = :version_type
              AND status = 'success'
              AND is_current = true
            LIMIT 1
            """
        ),
        {
            "track_date": track_date,
            "version_type": version_type,
        },
    ).first()

    return result is not None


def _mark_version_failed(
    *,
    version_id: int,
    error_message: str,
) -> None:
    db.session.execute(
        text(
            """
            UPDATE track_daily_versions
            SET
                status = 'failed',
                finished_at_utc = :finished_at_utc,
                error_message = :error_message
            WHERE id = :version_id
            """
        ),
        {
            "version_id": version_id,
            "finished_at_utc": datetime.now(timezone.utc),
            "error_message": error_message[:1000],
        },
    )
    db.session.commit()


def _rebuild_one_date(
    *,
    track_date: date,
    requested_by: str,
    trigger_source: str,
    version_type: str,
    generation_mode: str,
    commit: bool,
    skip_existing_version: bool,
) -> dict[str, Any]:
    if skip_existing_version and _current_success_version_exists(
        track_date=track_date,
        version_type=version_type,
    ):
        print(
            f"SKIP {track_date.isoformat()} "
            f"ya existe versión current success {version_type}"
        )
        return {
            "status": "skipped_existing_version",
            "track_date": track_date.isoformat(),
            "version_type": version_type,
        }

    missing_snapshots = _missing_required_snapshots(track_date)

    if missing_snapshots:
        print(
            f"SKIP {track_date.isoformat()} faltan snapshots: "
            f"{', '.join(missing_snapshots)}"
        )
        return {
            "status": "skipped_missing_snapshots",
            "track_date": track_date.isoformat(),
            "missing_snapshots": missing_snapshots,
        }

    if not commit:
        print(
            f"DRY-RUN {track_date.isoformat()} "
            f"refrescaría sources + mart {version_type}"
        )
        return {
            "status": "dry_run",
            "track_date": track_date.isoformat(),
            "version_type": version_type,
            "generation_mode": generation_mode,
        }

    version_id: int | None = None

    try:
        sources_result = {
            "ingresos": refresh_track_source_ingresos_daily_for_date(
                business_date=track_date,
            ),
            "desempeno": refresh_track_source_desempeno_daily_for_date(
                business_date=track_date,
            ),
            "nuevos": refresh_track_source_nuevos_daily_for_date(
                business_date=track_date,
            ),
        }

        db.session.commit()

        version = replace_current_track_daily_version(
            track_date=track_date,
            version_type=version_type,
            status="running",
            started_at_utc=datetime.now(timezone.utc),
            requested_by=requested_by,
            trigger_source=trigger_source,
            retry_count=0,
            auto_commit=True,
        )
        version_id = int(version.id)

        mart_result = refresh_track_daily_mart_for_date(
            business_date=track_date,
            generation_mode=generation_mode,
            track_daily_version_id=version.id,
        )

        mark_track_daily_version_success(
            version_id=version.id,
            generated_at_utc=datetime.now(timezone.utc),
            finished_at_utc=datetime.now(timezone.utc),
            auto_commit=True,
        )

        print(
            f"OK {track_date.isoformat()} "
            f"version_id={version.id} {version_type}"
        )

        return {
            "status": "rebuilt",
            "track_date": track_date.isoformat(),
            "track_daily_version_id": version.id,
            "version_type": version_type,
            "generation_mode": generation_mode,
            "sources_result": sources_result,
            "mart_result": mart_result,
        }

    except Exception as exc:
        db.session.rollback()

        if version_id is not None:
            _mark_version_failed(
                version_id=version_id,
                error_message=str(exc),
            )

        print(f"ERROR {track_date.isoformat()}: {exc}")
        raise


def _write_jsonl(output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconstruye Track histórico desde fuentes estructuradas ya importadas."
    )
    parser.add_argument("--date", default=None, help="Fecha específica YYYY-MM-DD")
    parser.add_argument("--month", default=None, help="Mes específico YYYY-MM")
    parser.add_argument("--commit", action="store_true", help="Ejecuta cambios reales.")
    parser.add_argument(
        "--skip-existing-version",
        action="store_true",
        help="Omite fechas que ya tengan versión current success del mismo tipo.",
    )
    parser.add_argument("--requested-by", default="ADMICORP")
    parser.add_argument("--trigger-source", default="historical_backfill_base_sources")
    parser.add_argument("--version-type", default="base_nocturna_canonica")
    parser.add_argument("--generation-mode", default="official_closed_day")
    parser.add_argument(
        "--output",
        default="rebuild_track_from_sources_result.jsonl",
    )

    args = parser.parse_args()

    if not args.date and not args.month:
        raise RuntimeError("Debes enviar --date YYYY-MM-DD o --month YYYY-MM.")

    if args.date and args.month:
        raise RuntimeError("Usa solo --date o solo --month, no ambos.")

    if args.date:
        selected_dates = [
            _parse_date(args.date, field_name="date")
        ]
    else:
        selected_dates = _dates_for_month(args.month)

    print("Rebuild Track desde fuentes")
    print(f"Commit: {args.commit}")
    print(f"Fechas seleccionadas: {len(selected_dates)}")
    print(f"Version type: {args.version_type}")
    print(f"Generation mode: {args.generation_mode}")

    app = create_app()

    results: list[dict[str, Any]] = []

    with app.app_context():
        for track_date in selected_dates:
            result = _rebuild_one_date(
                track_date=track_date,
                requested_by=args.requested_by,
                trigger_source=args.trigger_source,
                version_type=args.version_type,
                generation_mode=args.generation_mode,
                commit=args.commit,
                skip_existing_version=args.skip_existing_version,
            )
            results.append(result)

    output_path = Path(args.output).resolve()
    _write_jsonl(output_path, results)

    print(f"Resultado escrito en: {output_path}")


if __name__ == "__main__":
    main()