from __future__ import annotations

import argparse
import json
from datetime import date

from app import create_app, db

from .attendance_capture_service import (
    capture_and_ingest_attendance,
    capture_and_validate_attendance,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "La fecha debe usar YYYY-MM-DD."
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga e ingesta el reporte "
            "de Estadísticas de Asistencias."
        )
    )
    parser.add_argument(
        "--date",
        dest="business_date",
        required=True,
        type=_parse_date,
        help="Fecha de negocio YYYY-MM-DD.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Reintentos completos de descarga.",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Muestra Chromium durante la prueba.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help=(
            "Descarga y parsea sin escribir "
            "en PostgreSQL."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    app = create_app()
    if args.show_browser:
        app.config["SHOW_BROWSER"] = True

    with app.app_context():
        try:
            if args.validate_only:
                result = (
                    capture_and_validate_attendance(
                        business_date=(
                            args.business_date
                        ),
                        max_retries=(
                            args.max_retries
                        ),
                    )
                )
            else:
                result = (
                    capture_and_ingest_attendance(
                        business_date=(
                            args.business_date
                        ),
                        max_retries=(
                            args.max_retries
                        ),
                        trigger_source="LOCAL_CLI",
                    )
                )
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        finally:
            db.session.remove()


if __name__ == "__main__":
    main()
