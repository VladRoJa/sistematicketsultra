"""Campaign-only dispatch suppression must not change frozen source or global blacklist."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest

from app.services import marketing_campaign_v2_delivery_export_service as delivery
from app.services import marketing_campaign_v2_dispatch_exclusion_service as exclusions
from app.models.marketing import MarketingCampaignV2RecipientDispatchExclusionORM


def recipient(recipient_id, branch=None, keys=()):
    return NS(
        id=recipient_id,
        campaign_id=8,
        phone_mx10=f"686{recipient_id:07d}",
        sucursal=branch,
        member_name="QA PRUEBA",
        tarifa_raw="DOMICILIADO",
        audience_family="DOMICILIADO",
        evidence_rows=[NS(sucursal_key=key) for key in keys],
    )


def test_projection_suppresses_three_only_on_campaign_eight(monkeypatch):
    rows = [
        recipient(59510, keys=("INDEPENDENCIA", "SEND MXL")),
        recipient(59859, keys=("INDEPENDENCIA", "TEC MXL")),
        recipient(60120, keys=("INDEPENDENCIA", "TEC MXL")),
        recipient(61200, branch="INDEPENDENCIA"),
    ]
    monkeypatch.setattr(
        delivery, "_load_frozen_campaign_recipients",
        lambda campaign_id, **_kw: ({"id": campaign_id, "name": "QA"}, rows),
    )
    monkeypatch.setattr(delivery, "get_blacklisted_phones", lambda **_kw: set())
    monkeypatch.setattr(
        delivery, "get_campaign_v2_excluded_recipient_ids",
        lambda campaign_id, **_kw: {59510, 59859, 60120} if campaign_id == 8 else set(),
    )
    session = NS()
    frozen, frozen_filename = delivery.export_campaign_v2_delivery_package(
        campaign_id=8, allowed_sucursal_keys=None, session=session,
    )
    assert "COHORTE_CONGELADA" in frozen_filename
    with ZipFile(BytesIO(frozen)) as archive:
        assert any("SIN_SUCURSAL" in name for name in archive.namelist())

    p8 = delivery.build_campaign_v2_sendable_projection(
        campaign_id=8, allowed_sucursal_keys=None, session=session,
    )
    assert len(p8["frozen_recipients"]) == 4
    assert [r.id for r in p8["sendable_recipients"]] == [61200]
    assert p8["campaign_excluded_recipient_ids"] == (59510, 59859, 60120)
    p9 = delivery.build_campaign_v2_sendable_projection(
        campaign_id=9, allowed_sucursal_keys=None, session=session,
    )
    assert len(p9["sendable_recipients"]) == 4
    assert p9["campaign_excluded_recipient_ids"] == ()


def _mock_mutation(monkeypatch, *, provider_children=False, rows=None, already=()):
    ids = [59510, 59859, 60120]
    recipients = rows if rows is not None else [
        recipient(59510, keys=("INDEPENDENCIA", "SEND MXL")),
        recipient(59859, keys=("INDEPENDENCIA", "TEC MXL")),
        recipient(60120, keys=("INDEPENDENCIA", "TEC MXL")),
    ]
    session = MagicMock()
    campaign = NS(id=8, frozen_at="2026-10-07")
    def query(model):
        result = MagicMock()
        if model is exclusions.MarketingCampaignV2ORM:
            result.filter.return_value.with_for_update.return_value.one.return_value = campaign
        elif model is exclusions.MarketingCampaignV2ProviderCampaignORM.id:
            result.filter.return_value.first.return_value = (1,) if provider_children else None
        elif model is exclusions.MarketingCampaignV2RecipientORM:
            result.filter.return_value.all.return_value = recipients
        return result
    session.query.side_effect = query
    monkeypatch.setattr(exclusions, "get_campaign_v2", lambda **_kw: {"id": 8})
    monkeypatch.setattr(
        exclusions, "get_campaign_v2_excluded_recipient_ids",
        lambda **_kw: set(already),
    )
    return session, ids


def test_exclusion_write_is_audited_and_transaction_owned(monkeypatch):
    session, ids = _mock_mutation(monkeypatch)
    result = exclusions.add_campaign_v2_ambiguous_branch_exclusions(
        campaign_id=8, recipient_ids=ids, actor_user_id=42,
        allowed_sucursal_keys=None, session=session,
    )
    assert result == {
        "campaign_id": 8, "excluded_recipient_ids": ids,
        "added": 3, "already_present": 0,
    }
    assert session.add.call_count == 3
    assert session.flush.call_count == 1
    assert not session.commit.called
    rows = [call.args[0] for call in session.add.call_args_list]
    assert all(isinstance(r, MarketingCampaignV2RecipientDispatchExclusionORM) for r in rows)
    assert {r.recipient_id for r in rows} == set(ids)
    assert all(r.campaign_id == 8 and r.created_by_user_id == 42 for r in rows)
    assert all(r.reason == exclusions.AMBIGUOUS_BRANCH_EVIDENCE for r in rows)


def test_exclusion_retry_does_not_create_duplicate_rows(monkeypatch):
    session, ids = _mock_mutation(monkeypatch, already=(59510, 59859, 60120))
    result = exclusions.add_campaign_v2_ambiguous_branch_exclusions(
        campaign_id=8, recipient_ids=ids, actor_user_id=42,
        allowed_sucursal_keys=None, session=session,
    )
    assert result["added"] == 0
    assert result["already_present"] == 3
    session.add.assert_not_called()


@pytest.mark.parametrize(
    "override,expected",
    [
        ({"provider_children": True}, "provider children"),
        ({"rows": [recipient(59510, keys=("INDEPENDENCIA", "SEND MXL"))]}, "no pertenece"),
        ({"rows": [
            recipient(59510, branch="INDEPENDENCIA", keys=("INDEPENDENCIA", "SEND MXL")),
            recipient(59859, keys=("INDEPENDENCIA", "TEC MXL")),
            recipient(60120, keys=("INDEPENDENCIA", "TEC MXL")),
        ]}, "sucursal definida"),
        ({"rows": [
            recipient(59510, keys=("INDEPENDENCIA",)),
            recipient(59859, keys=("INDEPENDENCIA", "TEC MXL")),
            recipient(60120, keys=("INDEPENDENCIA", "TEC MXL")),
        ]}, "no tiene evidencias conflictivas"),
    ],
)
def test_ambiguous_write_fails_closed(monkeypatch, override, expected):
    session, ids = _mock_mutation(monkeypatch, **override)
    with pytest.raises(exclusions.CampaignV2ScopedExclusionValidationError, match=expected):
        exclusions.add_campaign_v2_ambiguous_branch_exclusions(
            campaign_id=8, recipient_ids=ids, actor_user_id=42,
            allowed_sucursal_keys=None, session=session,
        )
    session.add.assert_not_called()


@pytest.mark.parametrize("ids", [[], [59510, 59510], [True], [0], ["59510"]])
def test_invalid_ids_never_start_mutation(ids):
    session = MagicMock()
    with pytest.raises(exclusions.CampaignV2ScopedExclusionValidationError):
        exclusions.add_campaign_v2_ambiguous_branch_exclusions(
            campaign_id=8, recipient_ids=ids, actor_user_id=42,
            allowed_sucursal_keys=None, session=session,
        )
    session.query.assert_not_called()
    session.add.assert_not_called()


def test_exclusion_reader_enforces_both_campaign_scopes_on_real_sqlite():
    import sqlalchemy as sa
    from sqlalchemy.orm import Session
    metadata = sa.MetaData()
    recipients = sa.Table(
        "marketing_campaign_v2_recipients", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("campaign_id", sa.BigInteger, nullable=False),
    )
    exclusions_table = sa.Table(
        "marketing_campaign_v2_recipient_dispatch_exclusions", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("campaign_id", sa.BigInteger, nullable=False),
        sa.Column("recipient_id", sa.BigInteger, nullable=False),
    )
    engine = sa.create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(recipients.insert(), [
            {"id": 59510, "campaign_id": 8},
            {"id": 59859, "campaign_id": 8},
            {"id": 60120, "campaign_id": 9},
        ])
        session.execute(exclusions_table.insert(), [
            {"id": 1, "campaign_id": 8, "recipient_id": 59510},
            {"id": 2, "campaign_id": 8, "recipient_id": 59859},
            # Deliberately corrupted association, safely ignored.
            {"id": 3, "campaign_id": 8, "recipient_id": 60120},
        ])
        session.commit()
        assert exclusions.get_campaign_v2_excluded_recipient_ids(
            campaign_id=8, session=session,
        ) == {59510, 59859}
        assert exclusions.get_campaign_v2_excluded_recipient_ids(
            campaign_id=9, session=session,
        ) == set()
    engine.dispose()


def test_real_preflight_fingerprint_and_unresolved_blocker_follow_scoped_exclusions(monkeypatch):
    from datetime import datetime, timezone
    from app.services import marketing_campaign_v2_preflight_service as preflight
    from app.services.marketing_campaign_v2_dispatch_branch_service import (
        MarketingCampaignV2DispatchBranch,
    )
    rows = [
        recipient(59510, keys=("INDEPENDENCIA", "SEND MXL")),
        recipient(59859, keys=("INDEPENDENCIA", "TEC MXL")),
        recipient(60120, keys=("INDEPENDENCIA", "TEC MXL")),
        recipient(61200, branch="INDEPENDENCIA"),
    ]
    monkeypatch.setattr(
        delivery, "_load_frozen_campaign_recipients",
        lambda campaign_id, **_kw: (
            {"id": campaign_id, "name": "Invita y gana", "purpose": "NEW_SALE"}, rows
        ),
    )
    monkeypatch.setattr(delivery, "get_blacklisted_phones", lambda **_kw: set())
    excluded = {59510, 59859, 60120}
    monkeypatch.setattr(
        delivery, "get_campaign_v2_excluded_recipient_ids",
        lambda **_kw: set(excluded),
    )
    monkeypatch.setattr(
        preflight, "resolve_dispatch_template",
        lambda **_kw: NS(
            id=1, template_name="invita_y_gana_4800",
            variables_json={"1": "first_name"},
            compatible_channel_ids_json=["ind-channel"],
            metadata_json={},
        ),
    )
    monkeypatch.setattr(preflight, "template_file_url", lambda _template: None)
    monkeypatch.setattr(
        preflight, "resolve_frozen_recipient_branch",
        lambda row, **_kw: (
            MarketingCampaignV2DispatchBranch(
                sucursal_id=3, sucursal_canon="INDEPENDENCIA",
                track_label="Independencia", matched_key="INDEPENDENCIA",
            ) if row.sucursal else None
        ),
    )
    monkeypatch.setattr(
        preflight, "resolve_dispatch_channel_binding",
        lambda **_kw: NS(id=3, provider_channel_id="ind-channel"),
    )
    now = datetime(2026, 10, 8, 18, tzinfo=timezone.utc)
    plan = preflight.build_campaign_v2_preflight(
        campaign_id=8, template_id=1,
        allowed_sucursal_keys=None, session=NS(), now=now,
    )
    assert plan.ready
    assert plan.frozen_count == 4
    assert len(plan.sendable_phones) == 1
    assert len(plan.campaign_excluded_recipient_ids) == 3
    assert len(plan.batches) == 1
    assert plan.blocked_missing_branch == ()
    serialized = preflight.serialize_campaign_v2_preflight(plan)
    assert serialized["suppressed"]["campaign_exclusions"] == 3
    assert serialized["sendable_count"] == 1
    fingerprint = plan.dispatch_fingerprint

    # A changed scoped exclusion set forces a different dispatch fingerprint,
    # and reintroduces its unresolved recipient as a blocker.
    excluded.clear()
    raw = preflight.build_campaign_v2_preflight(
        campaign_id=8, template_id=1,
        allowed_sucursal_keys=None, session=NS(), now=now,
    )
    assert not raw.ready
    assert len(raw.blocked_missing_branch) == 3
    assert len(raw.sendable_phones) == 4
    assert raw.dispatch_fingerprint != fingerprint
