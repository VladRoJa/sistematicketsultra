"""Dry-run controlado para importar aparatos de Insurgentes al inventario.

Este script NO escribe en la base de datos. Valida la fuente normalizada,
catálogos y estado actual del inventario para clasificar cada fila como:

- CREAR: no existe el código o falta únicamente la asignación a Insurgentes.
- OMITIR: el código ya existe con los mismos datos y stock positivo en Insurgentes.
- CONFLICTO: el código existe con datos distintos o está asignado con stock a otra sucursal.

Uso desde el contenedor/backend:

    python -m scripts.import_inventario_insurgentes_dry_run

También puede indicarse otra fuente CSV compatible:

    python -m scripts.import_inventario_insurgentes_dry_run --source /ruta/fuente.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
import re
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models.catalogos import CategoriaInventario
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.mantenimiento_equipo import FamiliaEquipoORM
from app.models.sucursal_model import Sucursal


EXPECTED_SUCURSAL_ID = 22
EXPECTED_SUCURSAL_NAME = "Insurgentes"
EXPECTED_ROWS = 174

DEFAULT_SOURCE = (
    BACKEND_ROOT
    / "data"
    / "imports"
    / "inventario_insurgentes_2026.csv"
)

REQUIRED_COLUMNS = (
    "sucursal_id",
    "nomenclatura",
    "codigo_interno",
    "no_equipo",
    "tipo",
    "nombre",
    "descripcion",
    "marca",
    "categoria",
    "subcategoria",
    "familia_key",
    "familia_equipo_id",
    "categoria_inventario_id",
    "unidad_medida",
)

EXPECTED_MAPPING = {
    "CC": {
        "categoria": "Maquinas",
        "subcategoria": "Cardio",
        "familia_key": "CAMINADORA",
        "familia_equipo_id": 1,
        "categoria_inventario_id": 4,
    },
    "CE": {
        "categoria": "Maquinas",
        "subcategoria": "Cardio",
        "familia_key": "ELIPTICA",
        "familia_equipo_id": 2,
        "categoria_inventario_id": 4,
    },
    "CES": {
        "categoria": "Maquinas",
        "subcategoria": "Cardio",
        "familia_key": "ESCALADORA",
        "familia_equipo_id": 3,
        "categoria_inventario_id": 4,
    },
    "CS": {
        "categoria": "Maquinas",
        "subcategoria": "Spinning",
        "familia_key": "SPINNING",
        "familia_equipo_id": 4,
        "categoria_inventario_id": 4,
    },
    "PI": {
        "categoria": "Maquinas",
        "subcategoria": "Selectorizado",
        "familia_key": "PESO_INTEGRADO",
        "familia_equipo_id": 6,
        "categoria_inventario_id": 7,
    },
    "PL": {
        "categoria": "Maquinas",
        "subcategoria": "Peso Libre",
        "familia_key": "PESO_LIBRE",
        "familia_equipo_id": 7,
        "categoria_inventario_id": 3,
    },
}


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Valida la importación de 174 aparatos de Insurgentes sin escribir "
            "en la base de datos."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"CSV normalizado. Default: {DEFAULT_SOURCE}",
    )
    return parser.parse_args(argv)


def _clean(value):
    return str(value or "").strip()


def _int_field(row, field, row_number):
    raw = _clean(row.get(field))
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"fila {row_number}: {field} debe ser entero; valor={raw!r}"
        )


def _load_source(path: Path):
    if not path.is_file():
        raise ValueError(f"fuente no encontrada: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = tuple(reader.fieldnames or ())
        missing = [field for field in REQUIRED_COLUMNS if field not in headers]
        if missing:
            raise ValueError(
                "faltan columnas requeridas en la fuente: " + ", ".join(missing)
            )

        rows = []
        for row_number, raw in enumerate(reader, start=2):
            if not any(_clean(value) for value in raw.values()):
                continue

            row = {key: _clean(raw.get(key)) for key in REQUIRED_COLUMNS}
            row["sucursal_id"] = _int_field(row, "sucursal_id", row_number)
            row["familia_equipo_id"] = _int_field(
                row, "familia_equipo_id", row_number
            )
            row["categoria_inventario_id"] = _int_field(
                row, "categoria_inventario_id", row_number
            )
            row["_row_number"] = row_number
            rows.append(row)

    return rows


def _validate_source(rows):
    errors = []

    if len(rows) != EXPECTED_ROWS:
        errors.append(
            f"se esperaban {EXPECTED_ROWS} filas y se encontraron {len(rows)}"
        )

    codes = [_clean(row["codigo_interno"]).upper() for row in rows]
    duplicates = sorted(
        code for code, count in Counter(codes).items() if code and count > 1
    )
    if duplicates:
        errors.append(
            "códigos duplicados en fuente: " + ", ".join(duplicates)
        )

    no_equipos = []
    for row in rows:
        row_number = row["_row_number"]
        nomenclatura = row["nomenclatura"].upper()
        code = row["codigo_interno"].upper()
        row["codigo_interno"] = code
        row["nomenclatura"] = nomenclatura

        expected = EXPECTED_MAPPING.get(nomenclatura)
        if not expected:
            errors.append(
                f"fila {row_number}: nomenclatura no soportada {nomenclatura!r}"
            )
            continue

        if row["sucursal_id"] != EXPECTED_SUCURSAL_ID:
            errors.append(
                f"fila {row_number}: sucursal_id={row['sucursal_id']} "
                f"(esperado {EXPECTED_SUCURSAL_ID})"
            )

        if row["tipo"].casefold() != "aparatos":
            errors.append(
                f"fila {row_number}: tipo={row['tipo']!r} (esperado 'aparatos')"
            )

        expected_prefix = f"{EXPECTED_SUCURSAL_ID}{nomenclatura}JW"
        if not code.startswith(expected_prefix):
            errors.append(
                f"fila {row_number}: código {code!r} no inicia con "
                f"{expected_prefix!r}"
            )

        match = re.search(r"(\d+)$", code)
        if not match:
            errors.append(
                f"fila {row_number}: código {code!r} no termina en consecutivo"
            )
        else:
            code_number = match.group(1)
            if code_number != row["no_equipo"]:
                errors.append(
                    f"fila {row_number}: no_equipo={row['no_equipo']!r} "
                    f"no coincide con sufijo {code_number!r}"
                )
            try:
                no_equipos.append(int(code_number))
            except ValueError:
                pass

        for field in (
            "categoria",
            "subcategoria",
            "familia_key",
            "familia_equipo_id",
            "categoria_inventario_id",
        ):
            expected_value = expected[field]
            actual = row[field]
            if field in {"familia_equipo_id", "categoria_inventario_id"}:
                matches = actual == expected_value
            else:
                matches = _clean(actual).casefold() == str(expected_value).casefold()

            if not matches:
                errors.append(
                    f"fila {row_number}: {field}={actual!r}; "
                    f"esperado={expected_value!r}"
                )

        if not row["nombre"]:
            errors.append(f"fila {row_number}: nombre vacío")
        if not row["marca"]:
            errors.append(f"fila {row_number}: marca vacía")
        if row["unidad_medida"].casefold() != "pieza":
            errors.append(
                f"fila {row_number}: unidad_medida={row['unidad_medida']!r} "
                "(esperado 'pieza')"
            )

    expected_sequence = list(range(1, EXPECTED_ROWS + 1))
    if sorted(no_equipos) != expected_sequence:
        errors.append(
            "la secuencia de equipos no corresponde exactamente a 1..174"
        )

    return errors


def _validate_catalogs():
    errors = []

    sucursal = Sucursal.query.filter_by(
        sucursal_id=EXPECTED_SUCURSAL_ID
    ).first()
    if not sucursal:
        errors.append(
            f"no existe sucursal_id={EXPECTED_SUCURSAL_ID}"
        )
    elif _clean(sucursal.sucursal).casefold() != EXPECTED_SUCURSAL_NAME.casefold():
        errors.append(
            f"sucursal_id={EXPECTED_SUCURSAL_ID} es {sucursal.sucursal!r}, "
            f"no {EXPECTED_SUCURSAL_NAME!r}"
        )

    expected_families = {
        config["familia_key"]: config["familia_equipo_id"]
        for config in EXPECTED_MAPPING.values()
    }
    families = (
        FamiliaEquipoORM.query
        .filter(FamiliaEquipoORM.key.in_(tuple(expected_families)))
        .all()
    )
    family_by_key = {_clean(item.key).upper(): item for item in families}

    for key, expected_id in sorted(expected_families.items()):
        family = family_by_key.get(key)
        if not family:
            errors.append(f"familia faltante: {key}")
            continue
        if family.id != expected_id:
            errors.append(
                f"familia {key}: id={family.id}; esperado={expected_id}"
            )
        if not bool(family.activo):
            errors.append(f"familia inactiva: {key}")

    expected_category_ids = sorted(
        {config["categoria_inventario_id"] for config in EXPECTED_MAPPING.values()}
    )
    categories = (
        CategoriaInventario.query
        .filter(CategoriaInventario.id.in_(expected_category_ids))
        .all()
    )
    category_by_id = {item.id: item for item in categories}
    for category_id in expected_category_ids:
        category = category_by_id.get(category_id)
        if not category:
            errors.append(
                f"categoria_inventario_id faltante: {category_id}"
            )
        elif not bool(category.activo):
            errors.append(
                f"categoria_inventario_id inactiva: {category_id} "
                f"({category.nombre})"
            )

    return errors


def _same_text(left, right):
    return _clean(left).casefold() == _clean(right).casefold()


def _row_matches_inventory(row, inventory):
    comparisons = {
        "tipo": _same_text(inventory.tipo, row["tipo"]),
        "nombre": _same_text(inventory.nombre, row["nombre"]),
        "descripcion": _same_text(inventory.descripcion, row["descripcion"]),
        "marca": _same_text(inventory.marca, row["marca"]),
        "categoria": _same_text(inventory.categoria, row["categoria"]),
        "subcategoria": _same_text(inventory.subcategoria, row["subcategoria"]),
        "unidad_medida": _same_text(
            inventory.unidad_medida, row["unidad_medida"]
        ),
        "no_equipo": _same_text(inventory.no_equipo, row["no_equipo"]),
        "familia_equipo_id": (
            inventory.familia_equipo_id == row["familia_equipo_id"]
        ),
        "categoria_inventario_id": (
            inventory.categoria_inventario_id == row["categoria_inventario_id"]
        ),
    }
    mismatches = [
        field for field, matches in comparisons.items() if not matches
    ]
    return not mismatches, mismatches


def _classify_rows(rows):
    codes = [row["codigo_interno"] for row in rows]
    existing = (
        InventarioGeneral.query
        .filter(InventarioGeneral.codigo_interno.in_(codes))
        .all()
    )

    inventory_by_code = {}
    duplicate_db_codes = set()
    for item in existing:
        code = _clean(item.codigo_interno).upper()
        if code in inventory_by_code:
            duplicate_db_codes.add(code)
        else:
            inventory_by_code[code] = item

    existing_ids = [item.id for item in existing]
    links = []
    if existing_ids:
        links = (
            InventarioSucursal.query
            .filter(InventarioSucursal.inventario_id.in_(existing_ids))
            .all()
        )

    links_by_inventory = {}
    for link in links:
        links_by_inventory.setdefault(link.inventario_id, []).append(link)

    results = []
    for row in rows:
        code = row["codigo_interno"]

        if code in duplicate_db_codes:
            results.append(
                {
                    "action": "CONFLICTO",
                    "code": code,
                    "detail": "codigo_interno duplicado en inventario_general",
                    "row": row,
                }
            )
            continue

        inventory = inventory_by_code.get(code)
        if not inventory:
            results.append(
                {
                    "action": "CREAR",
                    "code": code,
                    "detail": "crear inventario + movimiento de entrada a Insurgentes",
                    "row": row,
                }
            )
            continue

        matches, mismatches = _row_matches_inventory(row, inventory)
        if not matches:
            results.append(
                {
                    "action": "CONFLICTO",
                    "code": code,
                    "detail": (
                        f"inventario_id={inventory.id}; campos distintos: "
                        + ", ".join(mismatches)
                    ),
                    "row": row,
                }
            )
            continue

        inventory_links = links_by_inventory.get(inventory.id, [])
        target_link = next(
            (
                link
                for link in inventory_links
                if link.sucursal_id == EXPECTED_SUCURSAL_ID
            ),
            None,
        )
        other_positive = [
            link
            for link in inventory_links
            if link.sucursal_id != EXPECTED_SUCURSAL_ID
            and (link.stock or 0) > 0
        ]

        if other_positive:
            branches = ", ".join(
                str(link.sucursal_id) for link in other_positive
            )
            results.append(
                {
                    "action": "CONFLICTO",
                    "code": code,
                    "detail": (
                        f"inventario_id={inventory.id} tiene stock positivo "
                        f"en otra(s) sucursal(es): {branches}"
                    ),
                    "row": row,
                }
            )
        elif target_link and (target_link.stock or 0) > 0:
            results.append(
                {
                    "action": "OMITIR",
                    "code": code,
                    "detail": (
                        f"inventario_id={inventory.id}; ya existe con stock="
                        f"{target_link.stock} en Insurgentes"
                    ),
                    "row": row,
                }
            )
        else:
            results.append(
                {
                    "action": "CREAR",
                    "code": code,
                    "detail": (
                        f"inventario_id={inventory.id}; datos coinciden y falta "
                        "únicamente movimiento/asignación a Insurgentes"
                    ),
                    "row": row,
                }
            )

    return results


def _print_results(results):
    for result in results:
        row = result["row"]
        print(
            f"{result['action']}: {result['code']} | "
            f"{row['nombre']} | {row['familia_key']} | "
            f"{row['subcategoria']} | {result['detail']}"
        )

    action_counts = Counter(item["action"] for item in results)
    family_counts = Counter(
        (item["action"], item["row"]["familia_key"])
        for item in results
    )

    print("\nRESUMEN")
    print(f"TOTAL={len(results)}")
    for action in ("CREAR", "OMITIR", "CONFLICTO"):
        print(f"{action}={action_counts.get(action, 0)}")

    print("\nRESUMEN POR FAMILIA")
    for family_key in sorted(
        {item["row"]["familia_key"] for item in results}
    ):
        values = [
            f"{action}={family_counts.get((action, family_key), 0)}"
            for action in ("CREAR", "OMITIR", "CONFLICTO")
        ]
        print(f"{family_key}: " + " ".join(values))


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

            # Seguridad explícita: este script jamás persiste cambios.
            db.session.rollback()

            return 3 if conflicts else 0

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
