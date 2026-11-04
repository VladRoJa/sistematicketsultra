"""Milestone #1214: deterministic skip, ambiguous stop, exact frozen recovery.

All provider HTTP is disabled; mocks represent durable children only.
"""
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2RecipientEvidenceORM as Evidence,
)
from app.services import marketing_campaign_v2_confirmed_rejection as safe
from app.services import marketing_campaign_v2_governed_dispatch_service as governed
from app.services import marketing_campaign_v2_background_worker_service as worker
from app.services import marketing_campaign_v2_failed_cohort_service as recovery

NOW = datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc)


def _child(id_, status, *, error=None, http=None, ref=None, provider=None):
    return NS(
        id=id_, status=status, sucursal_canon=f"BRANCH_{id_}",
        provider_campaign_id=provider,
        submitted_at=NOW if provider else None,
        submit_started_at=NOW if status != "READY" else None,
        submitted_by_user_id=47 if status != "READY" else None,
        error_code=error,
        support_ref=ref,
        provider_response_json={"http_status": http},
        reconciliation_resolution=None,
        retry_attempt_count=0,
        retry_history_json=[],
    )


def _rejection(id_=2):
    return _child(id_, "PROVIDER_ERROR", error="TEMPLATE_NOT_FOUND",
                  http=400, ref="bc-confirmed-123")


def test_only_proven_nonacceptance_is_safe_for_continuation():
    assert safe.confirmed_rejected_child(_rejection()) is True
    for status, code, http, ref in [
        ("PROVIDER_ERROR", "TEMPLATE_NOT_FOUND", 404, "bc-ref"),
        ("PROVIDER_ERROR", "TEMPLATE_NOT_FOUND", 400, None),
        ("PROVIDER_ERROR", "RATE_LIMITED", 400, "bc-ref"),
        ("PROVIDER_ERROR", "TEMPLATE_NOT_FOUND", 429, "bc-ref"),
        ("PROVIDER_ERROR", "TEMPLATE_NOT_FOUND", 503, "bc-ref"),
        ("RECONCILIATION_REQUIRED", "TRANSPORT_CONNECTIONERROR", None, None),
        ("SUBMITTING", "TEMPLATE_NOT_FOUND", 400, "bc-ref"),
    ]:
        assert not safe.confirmed_not_accepted(
            status=status, error_code=code, http_status=http, support_ref=ref,
        )
    attempt = _rejection()
    attempt.provider_campaign_id = "external"
    assert not safe.confirmed_rejected_child(attempt)


def test_proven_failed_middle_child_allows_next_ready_and_never_replays():
    ready = _child(3, "READY")
    original = _child(1, "SUBMITTED", provider="external-1")
    attempted, next_ready = governed._verified_prefix_and_suffix(
        ready=[original, _rejection(), ready],
        execution=NS(last_child_id=2),
    )
    assert [row.id for row in attempted] == [1, 2]
    assert [row.id for row in next_ready] == [3]
    first_failed, unattempted = governed._verified_prefix_and_suffix(
        ready=[_rejection(10), _child(11, "READY")],
        execution=NS(last_child_id=10),
    )
    assert [r.id for r in first_failed] == [10]
    assert [r.id for r in unattempted] == [11]


@pytest.mark.parametrize("change", [
    lambda rows, execution: setattr(rows[1], "status", "RECONCILIATION_REQUIRED"),
    lambda rows, execution: setattr(rows[1], "provider_response_json", {"http_status": 503}),
    lambda rows, execution: setattr(rows[1], "support_ref", None),
    lambda rows, execution: setattr(rows[1], "provider_campaign_id", "maybe-sent"),
    lambda rows, execution: setattr(rows[1], "submitted_at", NOW),
    lambda rows, execution: setattr(rows[2], "status", "SUBMITTED"),
    lambda rows, execution: setattr(execution, "last_child_id", 1),
])
def test_prefix_proof_blocks_ambiguous_or_out_of_order(change):
    rows = [_child(1, "SUBMITTED", provider="external-1"),
            _rejection(), _child(3, "READY")]
    execution = NS(last_child_id=2)
    change(rows, execution)
    with pytest.raises(governed.GovernedDispatchConflict):
        governed._verified_prefix_and_suffix(ready=rows, execution=execution)


def test_worker_records_rejection_without_marking_it_as_accepted(monkeypatch):
    failed = _rejection(2)
    failed.campaign_v2_id = 41
    job = NS(
        id=5, campaign_v2_id=41, current_child_id=2, last_accepted_child_id=1,
        status="RUNNING", worker_lease_until=NOW, pending_child_ids=[2, 3],
        initial_pending_count=2,
    )
    session = NS(get=lambda *_args: failed, commit=MagicMock())
    events = []
    monkeypatch.setattr(worker, "_owned", lambda *_args, **_kw: job)
    monkeypatch.setattr(worker, "_event", lambda _s, _j, kind, _at,
                        **kwargs: events.append((kind, kwargs)))
    monkeypatch.setattr(worker, "_ids", lambda _job: [2, 3])
    done = worker._rejected(session, 5, "worker", 1, 2, NOW)
    assert done is False
    assert job.last_accepted_child_id == 1
    assert job.current_child_id is None
    assert events[0][0] == "CHILD_REJECTED"
    session.commit.assert_called_once()


def test_worker_refuses_ambiguous_failure_before_progress(monkeypatch):
    failed = _rejection(2)
    failed.status = "RECONCILIATION_REQUIRED"
    failed.campaign_v2_id = 41
    job = NS(
        id=5, campaign_v2_id=41, current_child_id=2,
        status="RUNNING", pending_child_ids=[2, 3],
    )
    session = NS(get=lambda *_args: failed, commit=MagicMock())
    monkeypatch.setattr(worker, "_owned", lambda *_args, **_kw: job)
    with pytest.raises(worker.BackgroundWorkerReview, match="REJECTION_NOT_DEFINITIVE"):
        worker._rejected(session, 5, "worker", 1, 2, NOW)
    session.commit.assert_not_called()


def test_provider_snapshots_identify_exact_original_phones_without_duplicates():
    child = NS(recipient_count=2, request_snapshot_json={
        "leads": [{"phone": "526861234567"}, {"phone": "526861234568"}],
    })
    assert recovery._request_phones(child) == ("6861234567", "6861234568")
    child.request_snapshot_json["leads"][1]["phone"] = "526861234567"
    with pytest.raises(recovery.FailedCohortConflict):
        recovery._request_phones(child)


def test_failed_frozen_cohort_is_audited_idempotent_and_never_sends(monkeypatch):
    original = Campaign(
        name="Winback", purpose="REACTIVATION", source="EXPIRED_MEMBERS",
        audience_definition_json={"filters": {"allowed_sucursal_keys": ["A"]}},
    )
    row = Recipient(phone_mx10="6861234567", source="EXPIRED_MEMBERS",
                    sucursal="A", inclusion_reason="SOURCE_FROZEN")
    row.evidence_rows.append(Evidence(
        evidence_order=0, source="EXPIRED_MEMBERS",
        phone_raw="6861234567", phone_mx10="6861234567",
        sucursal="A", sucursal_key="A", evidence_json=["original"],
    ))
    review = {
        "original": original,
        "failed": [_rejection()],
        "recipients": (row,),
        "source_child_ids": [2],
        "fingerprint": "a"*64,
        "recipient_count": 1,
    }
    monkeypatch.setattr(recovery, "_evaluate", lambda **_kw: review)
    monkeypatch.setattr(recovery, "acquire_campaign_v2_contact_gate", lambda _session: None)

    class Session:
        def __init__(self):
            self.objects = []
            self.existing = None
            self.derived = None
            self.commits = 0

        def get_bind(self):
            return NS(dialect=NS(name="postgresql"))

        def query(self, _model):
            return self

        def filter(self, *_args):
            return self

        def with_for_update(self):
            return self

        def one_or_none(self):
            return self.existing

        def get(self, _model, _id):
            return self.derived

        def add(self, value):
            self.objects.append(value)
            if isinstance(value, Campaign):
                self.derived = value

        def flush(self):
            if self.derived and self.derived.id is None:
                self.derived.id = 900

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

    session = Session()
    confirmed = recovery.freeze_failed_cohort(
        source_campaign_id=41, expected_candidate_fingerprint="a"*64,
        expected_recipient_count=1, actor_user_id=47, session=session, now=NOW,
    )
    assert confirmed["created"] and confirmed["provider_requests"] == 0
    assert confirmed["derived_campaign_id"] == 900
    assert session.derived.source == recovery.FAILED_RECOVERY_SOURCE
    assert session.derived.recipients[0].phone_mx10 == row.phone_mx10
    assert session.derived.recipients[0].evidence_rows[0].evidence_json == ["original"]
    assert session.derived.audience_definition_json["failed_recovery"]["send_authorized"] is False
    first_commits = session.commits
    session.existing = NS(derived_campaign_id=900, recipient_count=1,
                          source_child_ids_json=[2])
    again = recovery.freeze_failed_cohort(
        source_campaign_id=41, expected_candidate_fingerprint="a"*64,
        expected_recipient_count=1, actor_user_id=47, session=session, now=NOW,
    )
    assert again["derived_campaign_id"] == 900
    assert again["created"] is False
    assert session.commits == first_commits


def test_worker_continues_between_two_confirmed_failures_without_replay(monkeypatch):
    sequence = [
        "SUBMITTED", "PROVIDER_ERROR", "SUBMITTED",
        "PROVIDER_ERROR", "SUBMITTED",
    ]
    ids = [11, 12, 13, 14, 15]
    job = NS(
        pending_child_ids=ids, initial_pending_count=len(ids),
        pending_children_digest=hashlib.sha256(
            json.dumps(ids, separators=(",", ":")).encode("ascii"),
        ).hexdigest(),
    )
    session = NS(rollback=MagicMock(), expire_all=MagicMock())
    provider_calls = []
    completions = []
    monkeypatch.setattr(worker, "_owned", lambda *_a, **_kw: job)
    monkeypatch.setattr(worker, "_prepare", lambda _s, _j, _w, _g, index, _c, _at: (
        {"child_id": ids[index]}, NS(),
    ))
    monkeypatch.setattr(worker, "execute_governed_child",
                        lambda **kw: provider_calls.append(kw["child_id"]) or {
                            "child_id": kw["child_id"],
                            "status": sequence[ids.index(kw["child_id"])],
                            "definitively_not_accepted": kw["child_id"] in (12, 14),
                        })
    monkeypatch.setattr(worker, "_accepted",
                        lambda _s, _j, _w, _g, id_, _at:
                        completions.append(("ACCEPTED", id_)) or id_ == 15)
    monkeypatch.setattr(worker, "_rejected",
                        lambda _s, _j, _w, _g, id_, _at:
                        completions.append(("REJECTED", id_)) or False)
    monkeypatch.setattr(worker, "_fail_closed",
                        lambda *_args: pytest.fail("confirmed rejections must not quarantine"))
    worker.process_claimed_job(
        session=session, job_id=7, worker_id="worker", generation=1,
        config={flag: True for flag in worker.FLAGS}, provider_factory=lambda: NS(),
    )
    assert provider_calls == ids
    assert completions == [
        ("ACCEPTED", 11), ("REJECTED", 12), ("ACCEPTED", 13),
        ("REJECTED", 14), ("ACCEPTED", 15),
    ]


def test_worker_stops_on_ambiguous_result_before_next_provider_call(monkeypatch):
    ids = [11, 12, 13]
    job = NS(
        pending_child_ids=ids, initial_pending_count=len(ids),
        pending_children_digest=hashlib.sha256(
            json.dumps(ids, separators=(",", ":")).encode("ascii"),
        ).hexdigest(),
    )
    session = NS(rollback=MagicMock(), expire_all=MagicMock())
    provider_calls = []
    quarantined = []
    monkeypatch.setattr(worker, "_owned", lambda *_a, **_kw: job)
    monkeypatch.setattr(worker, "_prepare", lambda _s, _j, _w, _g, index, _c, _at: (
        {"child_id": ids[index]}, NS(),
    ))
    def execute(**kw):
        provider_calls.append(kw["child_id"])
        return {
            "child_id": kw["child_id"],
            "status": "SUBMITTED" if kw["child_id"] == 11 else "RECONCILIATION_REQUIRED",
            "definitively_not_accepted": False,
        }
    monkeypatch.setattr(worker, "execute_governed_child", execute)
    monkeypatch.setattr(worker, "_accepted", lambda *_args: False)
    monkeypatch.setattr(worker, "_rejected", lambda *_args: pytest.fail(
        "ambiguous must never enter confirmed-rejected branch"
    ))
    monkeypatch.setattr(worker, "_fail_closed",
                        lambda _s, _j, _w, _g, reason: quarantined.append(reason))
    worker.process_claimed_job(
        session=session, job_id=7, worker_id="worker", generation=1,
        config={flag: True for flag in worker.FLAGS}, provider_factory=lambda: NS(),
    )
    assert provider_calls == [11, 12]
    assert quarantined == ["PROVIDER_RESULT_REVIEW_REQUIRED"]
