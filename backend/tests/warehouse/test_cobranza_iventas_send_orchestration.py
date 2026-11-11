"""One-click cobranza pilot: no provider network; synthetic one-branch jobs only."""
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from app.models.marketing import (
    MarketingCampaignV2DispatchApprovalORM as Approval,
    MarketingCampaignV2GovernedExecutionORM as Execution,
    MarketingCampaignV2ProviderCampaignORM as Child,
)
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as Job,
)
from app.services import marketing_campaign_v2_cobranza_send_service as svc


def _session(*, approval=None, execution=None, job=None):
    session = Mock()
    campaign = NS(
        source="EXCEL_IMPORT",
        name="COBRANZA RECURRENTE RECHAZADOS - 2026-11-10",
        audience_definition_json={"source_metadata": {
            "automation_job": "cobranza_recurrente_rechazados",
            "business_date": "2026-11-10",
            "template_id_at_freeze": 3,
        }},
    )
    session.get.return_value = campaign

    def query(model):
        q = Mock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = approval if model is Approval else None
        q.one_or_none.return_value = (
            execution if model is Execution else
            job if model is Job else None
        )
        q.all.return_value = [NS(id=77, sucursal_canon="AZAHARES_CUL")] if model is Child else []
        return q

    session.query.side_effect = query
    return session


def _plan(monkeypatch):
    batch = NS(
        sucursal_canon="AZAHARES_CUL",
        provider_channel_id="synthetic-channel",
        recipients=(NS(phone_mx10="6861000001"), NS(phone_mx10="6861000002")),
    )
    plan = NS(
        ready=True,
        campaign_id=19,
        batches=(batch,),
        sendable_phones=("6861000001", "6861000002"),
        dispatch_fingerprint="a" * 64,
    )
    monkeypatch.setattr(svc, "build_campaign_v2_preflight", Mock(return_value=plan))
    return plan


def test_one_click_queues_only_one_branch_without_provider_http(monkeypatch):
    _plan(monkeypatch)
    approved = Mock(return_value={
        "approval_id": 101, "manifest": {"AZAHARES_CUL": {"planned_status": "READY"}},
    })
    materialized = Mock()
    authorized = Mock(return_value={"execution_id": 201})
    enqueued = Mock(return_value=({"job_id": 301, "status": "QUEUED"}, True))
    monkeypatch.setattr(svc, "approve_dispatch_reservation", approved)
    monkeypatch.setattr(svc, "materialize_approved_manifest", materialized)
    monkeypatch.setattr(svc, "authorize_governed_dispatch", authorized)
    monkeypatch.setattr(svc, "enqueue_background_job", enqueued)

    outcome = svc.enqueue_cobranza_send(
        campaign_id=19, actor_user_id=47,
        allowed_sucursal_keys=None, session=_session(),
    )
    assert outcome == {
        "campaign_id": 19, "status": "QUEUED", "job_id": 301,
        "recipient_count": 2, "branch_count": 1,
    }
    assert approved.call_count == 1
    assert materialized.call_count == 1
    assert authorized.call_count == 1
    assert enqueued.call_count == 1
    kwargs = enqueued.call_args.kwargs
    assert kwargs["expected_pending_child_ids"] == [77]
    assert kwargs["confirmation"] == "ENVIAR PENDIENTES 1"
    assert kwargs["confirmed"] is True
    assert kwargs["actor_user_id"] == 47


def test_second_click_returns_existing_job_without_enqueue(monkeypatch):
    _plan(monkeypatch)
    manifest = {"AZAHARES_CUL": {"planned_status": "READY"}}
    approval = NS(
        id=101, template_id=3, dispatch_fingerprint="a" * 64,
        manifest_json=manifest,
    )
    execution = NS(
        id=201, approval_id=101, manifest_digest=svc.manifest_digest(manifest),
        status="AUTHORIZED",
    )
    job = NS(id=301, status="QUEUED")
    blocked = Mock(side_effect=AssertionError("never create another job"))
    for function in (
        "approve_dispatch_reservation", "materialize_approved_manifest",
        "authorize_governed_dispatch", "enqueue_background_job",
    ):
        monkeypatch.setattr(svc, function, blocked)

    outcome = svc.enqueue_cobranza_send(
        campaign_id=19, actor_user_id=47,
        allowed_sucursal_keys=None,
        session=_session(approval=approval, execution=execution, job=job),
    )
    assert outcome["job_id"] == 301
    assert outcome["status"] == "QUEUED"
    assert blocked.call_count == 0


def test_manual_campaign_cannot_use_cobranza_one_click(monkeypatch):
    session = _session()
    session.get.return_value.source = "QA_MANUAL"
    preflight = Mock(side_effect=AssertionError("must not enter preflight"))
    monkeypatch.setattr(svc, "build_campaign_v2_preflight", preflight)
    with pytest.raises(svc.CobranzaSendConflict, match="automática"):
        svc.enqueue_cobranza_send(
            campaign_id=19, actor_user_id=47,
            allowed_sucursal_keys=None, session=session,
        )
    preflight.assert_not_called()
