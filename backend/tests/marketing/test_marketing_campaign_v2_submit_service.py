from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.services import marketing_campaign_v2_submit_service as service
from app.services.marketing_campaign_v2_preflight_service import (
    CampaignV2DispatchBatchPlan,
    CampaignV2DispatchRecipientPlan,
    CampaignV2PreflightPlan,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderAmbiguousError,
    CampaignProviderCreateResult,
    CampaignProviderDeterministicError,
)


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


NOW = datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)
FINGERPRINT = "a" * 64


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("sucursales", metadata, Column("sucursal_id", Integer, primary_key=True))
    Table(
        "marketing_campaign_v2_channel_bindings",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    Table(
        "marketing_campaign_v2_templates",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderCampaignORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        value.execute(
            Table("users", MetaData(), autoload_with=engine).insert().values(id=7)
        )
        value.execute(
            Table("sucursales", MetaData(), autoload_with=engine).insert(),
            [{"sucursal_id": 1}, {"sucursal_id": 2}],
        )
        value.execute(
            Table(
                "marketing_campaign_v2_channel_bindings",
                MetaData(),
                autoload_with=engine,
            ).insert(),
            [{"id": 101}, {"id": 102}],
        )
        value.execute(
            Table(
                "marketing_campaign_v2_templates",
                MetaData(),
                autoload_with=engine,
            ).insert().values(id=10)
        )
        value.add(
            MarketingCampaignV2ORM(
                id=77,
                name="QA M2",
                purpose="REACTIVATION",
                source="EXPIRED_MEMBERS",
                audience_definition_json={"schema_version": 1},
                created_by_user_id=7,
                frozen_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        value.commit()
        yield value
    engine.dispose()


def _recipient(recipient_id: int, phone: str, name: str):
    return CampaignV2DispatchRecipientPlan(
        recipient_id=recipient_id,
        phone_mx10=phone,
        variables=(("1", name), ("2", "2026-10-31")),
    )


def _batch(
    branch_id: int,
    canon: str,
    channel: str,
    recipient_id: int,
    phone: str,
    *,
    file_url: str | None = None,
):
    return CampaignV2DispatchBatchPlan(
        sucursal_id=branch_id,
        sucursal_canon=canon,
        track_label=canon,
        channel_binding_id=100 + branch_id,
        provider_channel_id=channel,
        template_id=10,
        template_name="reactivacion_v1",
        recipients=(
            _recipient(recipient_id, phone, f"SOCIO {recipient_id}"),
        ),
        blocked_reasons=(),
        file_url=file_url,
    )


def _plan(
    *,
    fingerprint: str = FINGERPRINT,
    ready: bool = True,
    file_url: str | None = None,
):
    batches = (
        _batch(
            1,
            "TEC_MXL",
            "channel-1",
            1,
            "6861000001",
            file_url=file_url,
        ),
        _batch(
            2,
            "VILLAS_MXL",
            "channel-2",
            2,
            "6861000002",
            file_url=file_url,
        ),
    )
    if not ready:
        batches = (
            CampaignV2DispatchBatchPlan(
                **{
                    **batches[0].__dict__,
                    "blocked_reasons": ("MISSING_CHANNEL",),
                }
            ),
        )
    return CampaignV2PreflightPlan(
        campaign_id=77,
        campaign_name="QA M2",
        campaign_purpose="REACTIVATION",
        provider="IVENTAS",
        mode="IMMEDIATE",
        frozen_count=2,
        blacklisted_phones=(),
        sendable_phones=("6861000001", "6861000002"),
        batches=batches,
        blocked_missing_branch=(),
        blocked_missing_channel=((1,) if not ready else ()),
        blocked_missing_required_variable=(),
        blocked_invalid_phone=(),
        blocked_template_channel_mismatch=(),
        dispatch_fingerprint=fingerprint,
    )


class _Provider:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.on_call = None

    def create_campaign(self, batch):
        self.calls.append(batch)
        if self.on_call is not None:
            self.on_call(batch)
        if not self.outcomes:
            raise AssertionError("unexpected provider call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _success(provider_id: str, deduplicated: bool = False):
    return CampaignProviderCreateResult(
        provider_campaign_id=provider_id,
        deduplicated=deduplicated,
        http_status=200,
        response_metadata={
            "campaign": provider_id,
            "deduplicated": deduplicated,
        },
    )


def _install_plan(monkeypatch, plan):
    monkeypatch.setattr(
        service,
        "build_campaign_v2_preflight",
        lambda **_kwargs: plan,
    )


def _submit(session, provider, **overrides):
    kwargs = {
        "campaign_id": 77,
        "template_id": 10,
        "expected_dispatch_fingerprint": FINGERPRINT,
        "actor_user_id": 7,
        "allowed_sucursal_keys": None,
        "provider": provider,
        "send_enabled": True,
        "session": session,
        "now": NOW,
    }
    kwargs.update(overrides)
    return service.submit_campaign_v2(**kwargs)


def test_kill_switch_off_blocks_before_provider_or_rows(session, monkeypatch):
    _install_plan(monkeypatch, _plan())
    provider = _Provider([_success("never")])

    with pytest.raises(service.MarketingCampaignV2SubmitDisabledError):
        _submit(session, provider, send_enabled=False)

    assert provider.calls == []
    assert session.query(MarketingCampaignV2ProviderCampaignORM).count() == 0


def test_stale_fingerprint_blocks_before_provider_or_rows(session, monkeypatch):
    _install_plan(monkeypatch, _plan(fingerprint="b" * 64))
    provider = _Provider([_success("never")])

    with pytest.raises(service.MarketingCampaignV2SubmitPreconditionError):
        _submit(session, provider)

    assert provider.calls == []
    assert session.query(MarketingCampaignV2ProviderCampaignORM).count() == 0


def test_blocked_preflight_makes_zero_provider_calls(session, monkeypatch):
    _install_plan(monkeypatch, _plan(ready=False))
    provider = _Provider([_success("never")])

    with pytest.raises(service.MarketingCampaignV2SubmitPreconditionError):
        _submit(session, provider)

    assert provider.calls == []
    assert session.query(MarketingCampaignV2ProviderCampaignORM).count() == 0


def test_success_submits_batches_sequentially_and_persists_exact_snapshot(
    session,
    monkeypatch,
):
    _install_plan(monkeypatch, _plan())
    provider = _Provider([
        _success("provider-a"),
        _success("provider-b", deduplicated=True),
    ])

    result = _submit(session, provider)

    assert result.status == "SUBMITTED"
    assert result.all_submitted is True
    assert len(provider.calls) == 2
    rows = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .order_by(MarketingCampaignV2ProviderCampaignORM.sucursal_canon.asc())
        .all()
    )
    assert {row.status for row in rows} == {"SUBMITTED"}
    assert {row.provider_campaign_id for row in rows} == {
        "provider-a",
        "provider-b",
    }
    tec = next(row for row in rows if row.sucursal_canon == "TEC_MXL")
    assert tec.request_snapshot_json["leads"] == [
        {
            "phone": "5216861000001",
            "variables": ["SOCIO 1", "2026-10-31"],
            "url_variables": [],
        }
    ]
    assert tec.request_snapshot_json["provider_channel_id"] == "channel-1"
    assert tec.provider_response_json["campaign"] in {"provider-a", "provider-b"}
    assert tec.submit_started_at is not None
    assert tec.submitted_at is not None


def test_media_is_forwarded_and_persisted_in_snapshot(session, monkeypatch):
    file_url = "https://media.example.test/header.png"
    _install_plan(monkeypatch, _plan(file_url=file_url))
    provider = _Provider([
        _success("provider-a"),
        _success("provider-b"),
    ])

    _submit(session, provider)

    assert [call.file_url for call in provider.calls] == [file_url, file_url]
    rows = session.query(MarketingCampaignV2ProviderCampaignORM).all()
    assert {row.request_snapshot_json["file_url"] for row in rows} == {file_url}
    assert {row.template_snapshot_json["file_url"] for row in rows} == {file_url}


def test_second_submit_after_success_is_conflict_and_makes_zero_new_calls(
    session,
    monkeypatch,
):
    _install_plan(monkeypatch, _plan())
    first = _Provider([_success("provider-a"), _success("provider-b")])
    _submit(session, first)

    second = _Provider([_success("duplicate")])
    with pytest.raises(service.MarketingCampaignV2SubmitConflictError):
        _submit(session, second)

    assert second.calls == []


def test_reentrant_concurrent_submit_sees_submitting_and_cannot_post(
    session,
    monkeypatch,
):
    _install_plan(monkeypatch, _plan())
    first = _Provider([_success("provider-a"), _success("provider-b")])
    second = _Provider([_success("must-not-run")])
    observed = {"blocked": False}

    def during_first_provider_call(_batch):
        if len(first.calls) != 1:
            return
        with pytest.raises(service.MarketingCampaignV2SubmitConflictError):
            _submit(session, second)
        observed["blocked"] = True

    first.on_call = during_first_provider_call
    _submit(session, first)

    assert observed["blocked"] is True
    assert second.calls == []


def test_deterministic_error_is_persisted_and_stops_remaining_batches(
    session,
    monkeypatch,
):
    _install_plan(monkeypatch, _plan())
    provider = _Provider([
        CampaignProviderDeterministicError(
            code="TEMPLATE_NOT_FOUND",
            http_status=400,
            support_ref="safe-ref",
        ),
        _success("must-not-run"),
    ])

    result = _submit(session, provider)

    assert len(provider.calls) == 1
    assert result.status == "PROVIDER_ERROR"
    rows = {
        row.sucursal_canon: row
        for row in session.query(MarketingCampaignV2ProviderCampaignORM).all()
    }
    assert rows["TEC_MXL"].status == "PROVIDER_ERROR"
    assert rows["TEC_MXL"].error_code == "TEMPLATE_NOT_FOUND"
    assert rows["TEC_MXL"].support_ref == "safe-ref"
    assert rows["VILLAS_MXL"].status == "READY"


def test_ambiguous_error_requires_reconciliation_and_stops_remaining(
    session,
    monkeypatch,
):
    _install_plan(monkeypatch, _plan())
    provider = _Provider([
        CampaignProviderAmbiguousError(
            code="TRANSPORT_TIMEOUT",
            http_status=None,
            support_ref=None,
        ),
        _success("must-not-run"),
    ])

    result = _submit(session, provider)

    assert len(provider.calls) == 1
    assert result.status == "RECONCILIATION_REQUIRED"
    rows = {
        row.sucursal_canon: row
        for row in session.query(MarketingCampaignV2ProviderCampaignORM).all()
    }
    assert rows["TEC_MXL"].status == "RECONCILIATION_REQUIRED"
    assert rows["VILLAS_MXL"].status == "READY"


def test_first_batch_success_survives_second_batch_failure(session, monkeypatch):
    _install_plan(monkeypatch, _plan())
    provider = _Provider([
        _success("provider-a"),
        CampaignProviderDeterministicError(
            code="INVALID_CHANNEL_TOKEN",
            http_status=400,
            support_ref="ref-b",
        ),
    ])

    result = _submit(session, provider)

    assert len(provider.calls) == 2
    assert result.status == "PROVIDER_ERROR"
    rows = {
        row.sucursal_canon: row
        for row in session.query(MarketingCampaignV2ProviderCampaignORM).all()
    }
    assert rows["TEC_MXL"].status == "SUBMITTED"
    assert rows["TEC_MXL"].provider_campaign_id == "provider-a"
    assert rows["VILLAS_MXL"].status == "PROVIDER_ERROR"
    assert rows["VILLAS_MXL"].provider_campaign_id is None


def test_unexpected_provider_exception_is_ambiguous_not_retryable(
    session,
    monkeypatch,
):
    _install_plan(monkeypatch, _plan())
    provider = _Provider([RuntimeError("unknown")])

    result = _submit(session, provider)

    assert len(provider.calls) == 1
    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.batches[0].error_code == "UNEXPECTED_PROVIDER_RESULT"


def test_logs_do_not_contain_phones_or_variables(session, monkeypatch, caplog):
    _install_plan(monkeypatch, _plan())
    provider = _Provider([
        _success("provider-a"),
        _success("provider-b"),
    ])

    with caplog.at_level("INFO"):
        _submit(session, provider)

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "6861000001" not in text
    assert "5216861000001" not in text
    assert "SOCIO 1" not in text
    assert "channel-1" not in text
    assert "campaign_v2_provider_transition" in text
    assert "duration_ms" in text
    assert "'http_class': '2xx'" in text
    assert "support_ref" in text


def test_non_contiguous_template_variables_block_before_provider(
    session,
    monkeypatch,
):
    bad_batch = CampaignV2DispatchBatchPlan(
        sucursal_id=1,
        sucursal_canon="TEC_MXL",
        track_label="TEC_MXL",
        channel_binding_id=101,
        provider_channel_id="channel-1",
        template_id=10,
        template_name="reactivacion_v1",
        recipients=(
            CampaignV2DispatchRecipientPlan(
                recipient_id=1,
                phone_mx10="6861000001",
                variables=(("1", "ANA"), ("3", "X")),
            ),
        ),
        blocked_reasons=(),
    )
    plan = CampaignV2PreflightPlan(
        **{
            **_plan().__dict__,
            "batches": (bad_batch,),
            "sendable_phones": ("6861000001",),
        }
    )
    _install_plan(monkeypatch, plan)
    provider = _Provider([_success("never")])

    with pytest.raises(service.MarketingCampaignV2SubmitPreconditionError):
        _submit(session, provider)

    assert provider.calls == []
