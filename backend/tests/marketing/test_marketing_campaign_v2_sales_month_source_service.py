"""M2 worker adapter: prevalidated provider scopes and canonical sale-month evidence."""
from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.marketing_campaign_v2_sales_month_source_service import (
    UniqueSalesEvidenceError,
    _group_gasca_orders,
    _month_window,
    _proven_contacts,
    reconcile_sale_month,
)


SENT_A = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)
SENT_B = SENT_A + timedelta(days=1)
SNAP_CAPTURED = datetime(2026, 11, 1, 13, tzinfo=timezone.utc)
PHONE = "6861000001"


class Query:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *args):
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def yield_per(self, *args):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class ReadSession:
    def __init__(self, *results):
        self.results = iter(results)
        self.queries = 0
        self.no_autoflush = nullcontext()

    def query(self, *args):
        self.queries += 1
        return Query(next(self.results))


def child(campaign_id, child_id, submitted_at):
    return SimpleNamespace(
        id=child_id,
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        status="SUBMITTED",
        sucursal_id=16,
        submitted_at=submitted_at,
        submit_started_at=None,
        provider_campaign_id=f"provider-{child_id}",
        provider_channel_id="channel-1",
        recipient_count=1,
        request_snapshot_json={
            "provider_channel_id": "channel-1",
            "leads": [{"phone": f"521{PHONE}"}],
        },
    )


def snapshot(campaign_id, child_id, snapshot_id, fetched_at, raw_successful=1):
    return SimpleNamespace(
        id=snapshot_id,
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        provider_campaign_id=f"provider-{child_id}",
        fetched_at=fetched_at,
        analytics_status="ok",
        raw_successful=raw_successful,
    )


def recipient(campaign_id, recipient_id):
    return SimpleNamespace(
        id=recipient_id, campaign_id=campaign_id, phone_mx10=PHONE,
    )


def observation(snapshot_id, recipient_id, *, phone=PHONE, outcome="SUCCESSFUL"):
    return SimpleNamespace(
        snapshot_id=snapshot_id,
        campaign_recipient_id=recipient_id,
        normalized_phone=f"mx10:{phone}",
        outcome=outcome,
    )


def sale(row_id=1, amount="549.00", *, date_str="2026-10-23", time_str="12:00:00",
         status="ACTIVO", desc="CONVENIOS $549", kind="REACTIVACION", branch="AZAHARES"):
    return SimpleNamespace(
        id=row_id, telefono=PHONE, sucursal=branch, estatus=status,
        descripcion=desc, total=Decimal(amount), fecha=date_str, hora=time_str,
        id_orden="ABC123", folio="F-1", clave_producto="MEMBRESIA",
        tipo="CONTRATO", nuevo=kind,
    )


def session(*, missing_snapshot=False, missing_cut=False, conflicting_alias=False,
            invalid_recipient=False):
    ch_a, ch_b = child(1, 101, SENT_A), child(2, 102, SENT_B)
    campaign_a = SimpleNamespace(id=1, purpose="REACTIVATION", source="EXPIRED_MEMBERS")
    campaign_b = SimpleNamespace(id=2, purpose="REACTIVATION", source="EXPIRED_MEMBERS")
    snaps = [
        snapshot(1, 101, 999, SENT_A - timedelta(days=1)),
        snapshot(1, 101, 201, SENT_A),
        snapshot(2, 102, 202, SENT_B),
    ]
    if missing_snapshot:
        snaps = snaps[:-1]
    observations = [
        observation(201, 1001),
        observation(202, 1002, phone="6869000001" if invalid_recipient else PHONE),
    ]
    result_sets = [
        [(ch_a, campaign_a), (ch_b, campaign_b)],
        snaps,
        [recipient(1, 1001), recipient(2, 1002)],
        observations,
    ]
    if not missing_snapshot:
        result_sets += [
            [] if missing_cut else [
                SimpleNamespace(id=300, business_date=date(2026, 10, 31),
                                captured_at=SNAP_CAPTURED)
            ],
            [
                (SimpleNamespace(raw_branch_name="AZAHARES"),
                 SimpleNamespace(sucursal_id=16)),
                *(([(SimpleNamespace(raw_branch_name="AZAHARES"),
                      SimpleNamespace(sucursal_id=17))]) if conflicting_alias else []),
            ],
            [sale(), sale(2, "-50.00")],
        ]
    return ReadSession(*result_sets)


def test_m2_worker_uses_only_latest_proven_success_and_one_canonical_sale():
    active = session()
    result = reconcile_sale_month(
        from_date="2026-10-01", to_date="2026-10-31",
        window_days=7, session=active,
    )
    assert result["status"] == "READY"
    assert result["transactions_observed"] == 1
    assert result["revenue_observed_mxn"] == "499.00"
    assert result["campaigns"] == [
        {"campaign_id": 1, "buyers_observed": 0, "transactions_observed": 0,
         "revenue_observed_mxn": "0.00", "assisted_transactions": 1},
        {"campaign_id": 2, "buyers_observed": 1, "transactions_observed": 1,
         "revenue_observed_mxn": "499.00", "assisted_transactions": 0},
    ]
    assert result["sale_snapshot_id"] == 300
    assert result["contacts_proven"] == 2
    assert active.queries == 7
    assert "allocations_private" not in result
    assert PHONE not in repr(result)


def test_m2_worker_provider_snapshot_missing_marks_pending_not_zero():
    result = reconcile_sale_month(
        from_date="2026-10-01", to_date="2026-10-31",
        window_days=30, session=session(missing_snapshot=True),
    )
    assert result["status"] == "PENDING_PROVIDER_EVIDENCE"
    assert result["revenue_observed_mxn"] is None


def test_m2_worker_incomplete_venta_total_marks_pending_not_zero():
    result = reconcile_sale_month(
        from_date="2026-10-01", to_date="2026-10-31",
        window_days=7, session=session(missing_cut=True),
    )
    assert result["status"] == "PENDING_CANONICAL_SALES"
    assert result["transactions_observed"] is None


def test_m2_worker_rejects_alias_collision_and_wrong_proof():
    for kwargs, expected in [
        ({"conflicting_alias": True}, "PENDING_ALIAS_CONFLICT"),
        ({"invalid_recipient": True}, "PENDING_PROVIDER_EVIDENCE"),
    ]:
        result = reconcile_sale_month(
            from_date="2026-10-01", to_date="2026-10-31",
            window_days=7, session=session(**kwargs),
        )
        assert result["status"] == expected


def test_proof_with_old_and_new_provider_snapshots_only_counts_new():
    c = child(1, 101, SENT_A)
    result = _proven_contacts(
        children=[c], recipients=[recipient(1, 1001)],
        snapshots=[
            snapshot(1, 101, 201, SENT_A - timedelta(days=1)),
            snapshot(1, 101, 202, SENT_A),
        ],
        observations=[observation(201, 1001), observation(202, 1001)],
    )
    assert [(entry.child_id, p) for entry, p in result] == [(101, PHONE)]


def test_gasca_group_excludes_wrong_branch_wrong_kind_and_nonmembership():
    rows = [
        sale(1, "549.00"),
        sale(2, "-50.00"),
        sale(3, "300.00", branch="OTHER"),
        sale(4, "500.00", kind="NUEVO"),
        sale(5, "100.00", desc="PENALIZACION"),
    ]
    tx, scanned = _group_gasca_orders(
        rows=rows,
        contact_identities={(PHONE, 16, "REACTIVACION")},
        branch_aliases={"AZAHARES": 16, "OTHER": 17},
        first=date(2026, 10, 1), last=date(2026, 10, 31),
        snapshot_id=300,
    )
    assert scanned == 5
    assert len(tx) == 1
    assert tx[0].amount_mxn == Decimal("499.00")


def test_gasca_unverifiable_branch_for_proven_phone_fails_closed():
    with pytest.raises(UniqueSalesEvidenceError, match="alias"):
        _group_gasca_orders(
            rows=[sale(branch="INVENTED")],
            contact_identities={(PHONE, 16, "REACTIVACION")},
            branch_aliases={"AZAHARES": 16},
            first=date(2026, 10, 1), last=date(2026, 10, 31),
            snapshot_id=300,
        )


def test_month_window_is_sale_date_based_and_covers_prior_month_contact():
    first, last, sent_start, sale_start, sale_end = _month_window(
        "2026-11-01", "2026-11-30", window_days=30,
    )
    assert (first, last) == (date(2026, 11, 1), date(2026, 11, 30))
    assert sent_start.astimezone(timezone.utc) < sale_start
    assert sale_start == datetime(2026, 11, 1, 7, tzinfo=timezone.utc)
    assert sale_end == datetime(2026, 12, 1, 8, tzinfo=timezone.utc)
    with pytest.raises(UniqueSalesEvidenceError):
        _month_window("2026-10-15", "2026-11-01", window_days=7)
