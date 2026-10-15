"""Read-only M6 correction evidence via HTTP and real isolated PostgreSQL 16."""
from __future__ import annotations

import sqlalchemy as sa
import pytest

from test_google_ads_m6_manual_raw_postgres import real_warehouse, _snapshot
from test_google_ads_m6_manual_structured_postgres import lab, _ingest, _counts
from test_google_ads_m6_manual_publication_postgres import (
    publication_lab, _publish, _published,
)

URL = "/api/integrations/google-ads/manual/correction-status"


def _status(client, token, day="2026-10-13"):
    return client.get(
        URL + "?day=" + day,
        headers={"Authorization": "Bearer " + token} if token else {},
    )


def test_existing_raw_without_structured_is_diagnostic_only(publication_lab):
    client, token, other, engine, campaign, group = publication_lab
    raw_before = _snapshot(engine)
    response = _status(client, token)
    assert response.status_code == 200, response.get_json()
    data = response.json
    assert data["state"] == "RAW_ONLY_UNPUBLISHED"
    assert data["business_date"] == "2026-10-13"
    assert data["structured"]["campaign_rows"] == 0
    assert data["structured"]["group_rows"] == 0
    assert data["publications"] == []
    assert {x["upload_id"] for x in data["raw_reports"]} == {campaign, group}
    assert all(x["manual_pair_upload_audit_count"] == 1 for x in data["raw_reports"])
    assert all(x["pair_import_audit_count"] == 0 for x in data["raw_reports"])
    assert data["replacement_authorized"] is False
    assert data["can_delete_existing_raw"] is False
    assert data["can_auto_republish"] is False
    assert data["next_action"] == "REVIEW_CORRECTION_POLICY_REQUIRED"
    assert _snapshot(engine) == raw_before
    assert _published(engine) == ([], [])


def test_state_tracks_structured_then_canonical_without_modifying_data(
    publication_lab, monkeypatch,
):
    client, token, other, engine, campaign, group = publication_lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")

    staged = _ingest(client, token, campaign, group)
    assert staged.status_code == 201, staged.get_json()
    before = _counts(engine)
    info = _status(client, token)
    assert info.status_code == 200, info.get_json()
    data = info.json
    assert data["state"] == "STRUCTURED_UNPUBLISHED"
    assert data["structured"]["campaign_rows"] == 27
    assert data["structured"]["group_rows"] == 43
    assert data["structured"]["campaign_sources"] == [
        {"upload_id": campaign, "rows": 27},
    ]
    assert data["structured"]["group_sources"] == [
        {"upload_id": group, "rows": 43},
    ]
    assert all(x["pair_import_audit_count"] == 1 for x in data["raw_reports"])
    assert _counts(engine) == before

    published = _publish(client, token, campaign, group)
    assert published.status_code == 201, published.get_json()
    before_published = _published(engine)
    result = _status(client, token).json
    assert result["state"] == "CANONICAL_PUBLISHED"
    assert len(result["publications"]) == 1
    assert result["publications"][0]["is_canonical"] is True
    assert result["publications"][0]["revision"] == 1
    assert result["publications"][0]["campaign_upload_id"] == campaign
    assert result["publications"][0]["ad_group_upload_id"] == group
    assert all(x["pair_publish_audit_count"] == 1 for x in result["raw_reports"])
    assert result["replacement_authorized"] is False
    assert _published(engine) == before_published


def test_legacy_raw_and_archived_evidence_cannot_be_auto_replaced(publication_lab):
    client, token, other, engine, campaign, group = publication_lab
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE warehouse_uploads SET status = 'ARCHIVED'
            WHERE id = :upload
        """), {"upload": campaign})
        conn.execute(sa.text("""
            UPDATE warehouse_audit_logs
            SET details = jsonb_set(details::jsonb, '{upload_origin}',
                                    '"manual_route"')::json
            WHERE upload_id IN (:campaign, :group) AND action = 'UPLOAD'
        """), {"campaign": campaign, "group": group})
    data = _status(client, token).json
    assert data["state"] == "RAW_ONLY_UNPUBLISHED"
    assert data["replacement_authorized"] is False
    assert data["has_existing_period_evidence"] is True
    assert data["next_action"] == "REVIEW_CORRECTION_POLICY_REQUIRED"
    assert {row["status"] for row in data["raw_reports"]} == {"ACTIVE", "ARCHIVED"}
    assert all(row["manual_pair_upload_audit_count"] == 0
               for row in data["raw_reports"])


def test_requires_auth_and_warehouse_scope_and_rejects_invalid_dates(
    publication_lab,
):
    client, token, other, engine, campaign, group = publication_lab
    assert _status(client, None).status_code == 401
    assert _status(client, other).status_code == 403
    for day in ("2026-10-12", "2026-13-01", "2026-10-13%26extra=x", "bad"):
        assert _status(client, token, day).status_code == 400
    data = _status(client, token, "2026-10-14").json
    assert data["state"] == "NO_RECORDS"
    assert data["raw_reports"] == []
    assert data["next_action"] == "NORMAL_M6_PAIR_PREFLIGHT"
    assert data["replacement_authorized"] is False
