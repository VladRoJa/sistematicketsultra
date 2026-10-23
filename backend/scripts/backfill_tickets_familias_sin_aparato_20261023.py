"""Clasificación puntual de cuatro tickets históricos sin aparato asociado.

Fuente de evidencia: reporte_mantenimiento_todo_23-oct-26.xlsx, pestaña Tickets.
NO asigna aparato, falla, condición operativa, estado ni catálogo de edificio.
Por defecto ejecuta una simulación; escribir exige --apply --expect-count 4.
La salida de la ejecución debe conservarse como registro de la intervención.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


# Criterios explícitos: el texto identifica la naturaleza de los equipos;
# no pretendemos inferir el aparato específico ni capturar una falla estructurada.
CASES = {
    2150: {
        "family": "PESO_INTEGRADO",
        "description": "10 pines selectores de peso",
        "reason": "Pines selectores de peso; familia Peso Integrado.",
    },
    2151: {
        "family": "PESO_INTEGRADO",
        "description": "10 pines selectores",
        "reason": "Pines selectores; familia Peso Integrado.",
    },
    2652: {
        "family": "SPINNING",
        "description": "PEDALES DE CONTACTO DE BICICLETAS SPINNNIG. 10 PARES.",
        "reason": "Pedales de contacto identificados para bicicletas spinning.",
    },
    2941: {
        "family": "ESCALADORA",
        "description": "sE DAÑARON LOS SENSORES DE LAS ESCALERAS SIN FIN LAS CUALES ESTAN FUERA DE SERVICIO",
        "reason": "Sensores de escaleras sin fin.",
    },
}

SELECT_TICKET = text("""
SELECT id, descripcion, departamento_id, aparato_id, estado,
       familia_equipo_id, falla_mantenimiento_id, condicion_operativa
FROM tickets
WHERE id = :ticket_id
""")
SELECT_TICKET_FOR_UPDATE = text("""
SELECT id, descripcion, departamento_id, aparato_id, estado,
       familia_equipo_id, falla_mantenimiento_id, condicion_operativa
FROM tickets
WHERE id = :ticket_id
FOR UPDATE
""")
SELECT_FAMILY = text("""
SELECT id FROM familia_equipo WHERE key = :key AND activo IS TRUE
""")
UPDATE_FAMILY = text("""
UPDATE tickets AS t
SET familia_equipo_id = :family_id
WHERE t.id = :ticket_id
  AND t.descripcion = :description
  AND t.departamento_id = 1
  AND t.aparato_id IS NULL
  AND t.estado IN ('abierto', 'en progreso', 'por_validar')
  AND t.familia_equipo_id IS NULL
  AND t.falla_mantenimiento_id IS NULL
  AND t.condicion_operativa IS NULL
  AND EXISTS (
      SELECT 1 FROM familia_equipo AS f
      WHERE f.id = :family_id AND f.key = :family_key AND f.activo IS TRUE
  )
RETURNING t.id
""")


def validation_error(row, case):
    """Devuelve motivo de exclusión; nunca sobreescribe diagnósticos existentes."""
    if row is None:
        return "TICKET_NO_EXISTE"
    if row["descripcion"] != case["description"]:
        return "DESCRIPCION_CAMBIO"
    if row["departamento_id"] != 1:
        return "NO_ES_MANTENIMIENTO"
    if row["aparato_id"] is not None:
        return "YA_TIENE_APARATO"
    if row["estado"] not in {"abierto", "en progreso", "por_validar"}:
        return "ESTADO_CAMBIO"
    if row["familia_equipo_id"] is not None:
        return "YA_TIENE_FAMILIA"
    if row["falla_mantenimiento_id"] is not None:
        return "YA_TIENE_FALLA"
    if row["condicion_operativa"] is not None:
        return "YA_TIENE_CONDICION"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-count", type=int)
    args = parser.parse_args(argv)
    if args.apply and args.expect_count != len(CASES):
        parser.error(f"--apply exige --expect-count {len(CASES)}")

    app = create_app()
    with app.app_context():
        try:
            # Inmovilizamos las filas solo durante una escritura autorizada.
            if not args.apply:
                db.session.execute(text("SET TRANSACTION READ ONLY"))
            select_query = SELECT_TICKET_FOR_UPDATE if args.apply else SELECT_TICKET
            ready, excluded = [], []
            for ticket_id, case in sorted(CASES.items()):
                row = db.session.execute(
                    select_query, {"ticket_id": ticket_id}
                ).mappings().first()
                reason = validation_error(row, case)
                family_id = db.session.execute(
                    SELECT_FAMILY, {"key": case["family"]}
                ).scalar_one_or_none()
                if not reason and family_id is None:
                    reason = "FAMILIA_NO_ACTIVA"
                if reason:
                    excluded.append((ticket_id, case, reason))
                else:
                    ready.append((ticket_id, case, family_id))

            print("FUENTE=reporte_mantenimiento_todo_23-oct-26.xlsx")
            print("ALCANCE=SOLO_TICKETS_FAMILIA_EQUIPO_ID")
            print(f"CANDIDATOS={len(CASES)} LISTOS={len(ready)} EXCLUIDOS={len(excluded)}")
            for ticket_id, case, family_id in ready:
                print(f"LISTO ticket={ticket_id} familia={case['family']} familia_id={family_id} motivo={case['reason']}")
            for ticket_id, case, reason in excluded:
                print(f"EXCLUIDO ticket={ticket_id} familia={case['family']} razon={reason}")

            if not args.apply:
                db.session.rollback()
                print("SIMULACION_SIN_CAMBIOS")
                return 0

            if excluded or len(ready) != args.expect_count:
                raise RuntimeError("Candidatos modificados o no elegibles; no se aplicará ningún cambio")

            applied = []
            for ticket_id, case, family_id in ready:
                updated_id = db.session.execute(UPDATE_FAMILY, {
                    "ticket_id": ticket_id,
                    "description": case["description"],
                    "family_id": family_id,
                    "family_key": case["family"],
                }).scalar_one_or_none()
                if updated_id != ticket_id:
                    raise RuntimeError(f"El ticket {ticket_id} cambió; se revierte toda la operación")
                applied.append((ticket_id, case["family"]))

            db.session.commit()
            print(f"APLICADO_UTC={datetime.now(timezone.utc).isoformat()}")
            for ticket_id, family in applied:
                print(f"ACTUALIZADO ticket={ticket_id} familia={family}")
            print(f"APLICADOS={len(applied)}")
            return 0
        except Exception as exc:
            db.session.rollback()
            print(f"ERROR_ROLLBACK: {exc}", file=sys.stderr)
            return 1
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
