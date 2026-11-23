"""Regression coverage for one-shot Costa provider-approved catalog linking."""
from types import SimpleNamespace as NS

import pytest

from scripts.marketing import link_costa_iventas_templates as bulk


def _fixtures():
    bindings = [
        {"sucursal_canon": branch, "sucursal_id": number,
         "provider_channel_id": f"channel-{number}",
         "is_active": True, "is_default": True}
        for number, branch in enumerate(bulk.COSTA, 1)
    ]
    inventories = {
        branch: tuple(
            NS(template_name=name, channel_id=f"channel-{number}", status="accepted")
            for name in bulk.expected_names(branch)
        )
        for number, branch in enumerate(bulk.COSTA, 1)
    }
    return bindings, inventories


def test_coast_has_32_distinct_templates_and_strict_loma_pricing():
    all_names = {name for branch in bulk.COSTA for name in bulk.expected_names(branch)}
    assert len(all_names) == 32
    assert len(bulk.COSTA) == 7
    for branch in bulk.COSTA:
        names = bulk.expected_names(branch)
        assert len(names) == 24
        if branch == "LOMA_BONITA":
            assert all("_499_" not in n for n in names)
            assert len([n for n in names if n.endswith("_449_lb")]) == 8
        else:
            assert all("_449_" not in n for n in names)
            assert len([n for n in names if n.endswith("_499_n1")]) == 8


def test_approval_checked_plan_guards_missing_name_variable_contract():
    bindings, inventories = _fixtures()
    plan = bulk.build_plan(bindings, inventories, [])
    assert len(plan) == 32
    assert sum(row.status == "READY" for row in plan) == 30
    assert {row.name for row in plan if row.status == "VERIFY_FIELDS"} == bulk.FIELD_REVIEW
    assert sum(len(row.channels) for row in plan) == 168
    assert len(next(row for row in plan if row.name == "1regresa_449_lb").channels) == 1
    assert len(next(row for row in plan if row.name == "1regresa_499_n1").channels) == 6


def test_unapproved_single_channel_blocks_that_template_without_expanding_scope():
    bindings, inventories = _fixtures()
    branch = "LOMA_BONITA"
    inventories[branch] = tuple(
        NS(template_name=record.template_name, channel_id=record.channel_id,
           status="pending" if record.template_name == "1regresa_449_lb" else record.status)
        for record in inventories[branch]
    )
    plan = bulk.build_plan(bindings, inventories, [])
    target = next(row for row in plan if row.name == "1regresa_449_lb")
    assert target.status == "PENDING_APPROVAL"
    assert target.reasons == ("LOMA_BONITA:pending",)
    assert next(row for row in plan if row.name == "2regresa_449_lb").status == "READY"


def test_catalog_same_name_matching_config_is_idempotent():
    bindings, inventories = _fixtures()
    expected_channels = [f"channel-{n}" for n in range(1, 8)]
    catalog = [{
        "provider": "IVENTAS",
        "template_name": "1regresa_299_n3",
        "is_active": True,
        "purposes": ["REACTIVATION"],
        "variables": {"1": "first_name"},
        "compatible_channel_ids": expected_channels,
    }]
    plan = bulk.build_plan(bindings, inventories, catalog)
    assert next(row for row in plan if row.name == "1regresa_299_n3").status == "ALREADY_LINKED"
    catalog[0]["variables"] = {}
    plan = bulk.build_plan(bindings, inventories, catalog)
    assert next(row for row in plan if row.name == "1regresa_299_n3").status == "CONFLICT"


def test_scope_missing_or_duplicate_bindings_fails_closed():
    bindings, inventories = _fixtures()
    with pytest.raises(ValueError, match="siete"):
        bulk.build_plan(bindings, {key: val for key, val in inventories.items() if key != "SANTA_FE"}, [])
    with pytest.raises(ValueError, match="único"):
        bulk.build_plan(bindings[:-1], inventories, [])
    bindings[1]["provider_channel_id"] = bindings[0]["provider_channel_id"]
    with pytest.raises(ValueError, match="mismo canal"):
        bulk.build_plan(bindings, inventories, [])


def test_unrelated_catalog_duplicates_do_not_block_costa_preview():
    bindings, inventories = _fixtures()
    other = {
        "provider": "IVENTAS", "template_name": "campana_historica",
        "is_active": True, "purposes": ["REACTIVATION"],
        "variables": {}, "compatible_channel_ids": ["some-channel"],
    }
    catalog = [other, {**other, "template_name": "CAMPANA_HISTORICA"}]

    plan = bulk.build_plan(bindings, inventories, catalog)

    assert len(plan) == 32
    assert sum(row.status == "READY" for row in plan) == 30
    assert {row.name for row in plan if row.status == "VERIFY_FIELDS"} == bulk.FIELD_REVIEW


def test_duplicate_costa_name_is_a_local_conflict_without_blocking_other_templates():
    bindings, inventories = _fixtures()
    existing = {
        "provider": "IVENTAS", "template_name": "1regresa_299_n3",
        "is_active": True, "purposes": ["REACTIVATION"],
        "variables": {"1": "first_name"},
        "compatible_channel_ids": [f"channel-{n}" for n in range(1, 8)],
    }
    catalog = [existing, {**existing, "template_name": "1REGRESA_299_N3"}]

    plan = bulk.build_plan(bindings, inventories, catalog)

    duplicate = next(row for row in plan if row.name == "1regresa_299_n3")
    assert duplicate.status == "CONFLICT"
    assert "duplicados" in duplicate.reasons[0]
    assert next(row for row in plan if row.name == "2regresa_399_n2").status == "READY"


def test_login_failure_identifies_branch_and_stops_without_catalog_writes(monkeypatch, capsys):
    from unittest.mock import MagicMock, Mock

    bindings, _ = _fixtures()
    by_branch = bulk._active_bindings(bindings)
    session = MagicMock()
    monkeypatch.setattr(bulk, "db", NS(session=session))
    monkeypatch.setattr(
        bulk, "load_iventas_template_credentials",
        lambda *, session: {
            row["sucursal_id"]: object() for row in by_branch.values()
        },
    )
    playwright = MagicMock()
    monkeypatch.setattr(bulk, "sync_playwright", lambda: playwright)
    read = Mock(side_effect=bulk.TemplateBrowserError("iVentas no confirmó el inicio de sesión."))
    monkeypatch.setattr(bulk, "read_template_inventory", read)

    with pytest.raises(bulk.TemplateBrowserError, match="PASEO_2000.*inicio de sesión"):
        bulk._load_inventories(by_branch)

    assert "Consultando inventario de PASEO_2000" in capsys.readouterr().out
    read.assert_called_once()
    playwright.__enter__.return_value.chromium.launch.return_value.close.assert_called_once()
