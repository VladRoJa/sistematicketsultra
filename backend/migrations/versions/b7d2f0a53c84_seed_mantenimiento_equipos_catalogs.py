"""seed mantenimiento equipos catalogs

Revision ID: b7d2f0a53c84
Revises: a6c1e9f42b73
Create Date: 2026-08-29
"""

import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "b7d2f0a53c84"
down_revision = "a6c1e9f42b73"
branch_labels = None
depends_on = None


FAMILIES = (
    ("CAMINADORA", "Caminadora"),
    ("ELIPTICA", "Elíptica"),
    ("ESCALADORA", "Escaladora"),
    ("SPINNING", "Spinning"),
    ("RECUMBENTE", "Recumbente"),
    ("PESO_INTEGRADO", "Peso Integrado"),
    ("PESO_LIBRE", "Peso Libre"),
)


FAILURE_NAMES = {
    "CAMINADORA": (
        "Banda desgastada",
        "Desnivelada",
        "Falta de mantenimiento",
        "Motor",
        "Motor de elevación",
        "No enciende",
        "Se apaga",
        "Se patina",
        "Se traba",
        "Soportes dañados",
        "Soportes vencidos",
        "Tablero",
        "Tarjeta",
        "Tarjeta de lubricación",
        "Tira lubricante",
        "Ruido / truena",
    ),
    "ELIPTICA": (
        "Alternador con ruido",
        "Balero dañado",
        "Batería",
        "Error 40",
        "Falla eléctrica en pantalla",
        "No enciende",
        "Pantalla se apaga",
        "Enciende y se apaga",
        "Pedales faltantes",
        "Tablero",
    ),
    "ESCALADORA": (
        "Banda dañada",
        "Escalones dañados",
        "Perno de escalón dañado",
        "Polea fuera de posición",
    ),
    "SPINNING": (
        "Asiento dañado",
        "Brazo de pedal derecho dañado",
        "Brazo de pedal izquierdo dañado",
        "Centro de masa dañado",
        "Centro de masa y pedales dañados",
        "Centro de masa, brazo izquierdo y pedales dañados",
        "Correa de pedal dañada",
        "Empaques del asiento",
        "No funciona",
        "Ajuste no funciona",
        "Pedal dañado",
        "Resistencia dañada",
    ),
    "RECUMBENTE": (
        "Asiento desgastado",
        "Asiento inestable",
        "Brazo de pedal dañado",
        "Centro de masa dañado",
        "Pasador de asiento faltante/dañado",
        "Pedal dañado",
        "Pedales con ruido",
    ),
    "PESO_INTEGRADO": (
        "Agarre de neopreno dañado",
        "Amortiguador dañado",
        "Asiento atorado",
        "Ajuste de asiento no funciona",
        "Asiento inestable",
        "Baleros dañados",
        "Barra de pedal fuera de posición",
        "Barras de polea dañadas",
        "Brazo de seguridad faltante/dañado",
        "Cable dañado",
        "Cable de calibre incorrecto",
        "Pin selector faltante",
        "Tornillos faltantes",
        "Perno de asiento dañado",
        "Pin de ajuste de rodillo dañado",
        "Pintura deteriorada",
        "Polea atorada",
        "Polea dañada",
        "Respaldo faltante/dañado",
        "Ruedas dañadas",
        "Asiento se baja solo",
        "Pieza de asiento desoldada",
        "Pieza desoldada",
        "Soporte de respaldo dañado",
        "Tapicería dañada",
        "Polea con ruido",
    ),
    "PESO_LIBRE": (
        "Amortiguador dañado",
        "Antiderrapante faltante/dañado",
        "Asiento suelto",
        "Cinturón dañado",
        "Empaque plástico faltante",
        "Pintura deteriorada",
        "Plásticos de agarre dañados",
        "Polea dañada",
        "Tapicería dañada",
        "Tornillo dañado",
        "Tuerca barrida",
    ),
}


def _catalog_key(name):
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"[^A-Z0-9]+", "_", ascii_name.upper()).strip("_")


def upgrade():
    family_table = sa.table(
        "familia_equipo",
        sa.column("key", sa.String()),
        sa.column("nombre", sa.String()),
        sa.column("activo", sa.Boolean()),
    )
    op.bulk_insert(
        family_table,
        [
            {"key": family_key, "nombre": name, "activo": True}
            for family_key, name in FAMILIES
        ],
    )

    bind = op.get_bind()
    family_ids = {
        row.key: row.id
        for row in bind.execute(
            sa.text(
                "SELECT id, key FROM familia_equipo "
                "WHERE key IN :family_keys"
            ).bindparams(
                sa.bindparam(
                    "family_keys",
                    value=[family_key for family_key, _ in FAMILIES],
                    expanding=True,
                )
            )
        )
    }

    expected_keys = {family_key for family_key, _ in FAMILIES}
    missing_keys = expected_keys.difference(family_ids)
    if missing_keys:
        raise RuntimeError(
            "No se pudieron resolver familias sembradas: "
            + ", ".join(sorted(missing_keys))
        )

    failure_table = sa.table(
        "falla_mantenimiento",
        sa.column("familia_equipo_id", sa.Integer()),
        sa.column("key", sa.String()),
        sa.column("nombre", sa.String()),
        sa.column("activo", sa.Boolean()),
        sa.column("orden", sa.Integer()),
    )
    failure_rows = []
    for family_key, names in FAILURE_NAMES.items():
        for order, name in enumerate(names, start=1):
            failure_rows.append(
                {
                    "familia_equipo_id": family_ids[family_key],
                    "key": _catalog_key(name),
                    "nombre": name,
                    "activo": True,
                    "orden": order,
                }
            )

    op.bulk_insert(failure_table, failure_rows)


def downgrade():
    bind = op.get_bind()
    family_keys = [family_key for family_key, _ in FAMILIES]
    expanding_keys = sa.bindparam(
        "family_keys",
        value=family_keys,
        expanding=True,
    )
    bind.execute(
        sa.text(
            "DELETE FROM falla_mantenimiento "
            "WHERE familia_equipo_id IN ("
            "SELECT id FROM familia_equipo WHERE key IN :family_keys"
            ")"
        ).bindparams(expanding_keys)
    )
    bind.execute(
        sa.text(
            "DELETE FROM familia_equipo WHERE key IN :family_keys"
        ).bindparams(
            sa.bindparam(
                "family_keys",
                value=family_keys,
                expanding=True,
            )
        )
    )
