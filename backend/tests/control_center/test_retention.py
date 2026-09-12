from app.control_center.retention import RetentionBranchRow, _aggregate_rows


def test_retention_aggregate_sums_actuals_targets_and_usage():
    rows = [
        RetentionBranchRow(
            sucursal_id=1,
            sucursal_canon="VILLAS_DEL_REY",
            sucursal="Villas del Rey",
            bajas_reales_mtd=30,
            meta_bajas_mes=40,
        ),
        RetentionBranchRow(
            sucursal_id=2,
            sucursal_canon="VILLA_VERDE",
            sucursal="Villa Verde",
            bajas_reales_mtd=35,
            meta_bajas_mes=40,
        ),
    ]

    summary = _aggregate_rows(rows)

    assert summary["bajas_reales_mtd"] == 65
    assert summary["meta_bajas_mes"] == 80
    assert summary["limit_usage_ratio"] == 0.8125
    assert summary["remaining_margin"] == 15
    assert summary["branch_count"] == 2
    assert summary["actual_coverage_branch_count"] == 2
    assert summary["target_coverage_branch_count"] == 2


def test_retention_aggregate_does_not_publish_partial_target_ratio():
    rows = [
        RetentionBranchRow(
            sucursal_id=1,
            sucursal_canon="VILLAS_DEL_REY",
            sucursal="Villas del Rey",
            bajas_reales_mtd=12,
            meta_bajas_mes=20,
        ),
        RetentionBranchRow(
            sucursal_id=2,
            sucursal_canon="VILLA_VERDE",
            sucursal="Villa Verde",
            bajas_reales_mtd=9,
            meta_bajas_mes=None,
        ),
    ]

    summary = _aggregate_rows(rows)

    assert summary["bajas_reales_mtd"] == 21
    assert summary["meta_bajas_mes"] is None
    assert summary["limit_usage_ratio"] is None
    assert summary["remaining_margin"] is None
    assert summary["target_coverage_branch_count"] == 1
