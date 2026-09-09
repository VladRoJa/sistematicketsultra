import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_reactivation_service as service


NOW = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)


def _decision(
    row_id,
    *,
    group="DOMICILIATED_FLOW",
    phone="6861000001",
    adeudo="100.00",
    status="CONTACT_HISTORY_UNKNOWN",
    reason="NO_OUTBOUND_EVIDENCE",
    campaign_eligibility="EXCLUDED_TARIFF",
    eligibility_reason="TARIFF_DOMICILIATED_FLOW",
):
    return {
        "vencido_row_id": row_id,
        "tarifa_group": group,
        "phone_mx10": phone,
        "adeudo": adeudo,
        "status": status,
        "reason": reason,
        "campaign_eligibility": campaign_eligibility,
        "eligibility_reason": eligibility_reason,
    }


def _plan(rows):
    return {
        "sources": {},
        "decision_rows": rows,
        "eligible_rows": [],
        "summary": {
            "total_candidates": len(rows),
            "eligible": 0,
            "excluded_active": sum(row["eligibility_reason"] == "ACTIVE_CONFIRMED" for row in rows),
            "excluded_invalid_phone": 0,
            "review_identity": sum(row["eligibility_reason"] == "REVIEW_IDENTITY" for row in rows),
            "duplicate_phone": 0,
            "excluded_tariff": sum(row["campaign_eligibility"] == "EXCLUDED_TARIFF" for row in rows),
            "excluded_tariff_general": 0,
            "domiciliated_flow": sum(row["eligibility_reason"] == "TARIFF_DOMICILIATED_FLOW" for row in rows),
            "borron_cuenta_nueva": 0,
            "review_tariff": sum(row["eligibility_reason"] == "REVIEW_TARIFF" for row in rows),
            "excluded_recent_campaign": 0,
            "review": sum(row["campaign_eligibility"] == "REVIEW" for row in rows),
        },
    }


def test_bcn_base_candidate_requires_domiciliated_positive_debt_and_safe_identity():
    eligible = _decision(1, adeudo="1250.50")
    no_debt = _decision(2, adeudo="0.00")
    negative_debt = _decision(3, adeudo="-10.00")
    active = _decision(
        4,
        adeudo="900.00",
        status="EXCLUDED_ACTIVE",
        reason="ACTIVE_CONFIRMED",
        campaign_eligibility="EXCLUDED_ACTIVE",
        eligibility_reason="ACTIVE_CONFIRMED",
    )
    identity_review = _decision(
        5,
        adeudo="500.00",
        status="REVIEW_ACTIVE_MATCH",
        reason="ACTIVE_REVIEW",
        campaign_eligibility="REVIEW",
        eligibility_reason="REVIEW_IDENTITY",
    )
    reactivate = _decision(
        6,
        group="REACTIVATE",
        adeudo="2000.00",
        campaign_eligibility="ELIGIBLE",
        eligibility_reason=None,
    )

    assert audience._is_bcn_base_candidate(eligible) is True
    assert audience._is_bcn_base_candidate(no_debt) is False
    assert audience._is_bcn_base_candidate(negative_debt) is False
    assert audience._is_bcn_base_candidate(active) is False
    assert audience._is_bcn_base_candidate(identity_review) is False
    assert audience._is_bcn_base_candidate(reactivate) is False


def test_breakdown_counts_bcn_as_subset_of_domiciliated_flow():
    plan = _plan([
        _decision(1, adeudo="100.00"),
        _decision(2, adeudo="0.00"),
        _decision(3, adeudo="50.00"),
        _decision(
            4,
            group="EXCLUDE",
            adeudo="1000.00",
            eligibility_reason="TARIFF_EXCLUDED",
        ),
    ])

    audience._add_campaign_breakdown(plan)

    assert plan["summary"]["domiciliated_flow"] == 3
    assert plan["summary"]["borron_cuenta_nueva"] == 2
    assert plan["summary"]["excluded_tariff_general"] == 1


def test_bcn_selector_keeps_only_positive_debt_unique_valid_phones():
    plan = _plan([
        _decision(1, phone="6861000001", adeudo="100.00"),
        _decision(2, phone="6861000001", adeudo="200.00"),
        _decision(3, phone=None, adeudo="300.00"),
        _decision(4, phone="6861000004", adeudo="0.00"),
        _decision(
            5,
            group="REACTIVATE",
            phone="6861000005",
            adeudo="999.00",
            campaign_eligibility="ELIGIBLE",
            eligibility_reason=None,
        ),
    ])

    audience._select_bcn_audience(plan)

    assert [row["vencido_row_id"] for row in plan["eligible_rows"]] == [1]
    assert plan["summary"]["eligible"] == 1
    assert plan["summary"]["duplicate_phone"] == 1
    assert plan["summary"]["excluded_invalid_phone"] == 1


class Query:
    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return NS(period_key="CANONICAL")


def test_bcn_template_reuses_expired_engine_with_explicit_day_range(monkeypatch):
    calls = {}
    monkeypatch.setattr(audience, "exported_counts", lambda *args, **kwargs: {})

    def expired(**kwargs):
        calls.update(kwargs)
        return _plan([
            _decision(1, phone="6861000001", adeudo="450.00"),
            _decision(2, phone="6861000002", adeudo="0.00"),
        ])

    result = audience.prepare_v1_plan(
        filters={
            "campaign_type": "BORRON_CUENTA_NUEVA",
            "dias_desde": 91,
            "dias_hasta": 365,
        },
        allowed_sucursal_keys=None,
        session=NS(query=lambda *args: Query()),
        now=NOW,
        active_builder=None,
        expired_builder=expired,
    )

    assert calls["date_from"] == NOW.date() - timedelta(days=365)
    assert calls["date_to"] == NOW.date() - timedelta(days=91)
    assert result["summary"]["borron_cuenta_nueva"] == 1
    assert result["summary"]["eligible"] == 1
    assert result["eligible_rows"][0]["vencido_row_id"] == 1


@pytest.mark.parametrize("lower,upper", [(None, None), (0, 365), (91, 90)])
def test_bcn_template_requires_valid_range(lower, upper):
    with pytest.raises(service.MarketingReactivationValidationError):
        audience.prepare_v1_plan(
            filters={
                "campaign_type": "BORRON_CUENTA_NUEVA",
                "dias_desde": lower,
                "dias_hasta": upper,
            },
            allowed_sucursal_keys=None,
            session=None,
            now=NOW,
            active_builder=None,
            expired_builder=None,
        )


def _assignment_value(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if name in targets:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    return None


def test_alembic_graph_has_corrective_bcn_migration_as_single_head():
    versions = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    revisions = set()
    parents = set()
    for path in versions.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = _assignment_value(tree, "revision")
        down_revision = _assignment_value(tree, "down_revision")
        if revision:
            revisions.add(revision)
        if isinstance(down_revision, str):
            parents.add(down_revision)
        elif down_revision:
            parents.update(down_revision)

    assert revisions - parents == {"d2e5f8a0b4c6"}


def test_corrective_migration_maps_legacy_bcn_group_back_to_domiciliated():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "d2e5f8a0b4c6_restore_reactivation_tariff_groups.py"
    )
    source = path.read_text(encoding="utf-8")
    assert 'down_revision: str = "c1d4e7f9a2b3"' in source
    assert "SET reactivation_group = 'DOMICILIATED_FLOW'" in source
    assert "WHERE reactivation_group = 'BORRON_CUENTA_NUEVA'" in source
