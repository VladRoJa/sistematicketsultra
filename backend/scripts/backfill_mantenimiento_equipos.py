"""Backfill explícito de diagnóstico histórico para un único ticket."""

import argparse
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.services.mantenimiento_equipos_service import (
    MantenimientoEquiposError,
    preparar_backfill_ticket_historico,
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Clasifica un ticket histórico sin modificar la familia actual "
            "del aparato. Por defecto sólo valida y revierte."
        )
    )
    parser.add_argument("--ticket-id", required=True, type=int)
    parser.add_argument("--familia-key", required=True)
    parser.add_argument("--falla-key", required=True)
    parser.add_argument(
        "--condicion",
        required=True,
        choices=("TRABAJA", "NO_TRABAJA"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Confirma y persiste el cambio. Sin esta opción se hace rollback.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    app = create_app()

    with app.app_context():
        try:
            ticket = preparar_backfill_ticket_historico(
                args.ticket_id,
                args.familia_key,
                args.falla_key,
                args.condicion,
            )
            prepared_values = (
                ticket.id,
                ticket.familia_equipo_id,
                ticket.falla_mantenimiento_id,
                ticket.condicion_operativa,
            )

            if args.apply:
                db.session.commit()
                action = "APLICADO"
            else:
                db.session.rollback()
                action = "SIMULADO"

            ticket_id, family_id, failure_id, condition = prepared_values
            print(
                f"{action}: ticket_id={ticket_id} "
                f"familia_equipo_id={family_id} "
                f"falla_mantenimiento_id={failure_id} "
                f"condicion_operativa={condition}"
            )
            return 0
        except MantenimientoEquiposError as exc:
            db.session.rollback()
            print(f"ERROR: {exc.message}", file=sys.stderr)
            return 2
        except Exception as exc:
            db.session.rollback()
            print(f"ERROR INESPERADO: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
