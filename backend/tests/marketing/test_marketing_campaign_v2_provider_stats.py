from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import Column, Integer, String, MetaData, Table, create_engine, event, text
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
    fetch_campaign_v2_provider_stats,
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
    Table(
        "marketing_campaign_v2_provider_campaigns", metadata,
        Column("id", Integer, primary_key=True),
        Column("campaign_v2_id", Integer, nullable=False),
        Column("provider", String, nullable=False),
        Column("provider_campaign_id", String),
        Column("status", String, nullable=False),
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


def test_provider_stats_fetch_resolves_child_and_rejects_foreign_child(session):
    session.execute(text("""
        INSERT INTO marketing_campaign_v2_provider_campaigns
        (id, campaign_v2_id, provider, provider_campaign_id, status)
        VALUES (101, 1, 'IVENTAS', 'child-external-101', 'SUBMITTED'),
               (102, 2, 'IVENTAS', 'other-campaign', 'SUBMITTED')
    """))
    session.commit()
    provider = FakeProvider(stats=_stats())
    fetched = fetch_campaign_v2_provider_stats(
        campaign_id=1,
        provider_campaign_child_id=101,
        allowed_sucursal_keys=['BRANCH A'],
        session=session,
        provider_resolver=lambda key: provider,
    )
    assert fetched.provider_campaign_child_id == 101
    assert fetched.provider_campaign_id == 'child-external-101'
    assert provider.calls == ['child-external-101']

    with pytest.raises(MarketingCampaignV2ProviderStatsUnboundError):
        fetch_campaign_v2_provider_stats(
            campaign_id=1,
            provider_campaign_child_id=102,
            allowed_sucursal_keys=['BRANCH A'],
            session=session,
            provider_resolver=lambda key: provider,
        )
    assert provider.calls == ['child-external-101']


def test_m3_get_child_stats_uses_exact_internal_binding_and_frozen_scope(session):
    session.execute(text("""
        INSERT INTO marketing_campaign_v2_provider_campaigns
        (id, campaign_v2_id, provider, provider_campaign_id, status)
        VALUES (101, 1, 'IVENTAS', 'child-external-101', 'SUBMITTED'),
               (102, 2, 'IVENTAS', 'foreign-child', 'SUBMITTED')
    """))
    session.commit()
    provider = FakeProvider(stats=_stats())
    result = get_campaign_v2_provider_stats(
        campaign_id=1,
        provider_campaign_child_id=101,
        allowed_sucursal_keys=('BRANCH A',),
        session=session,
        provider_resolver=lambda key: provider,
    )
    assert result["provider_campaign_child_id"] == 101
    assert result["provider_campaign_id"] == 'child-external-101'
    assert provider.calls == ['child-external-101']

    with pytest.raises(MarketingCampaignV2NotFoundError):
        get_campaign_v2_provider_stats(
            campaign_id=1,
            provider_campaign_child_id=101,
            allowed_sucursal_keys=('BRANCH B',),
            session=session,
            provider_resolver=lambda key: provider,
        )
    with pytest.raises(MarketingCampaignV2ProviderStatsUnboundError):
        get_campaign_v2_provider_stats(
            campaign_id=1,
            provider_campaign_child_id=102,
            allowed_sucursal_keys=('BRANCH A',),
            session=session,
            provider_resolver=lambda key: provider,
        )
    assert provider.calls == ['child-external-101']
