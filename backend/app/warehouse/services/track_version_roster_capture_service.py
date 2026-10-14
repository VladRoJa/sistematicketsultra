"""M1-F6 stage 2 — capture the *live-at-build* Track branch roster.

This is evidence of the catalog observed when the mart was built, NOT evidence
of historical branch validity for track_date. The historical SLA must remain
UNKNOWN. Persist in the mart refresh transaction; never commit here.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Sequence

from app.extensions import db
from app.models.warehouse import (
    TrackVersionRosterMemberORM,
    TrackVersionRosterSnapshotORM,
)

ROSTER_SOURCE = "LIVE_TRACK_CATALOG_NON_DEMO_AT_CAPTURE"


class TrackVersionRosterCaptureError(ValueError):
    """Reject uncertain or divergent Track roster evidence."""


def normalized_roster(branches: Sequence[Any]) -> list[tuple[str, int | None]]:
    """Return deterministic branch code/ID pairs from one catalog read.

    The exact original codes are used for the mart: do not silently trim or
    normalize an invalid code that would differ from the written mart rows.
    """
    pairs: list[tuple[str, int | None]] = []
    for branch in branches:
        code = getattr(branch, "sucursal_canon", None)
        source_id = getattr(branch, "sucursal_id", None)
        if not isinstance(code, str) or not code or code != code.strip():
            raise TrackVersionRosterCaptureError("Código Track vacío o sin normalizar.")
        if source_id is not None and (
            isinstance(source_id, bool)
            or not isinstance(source_id, int)
            or source_id <= 0
        ):
            raise TrackVersionRosterCaptureError("ID operativo de sucursal inválido.")
        pairs.append((code, source_id))

    if not pairs or len(set(code for code, _ in pairs)) != len(pairs):
        raise TrackVersionRosterCaptureError(
            "Catálogo Track vacío o con sucursales duplicadas."
        )
    return sorted(pairs, key=lambda pair: pair[0])


def roster_digest(pairs: Sequence[tuple[str, int | None]]) -> str:
    """Canonical SHA-256 of the ordered code/ID pairs, encoded as UTF-8 JSON."""
    raw = json.dumps(
        [[code, branch_id] for code, branch_id in pairs],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def assert_mart_matches_roster(
    *,
    track_date: date,
    generation_mode: str,
    mart_rows: Sequence[dict],
    expected: Sequence[tuple[str, int | None]],
) -> None:
    """No snapshot can attest a different mart from its expected roster."""
    codes = [row.get("sucursal_canon") for row in mart_rows]
    expected_codes = [code for code, _ in expected]
    if len(codes) != len(expected_codes) or sorted(codes) != expected_codes:
        raise TrackVersionRosterCaptureError(
            "El mart no corresponde exactamente al universo Track capturado."
        )
    if any(
        row.get("track_date") != track_date.isoformat()
        or row.get("generation_mode") != generation_mode
        for row in mart_rows
    ):
        raise TrackVersionRosterCaptureError(
            "Fecha o modo divergente entre mart y universo Track."
        )


def capture_roster_for_version(
    *,
    version_id: int,
    track_date: date,
    branch_rows: Sequence[Any],
    mart_rows: Sequence[dict],
    generation_mode: str,
) -> dict:
    """Stage the snapshot, members, and irreversible seal in caller session.

    Must be called for a freshly running version, once, immediately before
    committing the exact mart rows. PostgreSQL triggers enforce the version's
    running state, prevent retroactive modifications and guard cardinality.
    Caller owns COMMIT/ROLLBACK for the mart and the sealed snapshot together.
    """
    if isinstance(version_id, bool) or not isinstance(version_id, int) or version_id <= 0:
        raise TrackVersionRosterCaptureError("version_id Track inválido.")
    if not isinstance(track_date, date):
        raise TrackVersionRosterCaptureError("track_date inválida.")
    pairs = normalized_roster(branch_rows)
    assert_mart_matches_roster(
        track_date=track_date,
        generation_mode=generation_mode,
        mart_rows=mart_rows,
        expected=pairs,
    )
    if db.session.get(TrackVersionRosterSnapshotORM, version_id) is not None:
        raise TrackVersionRosterCaptureError(
            "La versión Track ya tiene evidencia de universo: no se sobreescribe."
        )

    snapshot = TrackVersionRosterSnapshotORM(
        version_id=version_id,
        track_date=track_date,
        expected_branch_count=len(pairs),
        roster_sha256=roster_digest(pairs),
        source_kind=ROSTER_SOURCE,
        historical_roster_verified=False,
    )
    db.session.add(snapshot)
    db.session.flush()  # Database guard checks version/date/status.

    db.session.add_all([
        TrackVersionRosterMemberORM(
            version_id=version_id,
            sucursal_canon=code,
            sucursal_id_at_capture=branch_id,
        )
        for code, branch_id in pairs
    ])
    db.session.flush()

    snapshot.sealed_at_utc = db.func.current_timestamp()
    db.session.flush()  # Database guard verifies member count and seals.

    return {
        "version_id": version_id,
        "expected_branch_count": len(pairs),
        "roster_sha256": snapshot.roster_sha256,
        "source_kind": ROSTER_SOURCE,
        "sealed": True,
        "historical_roster_verified": False,
    }
