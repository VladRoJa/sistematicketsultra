"""Regression checks for the WSO-01 RAW deletion preflight; no DB access."""

import json
import hashlib
import sys

import pytest

from scripts.ops import wso01_corte_caja_files as files


def test_only_expected_corte_caja_layout_is_accepted():
    path = files._validate_relative(
        "uploads/warehouse/gasca/corte_caja/2026/09", "export.xlsx"
    )
    assert path.as_posix() == (
        "uploads/warehouse/gasca/corte_caja/2026/09/export.xlsx"
    )


@pytest.mark.parametrize(
    "stored_path,filename",
    [
        ("uploads/warehouse/gasca/venta_total/2026/09", "export.xlsx"),
        ("uploads/warehouse/gasca/corte_caja/../../", "export.xlsx"),
        ("/tmp/uploads/warehouse/gasca/corte_caja/2026/09", "export.xlsx"),
        ("uploads/warehouse/gasca/corte_caja/2026/09", "../export.xlsx"),
    ],
)
def test_rejects_wrong_report_and_path_traversal(stored_path, filename):
    with pytest.raises(RuntimeError, match="storage path"):
        files._validate_relative(stored_path, filename)


def test_rejects_symlinked_folder(tmp_path):
    warehouse = tmp_path / "uploads" / "warehouse"
    warehouse.mkdir(parents=True)
    (warehouse / "gasca").symlink_to(tmp_path, target_is_directory=True)
    relative = files._validate_relative(
        "uploads/warehouse/gasca/corte_caja/2026/09", "export.xlsx"
    )
    with pytest.raises(RuntimeError):
        files._safe_file(tmp_path, relative, must_exist=False)


def test_manifest_rejects_duplicate_upload_id(tmp_path):
    file = tmp_path / "manifest.json"
    item = {
        "id": 7,
        "relative": "uploads/warehouse/gasca/corte_caja/2026/09/one.xlsx",
        "size": 3,
        "sha256": "a" * 64,
    }
    file.write_text(json.dumps({"report_key": "corte_caja", "items": [item, item]}))
    with pytest.raises(RuntimeError, match="duplicate manifest"):
        files._read_manifest(file)


def _synthetic_manifest(tmp_path):
    root = tmp_path
    relative = "uploads/warehouse/gasca/corte_caja/2026/09/one.xlsx"
    target = root / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"hello")
    manifest = root / "private" / "wso01" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "report_key": "corte_caja",
        "items": [{
            "id": 7,
            "relative": relative,
            "size": 5,
            "sha256": hashlib.sha256(b"hello").hexdigest(),
        }],
    }))
    return root, target, manifest


def _args(monkeypatch, mode, root, manifest, *flags):
    monkeypatch.setattr(sys, "argv", [
        "wso01_corte_caja_files", mode, "--root", str(root),
        "--manifest", str(manifest), "--expected-count", "1",
        "--expected-bytes", "5", *flags,
    ])


def test_delete_requires_migration_before_removing_any_file(tmp_path, monkeypatch):
    root, target, manifest = _synthetic_manifest(tmp_path)

    def blocked():
        raise RuntimeError("Alembic retirement incomplete")

    monkeypatch.setattr(files, "_assert_retired_in_db", blocked)
    _args(monkeypatch, "delete", root, manifest, "--apply", "--ack-irreversible")
    with pytest.raises(RuntimeError, match="Alembic retirement incomplete"):
        files.main()
    assert target.read_bytes() == b"hello"


def test_delete_dry_run_does_not_remove_file(tmp_path, monkeypatch):
    root, target, manifest = _synthetic_manifest(tmp_path)
    monkeypatch.setattr(files, "_assert_retired_in_db", lambda: None)
    _args(monkeypatch, "delete", root, manifest)
    files.main()
    assert target.read_bytes() == b"hello"


def test_delete_is_irreversible_and_scoped_to_manifest(tmp_path, monkeypatch):
    root, target, manifest = _synthetic_manifest(tmp_path)
    keep = root / "uploads" / "warehouse" / "gasca" / "venta_total" / "2026" / "09" / "keep.xlsx"
    keep.parent.mkdir(parents=True)
    keep.write_bytes(b"unrelated")
    monkeypatch.setattr(files, "_assert_retired_in_db", lambda: None)
    _args(monkeypatch, "delete", root, manifest, "--apply", "--ack-irreversible")
    files.main()
    assert not target.exists()
    assert keep.read_bytes() == b"unrelated"
    # The same manifest can finish an interrupted deletion without touching other files.
    files.main()
    assert keep.read_bytes() == b"unrelated"


def test_delete_refuses_modified_file(tmp_path, monkeypatch):
    root, target, manifest = _synthetic_manifest(tmp_path)
    target.write_bytes(b"wrong")
    monkeypatch.setattr(files, "_assert_retired_in_db", lambda: None)
    _args(monkeypatch, "delete", root, manifest, "--apply", "--ack-irreversible")
    with pytest.raises(RuntimeError, match="changed file"):
        files.main()
    assert target.read_bytes() == b"wrong"
