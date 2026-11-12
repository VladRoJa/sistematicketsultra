"""One-day production auto-pilot safety; no live provider calls or PII."""
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from flask import Flask

from app.warehouse.jobs import cobranza_iventas_auto_pilot as svc


@pytest.fixture
def authorized_env(monkeypatch):
    monkeypatch.setenv("COBRANZA_IVENTAS_AUTO_SEND_ENABLED", "true")
    monkeypatch.setenv("COBRANZA_IVENTAS_AUTO_SEND_DATE", "2026-11-12")
    monkeypatch.setenv("COBRANZA_IVENTAS_AUTO_SEND_BRANCH", "VILLAS_DEL_REY")
    monkeypatch.setenv("COBRANZA_IVENTAS_AUTO_SEND_MAX_RECIPIENTS", "30")
    monkeypatch.setenv("COBRANZA_IVENTAS_AUTO_SEND_OPERATOR_ID", "47")


def test_auto_send_defaults_off(monkeypatch):
    monkeypatch.delenv("COBRANZA_IVENTAS_AUTO_SEND_ENABLED", raising=False)
    assert svc.auto_pilot_config(date(2026, 11, 12)) is None


def test_auto_send_never_runs_on_another_day(authorized_env):
    assert svc.auto_pilot_config(date(2026, 11, 11)) is None
    assert svc.auto_pilot_config(date(2026, 11, 13)) is None


@pytest.mark.parametrize("name,value", [
    ("COBRANZA_IVENTAS_AUTO_SEND_DATE", "2026-11-13"),
    ("COBRANZA_IVENTAS_AUTO_SEND_BRANCH", "VILLA_VERDE"),
    ("COBRANZA_IVENTAS_AUTO_SEND_MAX_RECIPIENTS", "31"),
    ("COBRANZA_IVENTAS_AUTO_SEND_MAX_RECIPIENTS", "0"),
    ("COBRANZA_IVENTAS_AUTO_SEND_OPERATOR_ID", "0"),
])
def test_invalid_authorization_blocks(authorized_env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(svc.AutoPilotBlocked):
        svc.auto_pilot_config(date(2026, 11, 12))


def _session(recipients=21, pilot="VILLAS_DEL_REY", actor_global=True):
    sess = Mock()
    campaign = NS(audience_definition_json={"source_metadata": {
        "automation_job": "cobranza_recurrente_rechazados",
        "business_date": "2026-11-12",
        "pilot_branch_key": pilot,
        "auto_pilot_date": "2026-11-12",
    }})
    actor = NS(id=47)
    sess.get.side_effect = lambda model, key: campaign if model is svc.MarketingCampaignV2ORM else actor
    query = Mock()
    query.filter.return_value = query
    query.scalar.return_value = recipients
    sess.query.return_value = query
    access = NS(
        is_global=actor_global,
        can_manage_campaigns=True,
        can_preflight_campaigns=True,
        can_manage_dispatch_config=True,
        can_send_campaigns=True,
    )
    return sess, access


def test_queues_with_original_governed_service(monkeypatch, authorized_env):
    app = Flask(__name__)
    for name in svc.DISPATCH_FLAGS:
        app.config[name] = True
    sess, access = _session()
    monkeypatch.setattr(svc.db, "session", sess)
    monkeypatch.setattr(svc, "resolve_marketing_access", lambda actor: access)
    enqueue = Mock(return_value={"job_id": 17, "status": "QUEUED"})
    monkeypatch.setattr(svc, "enqueue_cobranza_send", enqueue)
    with app.app_context():
        result = svc.queue_auto_pilot(
            day=date(2026, 11, 12), campaign_id=95,
            settings=svc.auto_pilot_config(date(2026, 11, 12)),
        )
    assert result["status"] == "QUEUED"
    assert enqueue.call_args.kwargs == {
        "campaign_id": 95, "actor_user_id": 47,
        "allowed_sucursal_keys": None, "session": sess,
    }


@pytest.mark.parametrize("recipients,pilot,actor_global,flags_on", [
    (31, "VILLAS_DEL_REY", True, True),
    (0, "VILLAS_DEL_REY", True, True),
    (21, "VILLA_VERDE", True, True),
    (21, "VILLAS_DEL_REY", False, True),
    (21, "VILLAS_DEL_REY", True, False),
])
def test_fail_closed_never_enqueues(
    monkeypatch, authorized_env, recipients, pilot, actor_global, flags_on
):
    app = Flask(__name__)
    for name in svc.DISPATCH_FLAGS:
        app.config[name] = flags_on
    sess, access = _session(recipients, pilot, actor_global)
    monkeypatch.setattr(svc.db, "session", sess)
    monkeypatch.setattr(svc, "resolve_marketing_access", lambda actor: access)
    enqueue = Mock(side_effect=AssertionError("No provider dispatch!"))
    monkeypatch.setattr(svc, "enqueue_cobranza_send", enqueue)
    with app.app_context(), pytest.raises(svc.AutoPilotBlocked):
        svc.queue_auto_pilot(
            day=date(2026, 11, 12), campaign_id=95,
            settings=svc.auto_pilot_config(date(2026, 11, 12)),
        )
    enqueue.assert_not_called()


def test_other_date_cannot_dispatch(monkeypatch, authorized_env):
    app = Flask(__name__)
    with app.app_context(), pytest.raises(svc.AutoPilotBlocked):
        svc.queue_auto_pilot(
            day=date(2026, 11, 13), campaign_id=95,
            settings=svc.auto_pilot_config(date(2026, 11, 12)),
        )


def test_blocked_pilot_remains_visible_without_reenqueuing(monkeypatch):
    campaign = NS(audience_definition_json={"source_metadata": {
        "auto_pilot_date": "2026-11-12", "pilot_branch_key": "VILLAS_DEL_REY",
    }})
    session = Mock()
    session.get.return_value = campaign
    monkeypatch.setattr(svc.db, "session", session)
    svc.mark_auto_pilot_blocked(95)
    assert campaign.audience_definition_json["source_metadata"]["auto_pilot_blocked"] is True
    session.commit.assert_called_once()
