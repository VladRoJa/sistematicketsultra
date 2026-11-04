"""Campaign V2: Independencia origin, TEC transport; all tests offline."""
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_v2_channel_routing_service as routing
from app.services.marketing_campaign_v2_branch_exception_capacity import (
    restricted_batch, assess_branch_exception_capacity,
)
from app.services.marketing_campaign_v2_submit_service import _provider_campaign_name


SOURCE_CHANNEL = "6a29c8ffe83fa20008b5a789"
TECH_CHANNEL = "6a86010a24aa9a00076c9800"


def binding(id_, branch, branch_id, channel, metadata=None):
    return NS(
        id=id_, sucursal_id=branch_id, sucursal_canon=branch,
        provider="IVENTAS", provider_channel_id=channel,
        is_active=True, is_default=True, metadata_json=metadata or {},
    )


def fixtures():
    source = binding(30, "INDEPENDENCIA", 3, SOURCE_CHANNEL,
                     {routing.METADATA_KEY: 40})
    target = binding(40, "TEC_MXL", 4, TECH_CHANNEL)
    return source, target


class FakeSession:
    def __init__(self, source, target):
        self.source, self.target = source, target

    def get(self, _model, id_):
        return self.target if id_ == self.target.id else None

    def query(self, _model):
        return self

    def filter(self, *_args):
        return self

    def one_or_none(self):
        return self.source


def test_route_snapshot_keeps_commercial_origin_and_effective_sender():
    source, target = fixtures()
    session = FakeSession(source, target)
    snap = routing.capture_sender_routes(
        session=session, recipient_origins=["INDEPENDENCIA", "TEC_MXL"],
    )
    assert snap["version"] == routing.SNAPSHOT_VERSION
    assert snap["routes"]["INDEPENDENCIA"] == {
        "source_binding_id": 30,
        "source_sucursal_id": 3,
        "outbound_binding_id": 40,
        "outbound_sucursal_canon": "TEC_MXL",
        "outbound_channel_id": TECH_CHANNEL,
    }
    resolved, via = routing.resolve_sender_binding(
        snapshot=snap, source_binding=source,
        branch=NS(sucursal_canon="INDEPENDENCIA", sucursal_id=3),
        session=session,
    )
    assert resolved is target and via == "TEC_MXL"
    # No changes to unrelated branch owner/channel.
    original, via_original = routing.resolve_sender_binding(
        snapshot=snap, source_binding=target,
        branch=NS(sucursal_canon="TEC_MXL", sucursal_id=4), session=session,
    )
    assert original is target and via_original is None
    assert source.sucursal_canon == "INDEPENDENCIA"
    assert source.provider_channel_id == SOURCE_CHANNEL


def test_no_config_or_no_independencia_keeps_legacy_contract():
    source, target = fixtures()
    s = FakeSession(source, target)
    assert routing.capture_sender_routes(
        session=s, recipient_origins=["TEC_MXL"]) is None
    source.metadata_json = {}
    assert routing.capture_sender_routes(
        session=s, recipient_origins=["INDEPENDENCIA"]) is None
    assert routing.resolve_sender_binding(
        snapshot=None, source_binding=source,
        branch=NS(sucursal_canon="INDEPENDENCIA", sucursal_id=3),
        session=s,
    ) == (source, None)


@pytest.mark.parametrize("mutation", [
    lambda source, target, snap: setattr(target, "provider_channel_id", "reassigned"),
    lambda source, target, snap: setattr(target, "is_active", False),
    lambda source, target, snap: setattr(target, "is_default", False),
    lambda source, target, snap: setattr(source, "is_active", False),
    lambda source, target, snap: source.metadata_json.clear(),
    lambda source, target, snap: snap["routes"]["INDEPENDENCIA"].update({"source_binding_id": 999}),
    lambda source, target, snap: snap["routes"]["INDEPENDENCIA"].update({"outbound_binding_id": 1000}),
    lambda source, target, snap: snap.update({"version": "unexpected"}),
    lambda source, target, snap: snap["routes"].update({"INSURGENTES": {}}),
])
def test_changed_sender_or_snapshot_blocks_preflight(mutation):
    source, target = fixtures()
    session = FakeSession(source, target)
    snap = routing.capture_sender_routes(
        session=session, recipient_origins=["INDEPENDENCIA"],
    )
    mutation(source, target, snap)
    with pytest.raises(routing.CampaignV2SenderRoutingConflict):
        routing.resolve_sender_binding(
            snapshot=snap, source_binding=source,
            branch=NS(sucursal_canon="INDEPENDENCIA", sucursal_id=3),
            session=session,
        )


def test_restricted_insurgentes_cannot_route_or_bypass_250():
    source, target = fixtures()
    other = binding(50, "INSURGENTES", 22, "6a2aff2d555186000912586d",
                    {routing.METADATA_KEY: target.id})
    with pytest.raises(routing.CampaignV2SenderRoutingConflict):
        routing.validate_binding_route_metadata(
            source=other, metadata=other.metadata_json,
            session=FakeSession(other, target),
        )


def test_restricted_quota_only_moves_with_frozen_verified_tec_sender():
    unverified = NS(sucursal_canon="INDEPENDENCIA", provider_channel_id=TECH_CHANNEL)
    routed = NS(sucursal_canon="INDEPENDENCIA",
                send_via_sucursal_canon="TEC_MXL",
                provider_channel_id=TECH_CHANNEL, recipients=tuple(range(3612)))
    assert restricted_batch(unverified) is True
    assert restricted_batch(routed) is False
    assert restricted_batch(NS(sucursal_canon="INSURGENTES",
                               provider_channel_id="6a2aff2d555186000912586d")) is True

    class NoOutboundQuery:
        def query(self, *_args):
            pytest.fail("Regular TEC channel has no Suite 250-message cap")

    quota = assess_branch_exception_capacity(
        plan=NS(batches=(routed,)), session=NoOutboundQuery(),
        now=__import__("datetime").datetime(2026, 11, 4,
                                           tzinfo=__import__("datetime").timezone.utc),
    )
    assert quota["status"] == "REVIEWABLE"
    assert quota["batches"][0]["sucursal_canon"] == "INDEPENDENCIA"
    assert quota["batches"][0]["provider_channel_id"] == TECH_CHANNEL
    assert quota["batches"][0]["restriction_kind"] == "NO_SUITE_DAILY_QUOTA"
    assert quota["batches"][0]["operator_channel_cap"] is None
    assert quota["send_authorized"] is False


def test_provider_name_discloses_origin_and_real_sender():
    outgoing = NS(sucursal_canon="INDEPENDENCIA",
                  send_via_sucursal_canon="TEC_MXL")
    title = _provider_campaign_name(
        NS(campaign_name="Winback noviembre"), outgoing)
    assert title == "Winback noviembre · INDEPENDENCIA (via TEC_MXL)"


def test_child_status_keeps_source_and_sender_after_provider_submission():
    from app.services.marketing_campaign_v2_submit_service import (
        _serialize_row_result_dict,
    )
    row = NS(
        id=900, sucursal_id=3, sucursal_canon="INDEPENDENCIA",
        provider_channel_id=TECH_CHANNEL, template_name="promos_noviembre_v",
        template_snapshot_json={
            "origin_sucursal_canon": "INDEPENDENCIA",
            "send_via_sucursal_canon": "TEC_MXL",
            "send_via_provider_channel_id": TECH_CHANNEL,
        },
        recipient_count=12, status="SUBMITTED", provider_campaign_id="synthetic-900",
        provider_deduplicated=False, scheduled_timezone=None, scheduled_local_at=None,
        scheduled_for=None, provider_send_at=None,
        reconciliation_resolution=None, reconciliation_note=None,
        reconciled_by_user_id=None, reconciled_at=None, retry_attempt_count=0,
        retry_last_attempt_at=None, retry_next_allowed_at=None,
        retry_last_by_user_id=None, error_code=None, support_ref=None,
    )
    result = _serialize_row_result_dict(row)
    assert result["sucursal_canon"] == "INDEPENDENCIA"
    assert result["send_via_sucursal_canon"] == "TEC_MXL"
    assert result["provider_channel_id"] == TECH_CHANNEL
    assert result["provider_campaign_id"] == "synthetic-900"
