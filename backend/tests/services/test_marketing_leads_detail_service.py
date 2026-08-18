from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

import app.services.marketing_leads_detail_service as service
from app.services.marketing_access import MarketingAccess


def _contact(contact_row_id=1, branch_id=7):
    return {
        "contact_row_id": contact_row_id,
        "sucursal_id": branch_id,
        "contact_id": f"contact-{contact_row_id}",
        "name": "Lead Uno",
        "phone_mx10": "6641234567",
        "phone_digits": "526641234567",
        "first_message_at_local": datetime(2026, 8, 3, 10, 30),
        "first_message_date_local": date(2026, 8, 3),
        "channel_name": "Facebook",
        "channel_platform": "META",
    }


def test_contact_with_one_meta_ad_produces_one_masked_row():
    rows = service._build_marketing_lead_rows(
        contact_rows=[_contact()],
        tag_rows=[
            {"iventas_contact_row_id": 1, "meta_ad_id": "ad-1"}
        ],
        meta_rows=[],
        branch_names={7: "Centro"},
    )

    assert len(rows) == 1
    assert rows[0]["meta_ad_ids"] == ["ad-1"]
    assert rows[0]["telefono"] == "*** *** 4567"
    assert "6641234567" not in rows[0]["telefono"]


def test_contact_with_three_meta_ads_stays_one_row():
    rows = service._build_marketing_lead_rows(
        contact_rows=[_contact()],
        tag_rows=[
            {"iventas_contact_row_id": 1, "meta_ad_id": "ad-1"},
            {"iventas_contact_row_id": 1, "meta_ad_id": "ad-2"},
            {"iventas_contact_row_id": 1, "meta_ad_id": "ad-3"},
        ],
        meta_rows=[],
        branch_names={7: "Centro"},
    )

    assert len(rows) == 1
    assert rows[0]["meta_ad_ids"] == ["ad-1", "ad-2", "ad-3"]


def test_missing_meta_enrichment_never_removes_lead():
    rows = service._build_marketing_lead_rows(
        contact_rows=[_contact()],
        tag_rows=[
            {"iventas_contact_row_id": 1, "meta_ad_id": "unknown"}
        ],
        meta_rows=[],
        branch_names={7: "Centro"},
    )

    assert len(rows) == 1
    assert rows[0]["campaign_names"] == []
    assert rows[0]["meta_enrichment_available"] is False


def test_partial_meta_enrichment_keeps_unknown_ad_id():
    rows = service._build_marketing_lead_rows(
        contact_rows=[_contact()],
        tag_rows=[
            {"iventas_contact_row_id": 1, "meta_ad_id": "known"},
            {"iventas_contact_row_id": 1, "meta_ad_id": "unknown"},
        ],
        meta_rows=[
            {
                "ad_id": "known",
                "campaign_name": "Campaña Centro",
                "ad_name": "Anuncio A",
            }
        ],
        branch_names={7: "Centro"},
    )

    assert rows[0]["meta_ad_ids"] == ["known", "unknown"]
    assert rows[0]["campaign_names"] == ["Campaña Centro"]


def test_lead_statement_requires_first_message_meta_tag_and_scope():
    statement = service.build_marketing_lead_contacts_statement(
        iventas_sync_run_id=22,
        branch_ids=(7,),
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "sync_run_id = 22" in sql
    assert "sucursal_id in (7)" in sql
    assert "first_message_at_utc is not null" in sql
    assert "exists" in sql
    assert "tag_kind = 'meta_ad'" in sql


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _Session:
    def __init__(self, results):
        self.results = iter(results)

    def execute(self, _statement):
        return _Result(next(self.results))


def test_detail_summary_equals_rows_for_selected_scope(monkeypatch):
    access = MarketingAccess(
        type="PRIMARY_BRANCH",
        is_global=False,
        branch_ids=(7,),
        role="GERENTE",
        can_edit_inputs=False,
    )
    monkeypatch.setattr(
        service,
        "resolve_marketing_detail_scope",
        lambda **_: (
            [SimpleNamespace(sucursal_id=7, name="Centro")],
            (7,),
            {"type": "PRIMARY_BRANCH", "branch_ids": [7]},
        ),
    )
    monkeypatch.setattr(
        service,
        "read_iventas_dashboard_month_data",
        lambda **_: SimpleNamespace(
            available=True,
            sync_run_id=22,
            period_key="IVENTAS-2026-08",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 17),
        ),
    )
    session = _Session(
        [
            [_contact(1), _contact(2)],
            [
                {"iventas_contact_row_id": 1, "meta_ad_id": "ad-1"},
                {"iventas_contact_row_id": 2, "meta_ad_id": "ad-2"},
            ],
            [],
        ]
    )

    detail = service.build_marketing_leads_detail(
        month="2026-08",
        access=access,
        today=date(2026, 8, 17),
        session=session,
    )

    assert detail["summary"]["leads"] == 2
    assert len(detail["rows"]) == 2
    assert {row["sucursal_id"] for row in detail["rows"]} == {7}
