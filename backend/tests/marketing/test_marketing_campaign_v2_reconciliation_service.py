from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.services import marketing_campaign_v2_reconciliation_service as service
from app.services.marketing_campaign_v2_submit_service import (
    get_campaign_v2_submit_state,
)


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


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
                name="QA RECONCILIATION",
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


def _ambiguous_child(
    session,
    *,
    child_id: int = 1001,
    branch_id: int = 1,
    canon: str = "TEC_MXL",
    channel_binding_id: int = 101,
    channel: str = "channel-1",
    idempotency_key: str = "b" * 64,
    scheduled: bool = False,
):
    row = MarketingCampaignV2ProviderCampaignORM(
        id=child_id,
        campaign_v2_id=77,
        provider="IVENTAS",
        sucursal_id=branch_id,
        sucursal_canon=canon,
        channel_binding_id=channel_binding_id,
        provider_channel_id=channel,
        template_id=10,
        template_name="reactivacion_v1",
        template_snapshot_json={},
        recipient_count=5,
        dispatch_fingerprint="a" * 64,
        idempotency_key=idempotency_key,
        status="RECONCILIATION_REQUIRED",
        created_by_user_id=7,
        scheduled_by_user_id=(7 if scheduled else None),
        scheduled_timezone=("America/Tijuana" if scheduled else None),
        scheduled_local_at=(
            datetime(2026, 10, 8, 12, 0)
            if scheduled
            else None
        ),
        scheduled_for=(
            datetime(2026, 10, 8, 19, 0, tzinfo=timezone.utc)
            if scheduled
            else None
        ),
        provider_send_at=(
            "2026-10-08T19:00:00.000Z"
            if scheduled
            else None
        ),
        created_at=NOW,
        updated_at=NOW,
        submit_started_at=NOW,
        request_snapshot_json={},
        provider_response_json={
            "http_status": 500,
            "error_code": "HTTP_500",
        },
        error_code="HTTP_500",
        support_ref="safe-ref",
    )
    session.add(row)
    session.commit()
    return row


def test_provider_campaign_found_resolves_immediate_child_to_submitted(session):
    row = _ambiguous_child(session)

    result = service.reconcile_campaign_v2_provider_child(
        child_id=row.id,
        resolution="PROVIDER_CAMPAIGN_FOUND",
        provider_campaign_id="provider-found-1",
        note="Validado manualmente en panel iVentas.",
        actor_user_id=8,
        session=session,
        now=NOW,
    )

    assert result["status"] == "SUBMITTED"
    assert result["provider_campaign_id"] == "provider-found-1"
    assert result["reconciliation"]["resolution"] == (
        "PROVIDER_CAMPAIGN_FOUND"
    )

    persisted = session.get(MarketingCampaignV2ProviderCampaignORM, row.id)
    assert persisted.status == "SUBMITTED"
    assert persisted.provider_campaign_id == "provider-found-1"
    assert persisted.reconciled_by_user_id == 8
    assert persisted.reconciled_at.replace(tzinfo=timezone.utc) == NOW
    assert persisted.error_code is None
    assert persisted.support_ref is None
    assert persisted.reconciliation_snapshot_json["previous"] == {
        "status": "RECONCILIATION_REQUIRED",
        "error_code": "HTTP_500",
        "support_ref": "safe-ref",
        "provider_campaign_id": None,
    }


def test_provider_campaign_found_resolves_scheduled_child_to_scheduled(session):
    row = _ambiguous_child(session, scheduled=True)

    result = service.reconcile_campaign_v2_provider_child(
        child_id=row.id,
        resolution="provider_campaign_found",
        provider_campaign_id="provider-scheduled-found",
        note="Campaña programada visible en iVentas.",
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    assert result["status"] == "SCHEDULED"
    persisted = session.get(MarketingCampaignV2ProviderCampaignORM, row.id)
    assert persisted.status == "SCHEDULED"
    assert persisted.provider_send_at == "2026-10-08T19:00:00.000Z"


def test_not_created_confirmed_becomes_retry_eligible_without_retry(session):
    row = _ambiguous_child(session)

    result = service.reconcile_campaign_v2_provider_child(
        child_id=row.id,
        resolution="NOT_CREATED_CONFIRMED",
        note="Proveedor confirmó que el create no generó campaña.",
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    assert result["status"] == "RETRY_ELIGIBLE"
    assert result["provider_campaign_id"] is None

    persisted = session.get(MarketingCampaignV2ProviderCampaignORM, row.id)
    assert persisted.status == "RETRY_ELIGIBLE"
    assert persisted.provider_campaign_id is None
    assert persisted.error_code == "RECONCILED_NOT_CREATED"
    assert persisted.reconciliation_resolution == "NOT_CREATED_CONFIRMED"

    state = get_campaign_v2_submit_state(
        campaign_id=77,
        session=session,
    )
    assert state["status"] == "RETRY_ELIGIBLE"
    assert state["batches"][0]["status"] == "RETRY_ELIGIBLE"
    assert state["batches"][0]["reconciliation_resolution"] == (
        "NOT_CREATED_CONFIRMED"
    )
    assert state["batches"][0]["reconciled_at"] is not None


def test_resolution_is_one_shot(session):
    row = _ambiguous_child(session)

    service.reconcile_campaign_v2_provider_child(
        child_id=row.id,
        resolution="NOT_CREATED_CONFIRMED",
        note="Confirmación manual inicial.",
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    with pytest.raises(
        service.MarketingCampaignV2ReconciliationConflictError
    ):
        service.reconcile_campaign_v2_provider_child(
            child_id=row.id,
            resolution="PROVIDER_CAMPAIGN_FOUND",
            provider_campaign_id="must-not-bind",
            note="Segundo intento no permitido.",
            actor_user_id=7,
            session=session,
            now=NOW,
        )


def test_only_reconciliation_required_child_can_be_resolved(session):
    row = _ambiguous_child(session)
    row.status = "PROVIDER_ERROR"
    session.commit()

    with pytest.raises(
        service.MarketingCampaignV2ReconciliationConflictError,
        match="ya no requiere",
    ):
        service.reconcile_campaign_v2_provider_child(
            child_id=row.id,
            resolution="NOT_CREATED_CONFIRMED",
            note="No debe aplicar.",
            actor_user_id=7,
            session=session,
            now=NOW,
        )


def test_found_requires_provider_campaign_id(session):
    row = _ambiguous_child(session)

    with pytest.raises(
        service.MarketingCampaignV2ReconciliationValidationError,
        match="provider_campaign_id es obligatorio",
    ):
        service.reconcile_campaign_v2_provider_child(
            child_id=row.id,
            resolution="PROVIDER_CAMPAIGN_FOUND",
            note="Existe evidencia manual.",
            actor_user_id=7,
            session=session,
            now=NOW,
        )


def test_not_created_rejects_provider_campaign_id(session):
    row = _ambiguous_child(session)

    with pytest.raises(
        service.MarketingCampaignV2ReconciliationValidationError,
        match="debe omitirse",
    ):
        service.reconcile_campaign_v2_provider_child(
            child_id=row.id,
            resolution="NOT_CREATED_CONFIRMED",
            provider_campaign_id="contradictory-id",
            note="Evidencia contradictoria.",
            actor_user_id=7,
            session=session,
            now=NOW,
        )


def test_note_is_required_for_manual_evidence(session):
    row = _ambiguous_child(session)

    with pytest.raises(
        service.MarketingCampaignV2ReconciliationValidationError,
        match="note es obligatorio",
    ):
        service.reconcile_campaign_v2_provider_child(
            child_id=row.id,
            resolution="NOT_CREATED_CONFIRMED",
            note="   ",
            actor_user_id=7,
            session=session,
            now=NOW,
        )


def test_duplicate_provider_campaign_id_is_rejected(session):
    row = _ambiguous_child(session)
    existing = _ambiguous_child(
        session,
        child_id=1002,
        branch_id=2,
        canon="VILLAS_DEL_REY",
        channel_binding_id=102,
        channel="channel-2",
        idempotency_key="c" * 64,
    )
    existing.status = "SUBMITTED"
    existing.provider_campaign_id = "provider-existing"
    session.commit()

    with pytest.raises(
        service.MarketingCampaignV2ReconciliationConflictError,
        match="otro child",
    ):
        service.reconcile_campaign_v2_provider_child(
            child_id=row.id,
            resolution="PROVIDER_CAMPAIGN_FOUND",
            provider_campaign_id="provider-existing",
            note="ID encontrado pero pertenece a otro child.",
            actor_user_id=7,
            session=session,
            now=NOW,
        )


def test_unknown_child_is_404_domain_error(session):
    with pytest.raises(
        service.MarketingCampaignV2ReconciliationNotFoundError
    ):
        service.reconcile_campaign_v2_provider_child(
            child_id=9999,
            resolution="NOT_CREATED_CONFIRMED",
            note="No existe el child.",
            actor_user_id=7,
            session=session,
            now=NOW,
        )


def test_not_created_after_first_retry_applies_backoff(session):
    row = _ambiguous_child(session)
    row.retry_attempt_count = 1
    session.commit()

    result = service.reconcile_campaign_v2_provider_child(
        child_id=row.id,
        resolution="NOT_CREATED_CONFIRMED",
        note="Proveedor confirmó nuevamente que no se creó.",
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    assert result["status"] == "RETRY_ELIGIBLE"
    assert result["retry"]["attempt_count"] == 1
    assert result["retry"]["next_allowed_at"] == (
        "2026-10-08T18:01:00"
        if session.bind.dialect.name == "sqlite"
        else "2026-10-08T18:01:00+00:00"
    )


def test_not_created_after_third_retry_closes_as_exhausted(session):
    row = _ambiguous_child(session)
    row.retry_attempt_count = 3
    session.commit()

    result = service.reconcile_campaign_v2_provider_child(
        child_id=row.id,
        resolution="NOT_CREATED_CONFIRMED",
        note="Tercer intento confirmado como no creado.",
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    assert result["status"] == "RETRY_EXHAUSTED"
    assert result["retry"]["attempt_count"] == 3
    assert result["retry"]["next_allowed_at"] is None

    persisted = session.get(MarketingCampaignV2ProviderCampaignORM, row.id)
    assert persisted.status == "RETRY_EXHAUSTED"
    assert persisted.error_code == "RETRY_LIMIT_REACHED"
