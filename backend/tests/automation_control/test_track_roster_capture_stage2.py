"""M1-F6/2: deterministic roster and no false historic certification."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.warehouse.services.track_version_roster_capture_service import (
    TrackVersionRosterCaptureError,
    assert_mart_matches_roster,
    capture_roster_for_version,
    normalized_roster,
    roster_digest,
)


D = date(2026, 10, 14)
BRANCHES = [
    SimpleNamespace(sucursal_canon="VILLAS_DEL_REY", sucursal_id=8),
    SimpleNamespace(sucursal_canon="TEC_MXL", sucursal_id=7),
]
ROWS = [
    {"sucursal_canon": "TEC_MXL", "track_date": D.isoformat(),
     "generation_mode": "official_closed_day"},
    {"sucursal_canon": "VILLAS_DEL_REY", "track_date": D.isoformat(),
     "generation_mode": "official_closed_day"},
]


def test_canonical_roster_digest_independent_of_catalog_order():
    a = normalized_roster(BRANCHES)
    b = normalized_roster(list(reversed(BRANCHES)))
    assert a == b == [("TEC_MXL", 7), ("VILLAS_DEL_REY", 8)]
    assert roster_digest(a) == roster_digest(b)
    assert len(roster_digest(a)) == 64


@pytest.mark.parametrize("branches", [
    [],
    [BRANCHES[0], BRANCHES[0]],
    [SimpleNamespace(sucursal_canon=" TEC_MXL", sucursal_id=7)],
    [SimpleNamespace(sucursal_canon="", sucursal_id=None)],
    [SimpleNamespace(sucursal_canon="TEC_MXL", sucursal_id=True)],
    [SimpleNamespace(sucursal_canon="TEC_MXL", sucursal_id=0)],
])
def test_invalid_catalog_fails_closed(branches):
    with pytest.raises(TrackVersionRosterCaptureError):
        normalized_roster(branches)


@pytest.mark.parametrize("rows", [
    ROWS[:1],
    ROWS + [ROWS[0]],
    [ROWS[0], {**ROWS[1], "sucursal_canon": "DEMO"}],
    [ROWS[0], {**ROWS[1], "track_date": "2026-10-13"}],
    [ROWS[0], {**ROWS[1], "generation_mode": "manual_preview"}],
])
def test_roster_rejects_mart_mismatch(rows):
    with pytest.raises(TrackVersionRosterCaptureError):
        assert_mart_matches_roster(
            track_date=D, generation_mode="official_closed_day",
            mart_rows=rows, expected=normalized_roster(BRANCHES),
        )


def test_correct_mart_matches_exact_catalog():
    assert_mart_matches_roster(
        track_date=D, generation_mode="official_closed_day",
        mart_rows=ROWS, expected=normalized_roster(BRANCHES),
    )


def test_no_sql_writes_when_mart_diverges():
    with patch("app.warehouse.services.track_version_roster_capture_service.db.session") as session:
        with pytest.raises(TrackVersionRosterCaptureError):
            capture_roster_for_version(
                version_id=40, track_date=D, branch_rows=BRANCHES,
                mart_rows=ROWS[:1], generation_mode="official_closed_day",
            )
        session.add.assert_not_called()
        session.flush.assert_not_called()


def test_never_overwrite_sealed_snapshot():
    with patch("app.warehouse.services.track_version_roster_capture_service.db.session") as session:
        session.get.return_value = object()
        with pytest.raises(TrackVersionRosterCaptureError, match="no se sobreescribe"):
            capture_roster_for_version(
                version_id=40, track_date=D, branch_rows=BRANCHES,
                mart_rows=ROWS, generation_mode="official_closed_day",
            )
        session.add.assert_not_called()


def test_capture_does_not_commit_and_does_not_certify():
    with patch("app.warehouse.services.track_version_roster_capture_service.db.session") as session:
        session.get.return_value = None
        result = capture_roster_for_version(
            version_id=40, track_date=D, branch_rows=BRANCHES,
            mart_rows=ROWS, generation_mode="official_closed_day",
        )
    assert result["expected_branch_count"] == 2
    assert result["historical_roster_verified"] is False
    assert result["sealed"] is True
    assert len(result["roster_sha256"]) == 64
    session.commit.assert_not_called()
    session.flush.assert_called()
    assert session.add_all.call_count == 1


def test_refresh_uses_one_branch_snapshot_and_same_transaction():
    import inspect
    from app.warehouse.services import track_daily_mart_service as mart

    src = inspect.getsource(mart.refresh_track_daily_mart_for_date)
    assert src.count("_load_active_analytical_branches()") == 1
    assert "active_branches=active_branches" in src
    assert "branch_rows=active_branches" in src
    assert src.index("capture_roster_for_version(") < src.index("db.session.commit()")
    assert "db.session.rollback()" in src
