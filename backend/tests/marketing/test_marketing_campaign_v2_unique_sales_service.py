"""M2 first slice: deterministic exclusive revenue assignment; no DB or PII export."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.marketing_campaign_v2_unique_sales_service import (
    ATTRIBUTION_RULE_VERSION,
    CanonicalMembershipTransaction,
    ProvenContact,
    UniqueSalesEvidenceError,
    allocate_unique_membership_sales,
)


UTC = timezone.utc
T0 = datetime(2026, 10, 21, 16, 0, tzinfo=UTC)
PHONE = "6861234567"
OTHER = "6861234568"


def contact(campaign=1, child=10, when=T0, branch=1,
            phone=PHONE, kind="REACTIVACION"):
    return ProvenContact(
        campaign_id=campaign, child_id=child,
        provider_campaign_id=f"provider-{child}",
        branch_id=branch, phone_mx10=phone,
        sale_kind=kind, submitted_at=when,
    )


def purchase(key="order:abc", when=T0 + timedelta(days=3), amount="599.00",
             branch=1, phone=PHONE, kind="REACTIVACION", snapshot=40):
    return CanonicalMembershipTransaction(
        transaction_key=key, branch_id=branch,
        phone_mx10=phone, sale_kind=kind,
        occurred_at=when, amount_mxn=Decimal(amount),
        venta_total_snapshot_id=snapshot,
    )


def run(contacts, sales, window=7):
    return allocate_unique_membership_sales(
        contacts=contacts, transactions=sales, window_days=window,
    )


def test_same_sale_after_two_campaigns_is_not_counted_twice():
    first = contact(campaign=1, child=11)
    second = contact(campaign=2, child=22, when=T0 + timedelta(days=1))
    result = run([first, second], [purchase()])
    assert result["rule_version"] == ATTRIBUTION_RULE_VERSION
    assert result["transactions_observed"] == 1
    assert result["revenue_observed_mxn"] == "599.00"
    assert result["campaigns"] == [
        {"campaign_id": 1, "buyers_observed": 0, "transactions_observed": 0,
         "revenue_observed_mxn": "0.00", "assisted_transactions": 1},
        {"campaign_id": 2, "buyers_observed": 1, "transactions_observed": 1,
         "revenue_observed_mxn": "599.00", "assisted_transactions": 0},
    ]
    assert result["allocations_private"][0]["campaign_id"] == 2
    assert result["allocations_private"][0]["assisted_campaign_ids"] == [1]
    assert PHONE not in repr(result)


def test_cumulative_canonical_snapshots_do_not_duplicate_an_order():
    s = purchase()
    other_cut = replace(s, venta_total_snapshot_id=41)
    result = run([contact()], [s, other_cut])
    assert result["transactions_seen"] == 1
    assert result["duplicate_transaction_rows_ignored"] == 1
    assert result["transactions_observed"] == 1
    assert result["revenue_observed_mxn"] == "599.00"
    assert result["allocations_private"][0]["venta_total_snapshot_id"] == 41


def test_conflicting_snapshot_amount_or_timestamp_fails_closed():
    s = purchase()
    for bad in [
        replace(s, amount_mxn=Decimal("699.00"), venta_total_snapshot_id=41),
        replace(s, occurred_at=s.occurred_at + timedelta(minutes=1)),
    ]:
        with pytest.raises(UniqueSalesEvidenceError, match="reconciliar"):
            run([contact()], [s, bad])


def test_purchases_before_submission_or_outside_window_are_unmatched():
    sales = [
        purchase("order:before", when=T0 - timedelta(seconds=1)),
        purchase("order:same", when=T0),
        purchase("order:late", when=T0 + timedelta(days=31)),
    ]
    result = run([contact()], sales, window=30)
    assert result["transactions_seen"] == 3
    assert result["transactions_observed"] == 0
    assert result["transactions_unmatched"] == 3
    assert result["revenue_observed_mxn"] == "0.00"


def test_windows_boundary_cross_month_and_timezone_aware_comparison():
    sent = datetime(2026, 10, 30, 20, tzinfo=UTC)
    sale = purchase(when=sent + timedelta(days=14))
    c = contact(when=sent)
    assert run([c], [sale], window=7)["transactions_observed"] == 0
    assert run([c], [sale], window=14)["transactions_observed"] == 1
    assert run([c], [sale], window=30)["transactions_observed"] == 1
    # Equivalent aware timestamp in another zone compares identically.
    assert run([c], [replace(sale, occurred_at=sale.occurred_at.astimezone(
        timezone(timedelta(hours=-8))
    ))], window=14)["transactions_observed"] == 1


def test_sale_kind_and_branch_must_match_contact():
    touches = [
        contact(campaign=1, child=11, kind="NUEVO"),
        contact(campaign=2, child=22, branch=2),
    ]
    result = run(touches, [purchase()])
    assert result["transactions_observed"] == 0
    assert result["transactions_unmatched"] == 1


def test_deterministic_tie_breaker_when_two_contacts_have_same_second():
    result = run(
        [contact(campaign=3, child=15), contact(campaign=2, child=18),
         contact(campaign=1, child=10)],
        [purchase()],
    )
    assert result["allocations_private"][0]["campaign_id"] == 2
    assert result["allocations_private"][0]["assisted_campaign_ids"] == [1, 3]


def test_buyer_unique_per_campaign_even_with_multiple_orders():
    r = run([contact()], [purchase("order:one", amount="599.00"),
                          purchase("order:two", amount="299.00")])
    assert r["campaigns"][0]["buyers_observed"] == 1
    assert r["campaigns"][0]["transactions_observed"] == 2
    assert r["revenue_observed_mxn"] == "898.00"


@pytest.mark.parametrize("invalid", [
    replace(contact(), phone_mx10="123"),
    replace(contact(), submitted_at=datetime(2026, 10, 21)),
    replace(contact(), campaign_id=0),
    replace(contact(), sale_kind="RENOVACION"),
    replace(contact(), provider_campaign_id=""),
])
def test_unproven_contact_fields_fail_closed(invalid):
    with pytest.raises(UniqueSalesEvidenceError):
        run([invalid], [purchase()])


@pytest.mark.parametrize("invalid", [
    replace(purchase(), amount_mxn=Decimal("-5.00")),
    replace(purchase(), amount_mxn=Decimal("12.345")),
    replace(purchase(), transaction_key=""),
    replace(purchase(), occurred_at=datetime(2026, 10, 21)),
    replace(purchase(), venta_total_snapshot_id=0),
])
def test_unsupported_purchase_evidence_fails_closed(invalid):
    with pytest.raises(UniqueSalesEvidenceError):
        run([contact()], [invalid])


def test_only_supported_windows_and_prevalidated_source_claims():
    for invalid in (0, 8, 100, True, "7"):
        with pytest.raises(UniqueSalesEvidenceError):
            run([], [], window=invalid)
    assert run([], [], window=7)["status"] == "EVIDENCE_PREVALIDATED"
