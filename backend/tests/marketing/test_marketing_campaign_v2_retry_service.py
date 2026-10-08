from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.services import marketing_campaign_v2_reconciliation_service
from app.services import marketing_campaign_v2_retry_service as service
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderAmbiguousError,
    CampaignProviderCreateResult,
    CampaignProviderDeterministicError,
    CampaignProviderDispatchBatch,
    CampaignProviderLead,
)


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


class SuccessProvider:
    def __init__(self, provider_campaign_id="provider-retry-1"):
        self.provider_campaign_id = provider_campaign_id
        self.calls = 0
        self.last_batch = None

    def create_campaign(self, batch):
        self.calls += 1
        self.last_batch = batch
        return CampaignProviderCreateResult(
            provider_campaign_id=self.provider_campaign_id,
            deduplicated=False,
            http_status=200,
            response_metadata={
                "campaign": self.provider_campaign_id,
                "deduplicated": False,
            },
        )


class AmbiguousProvider:
    def __init__(self):
        self.calls = 0

    def create_campaign(self, _batch):
        self.calls += 1
        raise CampaignProviderAmbiguousError(
            code="HTTP_500",
            http_status=500,
            support_ref="safe-ref",
        )


class DeterministicProvider:
    def __init__(self):
        self.calls = 0

    def create_campaign(self, _batch):
        self.calls += 1
        raise CampaignProviderDeterministicError(
            code="INVALID_TEMPLATE",
            http_status=400,
            support_ref="safe-ref",
        )


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
            Table("users", MetaData(), autoload_with=engine).insert(),
            [{"id": 7}, {"id": 8}],
        )
        value.execute(
            Table("sucursales", MetaData(), autoload_with=engine).insert(),
            [{"sucursal_id": 1}],
        )
        value.execute(
            Table(
                "marketing_campaign_v2_channel_bindings",
                MetaData(),
                autoload_with=engine,
            ).insert().values(id=101)
        )
        value.execute(
            Table(
                "marketing_campaign_v2_templates",
                MetaData(),
                autoload_with=engine,
            ).insert().values(id=10)
        )
        for campaign_id in (9, 10, 11, 77):
            value.add(
                MarketingCampaignV2ORM(
                    id=campaign_id,
                    name=f"QA RETRY {campaign_id}",
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


def _retry_child(
    session,
    *,
    child_id=1001,
    campaign_id=77,
    attempt_count=0,
    next_allowed_at=NOW,
    scheduled=False,
    scheduled_for=None,
):
    if scheduled:
        scheduled_for = scheduled_for or (NOW + timedelta(hours=1))

    row = MarketingCampaignV2ProviderCampaignORM(
        id=child_id,
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        sucursal_id=1,
        sucursal_canon="TEC_MXL",
        channel_binding_id=101,
        provider_channel_id="channel-1",
        template_id=10,
        template_name="reactivacion_v1",
        template_snapshot_json={},
        recipient_count=1,
        dispatch_fingerprint="a" * 64,
        idempotency_key="b" * 64,
        status="RETRY_ELIGIBLE",
        provider_campaign_id=None,
        created_by_user_id=7,
        scheduled_by_user_id=(7 if scheduled else None),
        scheduled_timezone=("America/Tijuana" if scheduled else None),
        scheduled_local_at=(
            datetime(2026, 10, 8, 12, 0)
            if scheduled
            else None
        ),
        scheduled_for=scheduled_for if scheduled else None,
        provider_send_at=(
            scheduled_for.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
            if scheduled
            else None
        ),
        reconciliation_resolution="NOT_CREATED_CONFIRMED",
        reconciliation_note="Proveedor confirmó que no fue creada.",
        reconciliation_snapshot_json={"schema_version": 1},
        reconciled_by_user_id=7,
        reconciled_at=NOW,
        retry_attempt_count=attempt_count,
        retry_next_allowed_at=next_allowed_at,
        retry_history_json=[],
        request_snapshot_json={"snapshot": "original"},
        provider_response_json={},
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.commit()
    return row


def _install_current_plan(monkeypatch, row, *, fingerprint=None, snapshot=None):
    batch_plan = SimpleNamespace(
        sucursal_id=int(row.sucursal_id),
        sucursal_canon=str(row.sucursal_canon),
    )
    plan = SimpleNamespace(
        dispatch_fingerprint=fingerprint or str(row.dispatch_fingerprint),
        batches=(batch_plan,),
    )
    provider_batch = CampaignProviderDispatchBatch(
        provider="IVENTAS",
        campaign_name="QA RETRY · TEC_MXL",
        provider_channel_id="channel-1",
        template_name="reactivacion_v1",
        leads=(
            CampaignProviderLead(
                phone="5216861000001",
                variables=("Vladimir",),
            ),
        ),
    )

    monkeypatch.setattr(
        service,
        "build_campaign_v2_preflight",
        lambda **_kwargs: plan,
    )
    monkeypatch.setattr(
        service,
        "build_campaign_v2_provider_dispatch_batch",
        lambda **_kwargs: provider_batch,
    )
    monkeypatch.setattr(
        service,
        "serialize_campaign_v2_provider_request_snapshot",
        lambda _batch: (
            {"snapshot": "original"}
            if snapshot is None
            else snapshot
        ),
    )


def test_safe_retry_success_calls_provider_once_and_archives_reconciliation(
    session,
    monkeypatch,
):
    row = _retry_child(session)
    _install_current_plan(monkeypatch, row)
    provider = SuccessProvider()

    result = service.retry_campaign_v2_provider_child(
        child_id=row.id,
        actor_user_id=8,
        provider=provider,
        send_enabled=True,
        session=session,
        now=NOW,
    )

    assert provider.calls == 1
    assert result["status"] == "SUBMITTED"
    assert result["provider_campaign_id"] == "provider-retry-1"
    assert result["retry"]["attempt_count"] == 1
    assert result["retry"]["history"][-1]["outcome"] == "ACCEPTED"
    assert (
        result["retry"]["history"][-1]["source_reconciliation"]["resolution"]
        == "NOT_CREATED_CONFIRMED"
    )

    persisted = session.get(MarketingCampaignV2ProviderCampaignORM, row.id)
    assert persisted.reconciliation_resolution is None
    assert persisted.reconciliation_note is None
    assert persisted.reconciled_at is None
    assert persisted.retry_last_by_user_id == 8


def test_ambiguous_retry_returns_to_reconciliation_without_second_post(
    session,
    monkeypatch,
):
    row = _retry_child(session)
    _install_current_plan(monkeypatch, row)
    provider = AmbiguousProvider()

    result = service.retry_campaign_v2_provider_child(
        child_id=row.id,
        actor_user_id=8,
        provider=provider,
        send_enabled=True,
        session=session,
        now=NOW,
    )

    assert provider.calls == 1
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["retry"]["attempt_count"] == 1
    assert result["retry"]["history"][-1]["outcome"] == "AMBIGUOUS"
    assert result["reconciliation"]["resolution"] is None

    reconciled = marketing_campaign_v2_reconciliation_service.reconcile_campaign_v2_provider_child(
        child_id=row.id,
        resolution="NOT_CREATED_CONFIRMED",
        note="Provider confirmó nuevamente que no se creó.",
        actor_user_id=7,
        session=session,
        now=NOW + timedelta(seconds=10),
    )

    assert reconciled["status"] == "RETRY_ELIGIBLE"
    assert reconciled["retry"]["attempt_count"] == 1
    assert reconciled["retry"]["next_allowed_at"] is not None


def test_deterministic_retry_error_is_not_retry_eligible(
    session,
    monkeypatch,
):
    row = _retry_child(session)
    _install_current_plan(monkeypatch, row)
    provider = DeterministicProvider()

    result = service.retry_campaign_v2_provider_child(
        child_id=row.id,
        actor_user_id=8,
        provider=provider,
        send_enabled=True,
        session=session,
        now=NOW,
    )

    assert provider.calls == 1
    assert result["status"] == "PROVIDER_ERROR"
    assert result["retry"]["attempt_count"] == 1
    assert result["retry"]["history"][-1]["outcome"] == (
        "DETERMINISTIC_ERROR"
    )


def test_fingerprint_change_blocks_retry_without_provider_call(
    session,
    monkeypatch,
):
    row = _retry_child(session)
    _install_current_plan(monkeypatch, row, fingerprint="c" * 64)
    provider = SuccessProvider()

    with pytest.raises(
        service.MarketingCampaignV2SafeRetryPreconditionError,
        match="plan vigente cambió",
    ):
        service.retry_campaign_v2_provider_child(
            child_id=row.id,
            actor_user_id=8,
            provider=provider,
            send_enabled=True,
            session=session,
            now=NOW,
        )

    assert provider.calls == 0
    persisted = session.get(MarketingCampaignV2ProviderCampaignORM, row.id)
    assert persisted.retry_attempt_count == 0
    assert persisted.status == "RETRY_ELIGIBLE"


def test_request_snapshot_change_blocks_retry_without_provider_call(
    session,
    monkeypatch,
):
    row = _retry_child(session)
    _install_current_plan(
        monkeypatch,
        row,
        snapshot={"snapshot": "changed"},
    )
    provider = SuccessProvider()

    with pytest.raises(
        service.MarketingCampaignV2SafeRetryPreconditionError,
        match="request provider vigente difiere",
    ):
        service.retry_campaign_v2_provider_child(
            child_id=row.id,
            actor_user_id=8,
            provider=provider,
            send_enabled=True,
            session=session,
            now=NOW,
        )

    assert provider.calls == 0


def test_backoff_blocks_retry_without_consuming_attempt(
    session,
    monkeypatch,
):
    row = _retry_child(
        session,
        attempt_count=1,
        next_allowed_at=NOW + timedelta(seconds=60),
    )
    _install_current_plan(monkeypatch, row)
    provider = SuccessProvider()

    with pytest.raises(
        service.MarketingCampaignV2SafeRetryPreconditionError,
        match="backoff",
    ):
        service.retry_campaign_v2_provider_child(
            child_id=row.id,
            actor_user_id=8,
            provider=provider,
            send_enabled=True,
            session=session,
            now=NOW,
        )

    assert provider.calls == 0
    assert session.get(
        MarketingCampaignV2ProviderCampaignORM,
        row.id,
    ).retry_attempt_count == 1


def test_scheduled_retry_with_expired_send_at_is_blocked(
    session,
    monkeypatch,
):
    row = _retry_child(
        session,
        scheduled=True,
        scheduled_for=NOW - timedelta(minutes=1),
    )
    _install_current_plan(monkeypatch, row)
    provider = SuccessProvider()

    with pytest.raises(
        service.MarketingCampaignV2SafeRetryPreconditionError,
        match="sendAt original ya venció",
    ):
        service.retry_campaign_v2_provider_child(
            child_id=row.id,
            actor_user_id=8,
            provider=provider,
            send_enabled=True,
            session=session,
            now=NOW,
        )

    assert provider.calls == 0


@pytest.mark.parametrize("campaign_id", [9, 10, 11])
def test_never_retry_campaign_ids_are_blocked_even_if_state_is_eligible(
    session,
    monkeypatch,
    campaign_id,
):
    row = _retry_child(session, campaign_id=campaign_id)
    _install_current_plan(monkeypatch, row)
    provider = SuccessProvider()

    with pytest.raises(
        service.MarketingCampaignV2SafeRetryPreconditionError,
        match="bloqueada permanentemente",
    ):
        service.retry_campaign_v2_provider_child(
            child_id=row.id,
            actor_user_id=8,
            provider=provider,
            send_enabled=True,
            session=session,
            now=NOW,
        )

    assert provider.calls == 0


def test_kill_switch_off_blocks_retry_before_provider(
    session,
    monkeypatch,
):
    row = _retry_child(session)
    _install_current_plan(monkeypatch, row)
    provider = SuccessProvider()

    with pytest.raises(service.MarketingCampaignV2SafeRetryDisabledError):
        service.retry_campaign_v2_provider_child(
            child_id=row.id,
            actor_user_id=8,
            provider=provider,
            send_enabled=False,
            session=session,
            now=NOW,
        )

    assert provider.calls == 0


def test_scheduled_retry_preserves_backend_schedule(
    session,
    monkeypatch,
):
    row = _retry_child(
        session,
        scheduled=True,
        scheduled_for=NOW + timedelta(hours=1),
    )
    captured = {}
    batch_plan = SimpleNamespace(
        sucursal_id=1,
        sucursal_canon="TEC_MXL",
    )
    plan = SimpleNamespace(
        dispatch_fingerprint=row.dispatch_fingerprint,
        batches=(batch_plan,),
    )

    def fake_preflight(**kwargs):
        captured.update(kwargs)
        return plan

    monkeypatch.setattr(service, "build_campaign_v2_preflight", fake_preflight)
    monkeypatch.setattr(
        service,
        "build_campaign_v2_provider_dispatch_batch",
        lambda **_kwargs: CampaignProviderDispatchBatch(
            provider="IVENTAS",
            campaign_name="QA RETRY · TEC_MXL",
            provider_channel_id="channel-1",
            template_name="reactivacion_v1",
            leads=(
                CampaignProviderLead(
                    phone="5216861000001",
                    variables=("Vladimir",),
                ),
            ),
            send_at=row.provider_send_at,
        ),
    )
    monkeypatch.setattr(
        service,
        "serialize_campaign_v2_provider_request_snapshot",
        lambda _batch: {"snapshot": "original"},
    )
    provider = SuccessProvider("provider-scheduled-retry")

    result = service.retry_campaign_v2_provider_child(
        child_id=row.id,
        actor_user_id=8,
        provider=provider,
        send_enabled=True,
        session=session,
        now=NOW,
    )

    assert result["status"] == "SCHEDULED"
    assert captured["schedule"] == {
        "timezone": "America/Tijuana",
        "local_datetime": "2026-10-08T12:00:00",
    }
    assert provider.calls == 1
