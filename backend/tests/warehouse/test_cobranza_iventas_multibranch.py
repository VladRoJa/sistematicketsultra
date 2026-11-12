"""Synthetic, no HTTP: independent daily cobranza batches and fail-closed gates."""
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import Mock, MagicMock

import pytest
from openpyxl import Workbook

from app.warehouse.jobs import cobranza_iventas_multibranch as svc
from app.warehouse.jobs import cobranza_iventas_preparation as preparation


DAY = date(2026, 11, 13)


@pytest.fixture
def multi_env(monkeypatch):
    monkeypatch.setenv("COBRANZA_IVENTAS_MULTI_BRANCH_ENABLED", "true")
    monkeypatch.setenv("COBRANZA_IVENTAS_MULTI_BRANCH_START_DATE", "2026-11-13")
    monkeypatch.setenv("COBRANZA_IVENTAS_MULTI_BRANCH_KEYS", "ALFA,BETA,GAMMA")
    monkeypatch.setenv("COBRANZA_IVENTAS_MULTI_BRANCH_OPERATOR_ID", "47")
    monkeypatch.setenv("COBRANZA_IVENTAS_MULTI_BRANCH_MAX_RECIPIENTS_PER_BRANCH", "30")
    monkeypatch.setenv("COBRANZA_IVENTAS_MULTI_BRANCH_MAX_DAILY_RECIPIENTS", "60")


def test_multibranch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("COBRANZA_IVENTAS_MULTI_BRANCH_ENABLED", raising=False)
    assert svc.multi_branch_config(DAY) is None


def test_rollout_never_runs_before_start(multi_env):
    assert svc.multi_branch_config(date(2026, 11, 12)) is None
    assert svc.multi_branch_config(DAY).branch_keys == ("ALFA", "BETA", "GAMMA")


@pytest.mark.parametrize("name,value", [
    ("COBRANZA_IVENTAS_MULTI_BRANCH_START_DATE", "2026-11-12"),
    ("COBRANZA_IVENTAS_MULTI_BRANCH_KEYS", "ALFA,ALFA"),
    ("COBRANZA_IVENTAS_MULTI_BRANCH_KEYS", "ALFA,BETA, gamma"),
    ("COBRANZA_IVENTAS_MULTI_BRANCH_KEYS", "ALFA,,BETA"),
    ("COBRANZA_IVENTAS_MULTI_BRANCH_OPERATOR_ID", "0"),
    ("COBRANZA_IVENTAS_MULTI_BRANCH_MAX_RECIPIENTS_PER_BRANCH", "10001"),
    ("COBRANZA_IVENTAS_MULTI_BRANCH_MAX_DAILY_RECIPIENTS", "2"),
])
def test_invalid_rollout_never_queues(multi_env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(svc.MultiBranchBlocked):
        svc.multi_branch_config(DAY)


def _artifact(tmp_path, branch, phones):
    book = Workbook()
    sheet = book.active
    sheet.append(["Socio", "Telefono"])
    for n, phone in enumerate(phones):
        sheet.append([f"Test {n}", phone])
    path = tmp_path / f"{branch}.xlsx"
    book.save(path)
    return {"sucursal_raw": branch, "path": str(path)}


def _settings(branches=("ALFA", "BETA", "GAMMA"), per_branch=30, daily=60):
    return svc.MultiBranchConfig(
        start_date=DAY, branch_keys=tuple(branches), operator_id=47,
        max_recipients_per_branch=per_branch, max_daily_recipients=daily,
    )


def _ready(monkeypatch, fake_db):
    monkeypatch.setattr(svc, "_require_global_authorization", lambda *_: None)
    monkeypatch.setattr(svc.db, "session", fake_db)
    fake_db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(
        svc, "resolve_dispatch_branch_key",
        lambda raw, session: NS(sucursal_canon=raw),
    )
    audit = []
    monkeypatch.setattr(svc, "_audit", lambda settings, **kw: audit.append(kw))
    blocked = []
    monkeypatch.setattr(
        svc, "_persist_blocked",
        lambda campaign_id, day, branch: blocked.append((campaign_id, branch)),
    )
    return audit, blocked


def test_per_branch_failure_does_not_stop_independent_neighbors(
    monkeypatch, tmp_path,
):
    fake_db = MagicMock()
    audit, blocked = _ready(monkeypatch, fake_db)
    files = [
        _artifact(tmp_path, "ALFA", ["6861000001"]),
        _artifact(tmp_path, "BETA", ["6861000002"]),
        _artifact(tmp_path, "GAMMA", ["6861000003"]),
    ]
    prepared = []
    def prepare(**kwargs):
        branch = kwargs["isolated_branch_key"]
        prepared.append(branch)
        return {"status": "PREPARED", "campaign_id": {"ALFA": 101, "BETA": 102, "GAMMA": 103}[branch]}
    monkeypatch.setattr(svc, "prepare_cobranza_iventas_campaign", prepare)
    def queue(day, branch, campaign_id, settings):
        if branch == "BETA":
            raise svc.MultiBranchBlocked("Synthetic uncertain provider gate")
        return {"status": "QUEUED", "job_id": campaign_id + 100, "recipient_count": 1}
    monkeypatch.setattr(svc, "_queue_branch", queue)

    output = svc.process_multi_branch(day=DAY, artifacts=files, settings=_settings())
    assert prepared == ["ALFA", "BETA", "GAMMA"]
    assert output["queued_branches"] == 2
    assert output["skipped_branches"] == 1
    assert [(r["branch"], r["status"]) for r in output["branches"]] == [
        ("ALFA", "QUEUED"), ("BETA", "SKIPPED"), ("GAMMA", "QUEUED"),
    ]
    assert blocked == [(102, "BETA")]
    assert fake_db.rollback.called
    assert len([a for a in audit if a["status"] == "SKIPPED"]) == 1


def test_shared_phone_across_branches_is_excluded_from_both(
    monkeypatch, tmp_path,
):
    fake_db = MagicMock()
    _ready(monkeypatch, fake_db)
    files = [
        _artifact(tmp_path, "ALFA", ["6861000001", "6861000002"]),
        _artifact(tmp_path, "BETA", ["6861000002", "6861000003"]),
        _artifact(tmp_path, "GAMMA", ["6861000004"]),
    ]
    safe_by_branch = {}
    def prepare(**kwargs):
        safe_by_branch[kwargs["isolated_branch_key"]] = kwargs["allowed_phones"]
        return {"status": "PREPARED", "campaign_id": len(safe_by_branch)}
    monkeypatch.setattr(svc, "prepare_cobranza_iventas_campaign", prepare)
    monkeypatch.setattr(
        svc, "_queue_branch",
        lambda day, branch, campaign_id, settings: {
            "status": "QUEUED", "job_id": campaign_id, "recipient_count": 1,
        },
    )
    result = svc.process_multi_branch(day=DAY, artifacts=files, settings=_settings())
    assert result["ambiguous_phones_excluded"] == 1
    assert safe_by_branch == {
        "ALFA": frozenset({"6861000001"}),
        "BETA": frozenset({"6861000003"}),
        "GAMMA": frozenset({"6861000004"}),
    }


def test_invalid_file_skips_one_branch_and_next_proceeds(monkeypatch, tmp_path):
    fake_db = MagicMock()
    _ready(monkeypatch, fake_db)
    good = _artifact(tmp_path, "ALFA", ["6861000001"])
    bad = _artifact(tmp_path, "BETA", ["6861000002"])
    book = Workbook()
    book.active.append(["Socio", "SIN COLUMNA"])
    book.save(bad["path"])
    later = _artifact(tmp_path, "GAMMA", ["6861000003"])
    monkeypatch.setattr(
        svc, "prepare_cobranza_iventas_campaign",
        lambda **kw: {"status": "PREPARED", "campaign_id": 88},
    )
    monkeypatch.setattr(
        svc, "_queue_branch",
        lambda day, branch, campaign_id, settings: {
            "status": "QUEUED", "job_id": 89, "recipient_count": 1,
        },
    )
    result = svc.process_multi_branch(
        day=DAY, artifacts=[good, bad, later], settings=_settings(),
    )
    assert [r["status"] for r in result["branches"]] == [
        "QUEUED", "SKIPPED", "QUEUED",
    ]
    assert result["branches"][1]["reason"] == "INVALID_BRANCH_FILE"


def test_daily_limit_stops_before_any_dispatch(monkeypatch, tmp_path):
    fake_db = MagicMock()
    _ready(monkeypatch, fake_db)
    prepare = Mock(side_effect=AssertionError("Must not freeze cohort"))
    monkeypatch.setattr(svc, "prepare_cobranza_iventas_campaign", prepare)
    files = [
        _artifact(tmp_path, "ALFA", ["6861000001", "6861000002"]),
        _artifact(tmp_path, "BETA", ["6861000003"]),
    ]
    with pytest.raises(svc.MultiBranchBlocked, match="límite diario"):
        svc.process_multi_branch(
            day=DAY, artifacts=files,
            settings=_settings(branches=("ALFA", "BETA"), daily=2),
        )
    prepare.assert_not_called()


def test_existing_general_campaign_blocks_all_branches(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(svc, "_require_global_authorization", lambda *_: None)
    monkeypatch.setattr(svc.db, "session", fake_db)
    fake_db.query.return_value.filter.return_value.first.return_value = (91,)
    with pytest.raises(svc.MultiBranchBlocked, match="campaña general"):
        svc.process_multi_branch(day=DAY, artifacts=[], settings=_settings())


def test_isolated_campaign_rejects_wrong_metadata(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(svc.db, "session", fake_db)
    fake_db.get.return_value = NS(
        name="COBRANZA RECURRENTE RECHAZADOS - 2026-11-13 - BETA",
        audience_definition_json={"source_metadata": {
            "automation_job": "cobranza_recurrente_rechazados",
            "business_date": "2026-11-13",
            "isolated_branch_key": "BETA",
            "auto_multibranch_date": "2026-11-13",
        }},
    )
    with pytest.raises(svc.MultiBranchBlocked, match="Identidad"):
        svc._queue_branch(DAY, "ALFA", 92, _settings())


def test_isolated_campaign_freeze_never_reuses_general_name(monkeypatch, tmp_path):
    artifact = _artifact(tmp_path, "ALFA", ["6861000001"])
    session = MagicMock()
    session.query.return_value.filter.return_value.one_or_none.return_value = None
    monkeypatch.setattr(preparation.db, "session", session)
    monkeypatch.setenv("COBRANZA_IVENTAS_TEMPLATE_ID", "14")
    monkeypatch.setenv("WAREHOUSE_AUTOMATION_USER_ID", "47")
    monkeypatch.setattr(preparation, "resolve_dispatch_template", lambda **kw: NS())
    monkeypatch.setattr(preparation, "resolve_dispatch_branch_key",
                        lambda raw, session: NS(sucursal_canon=raw, sucursal_id=1))
    monkeypatch.setattr(preparation, "resolve_dispatch_channel_binding",
                        lambda **kw: NS(provider_channel_id="channel-1"))
    monkeypatch.setattr(preparation, "template_allows_channel", lambda *a: True)
    monkeypatch.setattr(preparation, "preview_excel_campaign",
                        lambda **kw: {"preview_fingerprint": "a" * 64})
    captured = {}
    def freeze(**kwargs):
        captured.update(kwargs)
        return {"campaign_id": 66, "recipient_count": 1, "blacklist_excluded_count": 0}
    monkeypatch.setattr(preparation, "freeze_excel_campaign", freeze)
    result = preparation.prepare_cobranza_iventas_campaign(
        business_date=DAY, artifacts=[artifact], isolated_branch_key="ALFA",
        allowed_phones=frozenset({"6861000001"}),
    )
    assert result["campaign_id"] == 66
    assert captured["name"] == "COBRANZA RECURRENTE RECHAZADOS - 2026-11-13 - ALFA"
    assert captured["source_metadata_extra"]["isolated_branch_key"] == "ALFA"
    assert captured["source_metadata_extra"]["auto_multibranch_date"] == "2026-11-13"
    assert "pilot_branch_key" not in captured["source_metadata_extra"]


def test_unselected_branch_still_prevents_duplicate_phone_dispatch(monkeypatch, tmp_path):
    fake_db = MagicMock()
    _ready(monkeypatch, fake_db)
    files = [
        _artifact(tmp_path, "ALFA", ["6861000001", "6861000002"]),
        _artifact(tmp_path, "BETA", ["6861000002"]),  # not authorized to send
        _artifact(tmp_path, "GAMMA", ["6861000003"]),
    ]
    captured = {}
    def prepare(**kwargs):
        captured[kwargs["isolated_branch_key"]] = kwargs["allowed_phones"]
        return {"status": "PREPARED", "campaign_id": len(captured)}
    monkeypatch.setattr(svc, "prepare_cobranza_iventas_campaign", prepare)
    monkeypatch.setattr(
        svc, "_queue_branch",
        lambda day, branch, campaign_id, settings: {
            "status": "QUEUED", "job_id": campaign_id, "recipient_count": 1,
        },
    )
    result = svc.process_multi_branch(
        day=DAY, artifacts=files,
        settings=_settings(branches=("ALFA", "GAMMA")),
    )
    assert result["ambiguous_phones_excluded"] == 1
    assert captured == {
        "ALFA": frozenset({"6861000001"}),
        "GAMMA": frozenset({"6861000003"}),
    }
