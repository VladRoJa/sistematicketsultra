"""M1-F6/3: do not invent dated Track branch membership."""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.warehouse.services.track_effective_roster_service import (
    TrackEffectiveRosterError,
    _authorized_actor,
    attest_future_track_roster,
    read_effective_roster_for_date,
)


def test_only_explicit_admicorp_identity_can_attest():
    assert _authorized_actor(SimpleNamespace(id=12, username="ADMICORP")) == 12
    for identity in [
        SimpleNamespace(id=3, username="ADMINISTRADOR"),
        SimpleNamespace(id=3, username="SISTEMAS"),
        SimpleNamespace(id=None, username="ADMICORP"),
        SimpleNamespace(id=True, username="ADMICORP"),
    ]:
        with pytest.raises(TrackEffectiveRosterError):
            _authorized_actor(identity)


def test_backdating_denied_without_db_or_catalog_access():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/Tijuana")).date()
    user = SimpleNamespace(id=12, username="ADMICORP")
    with patch(
        "app.warehouse.services.track_effective_roster_service._load_active_analytical_branches"
    ) as loader:
        for day in [today, today - timedelta(days=1)]:
            with pytest.raises(TrackEffectiveRosterError, match="futuras"):
                attest_future_track_roster(
                    effective_from=day, user=user, source_reference="CONTROL-2026-001"
                )
    loader.assert_not_called()


def test_attestation_requires_real_document_reference():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tomorrow = datetime.now(ZoneInfo("America/Tijuana")).date() + timedelta(days=1)
    with patch(
        "app.warehouse.services.track_effective_roster_service._load_active_analytical_branches"
    ) as loader:
        with pytest.raises(TrackEffectiveRosterError, match="Referencia"):
            attest_future_track_roster(
                effective_from=tomorrow,
                user=SimpleNamespace(id=12, username="ADMICORP"),
                source_reference="",
            )
    loader.assert_not_called()


def test_no_automatic_attestation_from_mart_build():
    import inspect
    from app.warehouse.services import track_daily_mart_service
    src = inspect.getsource(track_daily_mart_service.refresh_track_daily_mart_for_date)
    assert "attest_future_track_roster" not in src
    assert "capture_roster_for_version" in src


def test_no_history_is_unknown_not_verified():
    q = MagicMock()
    for method in ["filter", "order_by", "limit"]:
        getattr(q, method).return_value = q
    q.all.return_value = []
    with patch(
        "app.warehouse.services.track_effective_roster_service.db.session.query",
        return_value=q,
    ):
        result = read_effective_roster_for_date(date(2026, 10, 13))
    assert result == {
        "verified": False,
        "reason_code": "NO_EFFECTIVE_ROSTER_ATTESTATION",
    }


def test_corrupted_attestation_digest_cannot_verify():
    epoch = SimpleNamespace(
        id=1, expected_branch_count=2, roster_sha256="a" * 64,
        effective_from=date(2026, 10, 15),
        sealed_at_utc=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        attested_at_utc=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    members = [SimpleNamespace(sucursal_canon="TEC_MXL", sucursal_id_at_attestation=7)]
    q1, q2 = MagicMock(), MagicMock()
    for q in (q1, q2):
        q.filter.return_value = q
        q.limit.return_value = q
    q1.order_by.return_value = q1
    q1.all.return_value = [epoch]
    q2.all.return_value = members
    with patch(
        "app.warehouse.services.track_effective_roster_service.db.session.query",
        side_effect=[q1, q2],
    ):
        result = read_effective_roster_for_date(date(2026, 10, 16))
    assert result["verified"] is False
    assert result["reason_code"] == "EFFECTIVE_ROSTER_INTEGRITY_ERROR"


def test_latest_unsealed_epoch_blocks_fallback_to_older_attestation():
    from datetime import datetime, timezone
    import inspect
    from app.warehouse.services import track_effective_roster_service as service

    reader_source = inspect.getsource(service.read_effective_roster_for_date)
    assert "sealed_at_utc.isnot(None)" not in reader_source

    q = MagicMock()
    for method in ("filter", "order_by", "limit"):
        getattr(q, method).return_value = q
    q.all.return_value = [
        SimpleNamespace(
            id=2, effective_from=date(2026, 10, 17), sealed_at_utc=None,
        ),
        SimpleNamespace(
            id=1, effective_from=date(2026, 10, 16),
            sealed_at_utc=datetime(2026, 10, 15, tzinfo=timezone.utc),
        ),
    ]
    with patch(
        "app.warehouse.services.track_effective_roster_service.db.session.query",
        return_value=q,
    ) as query:
        result = service.read_effective_roster_for_date(date(2026, 10, 17))
    assert result == {
        "verified": False,
        "reason_code": "EFFECTIVE_ROSTER_UNSEALED",
    }
    query.assert_called_once()


def test_valid_sealed_epoch_exposes_timestamps_for_next_stage():
    from datetime import datetime, timezone
    from app.warehouse.services.track_version_roster_capture_service import roster_digest
    day = date(2026, 10, 17)
    pairs = [("TEC_MXL", 7), ("VILLAS_DEL_REY", 8)]
    epoch = SimpleNamespace(
        id=14,
        effective_from=day,
        sealed_at_utc=datetime(2026, 10, 16, 16, 5, tzinfo=timezone.utc),
        attested_at_utc=datetime(2026, 10, 16, 16, tzinfo=timezone.utc),
        expected_branch_count=2,
        roster_sha256=roster_digest(pairs),
    )
    rows = [
        SimpleNamespace(sucursal_canon=code, sucursal_id_at_attestation=ident)
        for code, ident in pairs
    ]
    q_epoch, q_members = MagicMock(), MagicMock()
    for q in (q_epoch, q_members):
        q.filter.return_value = q
        q.limit.return_value = q
    q_epoch.order_by.return_value = q_epoch
    q_epoch.all.return_value = [epoch]
    q_members.all.return_value = rows
    with patch(
        "app.warehouse.services.track_effective_roster_service.db.session.query",
        side_effect=[q_epoch, q_members],
    ):
        result = read_effective_roster_for_date(day)
    assert result["verified"] is True
    assert result["epoch_id"] == 14
    assert result["sealed_at_utc"] == "2026-10-16T16:05:00+00:00"
    assert result["attested_at_utc"] == "2026-10-16T16:00:00+00:00"
