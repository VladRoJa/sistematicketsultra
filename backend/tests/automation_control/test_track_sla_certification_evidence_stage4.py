"""M1-F6/4: verified roster+mart+clock is evidence, never automatic green."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.automation_control.track_sla_certification_evidence_service import (
    inspect_track_base_certification_evidence,
    verify_base_publication,
)
from app.warehouse.services.track_version_roster_capture_service import roster_digest


D = date(2026, 10, 17)
LOCAL = "-07:00"
PAIRS = [("AZAHARES_CUL", 1), ("TEC_MXL", 7)]
DIGEST = roster_digest(PAIRS)
EPOCH = {
    "verified": True,
    "epoch_id": 4,
    "attested_at_utc": "2026-10-16T16:00:00+00:00",
    "sealed_at_utc": "2026-10-16T16:05:00+00:00",
    "expected_branch_count": 2,
    "roster_sha256": DIGEST,
    "branches": PAIRS,
}
NOW = datetime.fromisoformat("2026-10-18T04:00:00-07:00")
START = datetime.fromisoformat("2026-10-17T23:30:00-07:00")
FINISH = datetime.fromisoformat("2026-10-18T01:40:00-07:00")
CAPTURE = datetime.fromisoformat("2026-10-18T01:30:00-07:00")
SEAL = datetime.fromisoformat("2026-10-18T01:35:00-07:00")


def fixture_data():
    version = SimpleNamespace(
        id=44, track_date=D, version_type="base_nocturna_canonica",
        status="success", is_current=True, started_at_utc=START,
        finished_at_utc=FINISH,
    )
    snapshot = SimpleNamespace(
        version_id=44, track_date=D,
        source_kind="LIVE_TRACK_CATALOG_NON_DEMO_AT_CAPTURE",
        historical_roster_verified=False, sealed_at_utc=SEAL,
        captured_at_utc=CAPTURE,
        expected_branch_count=2, roster_sha256=DIGEST,
    )
    members = [
        SimpleNamespace(sucursal_canon=code, sucursal_id_at_capture=ident)
        for code, ident in PAIRS
    ]
    mart = [
        SimpleNamespace(
            track_daily_version_id=44, track_date=D,
            sucursal_canon=code, generation_mode="official_closed_day",
        ) for code, _ in PAIRS
    ]
    return dict(
        business_date=D, now=NOW, version=version, epoch=EPOCH,
        snapshot=snapshot, snapshot_members=members, mart_rows=mart,
    )


def test_full_coverage_with_on_time_publish_is_still_non_ui_evidence():
    result = verify_base_publication(**fixture_data())
    assert result["evidence_verified"] is True
    assert result["historical_roster_verified"] is True
    assert result["published_on_time"] is True
    assert result["sla_status"] == "UNKNOWN"
    assert result["green_activation_authorized"] is False
    assert result["reason_code"] == "BASE_ROSTER_AND_DEADLINE_EVIDENCE_COMPLETE"


def test_finished_after_due_is_not_punctual_even_if_mart_correct():
    args = fixture_data()
    args["version"].finished_at_utc = datetime.fromisoformat(
        "2026-10-18T02:35:00-07:00"
    )
    result = verify_base_publication(**args)
    assert result["evidence_verified"] is True
    assert result["published_on_time"] is False
    assert result["reason_code"] == "BASE_PUBLISHED_AFTER_DUE"
    assert result["sla_status"] == "UNKNOWN"


@pytest.mark.parametrize(("alter","reason"), [
    (lambda x: x.update(epoch={"verified": False, "reason_code": "NO_EFFECTIVE_ROSTER_ATTESTATION"}), "NO_EFFECTIVE_ROSTER_ATTESTATION"),
    (lambda x: setattr(x["version"], "is_current", False), "BASE_VERSION_NOT_CURRENT_SUCCESS"),
    (lambda x: setattr(x["version"], "status", "running"), "BASE_VERSION_NOT_CURRENT_SUCCESS"),
    (lambda x: setattr(x["version"], "track_date", date(2026, 10, 16)), "BASE_VERSION_NOT_CURRENT_SUCCESS"),
    (lambda x: setattr(x["version"], "version_type", "cierre_canonico"), "BASE_VERSION_NOT_CURRENT_SUCCESS"),
    (lambda x: setattr(x["version"], "finished_at_utc", None), "BASE_TIME_OR_ATTESTATION_UNVERIFIED"),
    (lambda x: setattr(x["version"], "finished_at_utc", datetime.fromisoformat("2026-10-18T05:00:00-07:00")), "BASE_TIME_OR_ATTESTATION_UNVERIFIED"),
    (lambda x: x["epoch"].update(attested_at_utc="2026-10-17T20:00:00+00:00"), "BASE_TIME_OR_ATTESTATION_UNVERIFIED"),
    (lambda x: x["epoch"].update(sealed_at_utc="2026-10-17T20:00:00+00:00"), "BASE_TIME_OR_ATTESTATION_UNVERIFIED"),
    (lambda x: x["epoch"].update(sealed_at_utc="2026-10-16T15:59:00+00:00"), "BASE_TIME_OR_ATTESTATION_UNVERIFIED"),
    (lambda x: x["epoch"].pop("sealed_at_utc"), "BASE_TIME_OR_ATTESTATION_UNVERIFIED"),
    (lambda x: x.update(snapshot=None), "VERSION_ROSTER_SNAPSHOT_UNVERIFIED"),
    (lambda x: setattr(x["snapshot"], "sealed_at_utc", None), "VERSION_ROSTER_SNAPSHOT_UNVERIFIED"),
    (lambda x: setattr(x["snapshot"], "roster_sha256", "a"*64), "VERSION_EFFECTIVE_ROSTER_MISMATCH"),
    (lambda x: x["snapshot_members"].pop(), "VERSION_EFFECTIVE_ROSTER_MISMATCH"),
    (lambda x: x["mart_rows"].pop(), "BASE_MART_COVERAGE_UNVERIFIED"),
    (lambda x: setattr(x["mart_rows"][0], "track_date", date(2026, 10, 16)), "BASE_MART_COVERAGE_UNVERIFIED"),
    (lambda x: setattr(x["mart_rows"][0], "generation_mode", "manual_preview"), "BASE_MART_COVERAGE_UNVERIFIED"),
])
def test_fail_closed_on_each_missing_dependency(alter, reason):
    args = fixture_data()
    args["epoch"] = dict(EPOCH)
    alter(args)
    result = verify_base_publication(**args)
    assert result["evidence_verified"] is False
    assert result["reason_code"] == reason
    assert result["historical_roster_verified"] is False
    assert result["sla_status"] == "UNKNOWN"
    assert not result["green_activation_authorized"]


def test_missing_current_base_returns_unknown_without_attestation_read():
    from unittest.mock import MagicMock
    q = MagicMock()
    q.filter.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    with patch(
        "app.services.automation_control.track_sla_certification_evidence_service.db.session.query",
        return_value=q,
    ), patch(
        "app.services.automation_control.track_sla_certification_evidence_service.read_effective_roster_for_date"
    ) as source:
        result = inspect_track_base_certification_evidence(
            business_date=D, now=NOW,
        )
    source.assert_not_called()
    assert result["evidence_verified"] is False


def test_public_sla_remains_unchanged_until_business_activation():
    import inspect
    from app.services.automation_control import (
        track_base_sla_service,
        freshness_service,
    )
    assert "inspect_track_base_certification_evidence" not in inspect.getsource(
        track_base_sla_service.read_track_base_sla
    )
    assert "inspect_track_base_certification_evidence" not in inspect.getsource(
        freshness_service.read_freshness
    )
