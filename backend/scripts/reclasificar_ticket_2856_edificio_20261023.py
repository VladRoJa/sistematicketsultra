"""Reclasifica exclusivamente el ticket #2856 de Aparatos a Edificio / AC.

Origen: auditoría SQL 2026-10-23. Solo actualiza clasificacion_id,
categoria e historial_fechas para guardar el antes/después.
No cambia departamento, sucursal, estado, fechas, responsables, aparatos,
familias, diagnóstico, descripción ni datos de refacciones.
Simula por defecto; --apply exige --expect-count 1.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.catalogos import CatalogoClasificacion  # noqa: E402
from app.models.ticket_model import Ticket  # noqa: E402


TICKET_ID = 2856
ORIGINAL_CLASSIFICATION_ID = 487
TARGET_CLASSIFICATION_ID = 34
TARGET_CATEGORY = "AC y ventilacion"

EXPECTED = {
    "descripcion": (
        "Las cajas que cuida los termostatos para AC, están fallando, "
        "algunas ya se cayeron y a otras no es cierra el seguro. "
    ),
    "estado": "abierto",
    "criticidad": 3,
    "departamento_id": 1,
    "clasificacion_id": ORIGINAL_CLASSIFICATION_ID,
    "categoria": "Aparatos",
    "subcategoria": None,
    "detalle": None,
    "categoria_inventario_id": None,
    "aparato_id": None,
    "familia_equipo_id": None,
    "falla_mantenimiento_id": None,
    "condicion_operativa": None,
    "equipo": None,
    "ubicacion": None,
    "problema_detectado": None,
    "necesita_refaccion": False,
    "descripcion_refaccion": "",
    "tipo_atencion": None,
    "asignado_a": None,
    "sucursal_id_destino": 4,
    "fecha_solucion": None,
}


def error_de_ticket(ticket):
    if ticket is None:
        return "TICKET_NO_EXISTE"
    for field, expected in EXPECTED.items():
        if getattr(ticket, field, None) != expected:
            return f"CAMPO_CAMBIO_{field}"
    if ticket.historial_fechas is not None and not isinstance(ticket.historial_fechas, list):
        return "HISTORIAL_NO_ES_LISTA"
    return None


def error_de_clasificaciones(actual, destino):
    if (
        actual is None
        or actual.id != ORIGINAL_CLASSIFICATION_ID
        or actual.nombre != "Aparatos"
        or actual.departamento_id != 1
        or not actual.activo
    ):
        return "CLASIFICACION_ACTUAL_CAMBIO"
    if (
        destino is None
        or destino.id != TARGET_CLASSIFICATION_ID
        or destino.nombre != TARGET_CATEGORY
        or destino.departamento_id != 1
        or not destino.activo
    ):
        return "CLASIFICACION_DESTINO_CAMBIO"
    padre = destino.padre
    raiz = padre.padre if padre else None
    if (
        padre is None
        or padre.id != 2
        or padre.nombre != "Edificio"
        or padre.departamento_id != 1
        or not padre.activo
        or raiz is None
        or raiz.nombre != "Mantenimiento"
        or raiz.departamento_id != 1
        or not raiz.activo
    ):
        return "JERARQUIA_EDIFICIO_CAMBIO"
    return None


def preparar_historial(historial, now):
    """Genera historial nuevo sin alterar ni eliminar entradas anteriores."""
    entries = list(historial or [])
    entries.append({
        "tipo": "maintenance_reclassification_v1",
        "origen": "correccion_auditada_ticket_2856_20261023",
        "fechaCambio": now.isoformat(),
        "cambiadoPor": "script_controlado",
        "motivo": "Reclasificacion de protecciones de termostatos: Aparatos a Edificio / AC y ventilacion.",
        "clasificacion_id_anterior": ORIGINAL_CLASSIFICATION_ID,
        "clasificacion_id_nuevo": TARGET_CLASSIFICATION_ID,
        "categoria_anterior": "Aparatos",
        "categoria_nueva": TARGET_CATEGORY,
    })
    entries.sort(
        key=lambda item: str(item.get("fechaCambio") or item.get("fecha") or "")
        if isinstance(item, dict) else "",
        reverse=True,
    )
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-count", type=int)
    args = parser.parse_args(argv)
    if args.apply and args.expect_count != 1:
        parser.error("--apply requiere --expect-count 1")

    app = create_app()
    with app.app_context():
        try:
            if not args.apply:
                db.session.execute(text("SET TRANSACTION READ ONLY"))

            query = Ticket.query.filter_by(id=TICKET_ID)
            if args.apply:
                query = query.with_for_update()
            ticket = query.first()
            actual = CatalogoClasificacion.query.filter_by(
                id=ORIGINAL_CLASSIFICATION_ID
            ).first()
            destino = CatalogoClasificacion.query.filter_by(
                id=TARGET_CLASSIFICATION_ID
            ).first()

            reason = error_de_ticket(ticket) or error_de_clasificaciones(actual, destino)
            print(f"TICKET={TICKET_ID} ORIGEN=APARATOS_487 DESTINO=EDIFICIO_AC_34")
            print("CAMPOS_A_CAMBIAR=clasificacion_id,categoria,historial_fechas")
            print(f"CANDIDATOS=1 LISTOS={0 if reason else 1} EXCLUIDOS={1 if reason else 0}")

            if reason:
                print(f"EXCLUIDO ticket={TICKET_ID} razon={reason}")
            else:
                print(
                    f"LISTO ticket={TICKET_ID} clasificacion={ORIGINAL_CLASSIFICATION_ID}"
                    f"->{TARGET_CLASSIFICATION_ID} categoria=Aparatos->{TARGET_CATEGORY}"
                )

            if not args.apply:
                db.session.rollback()
                print("SIMULACION_SIN_CAMBIOS")
                return 0

            if reason:
                raise RuntimeError("Datos cambiaron; no se aplicará la reclasificación")

            now = datetime.now(timezone.utc)
            ticket.clasificacion_id = TARGET_CLASSIFICATION_ID
            ticket.categoria = TARGET_CATEGORY
            ticket.historial_fechas = preparar_historial(ticket.historial_fechas, now)
            db.session.commit()
            print(f"ACTUALIZADO ticket={TICKET_ID} fecha_utc={now.isoformat()}")
            print("APLICADOS=1")
            return 0

        except Exception as exc:
            db.session.rollback()
            print(f"ERROR_ROLLBACK: {exc}", file=sys.stderr)
            return 1
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
