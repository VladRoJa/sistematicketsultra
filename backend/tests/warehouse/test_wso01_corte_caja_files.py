"""Regression checks for the WSO-01 RAW deletion preflight; no DB access."""

import json

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
