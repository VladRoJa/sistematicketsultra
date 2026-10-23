"""Contrato de los 40 alias operativos, sin cambios en enforcement ni BD.

La fuente de claves es el historial Alembic; las etiquetas viven en Angular.
Este test no conecta a PostgreSQL ni necesita ejecutar migraciones.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ALIAS_PATH = ROOT / "frontend/src/app/permissions-observability/permission-action-labels.ts"
MIGRATIONS = ROOT / "backend/migrations/versions"


def _migration_literal(filename, variable):
    tree = ast.parse((MIGRATIONS / filename).read_text(encoding="utf-8"))
    for item in tree.body:
        if isinstance(item, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == variable
            for target in item.targets
        ):
            return ast.literal_eval(item.value)
    raise AssertionError(f"{filename} no define {variable}")


def _seed_keys():
    original = _migration_literal(
        "3d4f6a8b9c10_seed_global_permissions_catalog.py", "ACTIONS",
    )
    module_entries = _migration_literal(
        "8f1e2d3c4b5a_add_permission_module_assignable_metadata.py",
        "VIEW_ACTIONS",
    )
    extra = _migration_literal(
        "7b8c9d0e1f2a_seed_permission_route_map_high_risk.py", "EXTRA_ACTIONS",
    )
    maintenance = _migration_literal(
        "c17a10202601_tickets_v1_maintenance_attention.py", "ACTIONS",
    )
    keys = (
        [row[2] for row in original]
        + [row[2] for row in module_entries]
        + [row["full_key"] for row in extra]
        + [row[1] for row in maintenance]
    )
    assert len(keys) == len(set(keys)) == 40
    return set(keys)


def _alias_rows():
    source = ALIAS_PATH.read_text(encoding="utf-8")
    return re.findall(
        r'^  \'([^\']+)\': \\{ label: "([^"]+)", explanation: "([^"]+)", purpose: "([^"]+)" \\},$',
        source, flags=re.MULTILINE,
    )


def test_all_40_seed_actions_have_one_human_readable_alias():
    rows = _alias_rows()
    actual = [row[0] for row in rows]
    assert len(actual) == len(set(actual)) == 40
    assert set(actual) == _seed_keys()


def test_action_labels_are_readable_and_do_not_masquerade_as_permissions():
    for key, label, explanation, purpose in _alias_rows():
        assert "." in key and " " in label, key
        assert "_" not in label and len(explanation) >= 25, key
        assert len(purpose) >= 5 and len(label) <= 65, key
        assert not re.search(r"\\b(autorizado|concedido)\\b", label, re.I), key


def test_unknown_actions_fall_back_without_inventing_a_permission():
    source = ALIAS_PATH.read_text(encoding="utf-8")
    assert "fallback?.trim()" in source
    assert "'Acción sin identificar'" in source
    assert "Descripción pendiente de validar" in source
    # Las claves full_key no se modifican ni se sustituyen en la API.
    assert "permissionActionLabel" in source
