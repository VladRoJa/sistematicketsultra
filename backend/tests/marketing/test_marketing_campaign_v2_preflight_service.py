from __future__ import annotations

from datetime import date
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_v2_preflight_service as service
from app.services.marketing_campaign_v2_dispatch_branch_service import (
    MarketingCampaignV2DispatchBranch,
)


def _recipient(
    recipient_id: int,
    phone: str,
    branch_id: int | None,
    *,
    name: str = "ANA LOPEZ",
    family: str = "DOMICILIADO",
    expiration: date | None = date(2026, 10, 31),
):
    return NS(
        id=recipient_id,
        phone_mx10=phone,
        member_name=name,
        member_id=f"M{recipient_id}",
        member_pin=f"P{recipient_id}",
        sucursal=(f"BRANCH {branch_id}" if branch_id is not None else None),
        tarifa_raw="MENSUALIDAD",
        audience_family=family,
        fecha_vencimiento_date=expiration,
        evidence_rows=[],
        _branch_id=branch_id,
    )


def _template(
    *,
    template_id: int = 10,
    name: str = "reactivacion_v1",
    variables=None,
    compatible=None,
):
    return NS(
        id=template_id,
        template_name=name,
        variables_json=variables or {"1": "first_name"},
        compatible_channel_ids_json=compatible or [],
    )


def _install(
    monkeypatch,
    recipients,
    *,
    frozen=None,
    blacklisted=(),
    template=None,
    channel_by_branch=None,
):
    frozen_rows = list(frozen if frozen is not None else recipients)
    sendable_rows = list(recipients)
    monkeypatch.setattr(
        service,
        "build_campaign_v2_sendable_projection",
        lambda **_kwargs: {
            "campaign": {
                "id": 7,
                "name": "QA M1",
                "purpose": "REACTIVATION",
            },
            "frozen_recipients": frozen_rows,
            "blacklisted_phones": tuple(sorted(blacklisted)),
            "sendable_recipients": sendable_rows,
        },
    )
    monkeypatch.setattr(
        service,
        "resolve_dispatch_template",
        lambda **_kwargs: template or _template(),
    )

    def resolve_branch(recipient, **_kwargs):
        if recipient._branch_id is None:
            return None
        return MarketingCampaignV2DispatchBranch(
            sucursal_id=recipient._branch_id,
            sucursal_canon=f"BRANCH_{recipient._branch_id}",
            track_label=f"Branch {recipient._branch_id}",
            matched_key=f"BRANCH {recipient._branch_id}",
        )

    monkeypatch.setattr(
        service,
        "resolve_frozen_recipient_branch",
        resolve_branch,
    )

    bindings = (
        {
            1: NS(id=101, provider_channel_id="channel-1"),
            2: NS(id=102, provider_channel_id="channel-2"),
        }
        if channel_by_branch is None
        else channel_by_branch
    )
    monkeypatch.setattr(
        service,
        "resolve_dispatch_channel_binding",
        lambda *, sucursal_id, **_kwargs: bindings.get(sucursal_id),
    )


def test_preflight_uses_exact_sendable_projection_and_preserves_frozen_count(
    monkeypatch,
):
    frozen = [
        _recipient(index, f"686100000{index}", 1)
        for index in range(1, 6)
    ]
    sendable = [frozen[0], frozen[2], frozen[4]]
    _install(
        monkeypatch,
        sendable,
        frozen=frozen,
        blacklisted=("6861000002", "6861000004"),
    )

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert plan.frozen_count == 5
    assert set(plan.sendable_phones) == {
        "6861000001",
        "6861000003",
        "6861000005",
    }
    payload = service.serialize_campaign_v2_preflight(plan)
    assert payload["suppressed"]["blacklist"] == 2
    assert payload["sendable_count"] == 3


def test_two_branches_produce_two_batches(monkeypatch):
    rows = [
        _recipient(1, "6861000001", 1),
        _recipient(2, "6861000002", 2),
    ]
    _install(monkeypatch, rows)

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert [batch.sucursal_id for batch in plan.batches] == [1, 2]
    assert plan.ready is True


def test_same_branch_multiple_families_stays_one_batch(monkeypatch):
    rows = [
        _recipient(1, "6861000001", 1, family="DOMICILIADO"),
        _recipient(2, "6861000002", 1, family="TRIMESTRAL"),
    ]
    _install(monkeypatch, rows)

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert len(plan.batches) == 1
    assert len(plan.batches[0].recipients) == 2


def test_phone_only_recipient_is_blocked_never_reassigned(monkeypatch):
    rows = [_recipient(1, "6861000001", None)]
    _install(monkeypatch, rows)

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert plan.blocked_missing_branch == (1,)
    assert plan.batches == ()
    assert plan.ready is False


def test_missing_channel_blocks_batch(monkeypatch):
    rows = [_recipient(1, "6861000001", 1)]
    _install(monkeypatch, rows, channel_by_branch={})

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert plan.blocked_missing_channel == (1,)
    assert plan.batches[0].blocked_reasons == ("MISSING_CHANNEL",)
    assert plan.ready is False


def test_required_variable_missing_blocks_recipient_and_batch(monkeypatch):
    rows = [_recipient(1, "6861000001", 1, expiration=None)]
    _install(
        monkeypatch,
        rows,
        template=_template(
            variables={"1": "first_name", "2": "expiration_date"}
        ),
    )

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert plan.blocked_missing_required_variable == (1,)
    assert "MISSING_REQUIRED_VARIABLE" in plan.batches[0].blocked_reasons
    assert plan.ready is False


def test_first_name_reuses_export_semantics(monkeypatch):
    rows = [_recipient(1, "6861000001", 1, name="MA DEL CARMEN LOPEZ")]
    _install(monkeypatch, rows)

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert dict(plan.batches[0].recipients[0].variables) == {"1": "CARMEN"}


def test_template_channel_mismatch_blocks_batch(monkeypatch):
    rows = [_recipient(1, "6861000001", 1)]
    _install(
        monkeypatch,
        rows,
        template=_template(compatible=["another-channel"]),
    )

    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert plan.blocked_template_channel_mismatch == (1,)
    assert plan.ready is False


def test_fingerprint_is_order_independent(monkeypatch):
    rows = [
        _recipient(1, "6861000001", 1),
        _recipient(2, "6861000002", 1),
    ]
    _install(monkeypatch, rows)
    first = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    _install(monkeypatch, list(reversed(rows)))
    second = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    assert first.dispatch_fingerprint == second.dispatch_fingerprint


@pytest.mark.parametrize("change", ["phone", "template", "channel"])
def test_fingerprint_changes_with_material_dispatch_inputs(monkeypatch, change):
    rows = [_recipient(1, "6861000001", 1)]
    template = _template()
    channels = {1: NS(id=101, provider_channel_id="channel-1")}
    _install(
        monkeypatch,
        rows,
        template=template,
        channel_by_branch=channels,
    )
    baseline = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    ).dispatch_fingerprint

    if change == "phone":
        rows = [_recipient(1, "6861000099", 1)]
    elif change == "template":
        template = _template(template_id=11, name="reactivacion_v2")
    else:
        channels = {1: NS(id=201, provider_channel_id="channel-2")}

    _install(
        monkeypatch,
        rows,
        template=template,
        channel_by_branch=channels,
    )
    changed = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=template.id,
        allowed_sucursal_keys=None,
        session=NS(),
    ).dispatch_fingerprint

    assert changed != baseline


def test_idempotency_key_is_deterministic_for_batch(monkeypatch):
    rows = [_recipient(1, "6861000001", 1)]
    _install(monkeypatch, rows)
    plan = service.build_campaign_v2_preflight(
        campaign_id=7,
        template_id=10,
        allowed_sucursal_keys=None,
        session=NS(),
    )

    first = service.build_provider_campaign_idempotency_key(
        campaign_v2_id=7,
        batch=plan.batches[0],
        dispatch_fingerprint=plan.dispatch_fingerprint,
    )
    second = service.build_provider_campaign_idempotency_key(
        campaign_v2_id=7,
        batch=plan.batches[0],
        dispatch_fingerprint=plan.dispatch_fingerprint,
    )

    assert len(first) == 64
    assert first == second
