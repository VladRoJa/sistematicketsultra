"""Commercial template certifications: strict historic/future evidence, no provider calls."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from app.services import marketing_campaign_v2_commercial_template_certification_service as service

NOW = datetime(2026, 11, 9, 20, tzinfo=timezone.utc)


def template():
    return NS(id=7, template_name="promos_noviembre_v", metadata_json={},
              updated_at=NOW - timedelta(days=1))


def child(**kwargs):
    defaults = dict(
        id=90, campaign_v2_id=41, template_id=7,
        template_name="promos_noviembre_v", provider="IVENTAS",
        provider_channel_id="tec", channel_binding_id=40,
        recipient_count=1, status="SUBMITTED", submitted_by_user_id=47,
        provider_campaign_id="provider-90", submitted_at=NOW,
        template_snapshot_json={
            "template_id": 7, "template_name": "promos_noviembre_v",
            "file_url": None,
        },
        request_snapshot_json={
            "provider": "IVENTAS", "provider_channel_id": "tec",
            "template_name": "promos_noviembre_v", "file_url": None,
            "leads": [{"phone": "5216861000001", "variables": []}],
        },
    )
    return NS(**(defaults | kwargs))


def observation(**kwargs):
    return NS(**(dict(
        campaign_recipient_id=123,
        normalized_phone="mx10:6861000001",
        outcome="SUCCESSFUL", delivery_bucket="DELIVERED",
    ) | kwargs))


def query_session(rows):
    session = MagicMock()
    query = session.query.return_value
    query.join.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.all.return_value = rows
    return session


@pytest.mark.parametrize("mutation", [
    None, "failed_delivery", "only_sent", "wrong_recipient", "wrong_channel",
    "wrong_binding", "other_template", "media_change", "wrong_request",
    "no_delivery_observation", "legacy_changed", "signature_changed",
])
def test_exact_child_delivery_and_template_version_required(mutation):
    current = template()
    row = child()
    obs = observation()
    if mutation == "failed_delivery": obs.outcome = "FAILED"
    if mutation == "only_sent": obs.delivery_bucket = "SENT"
    if mutation == "wrong_recipient": obs.normalized_phone = "mx10:6861000002"
    if mutation == "wrong_channel": row.provider_channel_id = "other"
    if mutation == "wrong_binding": row.channel_binding_id = 41
    if mutation == "other_template": row.template_id = 8
    if mutation == "media_change": current.metadata_json = {"file_url": "https://example.test/new.png"}
    if mutation == "wrong_request": row.request_snapshot_json["template_name"] = "bad"
    if mutation == "no_delivery_observation": obs.campaign_recipient_id = None
    if mutation == "legacy_changed": current.updated_at = NOW + timedelta(minutes=1)
    if mutation == "signature_changed":
        row.template_snapshot_json["certification_signature"] = "old-signature"
    matched = service._matching_child(
        row, obs, current, channel="tec", binding_id=40,
        signature="current-signature",
    )
    assert matched is (mutation is None)


def test_commercial_evidence_is_reused_without_any_new_send():
    current = template()
    row = child()
    snap = NS(id=201, fetched_at=NOW + timedelta(hours=1))
    session = query_session([(row, snap, observation())])
    with patch.object(service, "last_confirmed_template_rejection", return_value=None):
        result = service.commercial_certifications(
            template=current,
            groups={"tec": {"binding_id": 40, "sender": "TEC_MXL"}},
            signature="current-signature", session=session,
            now=NOW + timedelta(days=30),
        )
    assert result["tec"]["source"] == "COMMERCIAL_DELIVERY"
    assert result["tec"]["child_id"] == 90
    assert result["tec"]["snapshot_id"] == 201
    assert result["tec"]["delivery_status"] == "ENTREGADA"
    assert "6861000001" not in str(result)
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_confirmed_not_found_after_success_revokes_commercial_certificate():
    session = query_session([
        (child(), NS(id=201, fetched_at=NOW + timedelta(hours=1)), observation())
    ])
    with patch.object(service, "last_confirmed_template_rejection",
                      return_value=NS(id=100, error_code="TEMPLATE_NOT_FOUND")):
        result = service.commercial_certifications(
            template=template(), groups={"tec": {"binding_id": 40}},
            signature="current", session=session, now=NOW + timedelta(days=1),
        )
    assert result == {}


def test_missing_provider_observation_never_certifies_submitted_child():
    session = query_session([])
    result = service.commercial_certifications(
        template=template(), groups={"tec": {"binding_id": 40}},
        signature="current", session=session,
    )
    assert result == {}


def test_future_fingerprint_allows_irrelevant_catalog_edit():
    row = child()
    row.template_snapshot_json["certification_signature"] = "version-a"
    current = template()
    current.updated_at = NOW + timedelta(days=2)
    assert service._matching_child(
        row, observation(), current, channel="tec",
        binding_id=40, signature="version-a",
    )


def test_rejection_query_only_accepts_deterministic_provider_error():
    session = query_session([
        NS(id=6, submit_started_at=NOW + timedelta(hours=1)),
        NS(id=5, submit_started_at=NOW),
    ])
    with patch.object(service, "confirmed_rejected_child",
                      side_effect=[False, True]):
        found = service.last_confirmed_template_rejection(
            template_id=7, channel="tec", session=session,
            after=NOW - timedelta(hours=1),
        )
    assert found.id == 5
