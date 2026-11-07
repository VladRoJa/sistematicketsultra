"""Regression tests for Serrania's historical clean-bootstrap migration."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "840a64d2ee63_add_serrania_to_track_catalog.py"
)


class RecordingOperations:
    def __init__(self):
        self.calls = []

    def drop_constraint(self, name, table, *, type_):
        self.calls.append(("drop_constraint", name, table, type_))

    def create_check_constraint(self, name, table, condition):
        self.calls.append(("create_check_constraint", name, table, condition))

    def execute(self, statement):
        self.calls.append(("execute", statement))


def _run_migration(monkeypatch, method):
    spec = spec_from_file_location("serrania_bootstrap_test", MIGRATION_PATH)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    recording = RecordingOperations()
    monkeypatch.setattr(migration, "op", recording)
    getattr(migration, method)()
    return recording.calls


def test_upgrade_widens_source_family_before_inserting_serrania(monkeypatch):
    calls = _run_migration(monkeypatch, "upgrade")
    assert [call[0] for call in calls] == [
        "drop_constraint",
        "create_check_constraint",
        "execute",
        "execute",
    ]
    assert calls[0][1:3] == (
        "ck_track_branch_aliases_source_family", "track_branch_aliases",
    )
    allowed = calls[1][3]
    for name in (
        "manual_targets", "gasca_family", "domiciliados_total",
        "domiciliados_recep", "venta_tienda",
        "totalpass_family", "wellhub_family",
    ):
        assert f"'{name}'" in allowed
    assert "INSERT INTO track_branch_catalog" in calls[2][1]
    assert "INSERT INTO track_branch_aliases" in calls[3][1]
    assert "'wellhub_family'" in calls[3][1]
    assert "'totalpass_family'" in calls[3][1]


def test_downgrade_removes_serrania_before_restoring_five_families(monkeypatch):
    calls = _run_migration(monkeypatch, "downgrade")
    assert [call[0] for call in calls] == [
        "execute",
        "execute",
        "drop_constraint",
        "create_check_constraint",
    ]
    assert "DELETE FROM track_branch_aliases" in calls[0][1]
    assert "DELETE FROM track_branch_catalog" in calls[1][1]
    allowed = calls[3][3]
    for name in (
        "manual_targets", "gasca_family", "domiciliados_total",
        "domiciliados_recep", "venta_tienda",
    ):
        assert f"'{name}'" in allowed
    assert "'wellhub_family'" not in allowed
    assert "'totalpass_family'" not in allowed
