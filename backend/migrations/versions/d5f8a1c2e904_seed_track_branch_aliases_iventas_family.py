"""seed track_branch_aliases iventas_family

Revision ID: d5f8a1c2e904
Revises: a7d4e2c91f63
Create Date: 2026-08-08

"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d5f8a1c2e904"
down_revision = "a7d4e2c91f63"
branch_labels = None
depends_on = None


SOURCE_FAMILY = "iventas_family"

SOURCE_FAMILY_CHECK_NAME = (
    "ck_track_branch_aliases_source_family"
)

BASE_SOURCE_FAMILIES = (
    "manual_targets",
    "gasca_family",
    "domiciliados_total",
    "domiciliados_recep",
    "venta_tienda",
    "totalpass_family",
    "wellhub_family",
)

UPGRADED_SOURCE_FAMILIES = (
    *BASE_SOURCE_FAMILIES,
    SOURCE_FAMILY,
)

EXPECTED_ALIASES = (
    ("villas-del-rey", "VILLAS_DEL_REY", 1),
    ("villa-verde", "VILLA_VERDE", 2),
    ("independencia", "INDEPENDENCIA", 3),
    ("tecnologico", "TEC_MXL", 4),
    ("sendero-mexicali", "SEND_MXL", 5),
    ("san-luis-rio-colorado", "SAN_LUIS", 6),
    ("pabellon-rosarito", "PABELLON_RTO", 7),
    ("mision", "MISION_ENS", 8),
    ("paseo-2000", "PASEO_2000", 9),
    ("loma-bonita", "LOMA_BONITA", 10),
    ("santa-fe", "SANTA_FE", 11),
    ("carrousel", "CARROUSEL_TJ", 12),
    ("papalote", "PAPALOTE_TJ", 13),
    ("sendero-culiacan", "SEND_CUL", 14),
    ("san-isidro", "SAN_ISIDRO_CUL", 15),
    ("azahares", "AZAHARES_CUL", 16),
    ("santa-catarina", "STA_CATARINA", 17),
    ("saltillo-sur", "SEND_SALTILLO", 18),
    ("sendero-chihuahua", "SEND_CHIH", 19),
    ("paseo-la-paz", "PASEO_LA_PAZ", 20),
    ("ixtapaluca", "IXTAPALUCA", 21),
    ("insurgentes", "INSURGENTES", 22),
    ("tlalnepantla", "TLALNEPANTLA", 23),
    ("villalta", "SALTILLO_VILLALTA", 24),
    ("metepec", "METEPEC", 25),
    ("serrania", "SERRANIA", 26),
)


def _expected_by_raw():
    return {
        raw_branch_name: (
            sucursal_canon,
            sucursal_id,
        )
        for (
            raw_branch_name,
            sucursal_canon,
            sucursal_id,
        ) in EXPECTED_ALIASES
    }


def _read_source_family_check(connection):
    row = connection.execute(
        sa.text(
            """
            SELECT
                pg_get_constraintdef(
                    c.oid,
                    true
                ) AS definition
            FROM pg_constraint AS c
            WHERE c.conrelid =
                  'track_branch_aliases'::regclass
              AND c.contype = 'c'
              AND c.conname = :constraint_name
            """
        ),
        {
            "constraint_name":
                SOURCE_FAMILY_CHECK_NAME,
        },
    ).mappings().one_or_none()

    if row is None:
        raise RuntimeError(
            "No existe el CHECK esperado: "
            f"{SOURCE_FAMILY_CHECK_NAME}."
        )

    return row["definition"]


def _allowed_families_from_check(
    connection,
):
    definition = _read_source_family_check(
        connection
    )

    values = re.findall(
        r"'([^']+)'",
        definition,
    )

    return set(values)


def _assert_source_family_check(
    connection,
    expected_families,
):
    actual = _allowed_families_from_check(
        connection
    )

    expected = set(expected_families)

    if actual != expected:
        raise RuntimeError(
            "Dominio inesperado en "
            f"{SOURCE_FAMILY_CHECK_NAME}. "
            f"Actual={sorted(actual)}; "
            f"esperado={sorted(expected)}."
        )


def _replace_source_family_check(
    connection,
    *,
    expected_before,
    desired_after,
):
    _assert_source_family_check(
        connection,
        expected_before,
    )

    op.drop_constraint(
        SOURCE_FAMILY_CHECK_NAME,
        "track_branch_aliases",
        type_="check",
    )

    values_sql = ", ".join(
        f"'{value}'"
        for value in desired_after
    )

    op.create_check_constraint(
        SOURCE_FAMILY_CHECK_NAME,
        "track_branch_aliases",
        f"source_family IN ({values_sql})",
    )

    _assert_source_family_check(
        connection,
        desired_after,
    )


def _validate_static_matrix():
    raw_names = [
        row[0]
        for row in EXPECTED_ALIASES
    ]

    canons = [
        row[1]
        for row in EXPECTED_ALIASES
    ]

    sucursal_ids = [
        row[2]
        for row in EXPECTED_ALIASES
    ]

    if len(EXPECTED_ALIASES) != 26:
        raise RuntimeError(
            "iventas_family debe contener "
            "exactamente 26 aliases."
        )

    if len(set(raw_names)) != 26:
        raise RuntimeError(
            "Hay códigos iVentas duplicados "
            "en la migración."
        )

    if len(set(canons)) != 26:
        raise RuntimeError(
            "Hay destinos Track duplicados "
            "en la migración."
        )

    if len(set(sucursal_ids)) != 26:
        raise RuntimeError(
            "Hay sucursal_id duplicados "
            "en la migración."
        )

    if "saltillo" in raw_names:
        raise RuntimeError(
            "El código iVentas 'saltillo' "
            "no es válido."
        )

    expected_special = {
        "saltillo-sur": (
            "SEND_SALTILLO",
            18,
        ),
        "villalta": (
            "SALTILLO_VILLALTA",
            24,
        ),
    }

    mapping = _expected_by_raw()

    for raw_name, expected in (
        expected_special.items()
    ):
        actual = mapping.get(raw_name)

        if actual != expected:
            raise RuntimeError(
                "Mapping Saltillo inválido: "
                f"{raw_name} -> {actual}; "
                f"esperado {expected}."
            )


def _validate_track_catalog(connection):
    rows = connection.execute(
        sa.text(
            """
            SELECT
                sucursal_canon,
                sucursal_id,
                is_track_active
            FROM track_branch_catalog
            """
        )
    ).mappings().all()

    by_canon = {
        row["sucursal_canon"]: row
        for row in rows
    }

    for (
        raw_branch_name,
        sucursal_canon,
        expected_sucursal_id,
    ) in EXPECTED_ALIASES:
        row = by_canon.get(
            sucursal_canon
        )

        if row is None:
            raise RuntimeError(
                "Falta sucursal Track requerida "
                "para iVentas: "
                f"{raw_branch_name} -> "
                f"{sucursal_canon}."
            )

        actual_sucursal_id = row[
            "sucursal_id"
        ]

        if (
            actual_sucursal_id
            != expected_sucursal_id
        ):
            raise RuntimeError(
                "sucursal_id inesperado para "
                f"{sucursal_canon}: "
                f"{actual_sucursal_id}; "
                "esperado "
                f"{expected_sucursal_id}."
            )

        if not bool(
            row["is_track_active"]
        ):
            raise RuntimeError(
                "Sucursal Track inactiva "
                "requerida por iVentas: "
                f"{sucursal_canon}."
            )

    if "LA_VIGA" in by_canon:
        raise RuntimeError(
            "LA_VIGA no debe existir en "
            "track_branch_catalog."
        )


def _read_iventas_family(connection):
    return connection.execute(
        sa.text(
            """
            SELECT
                raw_branch_name,
                sucursal_canon,
                is_active
            FROM track_branch_aliases
            WHERE source_family = :source_family
            ORDER BY raw_branch_name
            """
        ),
        {
            "source_family": SOURCE_FAMILY,
        },
    ).mappings().all()


def _assert_exact_family(connection):
    rows = _read_iventas_family(
        connection
    )

    if len(rows) != 26:
        raise RuntimeError(
            "iventas_family no contiene "
            "exactamente 26 filas. "
            f"Actual={len(rows)}."
        )

    expected = _expected_by_raw()

    observed_canons = []

    for row in rows:
        raw_name = row[
            "raw_branch_name"
        ]

        if raw_name not in expected:
            raise RuntimeError(
                "Alias iVentas inesperado: "
                f"{raw_name}."
            )

        (
            expected_canon,
            _expected_sucursal_id,
        ) = expected[raw_name]

        if (
            row["sucursal_canon"]
            != expected_canon
        ):
            raise RuntimeError(
                "Mapping iVentas incorrecto: "
                f"{raw_name} -> "
                f"{row['sucursal_canon']}; "
                f"esperado {expected_canon}."
            )

        if not bool(row["is_active"]):
            raise RuntimeError(
                "Alias iVentas inactivo: "
                f"{raw_name}."
            )

        observed_canons.append(
            row["sucursal_canon"]
        )

    if len(set(observed_canons)) != 26:
        raise RuntimeError(
            "iventas_family no resuelve "
            "a 26 destinos Track únicos."
        )


def upgrade():
    connection = op.get_bind()

    _validate_static_matrix()
    _validate_track_catalog(
        connection
    )

    existing = _read_iventas_family(
        connection
    )

    if existing:
        # Solo aceptamos un estado previamente
        # completo y exactamente equivalente.
        _assert_source_family_check(
            connection,
            UPGRADED_SOURCE_FAMILIES,
        )
        _assert_exact_family(
            connection
        )
        return

    # Antes del seed, el schema debe estar
    # exactamente en el dominio histórico
    # conocido. No se sobreescribe un CHECK
    # inesperado silenciosamente.
    _replace_source_family_check(
        connection,
        expected_before=BASE_SOURCE_FAMILIES,
        desired_after=UPGRADED_SOURCE_FAMILIES,
    )

    payload = [
        {
            "source_family": SOURCE_FAMILY,
            "raw_branch_name": raw_name,
            "sucursal_canon": canon,
            "notes": (
                "Marketing iVentas canonical "
                "branch alias"
            ),
        }
        for (
            raw_name,
            canon,
            _sucursal_id,
        ) in EXPECTED_ALIASES
    ]

    connection.execute(
        sa.text(
            """
            INSERT INTO track_branch_aliases (
                source_family,
                raw_branch_name,
                sucursal_canon,
                is_active,
                notes
            )
            VALUES (
                :source_family,
                :raw_branch_name,
                :sucursal_canon,
                true,
                :notes
            )
            """
        ),
        payload,
    )

    _assert_exact_family(
        connection
    )


def downgrade():
    connection = op.get_bind()

    _validate_static_matrix()

    # El downgrade solo procede si tanto el
    # schema como la familia siguen exactamente
    # en el estado creado por esta revision.
    _assert_source_family_check(
        connection,
        UPGRADED_SOURCE_FAMILIES,
    )

    _assert_exact_family(
        connection
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM track_branch_aliases
            WHERE source_family = :source_family
            """
        ),
        {
            "source_family": SOURCE_FAMILY,
        },
    )

    remaining = _read_iventas_family(
        connection
    )

    if remaining:
        raise RuntimeError(
            "No se pudo retirar por completo "
            "iventas_family."
        )

    _replace_source_family_check(
        connection,
        expected_before=UPGRADED_SOURCE_FAMILIES,
        desired_after=BASE_SOURCE_FAMILIES,
    )
