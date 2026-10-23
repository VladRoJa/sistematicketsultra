"""Sincroniza familias faltantes de tickets activos desde Inventario.

Por defecto solo simula; --apply requiere --expect-count de la simulación.
No modifica inventarios, códigos, fallas, condiciones, estados ni historial.
"""
import argparse
from collections import Counter
from pathlib import Path
import sys
import unicodedata

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

FAMILIES = {"CAMINADORA", "ELIPTICA", "ESCALADORA", "RECUMBENTE", "SPINNING", "PESO_LIBRE", "PESO_INTEGRADO"}

SELECT = text("""
SELECT t.id AS ticket_id, t.aparato_id, i.codigo_interno, i.nombre AS equipo,
       f.id AS familia_id, f.key AS familia_key, t.falla_mantenimiento_id
FROM tickets t
JOIN inventario_general i ON i.id = t.aparato_id
JOIN familia_equipo f ON f.id = i.familia_equipo_id
WHERE t.departamento_id = 1 AND t.estado IN ('abierto', 'en progreso', 'por_validar')
  AND t.familia_equipo_id IS NULL AND f.activo IS TRUE
ORDER BY t.id
""")

UPDATE = text("""
UPDATE tickets AS t SET familia_equipo_id = :family_id
WHERE t.id = :ticket_id AND t.departamento_id = 1
  AND t.estado IN ('abierto', 'en progreso', 'por_validar')
  AND t.familia_equipo_id IS NULL AND t.falla_mantenimiento_id IS NULL
  AND EXISTS (
    SELECT 1 FROM inventario_general i
    JOIN familia_equipo f ON f.id = i.familia_equipo_id
    WHERE i.id = t.aparato_id AND f.id = :family_id
      AND f.key = :family_key AND f.activo IS TRUE
  ) RETURNING t.id
""")


def normalized(value):
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").upper().strip()


def exclusion(row):
    if row["familia_key"] not in FAMILIES:
        return "FAMILIA_NO_RECONOCIDA"
    if row["falla_mantenimiento_id"] is not None:
        return "FALLA_EXISTENTE_SIN_FAMILIA"
    code, name = normalized(row["codigo_interno"]), normalized(row["equipo"])
    if ("CBV" in code or "BICICLETA VERTICAL" in name) and row["familia_key"] != "RECUMBENTE":
        return "BICICLETA_VERTICAL_FAMILIA_CONTRADICTORIA"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-count", type=int)
    args = parser.parse_args(argv)
    if args.apply and (args.expect_count is None or args.expect_count < 1):
        parser.error("--apply requiere --expect-count positivo obtenido de la simulación")

    app = create_app()
    with app.app_context():
        try:
            rows = db.session.execute(SELECT).mappings().all()
            ready, excluded = [], []
            for row in rows:
                reason = exclusion(row)
                (excluded if reason else ready).append((row, reason) if reason else row)
            print(f"CANDIDATOS={len(rows)} LISTOS={len(ready)} EXCLUIDOS={len(excluded)}")
            for family, count in sorted(Counter(row["familia_key"] for row in ready).items()):
                print(f"{family}={count}")
            for row, reason in excluded:
                print(f"EXCLUIDO ticket={row['ticket_id']} codigo={row['codigo_interno']} familia={row['familia_key']} razon={reason}")
            if not args.apply:
                db.session.rollback()
                print("SIMULACION_SIN_CAMBIOS")
                return 0
            if len(ready) != args.expect_count:
                raise ValueError(f"Conteo cambió: esperado={args.expect_count} actual={len(ready)}. Repita simulación.")
            for row in ready:
                updated = db.session.execute(UPDATE, {
                    "ticket_id": row["ticket_id"], "family_id": row["familia_id"], "family_key": row["familia_key"]
                }).scalar_one_or_none()
                if updated != row["ticket_id"]:
                    raise RuntimeError(f"Ticket {row['ticket_id']} cambió; cancelando toda la operación")
                print(f"ACTUALIZADO ticket={updated} aparato={row['aparato_id']} familia={row['familia_key']}")
            db.session.commit()
            print(f"APLICADOS={len(ready)}")
            return 0
        except Exception as exc:
            db.session.rollback()
            print(f"ERROR_ROLLBACK: {exc}", file=sys.stderr)
            return 1
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
