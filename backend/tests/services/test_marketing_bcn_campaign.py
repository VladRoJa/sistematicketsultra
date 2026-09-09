import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_reactivation_service as service


NOW = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)


def _decision(row_id, *, group, phone, status="CONTACT_HISTORY_UNKNOWN", reason="NO_OUTBOUND_EVIDENCE"):
    return {
        "vencido_row_id": row_id,
        "tarifa_group": group,
        "phone_mx10": phone,
        "status": status,
        "reason": reason,
        "campaign_eligibility": "REVIEW" if group == audience.BCN_GROUP else "EXCLUDED_TARIFF",
        "eligibility_reason": "REVIEW_TARIFF" if group == audience.BCN_GROUP else "TARIFF_EXCLUDED",
    }


def _plan(rows):
    return {
        "sources": {},
        "decision_rows": rows,
        "eligible_rows": [],
        "summary": {
            "total_candidates": len(rows),
            "eligible": 0,
            "excluded_active": 0,
            "excluded_invalid_phone": 0,
            "review_identity": 0,
            "duplicate_phone": 0,
            "excluded_tariff": sum(row["tarifa_group"] != audience.BCN_GROUP for row in rows),
            "domiciliated_flow": 0,
            "review_tariff": sum(row["tarifa_group"] == audience.BCN_GROUP for row in rows),
            "excluded_recent_campaign": 0,
            "review": sum(row["tarifa_group"] == audience.BCN_GROUP for row in rows),
        },
    }


def test_breakdown_separates_bcn_from_tariff_review():
    plan = _plan([
        _decision(1, group="EXCLUDE", phone="6861000001"),
        _decision(2, group=audience.BCN_GROUP, phone="6861000002"),
        _decision(3, group=audience.BCN_GROUP, phone="6861000003"),
    ])

    audience._add_campaign_breakdown(plan)
    audience._add_campaign_breakdown(plan)

    assert plan["summary"]["excluded_tariff_general"] == 1
    assert plan["summary"]["borron_cuenta_nueva"] == 2
    assert plan["summary"]["review_tariff"] == 0
    assert plan["summary"]["review"] == 0


def test_bcn_selector_keeps_only_safe_unique_bcn_phones():
    plan = _plan([
        _decision(1, group=audience.BCN_GROUP, phone="6861000001"),
        _decision(2, group=audience.BCN_GROUP, phone="6861000001"),
        _decision(3, group=audience.BCN_GROUP, phone=None),
        _decision(4, group=audience.BCN_GROUP, phone="6861000004", status="EXCLUDED_ACTIVE", reason="ACTIVE_CONFIRMED"),
        _decision(5, group="EXCLUDE", phone="6861000005"),
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
            _decision(1, group=audience.BCN_GROUP, phone="6861000001"),
            _decision(2, group="EXCLUDE", phone="6861000002"),
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


def test_alembic_graph_has_bcn_migration_as_single_head():
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

    assert revisions - parents == {"c1d4e7f9a2b3"}


def test_bcn_migration_expands_tariff_group_constraint():
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "c1d4e7f9a2b3_add_bcn_reactivation_group.py"
    source = path.read_text(encoding="utf-8")
    assert "BORRON_CUENTA_NUEVA" in source
    assert 'down_revision: str = "b9e2f7a4d3c5"' in source
