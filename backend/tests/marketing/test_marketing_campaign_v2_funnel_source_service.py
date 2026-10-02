from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import marketing_campaign_v2_funnel_source_service as service


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_args):
        return self

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.query_count = 0

    def query(self, *_args):
        self.query_count += 1
        return _Query(self.rows)

    def add(self, _value):
        raise AssertionError("La fuente Funnel no debe escribir DB.")

    def commit(self):
        raise AssertionError("La fuente Funnel no debe hacer commit.")


def _portfolio():
    return {
        "funnel_month": "2026-09",
        "funnel_cutoff_date": "2026-09-30",
        "iventas_sync_run_id": 77,
        "scope": {"type": "PRIMARY_BRANCH", "branch_ids": [1]},
        "rows": [
            {
                "phone_mx10": "6861111111",
                "contact_id": "active",
                "sucursal_id": 1,
                "channel": "WhatsApp",
                "source_date": "2026-09-01",
                "origin": "iVentas / Meta Ads",
                "bought": False,
            },
            {
                "phone_mx10": "6862222222",
                "contact_id": "keep-a",
                "sucursal_id": 1,
                "channel": "WhatsApp",
                "source_date": "2026-09-02",
                "origin": "iVentas / Meta Ads",
                "bought": False,
            },
            {
                "phone_mx10": "526862222222",
                "contact_id": "keep-b",
                "sucursal_id": 1,
                "channel": "WhatsApp",
                "source_date": "2026-09-03",
                "origin": "iVentas / Meta Ads",
                "bought": False,
            },
            {
                "phone_mx10": None,
                "contact_id": "invalid",
                "sucursal_id": 1,
                "channel": "WhatsApp",
                "source_date": "2026-09-04",
                "origin": "iVentas / Meta Ads",
                "bought": False,
            },
            {
                "phone_mx10": "6863333333",
                "contact_id": "outside",
                "sucursal_id": 2,
                "channel": "WhatsApp",
                "source_date": "2026-09-05",
                "origin": "iVentas / Meta Ads",
                "bought": False,
            },
            {
                "phone_mx10": "6864444444",
                "contact_id": "no-branch",
                "sucursal_id": None,
                "channel": "WhatsApp",
                "source_date": "2026-09-06",
                "origin": "iVentas / Meta Ads",
                "bought": False,
            },
        ],
        "buyer_excluded": [
            {
                "phone_mx10": "6869999999",
                "contact_id": "buyer",
                "sucursal_id": 1,
                "channel": "WhatsApp",
                "source_date": "2026-09-07",
                "origin": "iVentas / Meta Ads",
                "bought": True,
            }
        ],
    }


def _snapshot(snapshot_id=900):
    return SimpleNamespace(
        id=snapshot_id,
        cutoff_date=date(2026, 9, 30),
        snapshot_kind="daily",
        captured_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )


def test_funnel_adapter_bulk_suppression_scope_and_metadata(monkeypatch):
    monkeypatch.setattr(
        service,
        "build_marketing_funnel_portfolio_at_cutoff",
        lambda **_kwargs: _portfolio(),
    )
    monkeypatch.setattr(
        service,
        "marketing_branch_keys_by_sucursal_ids",
        lambda **_kwargs: {1: "BRANCH A", 2: "BRANCH B"},
    )
    monkeypatch.setattr(
        service.activos_resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: _snapshot(),
    )
    session = _Session([("526861111111",)])
    access = SimpleNamespace(is_global=False, branch_ids=(1,))

    result = service.load_campaign_v2_funnel_source(
        funnel_month="2026-09",
        funnel_cutoff_date="2026-09-30",
        marketing_access=access,
        session=session,
    )

    assert result.universe_count == 7
    assert len(result.buyer_excluded) == 1
    assert len(result.invalid_phone) == 1
    assert [row.contact_id for row in result.active_member_suppressed] == ["active"]
    assert [row.phone_mx10 for row in result.candidates] == [
        "6862222222",
        "6862222222",
    ]
    assert result.scoped_count == 2
    assert result.candidates[0].source_reference == "1:keep-a"
    assert result.metadata["funnel_month"] == "2026-09"
    assert result.metadata["funnel_cutoff_date"] == "2026-09-30"
    assert result.metadata["iventas_sync_run_id"] == 77
    assert result.metadata["active_members_snapshot_id"] == 900
    assert result.metadata["active_members_cutoff_date"] == "2026-09-30"
    assert session.query_count == 1


def test_limited_scope_fails_closed_for_missing_or_outside_branch(monkeypatch):
    portfolio = _portfolio()
    portfolio["rows"] = [
        portfolio["rows"][4],
        portfolio["rows"][5],
    ]
    portfolio["buyer_excluded"] = []
    monkeypatch.setattr(
        service,
        "build_marketing_funnel_portfolio_at_cutoff",
        lambda **_kwargs: portfolio,
    )
    monkeypatch.setattr(
        service,
        "marketing_branch_keys_by_sucursal_ids",
        lambda **_kwargs: {2: "BRANCH B"},
    )
    monkeypatch.setattr(
        service.activos_resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: _snapshot(),
    )

    result = service.load_campaign_v2_funnel_source(
        funnel_month="2026-09",
        funnel_cutoff_date="2026-09-30",
        marketing_access=SimpleNamespace(is_global=False, branch_ids=(1,)),
        session=_Session([]),
    )

    assert result.candidates == ()
    assert result.scoped_count == 0


def test_global_scope_can_preserve_phone_only_candidate_without_branch(monkeypatch):
    portfolio = _portfolio()
    portfolio["rows"] = [portfolio["rows"][5]]
    portfolio["buyer_excluded"] = []
    monkeypatch.setattr(
        service,
        "build_marketing_funnel_portfolio_at_cutoff",
        lambda **_kwargs: portfolio,
    )
    monkeypatch.setattr(
        service,
        "marketing_branch_keys_by_sucursal_ids",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        service.activos_resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: _snapshot(),
    )

    result = service.load_campaign_v2_funnel_source(
        funnel_month="2026-09",
        funnel_cutoff_date="2026-09-30",
        marketing_access=SimpleNamespace(is_global=True, branch_ids=()),
        session=_Session([]),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].sucursal_id is None
    assert result.candidates[0].phone_mx10 == "6864444444"


def test_active_snapshot_is_required(monkeypatch):
    monkeypatch.setattr(
        service,
        "build_marketing_funnel_portfolio_at_cutoff",
        lambda **_kwargs: _portfolio(),
    )
    monkeypatch.setattr(
        service,
        "marketing_branch_keys_by_sucursal_ids",
        lambda **_kwargs: {1: "BRANCH A", 2: "BRANCH B"},
    )
    monkeypatch.setattr(
        service.activos_resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: None,
    )

    with pytest.raises(
        service.MarketingCampaignV2FunnelSourceValidationError,
        match="snapshot canónico",
    ):
        service.load_campaign_v2_funnel_source(
            funnel_month="2026-09",
            funnel_cutoff_date="2026-09-30",
            marketing_access=SimpleNamespace(is_global=True, branch_ids=()),
            session=_Session([]),
        )


def test_funnel_adapter_has_no_provider_or_write_dependency():
    import inspect

    source = inspect.getsource(service)
    assert "provider" not in source.lower()
    assert ".add(" not in source
    assert ".commit(" not in source
