from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.services.marketing_reactivation_candidate_query import (
    ReactivationCandidateCursor,
    apply_candidate_cursor,
    build_latest_operational_episode_query,
    build_phone_variant_filter,
)


def _session_with_rows(rows):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE socios_vencidos_cartera (
                id INTEGER PRIMARY KEY,
                sucursal_raw VARCHAR(255), sucursal_key VARCHAR(255),
                pin VARCHAR(64), nombre VARCHAR(255), genero VARCHAR(50),
                edad_raw INTEGER, edad INTEGER, edad_status VARCHAR(32),
                fecha_vencimiento_local DATETIME,
                fecha_vencimiento_date DATE,
                fecha_ultimo_pago_local DATETIME, tarifa VARCHAR(255),
                correo_raw VARCHAR(320), telefono_raw VARCHAR(64),
                telefono_digits VARCHAR(32), adeudo NUMERIC(14, 2),
                row_hash VARCHAR(64), first_seen_at DATETIME,
                last_seen_at DATETIME, first_source_snapshot_id INTEGER,
                last_source_snapshot_id INTEGER
            )
        """))
        for row in rows:
            connection.execute(
                text("""
                    INSERT INTO socios_vencidos_cartera (
                        id, sucursal_raw, sucursal_key, pin, nombre,
                        fecha_vencimiento_date
                    ) VALUES (:id, :branch, :branch, :pin, :name, :expiration)
                """),
                row,
            )
    return Session(engine)


def _row(row_id, branch, pin, expiration):
    return {
        "id": row_id,
        "branch": branch,
        "pin": pin,
        "name": f"Socio {row_id}",
        "expiration": expiration,
    }


def test_latest_global_episode_is_selected_before_date_filter():
    session = _session_with_rows([
        _row(1, "TEC", "123", "2021-03-01"),
        _row(2, "TEC", "123", "2024-08-01"),
        _row(3, "TEC", "123", "2026-07-01"),
    ])

    all_years = build_latest_operational_episode_query(
        session=session,
        date_from=date(2019, 1, 1),
        date_to=date(2026, 12, 31),
    ).all()
    historical_window = build_latest_operational_episode_query(
        session=session,
        date_from=date(2021, 1, 1),
        date_to=date(2021, 12, 31),
    ).all()

    assert [row.id for row in all_years] == [3]
    assert historical_window == []


def test_same_pin_in_different_branches_is_two_operational_members():
    session = _session_with_rows([
        _row(1, "TEC", "123", "2026-07-01"),
        _row(2, "CENTRO", "123", "2026-07-02"),
    ])

    rows = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    ).all()

    assert {row.id for row in rows} == {1, 2}


def test_same_expiration_date_uses_highest_id_as_stable_tiebreaker():
    session = _session_with_rows([
        _row(10, "TEC", "123", "2026-07-01"),
        _row(20, "TEC", "123", "2026-07-01"),
    ])

    rows = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    ).all()

    assert [row.id for row in rows] == [20]


def test_query_compiles_to_partitioned_row_number_and_outer_range_filter():
    session = _session_with_rows([])
    query = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    sql = str(query.statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )).lower()
    assert "row_number() over (partition by" in sql
    assert "sucursal_key" in sql and "pin" in sql
    assert "fecha_vencimiento_date desc" in sql
    assert "socios_vencidos_cartera.id desc" in sql
    assert "episode_rank = 1" in sql
    assert "between '2026-01-01' and '2026-12-31'" in sql


def test_query_composes_branch_tariff_group_and_safe_search_filters():
    session = _session_with_rows([])
    query = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        sucursal="CENTRO",
        tarifa="ANUAL",
        tariff_group="REACTIVATE",
        search="Ana%_",
    )

    sql = str(query.statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )).lower()
    assert "sucursal_key = 'centro'" in sql
    assert "sucursal_raw = 'centro'" in sql
    assert "tarifa = 'anual'" in sql
    assert "marketing_reactivation_tariffs.is_active is true" in sql
    assert "reactivation_group = 'reactivate'" in sql
    assert "ana\\\\%%\\\\_%%" in sql
    assert "escape '\\\\'" in sql


def test_query_uses_allowlisted_ascending_and_descending_order():
    session = _session_with_rows([])
    ascending = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        sort="nombre",
        direction="asc",
    )
    descending = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        sort="telefono",
        direction="desc",
    )

    ascending_sql = str(ascending.statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )).lower()
    descending_sql = str(descending.statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )).lower()
    assert "nombre asc nulls last" in ascending_sql
    assert "telefono_raw desc nulls last" in descending_sql
    assert ascending_sql.rstrip().endswith("socios_vencidos_cartera.id desc")
    assert descending_sql.rstrip().endswith("socios_vencidos_cartera.id desc")


def test_query_applies_backend_branch_scope_before_resolution():
    session = _session_with_rows([
        _row(1, "CENTRO", "100", "2026-07-01"),
        _row(2, "NORTE", "200", "2026-07-01"),
    ])

    rows = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        allowed_sucursal_keys=("CENTRO",),
    ).all()

    assert [row.id for row in rows] == [1]


def test_cursor_uses_sort_value_then_descending_id_without_gaps():
    session = _session_with_rows([
        _row(30, "CENTRO", "300", "2026-07-01"),
        _row(20, "CENTRO", "200", "2026-07-01"),
        _row(10, "CENTRO", "100", "2026-07-01"),
        _row(5, "CENTRO", "050", "2026-06-30"),
    ])
    query = build_latest_operational_episode_query(
        session=session,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        sort="fecha_vencimiento",
        direction="desc",
    )
    first = query.limit(2).all()
    second = apply_candidate_cursor(
        query,
        cursor=ReactivationCandidateCursor(
            sort_value=first[-1].fecha_vencimiento_date,
            row_id=first[-1].id,
        ),
        sort="fecha_vencimiento",
        direction="desc",
    ).limit(2).all()

    assert [row.id for row in first + second] == [30, 20, 10, 5]


def test_phone_variant_filter_matches_mx10_52_and_521_forms():
    session = _session_with_rows([])
    expression = build_phone_variant_filter({"6861234567"})
    sql = str(expression.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))

    assert "6861234567" in sql
    assert "526861234567" in sql
    assert "5216861234567" in sql
