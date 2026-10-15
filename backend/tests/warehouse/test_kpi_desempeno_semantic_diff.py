"""M1: comparador semántico de KPI Desempeño, sin DB ni Warehouse."""

from dataclasses import replace
from io import BytesIO

import pandas as pd
import pytest

from app.warehouse.services.kpi_desempeno_parser import (
    EXPECTED_KPI_DESEMPENO_COLUMNS,
    parse_kpi_desempeno_xlsx,
)
from app.warehouse.services.kpi_desempeno_semantic_diff import (
    BLOCKED_BY_VALIDATION,
    DIFFERENCES_DETECTED,
    NO_CHANGE,
    KPI_METRIC_FIELDS,
    compare_kpi_desempeno_parsed,
    compare_kpi_desempeno_xlsx,
)


def _row(sucursal="CENTRO", **overrides):
    row = dict(
        zip(
            EXPECTED_KPI_DESEMPENO_COLUMNS,
            (sucursal, 110, 25, 40, 8, 7, 168, 200, 0.84),
        )
    )
    row.update(overrides)
    return row


def _xlsx(*rows, sheet="Data"):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(list(rows), columns=EXPECTED_KPI_DESEMPENO_COLUMNS).to_excel(
            writer, sheet_name=sheet, index=False
        )
    return out.getvalue()


def _parsed(*rows):
    return parse_kpi_desempeno_xlsx(file_bytes=_xlsx(*rows))


def _field_names(diff):
    return [change.field for change in diff.differences[0].fields]


def test_identical_xlsx_bytes_have_no_semantic_changes():
    raw = _xlsx(_row(), _row("NORTE"))
    result = compare_kpi_desempeno_xlsx(
        previous_file_bytes=raw, current_file_bytes=raw
    )
    assert result.status == NO_CHANGE
    assert result.previous_row_count == result.current_row_count == 2
    assert result.differences == ()
    assert result.to_dict()["requires_identity_review"] is False


def test_row_order_totals_and_normalized_name_do_not_change_metrics():
    previous = _xlsx(_row("  VILLA   VERDE  "), _row("NORTE"))
    current = _xlsx(
        _row("norte"),
        _row("Villa Verde"),
        _row("Totales:", Reactivaciones=999),
    )
    result = compare_kpi_desempeno_xlsx(
        previous_file_bytes=previous, current_file_bytes=current
    )
    assert result.status == NO_CHANGE


def test_change_in_three_reported_indicators_is_precise():
    old = _xlsx(_row())
    new = _xlsx(
        _row(
            **{
                "Socios Activos del Mes": 172,
                "Reactivaciones": 31,
                "Bajas": 9,
            }
        )
    )
    result = compare_kpi_desempeno_xlsx(
        previous_file_bytes=old, current_file_bytes=new
    )
    assert result.status == DIFFERENCES_DETECTED
    assert result.requires_identity_review is False
    assert len(result.differences) == 1
    assert result.differences[0].kind == "CHANGED"
    assert _field_names(result) == [
        "reactivaciones",
        "bajas",
        "socios_activos_del_mes",
    ]
    values = {field.field: (field.previous, field.current)
              for field in result.differences[0].fields}
    assert values["reactivaciones"] == (40, 31)
    assert values["bajas"] == (7, 9)


@pytest.mark.parametrize(
    ("col", "metric", "new_value"),
    [
        ("Socios Activos Inicio del Mes", "socios_activos_inicio_mes", 111),
        ("Clientes Nuevo Real", "clientes_nuevo_real", 26),
        ("Renovaciones", "renovaciones", 9),
        ("Meta de Socios Activos del Mes", "meta_socios_activos_del_mes", 201),
        ("Alcance de meta", "alcance_meta", 0.85),
    ],
)
def test_comparison_includes_all_metrics(col, metric, new_value):
    diff = compare_kpi_desempeno_xlsx(
        previous_file_bytes=_xlsx(_row()),
        current_file_bytes=_xlsx(_row(**{col: new_value})),
    )
    assert diff.status == DIFFERENCES_DETECTED
    assert _field_names(diff) == [metric]


def test_new_and_missing_branches_are_reported_not_silently_ignored():
    diff = compare_kpi_desempeno_parsed(
        previous=_parsed(_row("VILLA VERDE"), _row("CENTRO")),
        current=_parsed(_row("VILLA VERDE"), _row("SUR")),
    )
    assert diff.status == DIFFERENCES_DETECTED
    assert diff.requires_identity_review is True
    assert [(item.branch_key, item.kind) for item in diff.differences] == [
        ("centro", "REMOVED"),
        ("sur", "ADDED"),
    ]
    assert len(diff.differences[0].fields) == len(KPI_METRIC_FIELDS)
    assert all(f.current is None for f in diff.differences[0].fields)
    assert all(f.previous is None for f in diff.differences[1].fields)


def test_explicit_branch_aliases_allow_gasca_renames_without_inference():
    old = _parsed(_row("VILLA VERDE"))
    new = _parsed(_row("VV"))
    assert compare_kpi_desempeno_parsed(
        previous=old, current=new
    ).requires_identity_review
    diff = compare_kpi_desempeno_parsed(
        previous=old, current=new, sucursal_aliases={" VV ": "Villa Verde"}
    )
    assert diff.status == NO_CHANGE


def test_duplicate_normalized_branch_blocks_comparison():
    diff = compare_kpi_desempeno_parsed(
        previous=_parsed(_row("SUR"), _row(" sur ")),
        current=_parsed(_row("SUR")),
    )
    assert diff.status == BLOCKED_BY_VALIDATION
    assert "duplicada" in diff.validation_errors[0].lower()
    assert not diff.differences


def test_alias_collision_blocks_comparison():
    diff = compare_kpi_desempeno_parsed(
        previous=_parsed(_row("SUR"), _row("SUR B")),
        current=_parsed(_row("SUR")),
        sucursal_aliases={"SUR B": "SUR"},
    )
    assert diff.status == BLOCKED_BY_VALIDATION


def test_empty_alias_blocks_comparison():
    diff = compare_kpi_desempeno_parsed(
        previous=_parsed(_row()), current=_parsed(_row()),
        sucursal_aliases={"CENTRO": ""},
    )
    assert diff.status == BLOCKED_BY_VALIDATION


def test_invalid_excel_returns_blocked_without_side_effects():
    result = compare_kpi_desempeno_xlsx(
        previous_file_bytes=_xlsx(_row()),
        current_file_bytes=b"invalid.xlsx",
    )
    assert result.status == BLOCKED_BY_VALIDATION
    assert result.validation_errors
    assert result.differences == ()


def test_bad_columns_use_existing_parser_validation():
    bad = BytesIO()
    pd.DataFrame([{"Sucursal": "CENTRO", "Reactivaciones": 10}]).to_excel(
        bad, index=False
    )
    diff = compare_kpi_desempeno_xlsx(
        previous_file_bytes=_xlsx(_row()),
        current_file_bytes=bad.getvalue(),
    )
    assert diff.status == BLOCKED_BY_VALIDATION


def test_row_count_inconsistency_blocks_parsed_comparison():
    parsed = _parsed(_row())
    diff = compare_kpi_desempeno_parsed(
        previous=replace(parsed, row_count=3),
        current=parsed,
    )
    assert diff.status == BLOCKED_BY_VALIDATION


def test_nan_metric_blocks_parsed_comparison():
    old = _parsed(_row())
    bad = replace(old, rows=[replace(old.rows[0], alcance_meta=float("nan"))])
    diff = compare_kpi_desempeno_parsed(previous=old, current=bad)
    assert diff.status == BLOCKED_BY_VALIDATION


def test_float_binary_noise_is_ignored_but_real_change_is_detected():
    old = _parsed(_row())
    nearly_same = replace(
        old, rows=[replace(old.rows[0], alcance_meta=0.8400000000001)]
    )
    changed = replace(old, rows=[replace(old.rows[0], alcance_meta=0.841)])
    assert compare_kpi_desempeno_parsed(
        previous=old, current=nearly_same
    ).status == NO_CHANGE
    assert compare_kpi_desempeno_parsed(
        previous=old, current=changed
    ).status == DIFFERENCES_DETECTED


def test_file_paths_can_be_compared_without_writing_to_them(tmp_path):
    old = tmp_path / "old.xlsx"
    new = tmp_path / "new.xlsx"
    old.write_bytes(_xlsx(_row()))
    new.write_bytes(_xlsx(_row(Reactivaciones=45)))
    before = (old.read_bytes(), new.read_bytes())
    diff = compare_kpi_desempeno_xlsx(
        previous_file_path=str(old), current_file_path=str(new)
    )
    assert diff.status == DIFFERENCES_DETECTED
    assert (old.read_bytes(), new.read_bytes()) == before


def test_missing_source_is_blocked():
    diff = compare_kpi_desempeno_xlsx(
        current_file_bytes=_xlsx(_row())
    )
    assert diff.status == BLOCKED_BY_VALIDATION
