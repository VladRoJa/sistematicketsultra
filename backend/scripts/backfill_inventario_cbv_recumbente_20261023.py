"""Corrige la familia de cinco bicicletas verticales existentes en Inventario.

Fuente: QA 2026-10-23, cinco inventarios sin familia y seis tickets sin familia.
Bicicleta vertical se agrupa en la familia existente RECUMBENTE.
Simulación por defecto; --apply --expect-count 5 requiere confirmación posterior.
SOLO modifica inventario_general.familia_equipo_id; no altera nombres, códigos,
existencias, movimientos, fecha_inventario, historial o tickets.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

INVENTARIOS = {
    431: ("01CBVST04", (2807,)),
    1144: ("IXTCBVLF06", (2801, 2802)),
    1967: ("09CBVST02", (2992,)),
    2452: ("06CBVLF01", (2656,)),
    3330: ("12CBVST02", (2744,)),
}
FAMILY_KEY = "RECUMBENTE"

SELECT_INVENTARIOS = text("""
    SELECT id, codigo_interno, nombre, tipo, familia_equipo_id
    FROM inventario_general
    WHERE id IN (431, 1144, 1967, 2452, 3330)
    ORDER BY id
""")
SELECT_INVENTARIOS_FOR_UPDATE = text("""
    SELECT id, codigo_interno, nombre, tipo, familia_equipo_id
    FROM inventario_general
    WHERE id IN (431, 1144, 1967, 2452, 3330)
    ORDER BY id
    FOR UPDATE
""")
SELECT_TICKETS = text("""
    SELECT id, aparato_id, departamento_id, estado, familia_equipo_id
    FROM tickets
    WHERE id IN (2656, 2744, 2801, 2802, 2807, 2992)
    ORDER BY id
""")
SELECT_TICKETS_FOR_UPDATE = text("""
    SELECT id, aparato_id, departamento_id, estado, familia_equipo_id
    FROM tickets
    WHERE id IN (2656, 2744, 2801, 2802, 2807, 2992)
    ORDER BY id
    FOR UPDATE
""")
SELECT_FAMILY = text("""
    SELECT id FROM familia_equipo
    WHERE key = :family_key AND activo IS TRUE
""")
UPDATE = text("""
    UPDATE inventario_general i
    SET familia_equipo_id = :family_id
    WHERE i.id = :inventario_id
      AND i.codigo_interno = :codigo
      AND i.nombre = :nombre
      AND i.tipo = :tipo
      AND i.familia_equipo_id IS NULL
      AND EXISTS (
          SELECT 1 FROM familia_equipo f
          WHERE f.id = :family_id
            AND f.key = :family_key
            AND f.activo IS TRUE
      )
    RETURNING i.id
""")


def normalizar_nombre(value):
    return " ".join(str(value or "").split()).upper()


def validar_inventario(row, inventario_id, codigo_esperado):
    if row is None:
        return "INVENTARIO_NO_EXISTE"
    if row["codigo_interno"] != codigo_esperado:
        return "CODIGO_DIFERENTE"
    if normalizar_nombre(row["nombre"]) != "BICICLETA VERTICAL":
        return "NOMBRE_NO_ES_BICICLETA_VERTICAL"
    if str(row["tipo"] or "").strip().lower() not in {"aparato", "aparatos"}:
        return "TIPO_NO_APARATO"
    if row["familia_equipo_id"] is not None:
        return "FAMILIA_YA_ASIGNADA"
    if row["id"] != inventario_id:
        return "ID_DIFERENTE"
    return None


def validar_ticket(row, inventario_id):
    if row is None:
        return "TICKET_NO_EXISTE"
    if row["aparato_id"] != inventario_id:
        return "VINCULO_APARATO_CAMBIO"
    if row["departamento_id"] != 1:
        return "DEPARTAMENTO_CAMBIO"
    if row["estado"] not in {"abierto", "en progreso", "por_validar"}:
        return "ESTADO_CAMBIO"
    if row["familia_equipo_id"] is not None:
        return "FAMILIA_TICKET_YA_ASIGNADA"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-count", type=int)
    args = parser.parse_args(argv)
    if args.apply and args.expect_count != len(INVENTARIOS):
        parser.error(f"--apply requiere --expect-count {len(INVENTARIOS)}")

    app = create_app()
    with app.app_context():
        try:
            if not args.apply:
                db.session.execute(text("SET TRANSACTION READ ONLY"))

            familia_id = db.session.execute(
                SELECT_FAMILY, {"family_key": FAMILY_KEY}
            ).scalar_one_or_none()
            inventory_query = SELECT_INVENTARIOS_FOR_UPDATE if args.apply else SELECT_INVENTARIOS
            ticket_query = SELECT_TICKETS_FOR_UPDATE if args.apply else SELECT_TICKETS
            inventarios = {
                row["id"]: row
                for row in db.session.execute(inventory_query).mappings()
            }
            tickets = {
                row["id"]: row
                for row in db.session.execute(ticket_query).mappings()
            }

            ready, excluded = [], []
            if familia_id is None:
                raise RuntimeError("No existe familia RECUMBENTE activa; cancelando")

            for inventario_id, (codigo, ticket_ids) in sorted(INVENTARIOS.items()):
                row = inventarios.get(inventario_id)
                reason = validar_inventario(row, inventario_id, codigo)
                if reason is None:
                    for ticket_id in ticket_ids:
                        reason_ticket = validar_ticket(tickets.get(ticket_id), inventario_id)
                        if reason_ticket:
                            reason = f"TICKET_{ticket_id}_{reason_ticket}"
                            break
                if reason:
                    excluded.append((inventario_id, codigo, reason))
                else:
                    ready.append((inventario_id, codigo, ticket_ids, row))

            print(f"FUENTE=QA_INVENTARIO_CBV_2026-10-23 FAMILIA={FAMILY_KEY} ID={familia_id}")
            print("ALCANCE=SOLO_INVENTARIO_GENERAL_FAMILIA_EQUIPO_ID")
            print(f"CANDIDATOS={len(INVENTARIOS)} LISTOS={len(ready)} EXCLUIDOS={len(excluded)}")
            for inventario_id, codigo, ticket_ids, _ in ready:
                print(f"LISTO inventario={inventario_id} codigo={codigo} tickets={','.join(map(str, ticket_ids))}")
            for inventario_id, codigo, reason in excluded:
                print(f"EXCLUIDO inventario={inventario_id} codigo={codigo} razon={reason}")

            if not args.apply:
                db.session.rollback()
                print("SIMULACION_SIN_CAMBIOS")
                return 0

            if excluded or len(ready) != args.expect_count:
                raise RuntimeError("Cambios detectados en inventarios o tickets; rollback completo")

            updated = []
            for inventario_id, codigo, _, row in ready:
                updated_id = db.session.execute(UPDATE, {
                    "inventario_id": inventario_id,
                    "codigo": codigo,
                    "nombre": row["nombre"],
                    "tipo": row["tipo"],
                    "family_id": familia_id,
                    "family_key": FAMILY_KEY,
                }).scalar_one_or_none()
                if updated_id != inventario_id:
                    raise RuntimeError(f"Inventario {inventario_id} cambió; rollback completo")
                updated.append((inventario_id, codigo))

            db.session.commit()
            print(f"APLICADO_UTC={datetime.now(timezone.utc).isoformat()}")
            for inventario_id, codigo in updated:
                print(f"ACTUALIZADO inventario={inventario_id} codigo={codigo} familia={FAMILY_KEY}")
            print(f"APLICADOS={len(updated)}")
            print("NOTA=LOS_6_TICKETS_SIGUEN_SIN_FAMILIA;_REQUIEREN_BACKFILL_SEPARADO")
            return 0
        except Exception as exc:
            db.session.rollback()
            print(f"ERROR_ROLLBACK: {exc}", file=sys.stderr)
            return 1
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
