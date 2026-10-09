"""Offline characterization of the guarded M2 partial continuation (no HTTP)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_v2_partial_resume_service as resume
from app.services.marketing_campaign_v2_preflight_service import (
    CampaignV2DispatchBatchPlan,
    CampaignV2DispatchRecipientPlan,
    build_provider_campaign_idempotency_key,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderCreateResult,
    CampaignProviderDeterministicError,
)
from app.services.marketing_campaign_v2_submit_service import (
    MarketingCampaignV2SubmitPreconditionError,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)

FP = "3" * 64


def _setup(monkeypatch):
    batches = tuple(
        CampaignV2DispatchBatchPlan(
            sucursal_id=index,
            sucursal_canon=name,
            track_label=name,
            channel_binding_id=100 + index,
            provider_channel_id=f"channel-{index}",
            template_id=1,
            template_name="invita_y_gana_4800",
            recipients=(CampaignV2DispatchRecipientPlan(
                recipient_id=index,
                phone_mx10=f"686100000{index}",
                variables=(),
            ),),
            blocked_reasons=(),
            file_url="https://example.com/image.png",
        )
        for index, name in enumerate(("A", "B", "C"), start=1)
    )
    plan = NS(
        ready=True,
        mode="IMMEDIATE",
        dispatch_fingerprint=FP,
        batches=batches,
        provider="IVENTAS",
        campaign_id=8,
        campaign_name="Socios activos/venta nueva invita y gana",
        schedule=NS(provider_send_at=None),
    )
    rows = []
    for index, batch in enumerate(batches, start=1):
        if batch.sucursal_canon == "A":
            status, provider_id, error, ref = "SUBMITTED", "external-a", None, None
        elif batch.sucursal_canon == "B":
            status, provider_id, error, ref = "PROVIDER_ERROR", None, "TEMPLATE_NOT_FOUND", "support-b"
        else:
            status, provider_id, error, ref = "READY", None, None, None
        request = build_campaign_v2_provider_dispatch_batch(plan=plan, batch=batch)
        rows.append(NS(
            id=index + 100,
            campaign_v2_id=8,
            provider="IVENTAS",
            dispatch_fingerprint=FP,
            sucursal_id=index,
            sucursal_canon=batch.sucursal_canon,
            channel_binding_id=100 + index,
            provider_channel_id=f"channel-{index}",
            template_id=1,
            template_name="invita_y_gana_4800",
            recipient_count=1,
            idempotency_key=build_provider_campaign_idempotency_key(
                campaign_v2_id=8, batch=batch, dispatch_fingerprint=FP
            ),
            request_snapshot_json=serialize_campaign_v2_provider_request_snapshot(request),
            status=status,
            provider_campaign_id=provider_id,
            error_code=error,
            support_ref=ref,
            submit_started_at=None,
            submitted_at=datetime.now(timezone.utc) if status == "SUBMITTED" else None,
        ))

    monkeypatch.setattr(resume, "build_campaign_v2_preflight", lambda **_kw: plan)
    monkeypatch.setattr(resume, "_load_campaign_rows", lambda **_kw: rows)
    expected = dict(
        campaign_id=8,
        template_id=1,
        expected_fingerprint=FP,
        expected_submitted={"A": (1, "external-a")},
        expected_failed={"B": (1, "TEMPLATE_NOT_FOUND", "support-b")},
        expected_ready={"C": 1},
        session=object(),
    )
    return rows, plan, expected


def test_review_accepts_only_the_original_ready_child(monkeypatch):
    rows, _, expected = _setup(monkeypatch)
    review = resume.review_partial_resume(**expected)
    assert [(child.batch.sucursal_canon, child.child_id) for child in review.ready_children] == [("C", 103)]
    assert [r.status for r in rows] == ["SUBMITTED", "PROVIDER_ERROR", "READY"]


@pytest.mark.parametrize("mutation", [
    lambda rows, plan, expected: setattr(rows[0], "provider_campaign_id", "changed"),
    lambda rows, plan, expected: setattr(rows[0], "status", "READY"),
    lambda rows, plan, expected: setattr(rows[1], "error_code", "DIFFERENT_ERROR"),
    lambda rows, plan, expected: setattr(rows[1], "support_ref", "changed"),
    lambda rows, plan, expected: setattr(rows[2], "status", "SUBMITTED"),
    lambda rows, plan, expected: setattr(rows[2], "submit_started_at", datetime.now(timezone.utc)),
    lambda rows, plan, expected: setattr(rows[2], "recipient_count", 2),
    lambda rows, plan, expected: setattr(rows[2], "request_snapshot_json", {}),
    lambda rows, plan, expected: setattr(rows[2], "idempotency_key", "wrong"),
    lambda rows, plan, expected: setattr(rows[2], "channel_binding_id", 1),
    lambda rows, plan, expected: setattr(plan, "dispatch_fingerprint", "changed"),
    lambda rows, plan, expected: setattr(plan, "ready", False),
    lambda rows, plan, expected: rows.append(rows[0]),
    lambda rows, plan, expected: expected["expected_ready"].update({"NOT_IN_PLAN": 1}),
])
def test_review_fails_closed_on_drift(monkeypatch, mutation):
    rows, plan, expected = _setup(monkeypatch)
    mutation(rows, plan, expected)
    with pytest.raises(MarketingCampaignV2SubmitPreconditionError):
        resume.review_partial_resume(**expected)


def test_continuation_sends_ready_only(monkeypatch):
    rows, _, expected = _setup(monkeypatch)
    review = resume.review_partial_resume(**expected)
    transitioned = []
    persisted = []
    monkeypatch.setattr(resume, "_transition_ready_to_submitting", lambda **kw: transitioned.append(kw["row_id"]))
    monkeypatch.setattr(resume, "_persist_provider_success", lambda **kw: persisted.append(kw["row_id"]))
    monkeypatch.setattr(resume, "_log_transition", lambda **_kw: None)

    class Provider:
        calls = []
        def create_campaign(self, dispatch):
            self.calls.append(dispatch.provider_channel_id)
            return CampaignProviderCreateResult(
                provider_campaign_id="external-c", deduplicated=False, http_status=200,
                response_metadata={},
            )

    provider = Provider()
    results = resume.continue_ready_children(
        review=review, actor_user_id=7, provider=provider, send_enabled=True,
        session=object(),
    )
    assert results == [("C", "SUBMITTED", "external-c")]
    assert provider.calls == ["channel-3"]
    assert transitioned == [103]
    assert persisted == [103]
    assert [row.status for row in rows] == ["SUBMITTED", "PROVIDER_ERROR", "READY"]


def test_continuation_kill_switch_never_calls_provider(monkeypatch):
    _, _, expected = _setup(monkeypatch)
    review = resume.review_partial_resume(**expected)

    class NeverSend:
        def create_campaign(self, _batch):
            pytest.fail("provider must never be called")
    with pytest.raises(MarketingCampaignV2SubmitPreconditionError):
        resume.continue_ready_children(
            review=review, actor_user_id=7, provider=NeverSend(),
            send_enabled=False, session=object(),
        )


def test_deterministic_error_stops_sequence(monkeypatch):
    _, _, expected = _setup(monkeypatch)
    review = resume.review_partial_resume(**expected)
    failure = []
    monkeypatch.setattr(resume, "_transition_ready_to_submitting", lambda **_kw: None)
    monkeypatch.setattr(resume, "_persist_provider_failure", lambda **kw: failure.append(kw))
    monkeypatch.setattr(resume, "_log_transition", lambda **_kw: None)

    class Provider:
        def create_campaign(self, _dispatch):
            raise CampaignProviderDeterministicError(
                code="TEMPLATE_NOT_FOUND", http_status=404, support_ref="new-support"
            )
    results = resume.continue_ready_children(
        review=review, actor_user_id=7, provider=Provider(),
        send_enabled=True, session=object(),
    )
    assert results == [("C", "PROVIDER_ERROR", "TEMPLATE_NOT_FOUND")]
    assert len(failure) == 1
    assert failure[0]["status"] == "PROVIDER_ERROR"
    assert failure[0]["support_ref"] == "new-support"


def test_ambiguous_error_stops_without_retry(monkeypatch):
    from app.services.marketing_campaign_v2_provider import CampaignProviderAmbiguousError

    _, _, expected = _setup(monkeypatch)
    review = resume.review_partial_resume(**expected)
    review = resume.PartialResumeReview(
        plan=review.plan,
        # A second pending child must not be attempted after the first ambiguity.
        ready_children=(
            review.ready_children[0],
            resume.ReadyChild(batch=review.ready_children[0].batch, child_id=104),
        ),
    )
    sent = []
    failures = []
    monkeypatch.setattr(resume, "_transition_ready_to_submitting", lambda **_kw: None)
    monkeypatch.setattr(resume, "_persist_provider_failure", lambda **kw: failures.append(kw))
    monkeypatch.setattr(resume, "_log_transition", lambda **_kw: None)

    class Provider:
        def create_campaign(self, batch):
            sent.append(batch.provider_channel_id)
            raise CampaignProviderAmbiguousError(
                code="HTTP_503", http_status=503, support_ref="external-ambiguous"
            )

    outcomes = resume.continue_ready_children(
        review=review, actor_user_id=7, provider=Provider(),
        send_enabled=True, session=object(),
    )
    assert sent == ["channel-3"]
    assert outcomes == [("C", "RECONCILIATION_REQUIRED", "HTTP_503")]
    assert [failure["row_id"] for failure in failures] == [103]


def test_script_refuses_real_send_when_process_switch_is_off(monkeypatch):
    import importlib.util
    import sys
    from contextlib import nullcontext
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "resume_campaign8_pending.py"
    spec = importlib.util.spec_from_file_location("campaign8_resume_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "create_app", lambda: NS(
        app_context=lambda: nullcontext(),
        config={"CAMPAIGN_V2_PROVIDER_SEND_ENABLED": False},
    ))
    monkeypatch.setattr(module.UserORM, "get_by_username", lambda username: NS(id=7))
    monkeypatch.setattr(module, "resolve_marketing_access", lambda actor: NS(
        is_global=True, can_send_campaigns=True,
    ))
    monkeypatch.setattr(module, "db", NS(session=NS(remove=lambda: None)))
    monkeypatch.setattr(sys, "argv", ["resume_campaign8_pending.py", "--apply"])
    monkeypatch.setattr(module, "review_partial_resume",
                        lambda **_kw: pytest.fail("must not review or send"))
    with pytest.raises(RuntimeError, match="kill switch mismatch"):
        module.main()


def test_manifest_is_disjoint_and_exact():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "resume_campaign8_pending.py"
    spec = importlib.util.spec_from_file_location("campaign8_resume_manifest", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = list(module.SUBMITTED) + list(module.FAILED_SKIPPED) + list(module.READY)
    assert len(names) == len(set(names)) == 26
    assert len(module.SUBMITTED) == 11
    assert sum(count for count, _ in module.SUBMITTED.values()) == 5850
    assert module.FAILED_SKIPPED == {
        "PASEO_LA_PAZ": (170, "TEMPLATE_NOT_FOUND", "bc-mv09582n-ly0gq0")
    }
    assert len(module.READY) == 14
    assert sum(module.READY.values()) == 7979
    assert 5850 + 170 + 7979 == 13999
