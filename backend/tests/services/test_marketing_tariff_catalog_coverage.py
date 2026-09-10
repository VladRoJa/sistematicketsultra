import ast
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "e3f6a9b1c5d7_expand_reactivation_tariff_catalog.py"
)


def _assignment(name):
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing assignment {name}")


def test_high_confidence_tariff_batch_is_unique_and_uses_valid_groups():
    tariffs = _assignment("_TARIFFS")

    assert len(tariffs) == 29
    assert len({tarifa for tarifa, _, _ in tariffs}) == 29
    assert {group for _, _, group in tariffs} <= {
        "REACTIVATE",
        "DOMICILIATED_FLOW",
        "EXCLUDE",
        "REVIEW",
    }


def test_high_confidence_batch_keeps_ambiguous_tariffs_out():
    tariff_names = {tarifa for tarifa, _, _ in _assignment("_TARIFFS")}

    assert "SEMANA $400" not in tariff_names
    assert "SEMANA SLRC $199" not in tariff_names
    assert "DIA" not in tariff_names
    assert "BECA 1 DIAS" not in tariff_names
    assert "TARJETA DE REGALO" not in tariff_names
    assert "RECURRENTE ULTRAFITKIDS $399" not in tariff_names
    assert "BORRON Y CUENTA NUEVA HE 12 MESES" not in tariff_names


def test_explicit_domiciliated_and_recurrent_rows_use_domiciliated_flow():
    tariffs = _assignment("_TARIFFS")
    expected = {
        "DOMICILIADO 12 MESES $649 HE",
        "DOMICILIADO 12 MESES (CON PLAZO)",
        "DOMICILIADO 12 MESES $599 METEPEC",
        "CONVENIO DOMICILIADO $549",
        "RECURRENTE $799 HE",
        "DOMICILIADO PLAN ULTRA PAGO INCIAL 12 MESES $1,549 HE",
        "DOMICILIADO 12 MESES $599 PASEO VILLALTA",
        "PLAN RECURRENTE PAGO INCIAL $1,549 HE",
        "DOMICILIADO 12 MESES $499 PREVENTA",
        "DOMICILIADO SIN PLAZO $699 HE",
        "DOMICILIADO 12 MESES $399 JULIO",
    }
    groups = {tarifa: group for tarifa, _, group in tariffs}

    assert expected <= groups.keys()
    assert all(groups[tarifa] == "DOMICILIATED_FLOW" for tarifa in expected)


def test_migration_follows_current_head():
    assert _assignment("revision") == "e3f6a9b1c5d7"
    assert _assignment("down_revision") == "d2e5f8a0b4c6"
