"""Importacion controlada de aparatos de Insurgentes.

Reutiliza las validaciones del dry-run ya probado. Por defecto solo simula.
La escritura requiere --apply y se realiza en una sola transaccion.

Uso:

    python -m scripts.import_inventario_insurgentes
    python -m scripts.import_inventario_insurgentes --apply
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models.inventario import (
    DetalleMovimiento,
    InventarioGeneral,
    InventarioSucursal,
    MovimientoInventario,
)
from app.models.user_model import UserORM
from scripts.import_inventario_insurgentes_dry_run import (
    DEFAULT_SOURCE,
    EXPECTED_SUCURSAL_ID,
    _classify_rows,
    _load_source,
    _print_results,
    _validate_catalogs,
    _validate_source,
)


IMPORT_USER_ID = 47
IMPORT_USERNAME = "ADMICORP"
TZ = ZoneInfo("America/Tijuana")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Valida e importa los aparatos de Insurgentes. Sin --apply no "
            "persiste ningun cambio."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"CSV normalizado. Default: {DEFAULT_SOURCE}",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Confirma la importacion y realiza un unico commit.",
    )
    return parser.parse_args(argv)


def _validate_import_user():
    user = UserORM.query.filter_by(id=IMPORT_USER_ID).first()
    if not user:
        return None, f"no existe users.id={IMPORT_USER_ID}"

    username = str(user.username or "").strip().upper()
    if username != IMPORT_USERNAME:
        return (
            None,
            f"users.id={IMPORT_USER_ID} corresponde a {user.username!r}, "
            f"no a {IMPORT_USERNAME!r}",
        )

    return user, None


def _create_inventory_from_row(row):
    inventory = InventarioGeneral(
        tipo=row["tipo"],
        nombre=row["nombre"],
        descripcion=row["descripcion"] or None,
        marca=row["marca"] or None,
        categoria=row["categoria"],
        subcategoria=row["subcategoria"],
        unidad_medida=row["unidad_medida"],
        codigo_interno=row["codigo_interno"],
        no_equipo=row["no_equipo"],
        fecha_inventario=datetime.now(TZ).date(),
        categoria_inventario_id=row["categoria_inventario_id"],
        familia_equipo_id=row["familia_equipo_id"],
    )
    db.session.add(inventory)
    db.session.flush()
    return inventory


def _apply_import(results):
    user, user_error = _validate_import_user()
    if user_error:
        raise ValueError(user_error)

    conflicts = [item for item in results if item["action"] == "CONFLICTO"]
    if conflicts:
        raise ValueError(
            f"la importacion tiene {len(conflicts)} conflicto(s); no se aplico nada"
        )

    to_create = [item for item in results if item["action"] == "CREAR"]
    if not to_create:
        print("APPLY: no hay registros pendientes; no se creo movimiento.")
        return None, 0

    movement = MovimientoInventario(
        tipo_movimiento="entrada",
        usuario_id=user.id,
        sucursal_id=EXPECTED_SUCURSAL_ID,
        observaciones=(
            "Carga inicial controlada de aparatos Insurgentes 2026; "
            "fuente inventario normalizado Suite Ultra"
        ),
    )
    db.session.add(movement)
    db.session.flush()

    applied = 0
    applied_codes = []

    for item in to_create:
        row = item["row"]
        code = row["codigo_interno"]

        inventory = InventarioGeneral.query.filter_by(
            codigo_interno=code
        ).first()
        if inventory is None:
            inventory = _create_inventory_from_row(row)

        link = InventarioSucursal.query.filter_by(
            inventario_id=inventory.id,
            sucursal_id=EXPECTED_SUCURSAL_ID,
        ).first()

        if link is None:
            link = InventarioSucursal(
                inventario_id=inventory.id,
                sucursal_id=EXPECTED_SUCURSAL_ID,
                stock=1,
            )
            db.session.add(link)
        else:
            link.stock = 1

        db.session.add(
            DetalleMovimiento(
                movimiento_id=movement.id,
                inventario_id=inventory.id,
                cantidad=1,
                unidad_medida=row["unidad_medida"],
            )
        )
        applied += 1
        applied_codes.append(code)

    db.session.flush()

    detail_count = DetalleMovimiento.query.filter_by(
        movimiento_id=movement.id
    ).count()
    if detail_count != applied:
        raise RuntimeError(
            f"movimiento_id={movement.id} tiene {detail_count} detalles; "
            f"se esperaban {applied}"
        )

    stock_count = (
        db.session.query(InventarioSucursal)
        .join(
            InventarioGeneral,
            InventarioGeneral.id == InventarioSucursal.inventario_id,
        )
        .filter(
            InventarioSucursal.sucursal_id == EXPECTED_SUCURSAL_ID,
            InventarioSucursal.stock == 1,
            InventarioGeneral.codigo_interno.in_(applied_codes),
        )
        .count()
    )
    if stock_count != applied:
        raise RuntimeError(
            f"solo {stock_count} de {applied} equipos quedaron con stock=1 "
            "antes del commit"
        )

    db.session.commit()
    return movement.id, applied


def main(argv=None):
    args = _parse_args(argv)

    try:
        rows = _load_source(args.source)
        source_errors = _validate_source(rows)
        if source_errors:
            for error in source_errors:
                print(f"ERROR FUENTE: {error}", file=sys.stderr)
            return 2

        app = create_app()
        with app.app_context():
            catalog_errors = _validate_catalogs()
            if catalog_errors:
                for error in catalog_errors:
                    print(f"ERROR CATALOGO: {error}", file=sys.stderr)
                return 2

            results = _classify_rows(rows)
            _print_results(results)

            conflicts = sum(
                1 for result in results if result["action"] == "CONFLICTO"
            )
            if conflicts:
                db.session.rollback()
                print(
                    f"\nNO APLICADO: existen {conflicts} conflicto(s).",
                    file=sys.stderr,
                )
                return 3

            if not args.apply:
                db.session.rollback()
                print("\nSIMULADO: sin --apply no se escribio nada en la base.")
                return 0

            movement_id, applied = _apply_import(results)
            print("\nAPLICADO")
            print(f"MOVIMIENTO_ID={movement_id}")
            print(f"USUARIO_ID={IMPORT_USER_ID}")
            print(f"SUCURSAL_ID={EXPECTED_SUCURSAL_ID}")
            print(f"EQUIPOS_APLICADOS={applied}")
            return 0

    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"ERROR INESPERADO: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            db.session.remove()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
