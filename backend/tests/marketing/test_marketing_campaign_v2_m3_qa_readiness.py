"""M3 fail-closed offline operator review tests; no provider, DB or HTTP."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m3_qa_readiness_gate import evaluate_m3_qa_readiness


def _valid_case():
    sha = "a" * 64
    preflight = {
        "campaign_id": 77,
        "campaign_name": "CI FAKE ONLY",
        "campaign_purpose": "REACTIVATION",
        "provider": "IVENTAS",
        "mode": "IMMEDIATE",
        "schedule": None,
        "frozen_count": 5,
        "suppressed": {"blacklist": 1},
        "sendable_count": 4,
        "template": {"id": 10, "template_name": "qa"},
        "batches": [
            {
                "sucursal_id": 1, "sucursal_canon": "BRANCH A",
                "provider_channel_id": "channel-a", "template_id": 10,
                "recipient_count": 2, "ready": True, "blocked_reasons": [],
            },
            {
                "sucursal_id": 2, "sucursal_canon": "BRANCH B",
                "provider_channel_id": "channel-b", "template_id": 10,
                "recipient_count": 2, "ready": True, "blocked_reasons": [],
            },
        ],
        "blocked": {
            "missing_branch": 0,
            "missing_channel": 0,
            "missing_required_variable": 0,
            "invalid_phone": 0,
            "template_channel_mismatch": 0,
        },
        "provider_campaign_count": 2,
        "dispatch_fingerprint_version": "campaign-v2-dispatch-v3",
        "dispatch_fingerprint": sha,
        "ready": True,
    }
    manifest = {
        "expected_campaign_id": 77,
        "expected_mode": "IMMEDIATE",
        "expected_sendable_count": 4,
        "max_qa_recipients": 4,
        "expected_provider_channels": {
            "BRANCH A": "channel-a", "BRANCH B": "channel-b",
        },
        "expected_template_id": 10,
        "reviewed_dispatch_fingerprint": sha,
        "frozen_export_sha256": "b" * 64,
        "sendable_export_sha256": "c" * 64,
        "frozen_export_reviewed": True,
        "sendable_export_reviewed": True,
        "qa_only_recipients_verified": True,
        "template_content_reviewed": True,
        "channel_ownership_reviewed": True,
        "fingerprint_reviewed": True,
    }
    return preflight, manifest


def test_small_reviewed_two_branch_qa_is_only_ready_for_human_approval():
    preflight, manifest = _valid_case()
    result = evaluate_m3_qa_readiness(preflight, manifest)
    assert result == {
        "status": "READY_FOR_HUMAN_APPROVAL",
        "errors": [],
        "send_authorized": False,
        "campaign_id": 77,
        "batch_count": 2,
        "sendable_count": 4,
    }


@pytest.mark.parametrize(
    ("edit", "error"),
    [
        (lambda p, m: p.update(ready=False), "PREFLIGHT_NOT_READY"),
        (lambda p, m: p.update(campaign_id=78), "CAMPAIGN_ID_MISMATCH"),
        (lambda p, m: p.update(provider="UNRECOGNIZED"), "PROVIDER_MISMATCH"),
        (lambda p, m: p["blocked"].update(missing_channel=1), "PREFLIGHT_HAS_BLOCKERS"),
        (lambda p, m: p["batches"][0].update(provider_channel_id="other"), "CHANNEL_MISMATCH"),
        (lambda p, m: p["batches"][0].update(recipient_count=3), "BATCH_TOTAL_MISMATCH"),
        (lambda p, m: p["batches"][0].update(sucursal_canon="BRANCH B"), "BRANCH_MISMATCH"),
        (lambda p, m: p["batches"][0].update(template_id=99), "TEMPLATE_MISMATCH"),
        (lambda p, m: p["batches"][0].update(blocked_reasons=["missing_channel"]), "BATCH_HAS_BLOCKERS"),
        (lambda p, m: p.update(sendable_count=20), "AUDIENCE_COUNT_MISMATCH"),
        (lambda p, m: m.update(max_qa_recipients=3), "AUDIENCE_COUNT_MISMATCH"),
        (lambda p, m: p["suppressed"].update(blacklist=2), "SUPPRESSION_COUNT_INCONSISTENT"),
        (lambda p, m: p.update(dispatch_fingerprint="d" * 64), "FINGERPRINT_UNCONFIRMED"),
        (lambda p, m: m.update(frozen_export_sha256=None), "EXPORT_HASH_MISSING"),
        (lambda p, m: m.update(sendable_export_reviewed=False), "MANUAL_REVIEW_MISSING"),
        (lambda p, m: m.update(qa_only_recipients_verified=False), "MANUAL_REVIEW_MISSING"),
        (lambda p, m: p.update(provider_campaign_count=1), "BATCH_COUNT_MISMATCH"),
        (lambda p, m: p["batches"][1].update(ready=False), "BATCH_HAS_BLOCKERS"),
        (lambda p, m: p.update(mode="SCHEDULED"), "DISPATCH_MODE_MISMATCH"),
        (lambda p, m: p.update(schedule={"timezone": "America/Tijuana"}), "UNEXPECTED_SCHEDULE"),
    ],
)
def test_qa_gate_fails_closed_on_integrity_or_manual_review_errors(edit, error):
    preflight, manifest = _valid_case()
    edit(preflight, manifest)
    result = evaluate_m3_qa_readiness(preflight, manifest)
    assert result["status"] == "BLOCKED"
    assert result["send_authorized"] is False
    assert error in result["errors"]


def test_scheduled_requires_exact_local_time_and_explicit_timezone():
    preflight, manifest = _valid_case()
    preflight["mode"] = manifest["expected_mode"] = "SCHEDULED"
    preflight["schedule"] = {
        "timezone": "America/Tijuana",
        "local_datetime": "2026-10-21T08:20:00",
        "scheduled_for_utc": "2026-10-21T15:20:00+00:00",
        "provider_send_at": "2026-10-21T15:20:00.000Z",
    }
    manifest.update(
        expected_timezone="America/Tijuana",
        expected_local_datetime="2026-10-21T08:20:00",
    )
    assert evaluate_m3_qa_readiness(preflight, manifest)["status"] == "READY_FOR_HUMAN_APPROVAL"
    manifest["expected_timezone"] = "America/Mexico_City"
    blocked = evaluate_m3_qa_readiness(preflight, manifest)
    assert "SCHEDULE_MISMATCH" in blocked["errors"]


def test_no_pii_is_ever_echoed_back_from_extra_fields():
    preflight, manifest = _valid_case()
    preflight["phone_mx10"] = "6869999999"
    manifest["authorization"] = "token_sensitive_value"
    output = evaluate_m3_qa_readiness(preflight, manifest)
    assert "6869999999" not in json.dumps(output)
    assert "token_sensitive_value" not in json.dumps(output)
    assert output["send_authorized"] is False


def test_malformed_input_and_cli_fail_closed(tmp_path):
    preflight, manifest = _valid_case()
    payload = tmp_path / "review.json"
    payload.write_text(json.dumps({"preflight": preflight, "manifest": manifest}), encoding="utf-8")
    script = Path(__file__).with_name("m3_qa_readiness_gate.py")
    outcome = subprocess.run(
        [sys.executable, str(script), "--input", str(payload)],
        text=True, capture_output=True, timeout=10,
    )
    assert outcome.returncode == 0
    assert json.loads(outcome.stdout)["status"] == "READY_FOR_HUMAN_APPROVAL"
    assert json.loads(outcome.stdout)["send_authorized"] is False

    payload.write_text('{"preflight":', encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, str(script), "--input", str(payload)],
        text=True, capture_output=True, timeout=10,
    )
    assert failed.returncode == 2
    assert json.loads(failed.stdout)["errors"] == ["INVALID_INPUT"]
