from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine, event
from sqlalchemy.orm import Session

from app.integrations.iventas.campaigns_client import (
    IVentasCampaignsConfigurationError,
    IVentasCampaignsProviderError,
)
from app.models.marketing import MarketingCampaignV2ORM
from app.services.marketing_campaign_iventas_provider import (
    IVentasCampaignProvider,
)
from app.services.marketing_campaign_iventas_stats_parser import (
    IVentasCampaignStatsInvariantError,
)
from app.services.marketing_campaign_provider import (
    CampaignProviderInteraction,
    CampaignProviderRawCounts,
    CampaignProviderStats,
)
from app.services.marketing_campaign_provider_registry import (
    CampaignProviderResolutionError,
    resolve_campaign_provider,
)
from app.services.marketing_campaign_v2_provider_stats_service import (
    MarketingCampaignV2ProviderStatsUnboundError,
    MarketingCampaignV2ProviderStatsUnsupportedError,
    MarketingCampaignV2ProviderStatsUpstreamError,
    get_campaign_v2_provider_stats,
)
from app.services.marketing_campaign_v2_query_service import (
    MarketingCampaignV2NotFoundError,
)


def _definition(scope=None):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "abc",
            "fingerprint_version": "campaign-v2-freeze-v1",
        },
    }


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    # Esquema mínimo de las tablas consultadas por el fallback, sin requerir
    # dependencias de despacho ni datos personales en la prueba unitaria.
    Table(
        "marketing_campaign_v2_provider_campaigns", metadata,
        Column("id", BigInteger, primary_key=True),
        Column("campaign_v2_id", BigInteger),
        Column("provider", String),
        Column("provider_campaign_id", String),
        Column("status", String),
        Column("recipient_count", Integer),
    )
    Table(
        "marketing_campaign_v2_recipients", metadata,
        Column("id", BigInteger, primary_key=True),
        Column("campaign_id", BigInteger),
    )
    metadata.create_all(engine)

    with Session(engine) as value:
        value.add_all(
            [
                MarketingCampaignV2ORM(
                    id=1,
                    name="Bound",
                    source="EXPIRED_MEMBERS",
                    provider="IVENTAS",
                    provider_campaign_id="external-123",
                    audience_definition_json=_definition(["BRANCH A"]),
                ),
                MarketingCampaignV2ORM(
                    id=2,
                    name="Unbound",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(["BRANCH A"]),
                ),
                MarketingCampaignV2ORM(
                    id=3,
                    name="Unsupported",
                    source="EXPIRED_MEMBERS",
                    provider="OTHER",
                    provider_campaign_id="external-999",
                    audience_definition_json=_definition(["BRANCH A"]),
                ),
            ]
        )
        value.commit()
        yield value

    engine.dispose()


def _stats(
    *,
    analytics_status="ok",
    analytics=None,
):
    return CampaignProviderStats(
        analytics_status=analytics_status,
        analytics=(
            {"responders": 79}
            if analytics is None
            else analytics
        ),
        raw_counts=CampaignProviderRawCounts(
            successful=3,
            failed=1,
            sent=1,
            delivered=1,
            viewed=1,
            answered=0,
            interaction_groups=1,
            interaction_items=2,
        ),
        successful_phones=frozenset({
            "mx10:6863333333",
            "mx10:6861111111",
            "mx10:6862222222",
        }),
        failed_phones=frozenset({
            "mx10:6864444444",
        }),
        sent_phones=frozenset({
            "mx10:6861111111",
        }),
        delivered_phones=frozenset({
            "mx10:6862222222",
        }),
        viewed_phones=frozenset({
            "mx10:6863333333",
        }),
        button_interactions=(
            CampaignProviderInteraction(
                label="INFORMACION",
                raw_item_count=2,
                unique_recipient_phones=frozenset({
                    "mx10:6863333333",
                    "mx10:6861111111",
                }),
            ),
        ),
    )


class FakeProvider:
    def __init__(self, *, stats=None, error=None):
        self.stats = stats
        self.error = error
        self.calls = []

    def capabilities(self):
        raise AssertionError("capabilities not needed for read-through")

    def get_campaign_stats(self, provider_campaign_id):
        self.calls.append(provider_campaign_id)
        if self.error is not None:
            raise self.error
        return self.stats


def test_default_resolver_builds_iventas(monkeypatch):
    monkeypatch.setenv(
        "IVENTAS_CAMPAIGNS_API_KEY",
        "test-key",
    )

    provider = resolve_campaign_provider(" iventas ")

    assert isinstance(provider, IVentasCampaignProvider)


def test_resolver_rejects_unknown_provider():
    with pytest.raises(
        CampaignProviderResolutionError,
        match="no soportado",
    ):
        resolve_campaign_provider("OTHER")


def test_read_through_uses_persisted_external_id_and_serializes_deterministically(
    session,
):
    provider = FakeProvider(stats=_stats())

    result = get_campaign_v2_provider_stats(
        campaign_id=1,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
        provider_resolver=lambda key: provider,
    )

    assert provider.calls == ["external-123"]
    assert result["campaign_id"] == 1
    assert result["provider"] == "IVENTAS"
    assert result["provider_campaign_id"] == "external-123"
    assert result["analytics_status"] == "ok"
    assert result["raw_counts"] == {
        "successful": 3,
        "failed": 1,
        "sent": 1,
        "delivered": 1,
        "viewed": 1,
        "answered": 0,
        "interaction_groups": 1,
        "interaction_items": 2,
    }
    assert result["recipients"]["successful"] == [
        "mx10:6861111111",
        "mx10:6862222222",
        "mx10:6863333333",
    ]
    assert result["button_interactions"] == [
        {
            "label": "INFORMACION",
            "raw_item_count": 2,
            "recipient_phones": [
                "mx10:6861111111",
                "mx10:6863333333",
            ],
        }
    ]
    assert result["analytics"] == {"responders": 79}


def test_read_through_accepts_not_synced_and_none_analytics(session):
    provider = FakeProvider(
        stats=replace(
            _stats(),
            analytics_status="not_synced",
            analytics=None,
        )
    )

    result = get_campaign_v2_provider_stats(
        campaign_id=1,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
        provider_resolver=lambda key: provider,
    )

    assert result["analytics_status"] == "not_synced"
    assert result["analytics"] is None
    assert result["raw_counts"]["successful"] == 3


def test_unbound_campaign_does_not_call_resolver(session):
    calls = []

    with pytest.raises(
        MarketingCampaignV2ProviderStatsUnboundError,
        match="binding",
    ):
        get_campaign_v2_provider_stats(
            campaign_id=2,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
            provider_resolver=lambda key: calls.append(key),
        )

    assert calls == []



def _add_child(session, *, child_id=20, status="SUBMITTED",
               recipient_count=4, external_id="external-child-2"):
    session.execute(
        Table(
            "marketing_campaign_v2_provider_campaigns",
            MetaData(), autoload_with=session.get_bind(),
        ).insert(),
        [{
            "id": child_id,
            "campaign_v2_id": 2,
            "provider": "IVENTAS",
            "provider_campaign_id": external_id,
            "status": status,
            "recipient_count": recipient_count,
        }],
    )


def _add_frozen(session, count=4):
    recipients = Table(
        "marketing_campaign_v2_recipients",
        MetaData(), autoload_with=session.get_bind(),
    )
    session.execute(recipients.insert(), [
        {"id": 100 + i, "campaign_id": 2}
        for i in range(count)
    ])


def test_one_submitted_child_with_complete_frozen_cohort_is_resolved(session):
    _add_frozen(session, count=4)
    _add_child(session)
    session.commit()
    from sqlalchemy import func
    from app.models.marketing import (
        MarketingCampaignV2ProviderCampaignORM,
        MarketingCampaignV2RecipientORM,
    )
    child = session.query(
        MarketingCampaignV2ProviderCampaignORM.status,
        MarketingCampaignV2ProviderCampaignORM.provider,
        MarketingCampaignV2ProviderCampaignORM.provider_campaign_id,
        MarketingCampaignV2ProviderCampaignORM.recipient_count,
    ).filter_by(campaign_v2_id=2).one()
    frozen_count = session.query(func.count(MarketingCampaignV2RecipientORM.id)).filter_by(
        campaign_id=2
    ).scalar()
    assert (child.status, child.provider, child.provider_campaign_id,
            child.recipient_count, frozen_count) == (
        "SUBMITTED", "IVENTAS", "external-child-2", 4, 4,
    )
    provider = FakeProvider(stats=_stats())
    result = get_campaign_v2_provider_stats(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
        provider_resolver=lambda key: provider,
    )
    assert provider.calls == ["external-child-2"]
    assert result["provider"] == "IVENTAS"
    assert result["provider_campaign_id"] == "external-child-2"
    assert result["raw_counts"]["successful"] == 3


@pytest.mark.parametrize("status,count", [
    ("READY", 4),
    ("SUBMITTED", 3),
    ("SCHEDULED", 4),
])
def test_ineligible_child_fails_closed_without_calling_provider(session, status, count):
    _add_frozen(session, count=4)
    _add_child(session, status=status, recipient_count=count)
    session.commit()
    provider = FakeProvider(stats=_stats())
    with pytest.raises(MarketingCampaignV2ProviderStatsUnboundError):
        get_campaign_v2_provider_stats(
            campaign_id=2,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
            provider_resolver=lambda key: provider,
        )
    assert provider.calls == []


def test_multiple_children_never_report_partial_campaign_stats(session):
    _add_frozen(session, count=4)
    _add_child(session, child_id=20, recipient_count=2)
    _add_child(session, child_id=21, recipient_count=2,
               external_id="external-child-3")
    session.commit()
    provider = FakeProvider(stats=_stats())
    with pytest.raises(MarketingCampaignV2ProviderStatsUnboundError):
        get_campaign_v2_provider_stats(
            campaign_id=2,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
            provider_resolver=lambda key: provider,
        )
    assert provider.calls == []


def test_out_of_scope_campaign_is_not_disclosed(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        get_campaign_v2_provider_stats(
            campaign_id=1,
            allowed_sucursal_keys=("BRANCH B",),
            session=session,
            provider_resolver=lambda key: FakeProvider(
                stats=_stats()
            ),
        )


def test_unsupported_provider_is_controlled(session):
    with pytest.raises(
        MarketingCampaignV2ProviderStatsUnsupportedError,
        match="OTHER",
    ):
        get_campaign_v2_provider_stats(
            campaign_id=3,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )


def test_provider_initialization_error_is_sanitized(session):
    def failing_resolver(provider_key):
        raise IVentasCampaignsConfigurationError(
            "secret config detail"
        )

    with pytest.raises(
        MarketingCampaignV2ProviderStatsUpstreamError
    ) as exc_info:
        get_campaign_v2_provider_stats(
            campaign_id=1,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
            provider_resolver=failing_resolver,
        )

    assert exc_info.value.retryable is False
    assert "secret config detail" not in str(exc_info.value)


def test_upstream_provider_error_is_sanitized(session):
    secret = "provider-raw-secret"
    provider = FakeProvider(
        error=IVentasCampaignsProviderError(
            status_code=429,
            provider_code=secret,
            support_ref=secret,
            retryable=True,
            retry_after_seconds=120.0,
        )
    )

    with pytest.raises(
        MarketingCampaignV2ProviderStatsUpstreamError
    ) as exc_info:
        get_campaign_v2_provider_stats(
            campaign_id=1,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
            provider_resolver=lambda key: provider,
        )

    error = exc_info.value
    assert error.retryable is True
    assert error.retry_after_seconds == 120.0
    assert secret not in str(error)


def test_parser_contract_error_is_not_silenced(session):
    provider = FakeProvider(
        error=IVentasCampaignStatsInvariantError(
            "sent/delivered conflict"
        )
    )

    with pytest.raises(
        MarketingCampaignV2ProviderStatsUpstreamError,
        match="contrato",
    ) as exc_info:
        get_campaign_v2_provider_stats(
            campaign_id=1,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
            provider_resolver=lambda key: provider,
        )

    assert exc_info.value.retryable is False


def test_read_through_executes_only_selects_and_never_commits(session):
    provider = FakeProvider(stats=_stats())
    unrelated = session.get(MarketingCampaignV2ORM, 2)
    unrelated.name = "Dirty but not flushed"

    statements = []
    engine = session.get_bind()

    def capture(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        statements.append(statement.strip().upper())

    event.listen(engine, "before_cursor_execute", capture)
    original_commit = session.commit

    def forbidden_commit():
        raise AssertionError("read-through must not commit")

    session.commit = forbidden_commit
    try:
        get_campaign_v2_provider_stats(
            campaign_id=1,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
            provider_resolver=lambda key: provider,
        )
    finally:
        session.commit = original_commit
        event.remove(engine, "before_cursor_execute", capture)

    assert statements
    assert all(statement.startswith("SELECT") for statement in statements)
    assert not session.new
    assert unrelated in session.dirty
    assert not session.deleted
