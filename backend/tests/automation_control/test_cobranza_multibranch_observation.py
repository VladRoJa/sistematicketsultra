"""Synthetic read-only monitoring of isolated cobranzas, no provider traffic."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from app.services.automation_control import cobranza_multibranch_observation_service as svc
from app.models.warehouse import WarehouseAuditLogORM as Audit
from app.models.marketing_campaign_v2_background_job import MarketingCampaignV2BackgroundJobORM as Job
from app.models.marketing import MarketingCampaignV2ProviderCampaignORM as Batch

UTC = timezone.utc
STAMP = datetime(2026, 11, 13, 17, 30, tzinfo=UTC)


def _audit(id, branch, status, campaign_id=None, expected=2, reason=None):
    return NS(id=id, created_at=STAMP, details={
        "business_date": "2026-11-13", "branch": branch,
        "status": status, "campaign_id": campaign_id,
        "expected_branches": expected, "reason": reason,
    })


def _install(monkeypatch, audits, jobs, batches):
    session = MagicMock()
    def query(model):
        query = MagicMock()
        if model is Audit:
            query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = audits
        elif model is Job:
            query.filter.return_value.order_by.return_value.all.return_value = jobs
        elif model is Batch:
            query.filter.return_value.all.return_value = batches
        return query
    session.query.side_effect = query
    monkeypatch.setattr(svc.db, "session", session)
    return session


def test_all_submitted_is_accepted_only_with_complete_expected_roster(monkeypatch):
    _install(
        monkeypatch,
        [_audit(8, "ALFA", "QUEUED", 101), _audit(7, "BETA", "QUEUED", 102)],
        [
            NS(id=20, campaign_v2_id=101, status="COMPLETED", stop_reason_code=None, finished_at=STAMP),
            NS(id=21, campaign_v2_id=102, status="COMPLETED", stop_reason_code=None, finished_at=STAMP),
        ],
        [
            NS(campaign_v2_id=101, status="SUBMITTED", recipient_count=8),
            NS(campaign_v2_id=102, status="SUBMITTED", recipient_count=9),
        ],
    )
    result = svc._read_day("2026-11-13")
    assert result["status_raw"] == "COMPLETED"
    assert result["counts"]["branches_submitted"] == 2
    assert result["counts"]["recipients_submitted"] == 17
    assert result["error_available"] is False
    assert result["evidence_type"] == "COBRANZA_BRANCH_AUDIT_AND_PROVIDER_JOBS"
    assert all(b["status"] == "SUBMITTED" for b in result["branches"])


def test_one_skipped_never_claims_all_delivered_or_completed(monkeypatch):
    _install(
        monkeypatch,
        [_audit(8, "ALFA", "QUEUED", 101),
         _audit(9, "BETA", "SKIPPED", reason="RECIPIENT_LIMIT")],
        [NS(id=20, campaign_v2_id=101, status="COMPLETED", stop_reason_code=None, finished_at=STAMP)],
        [NS(campaign_v2_id=101, status="SUBMITTED", recipient_count=8)],
    )
    result = svc._read_day("2026-11-13")
    assert result["status_raw"] == "PARTIAL"
    assert result["counts"]["branches_submitted"] == 1
    assert result["counts"]["branches_skipped"] == 1
    assert result["error_available"] is True
    diagnostic = svc._diagnostic(result)
    assert diagnostic["branch_failures"] == [
        {"branch_code": "BETA", "error_type": "RECIPIENT_LIMIT"}
    ]
    assert "no entrega" in diagnostic["sanitized_message"]


def test_queued_is_not_accepted(monkeypatch):
    _install(
        monkeypatch,
        [_audit(8, "ALFA", "QUEUED", 101), _audit(9, "BETA", "QUEUED", 102)],
        [NS(id=20, campaign_v2_id=101, status="QUEUED", stop_reason_code=None),
         NS(id=21, campaign_v2_id=102, status="QUEUED", stop_reason_code=None)],
        [NS(campaign_v2_id=101, status="READY", recipient_count=8),
         NS(campaign_v2_id=102, status="READY", recipient_count=9)],
    )
    result = svc._read_day("2026-11-13")
    assert result["status_raw"] == "RUNNING"
    assert result["counts"]["branches_pending"] == 2
    assert result["counts"]["branches_submitted"] == 0
    assert result["finished_at_utc"] is None


def test_uncertain_job_is_review_not_success(monkeypatch):
    _install(
        monkeypatch,
        [_audit(8, "ALFA", "QUEUED", 101), _audit(9, "BETA", "QUEUED", 102)],
        [NS(id=20, campaign_v2_id=101, status="REVIEW_REQUIRED",
            stop_reason_code="RECONCILIATION_REQUIRED", finished_at=None),
         NS(id=21, campaign_v2_id=102, status="COMPLETED",
            stop_reason_code=None, finished_at=STAMP)],
        [NS(campaign_v2_id=101, status="RECONCILIATION_REQUIRED", recipient_count=8),
         NS(campaign_v2_id=102, status="SUBMITTED", recipient_count=9)],
    )
    result = svc._read_day("2026-11-13")
    assert result["status_raw"] == "PARTIAL"
    assert result["counts"]["branches_review"] == 1
    assert result["counts"]["branches_submitted"] == 1
    assert result["branches"][0]["reason_code"] == "RECONCILIATION_REQUIRED"


def test_missing_expected_branch_is_never_green(monkeypatch):
    _install(
        monkeypatch,
        [_audit(8, "ALFA", "QUEUED", 101, expected=2)],
        [NS(id=20, campaign_v2_id=101, status="COMPLETED", stop_reason_code=None, finished_at=STAMP)],
        [NS(campaign_v2_id=101, status="SUBMITTED", recipient_count=8)],
    )
    result = svc._read_day("2026-11-13")
    assert result["status_raw"] == "PARTIAL"
    assert result["counts"]["branches_missing"] == 1


def test_last_error_does_not_mix_other_days_or_provider_payloads(monkeypatch):
    bad = {
        "run_id": 9, "business_date": "2026-11-12", "status_raw": "PARTIAL",
        "started_at_utc": None, "finished_at_utc": None,
        "counts": {"branches_expected": 2, "branches_observed": 2,
                   "branches_submitted": 1, "branches_pending": 0,
                   "branches_skipped": 1, "branches_review": 0, "branches_missing": 0},
        "branches": [
            {"branch": "BETA", "status": "SKIPPED", "reason_code": "RECIPIENT_LIMIT"},
        ],
        "evidence_truncated": False,
    }
    with patch.object(svc, "_days", return_value=(["2026-11-13", "2026-11-12"], False)), patch.object(
        svc, "_read_day", side_effect=lambda day: {**bad, "status_raw": "COMPLETED"} if day == "2026-11-13" else bad,
    ):
        diag = svc.multibranch_last_error()
    assert diag["business_date"] == "2026-11-12"
    assert diag["branch_failures"][0]["branch_code"] == "BETA"
    assert not any("686" in str(v) for v in diag.values())


def test_branch_reason_code_cannot_echo_provider_text():
    result = svc._branch_state(
        _audit(9, "ALFA", "QUEUED", 101),
        {101: NS(status="REVIEW_REQUIRED", stop_reason_code="secret bearer XYZ")},
        {101: [NS(status="RECONCILIATION_REQUIRED", recipient_count=8)]},
    )
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["reason_code"] == "PROVIDER_OR_JOB_REVIEW"


def test_list_runs_contract_uses_only_attributed_days(monkeypatch):
    with patch.object(svc, "_days", return_value=(["2026-11-13"], False)), patch.object(
        svc, "_read_day", return_value={"run_id": 9, "status_raw": "PARTIAL"},
    ):
        result = svc.list_multibranch_runs(limit=5, offset=0)
    assert result["coverage"] == "DOMAIN_RUNS"
    assert result["rows"] == [{"run_id": 9, "status_raw": "PARTIAL"}]
    assert result["has_more"] is False
