"""Dry-run controlado para importar aparatos de Metepec al inventario.

Este script NO escribe en la base de datos. Valida la fuente normalizada,
catálogos y estado actual del inventario para clasificar cada fila como:

- CREAR: no existe el aparato o falta únicamente la asignación a Metepec.
- OMITIR: el aparato ya existe con los mismos datos y stock positivo en Metepec.
- CONFLICTO: existe con datos distintos o tiene stock positivo en otra sucursal.

Las dos AIR BIKE de la fuente no traen codigo_interno. Se conservan así y se
comparan por sus datos físicos, sin inventar códigos.

Uso desde el contenedor/backend:

    python -m scripts.import_inventario_metepec_dry_run
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
import re
import sys

from sqlalchemy import or_

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models.catalogos import CategoriaInventario
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.mantenimiento_equipo import FamiliaEquipoORM
from app.models.sucursal_model import Sucursal


EXPECTED_SUCURSAL_ID = 25
EXPECTED_SUCURSAL_NAME = "Metepec"
EXPECTED_ROWS = 203
EXPECTED_CODED_ROWS = 201
EXPECTED_UNCODED_AIR_BIKES = 2

DEFAULT_SOURCE = (
    BACKEND_ROOT
    / "data"
    / "imports"
    / "inventario_metepec_2026.csv"
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

AIR_BIKE_MAPPING = {
    "categoria": "Maquinas",
    "subcategoria": "Cardio",
    "familia_key": "RECUMBENTE",
    "familia_equipo_id": 5,
    "categoria_inventario_id": 4,
    "nombre": "AIR BIKE",
    "descripcion": "TH15K08",
}


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Valida la importación de 203 aparatos de Metepec sin escribir "
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


def _validate_mapping(row, expected, errors):
    row_number = row["_row_number"]
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


def _validate_source(rows):
    errors = []

    if len(rows) != EXPECTED_ROWS:
        errors.append(
            f"se esperaban {EXPECTED_ROWS} filas y se encontraron {len(rows)}"
        )

    coded_rows = [row for row in rows if _clean(row["codigo_interno"])]
    uncoded_rows = [row for row in rows if not _clean(row["codigo_interno"])]

    if len(coded_rows) != EXPECTED_CODED_ROWS:
        errors.append(
            f"se esperaban {EXPECTED_CODED_ROWS} filas con código y se encontraron "
            f"{len(coded_rows)}"
        )

    if len(uncoded_rows) != EXPECTED_UNCODED_AIR_BIKES:
        errors.append(
            f"se esperaban {EXPECTED_UNCODED_AIR_BIKES} AIR BIKE sin código y se "
            f"encontraron {len(uncoded_rows)}"
        )

    codes = [_clean(row["codigo_interno"]).upper() for row in coded_rows]
    duplicates = sorted(
        code for code, count in Counter(codes).items() if code and count > 1
    )
    if duplicates:
        errors.append("códigos duplicados en fuente: " + ", ".join(duplicates))

    no_equipos = []
    for row in rows:
        row_number = row["_row_number"]
        row["codigo_interno"] = _clean(row["codigo_interno"]).upper()
        row["nomenclatura"] = _clean(row["nomenclatura"]).upper()

        if row["sucursal_id"] != EXPECTED_SUCURSAL_ID:
            errors.append(
                f"fila {row_number}: sucursal_id={row['sucursal_id']} "
                f"(esperado {EXPECTED_SUCURSAL_ID})"
            )

        if row["tipo"].casefold() != "aparatos":
            errors.append(
                f"fila {row_number}: tipo={row['tipo']!r} (esperado 'aparatos')"
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

        if not row["codigo_interno"]:
            if row["nomenclatura"] or row["no_equipo"]:
                errors.append(
                    f"fila {row_number}: AIR BIKE sin código debe conservar "
                    "nomenclatura y no_equipo vacíos"
                )
            if _clean(row["nombre"]).casefold() != AIR_BIKE_MAPPING["nombre"].casefold():
                errors.append(
                    f"fila {row_number}: nombre={row['nombre']!r}; esperado='AIR BIKE'"
                )
            if _clean(row["descripcion"]).casefold() != AIR_BIKE_MAPPING["descripcion"].casefold():
                errors.append(
                    f"fila {row_number}: descripcion={row['descripcion']!r}; "
                    "esperado='TH15K08'"
                )
            _validate_mapping(row, AIR_BIKE_MAPPING, errors)
            continue

        expected = EXPECTED_MAPPING.get(row["nomenclatura"])
        if not expected:
            errors.append(
                f"fila {row_number}: nomenclatura no soportada "
                f"{row['nomenclatura']!r}"
            )
            continue

        expected_prefix = f"{EXPECTED_SUCURSAL_ID}{row['nomenclatura']}JW"
        if not row["codigo_interno"].startswith(expected_prefix):
            errors.append(
                f"fila {row_number}: código {row['codigo_interno']!r} no inicia "
                f"con {expected_prefix!r}"
            )

        match = re.search(r"(\d+)$", row["codigo_interno"])
        if not match:
            errors.append(
                f"fila {row_number}: código {row['codigo_interno']!r} no termina "
                "en consecutivo"
            )
        else:
            code_number = match.group(1)
            if code_number != row["no_equipo"]:
                errors.append(
                    f"fila {row_number}: no_equipo={row['no_equipo']!r} no coincide "
                    f"con sufijo {code_number!r}"
                )
            try:
                no_equipos.append(int(code_number))
            except ValueError:
                pass

        _validate_mapping(row, expected, errors)

    expected_sequence = list(range(1, EXPECTED_CODED_ROWS + 1))
    if sorted(no_equipos) != expected_sequence:
        errors.append(
            "la secuencia de equipos con código no corresponde exactamente a 1..201"
        )

    return errors


def _validate_catalogs():
    errors = []

    sucursal = Sucursal.query.filter_by(sucursal_id=EXPECTED_SUCURSAL_ID).first()
    if not sucursal:
        errors.append(f"no existe sucursal_id={EXPECTED_SUCURSAL_ID}")
    elif _clean(sucursal.sucursal).casefold() != EXPECTED_SUCURSAL_NAME.casefold():
        errors.append(
            f"sucursal_id={EXPECTED_SUCURSAL_ID} es {sucursal.sucursal!r}, "
            f"no {EXPECTED_SUCURSAL_NAME!r}"
        )

    expected_families = {
        config["familia_key"]: config["familia_equipo_id"]
        for config in EXPECTED_MAPPING.values()
    }
    expected_families[AIR_BIKE_MAPPING["familia_key"]] = AIR_BIKE_MAPPING[
        "familia_equipo_id"
    ]

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
            errors.append(f"familia {key}: id={family.id}; esperado={expected_id}")
        if not bool(family.activo):
            errors.append(f"familia inactiva: {key}")

    expected_category_ids = sorted(
        {
            *(config["categoria_inventario_id"] for config in EXPECTED_MAPPING.values()),
            AIR_BIKE_MAPPING["categoria_inventario_id"],
        }
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
            errors.append(f"categoria_inventario_id faltante: {category_id}")
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
        "unidad_medida": _same_text(inventory.unidad_medida, row["unidad_medida"]),
        "no_equipo": _same_text(inventory.no_equipo, row["no_equipo"]),
        "familia_equipo_id": inventory.familia_equipo_id == row["familia_equipo_id"],
        "categoria_inventario_id": (
            inventory.categoria_inventario_id == row["categoria_inventario_id"]
        ),
    }
    mismatches = [field for field, matches in comparisons.items() if not matches]
    return not mismatches, mismatches


def _classify_inventory_link(row, inventory, links_by_inventory, code_label):
    matches, mismatches = _row_matches_inventory(row, inventory)
    if not matches:
        return {
            "action": "CONFLICTO",
            "code": code_label,
            "detail": (
                f"inventario_id={inventory.id}; campos distintos: "
                + ", ".join(mismatches)
            ),
            "row": row,
        }

    inventory_links = links_by_inventory.get(inventory.id, [])
    target_link = next(
        (link for link in inventory_links if link.sucursal_id == EXPECTED_SUCURSAL_ID),
        None,
    )
    other_positive = [
        link
        for link in inventory_links
        if link.sucursal_id != EXPECTED_SUCURSAL_ID and (link.stock or 0) > 0
    ]

    if other_positive:
        branches = ", ".join(str(link.sucursal_id) for link in other_positive)
        return {
            "action": "CONFLICTO",
            "code": code_label,
            "detail": (
                f"inventario_id={inventory.id} tiene stock positivo en otra(s) "
                f"sucursal(es): {branches}"
            ),
            "row": row,
        }

    if target_link and (target_link.stock or 0) > 0:
        return {
            "action": "OMITIR",
            "code": code_label,
            "detail": (
                f"inventario_id={inventory.id}; ya existe con stock="
                f"{target_link.stock} en Metepec"
            ),
            "row": row,
        }

    return {
        "action": "CREAR",
        "code": code_label,
        "detail": (
            f"inventario_id={inventory.id}; datos coinciden y falta únicamente "
            "movimiento/asignación a Metepec"
        ),
        "row": row,
    }


def _classify_rows(rows):
    coded_rows = [row for row in rows if row["codigo_interno"]]
    uncoded_rows = [row for row in rows if not row["codigo_interno"]]

    codes = [row["codigo_interno"] for row in coded_rows]
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

    air_bike_candidates = (
        InventarioGeneral.query
        .filter(
            or_(
                InventarioGeneral.codigo_interno.is_(None),
                InventarioGeneral.codigo_interno == "",
            ),
            InventarioGeneral.familia_equipo_id == AIR_BIKE_MAPPING["familia_equipo_id"],
        )
        .order_by(InventarioGeneral.id.asc())
        .all()
    )
    air_bike_candidates = [
        item
        for item in air_bike_candidates
        if _same_text(item.tipo, "aparatos")
        and _same_text(item.nombre, AIR_BIKE_MAPPING["nombre"])
        and _same_text(item.descripcion, AIR_BIKE_MAPPING["descripcion"])
        and _same_text(item.marca, "JW SPORTS")
        and _same_text(item.categoria, AIR_BIKE_MAPPING["categoria"])
        and _same_text(item.subcategoria, AIR_BIKE_MAPPING["subcategoria"])
        and item.categoria_inventario_id == AIR_BIKE_MAPPING["categoria_inventario_id"]
    ]

    all_existing = existing + air_bike_candidates
    existing_ids = [item.id for item in all_existing]
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
    for row in coded_rows:
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
                    "detail": "crear inventario + movimiento de entrada a Metepec",
                    "row": row,
                }
            )
            continue

        results.append(
            _classify_inventory_link(row, inventory, links_by_inventory, code)
        )

    for index, row in enumerate(uncoded_rows, start=1):
        code_label = f"SIN_CODIGO_AIR_BIKE_{index}"
        if index <= len(air_bike_candidates):
            inventory = air_bike_candidates[index - 1]
            results.append(
                _classify_inventory_link(
                    row, inventory, links_by_inventory, code_label
                )
            )
        else:
            results.append(
                {
                    "action": "CREAR",
                    "code": code_label,
                    "detail": (
                        "crear inventario sin codigo_interno + movimiento de entrada "
                        "a Metepec"
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
        (item["action"], item["row"]["familia_key"]) for item in results
    )

    print("\nRESUMEN")
    print(f"TOTAL={len(results)}")
    for action in ("CREAR", "OMITIR", "CONFLICTO"):
        print(f"{action}={action_counts.get(action, 0)}")

    print("\nRESUMEN POR FAMILIA")
    for family_key in sorted({item["row"]["familia_key"] for item in results}):
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
