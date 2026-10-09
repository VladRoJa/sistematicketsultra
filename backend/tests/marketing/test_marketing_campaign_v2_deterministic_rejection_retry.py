"""Campaign #8 La Paz explicit retry characterization. No network is used."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_v2_deterministic_rejection_retry as svc
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderCreateResult, CampaignProviderDeterministicError,
    CampaignProviderAmbiguousError,
)
from scripts.resume_campaign8_pending import SUBMITTED, READY, FINGERPRINT
from scripts.retry_campaign8_la_paz import ACCEPTED_COUNTS, ORIGINAL_PROVIDER_IDS


def _scenario(monkeypatch):
    names = sorted([*ACCEPTED_COUNTS, "PASEO_LA_PAZ"])
    batches, rows = [], []
    for index, name in enumerate(names, start=1):
        count = 170 if name == "PASEO_LA_PAZ" else ACCEPTED_COUNTS[name]
        batch = NS(
            sucursal_canon=name, sucursal_id=index,
            channel_binding_id=100 + index,
            provider_channel_id=f"channel-{index}",
            template_name="invita_y_gana_4800",
            ready=True, recipients=[NS(phone_mx10="6861000001")] * count,
        )
        child = NS(
            id=15 if name == "PASEO_LA_PAZ" else index + 100,
            campaign_v2_id=8, sucursal_canon=name, sucursal_id=index,
            provider="IVENTAS", dispatch_fingerprint=FINGERPRINT,
            channel_binding_id=100 + index, provider_channel_id=f"channel-{index}",
            template_id=1, template_name="invita_y_gana_4800",
            recipient_count=count, idempotency_key=f"idempotency-{name}",
            request_snapshot_json={"name": name},
            status="PROVIDER_ERROR" if name == "PASEO_LA_PAZ" else "SUBMITTED",
            provider_campaign_id=(
                None if name == "PASEO_LA_PAZ"
                else ORIGINAL_PROVIDER_IDS.get(name, f"new-provider-{name}")
            ),
            error_code="TEMPLATE_NOT_FOUND" if name == "PASEO_LA_PAZ" else None,
            support_ref="bc-mv09582n-ly0gq0" if name == "PASEO_LA_PAZ" else None,
            submitted_at=datetime.now(timezone.utc) if name != "PASEO_LA_PAZ" else None,
            retry_attempt_count=0, retry_history_json=[],
            reconciliation_resolution=None,
            provider_response_json={"http_status": 404},
        )
        batches.append(batch)
        rows.append(child)
    plan = NS(
        ready=True, mode="IMMEDIATE", provider="IVENTAS",
        campaign_id=8,
        campaign_name="Socios activos/venta nueva invita y gana",
        campaign_purpose="NEW_SALE", frozen_count=14002,
        sendable_phones=tuple(str(i) for i in range(13999)),
        blacklisted_phones=(), dispatch_fingerprint=FINGERPRINT,
        campaign_excluded_recipient_ids=(59510, 59859, 60120),
        batches=tuple(batches),
    )
    monkeypatch.setattr(svc, "build_campaign_v2_preflight", lambda **kw: plan)
    monkeypatch.setattr(svc, "_load_campaign_rows", lambda **kw: rows)
    monkeypatch.setattr(svc, "build_provider_campaign_idempotency_key",
                        lambda **kw: f"idempotency-{kw['batch'].sucursal_canon}")
    monkeypatch.setattr(svc, "build_campaign_v2_provider_dispatch_batch",
                        lambda **kw: NS(provider_channel_id=kw["batch"].provider_channel_id,
                                        name=kw["batch"].sucursal_canon))
    monkeypatch.setattr(svc, "serialize_campaign_v2_provider_request_snapshot",
                        lambda dispatch: {"name": dispatch.name})
    kwargs = dict(
        fingerprint=FINGERPRINT, accepted_counts=ACCEPTED_COUNTS,
        original_provider_ids=ORIGINAL_PROVIDER_IDS, session=object(),
    )
    return rows, plan, kwargs


def test_review_exact_25_accepted_and_one_deterministic_failure(monkeypatch):
    rows, _, kw = _scenario(monkeypatch)
    review = svc.review_campaign8_la_paz_retry(**kw)
    assert review.child_id == 15
    assert review.batch.sucursal_canon == "PASEO_LA_PAZ"
    assert sum(row.status == "SUBMITTED" for row in rows) == 25


@pytest.mark.parametrize("mutate", [
    lambda rows, p: setattr(rows[0], "status", "READY"),
    lambda rows, p: setattr(rows[0], "provider_campaign_id", None),
    lambda rows, p: setattr(rows[0], "request_snapshot_json", {}),
    lambda rows, p: setattr(rows[0], "recipient_count", 1),
    lambda rows, p: setattr(rows[0], "idempotency_key", "changed"),
    lambda rows, p: setattr(rows[0], "template_name", "different"),
    lambda rows, p: setattr(rows[0], "provider_channel_id", "different"),
    lambda rows, p: setattr(p, "dispatch_fingerprint", "different"),
    lambda rows, p: setattr(p, "ready", False),
    lambda rows, p: setattr(rows[-1], "status", "SUBMITTING") if rows[-1].sucursal_canon == "PASEO_LA_PAZ" else setattr(next(r for r in rows if r.sucursal_canon == "PASEO_LA_PAZ"), "status", "SUBMITTING"),
    lambda rows, p: setattr(next(r for r in rows if r.sucursal_canon == "PASEO_LA_PAZ"), "retry_attempt_count", 1),
    lambda rows, p: setattr(next(r for r in rows if r.sucursal_canon == "PASEO_LA_PAZ"), "error_code", "different"),
    lambda rows, p: setattr(next(r for r in rows if r.sucursal_canon == "PASEO_LA_PAZ"), "provider_campaign_id", "external"),
])
def test_review_denies_mutated_children(monkeypatch, mutate):
    rows, plan, kw = _scenario(monkeypatch)
    mutate(rows, plan)
    with pytest.raises(svc.Campaign8DeterministicRetryError):
        svc.review_campaign8_la_paz_retry(**kw)


def test_single_attempt_audits_original_error_before_http(monkeypatch):
    rows, _, kw = _scenario(monkeypatch)
    review = svc.review_campaign8_la_paz_retry(**kw)
    paz = next(r for r in rows if r.sucursal_canon == "PASEO_LA_PAZ")
    paz.id = 15
    paz.retry_last_attempt_at = None
    paz.retry_last_by_user_id = None
    paz.updated_at = None
    paz.submit_started_at = datetime.now(timezone.utc)
    paz.submitted_by_user_id = 1
    paz.retry_next_allowed_at = None

    class Query:
        def filter(self, *_args): return self
        def with_for_update(self): return self
        def one_or_none(self): return paz

    class Session:
        commits = 0
        def query(self, _model): return Query()
        def commit(self): self.commits += 1
        def rollback(self): pytest.fail("no rollback expected")

    session = Session()
    svc._mark_la_paz_retry_started(review=review, actor_user_id=7, session=session)
    assert session.commits == 1
    assert paz.status == "SUBMITTING"
    assert paz.retry_attempt_count == 1
    assert paz.error_code is None
    evidence = paz.retry_history_json[0]["source_deterministic_rejection"]
    assert evidence["error_code"] == "TEMPLATE_NOT_FOUND"
    assert evidence["support_ref"] == "bc-mv09582n-ly0gq0"
    with pytest.raises(svc.Campaign8DeterministicRetryError):
        svc._mark_la_paz_retry_started(review=review, actor_user_id=7, session=session)


def test_real_send_requires_process_switch(monkeypatch):
    _, _, kw = _scenario(monkeypatch)
    review = svc.review_campaign8_la_paz_retry(**kw)

    class NoProvider:
        def create_campaign(self, _batch):
            pytest.fail("HTTP forbidden")
    with pytest.raises(svc.Campaign8DeterministicRetryError):
        svc.send_campaign8_la_paz_once(
            review=review, actor_user_id=7, provider=NoProvider(),
            send_enabled=False, session=object(),
        )


def test_send_exactly_one_child_and_persist_success(monkeypatch):
    _, _, kw = _scenario(monkeypatch)
    review = svc.review_campaign8_la_paz_retry(**kw)
    events = []
    monkeypatch.setattr(svc, "_mark_la_paz_retry_started", lambda **x: events.append("durable_before_http"))
    monkeypatch.setattr(svc, "_finish_retry_success", lambda **x: events.append(("saved", x["provider_campaign_id"])))

    class Provider:
        def create_campaign(self, dispatch):
            events.append(("http", dispatch.name))
            return CampaignProviderCreateResult(
                provider_campaign_id="new-la-paz-id",
                deduplicated=False, http_status=200, response_metadata={},
            )

    result = svc.send_campaign8_la_paz_once(
        review=review, actor_user_id=7,
        provider=Provider(), send_enabled=True, session=object(),
    )
    assert result == ("SUBMITTED", "new-la-paz-id")
    assert events == ["durable_before_http", ("http", "PASEO_LA_PAZ"), ("saved", "new-la-paz-id")]


@pytest.mark.parametrize("error,status", [
    (CampaignProviderDeterministicError(code="TEMPLATE_NOT_FOUND", http_status=400, support_ref="ref2"), "PROVIDER_ERROR"),
    (CampaignProviderAmbiguousError(code="HTTP_503", http_status=503, support_ref="ref3"), "RECONCILIATION_REQUIRED"),
])
def test_failed_attempt_requires_explicit_reconciliation(monkeypatch, error, status):
    _, _, kw = _scenario(monkeypatch)
    review = svc.review_campaign8_la_paz_retry(**kw)
    outcomes = []
    monkeypatch.setattr(svc, "_mark_la_paz_retry_started", lambda **_kw: None)
    monkeypatch.setattr(svc, "_finish_retry_failure", lambda **kw: outcomes.append(kw))

    class Provider:
        def create_campaign(self, _dispatch): raise error

    result = svc.send_campaign8_la_paz_once(
        review=review, actor_user_id=7, provider=Provider(),
        send_enabled=True, session=object(),
    )
    assert result == (status, error.code)
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == status
    assert outcomes[0]["attempt_number"] == 1
