from datetime import date

import app.services.marketing_sales_funnel_cutoff_detail_service as service


def _base():
    return {
        "month": "2026-09",
        "month_start": date(2026, 9, 1),
        "cutoff_date": "2026-09-30",
        "selected_cutoff": date(2026, 9, 30),
        "scope": "branch_scope",
        "branch_ids": (1,),
        "branch_names": {1: "Sucursal 1"},
        "iventas_sync_run_id": 99,
        "rows": [
            {
                "branch_id": 1,
                "branch": "Sucursal 1",
                "date": "2026-09-05",
                "name": "Lead Uno",
                "phone": "6861234567",
                "contact_id": "contact-1",
                "channel": "WhatsApp",
                "origin": "iVentas / Meta Ads",
            },
            {
                "branch_id": 1,
                "branch": "Sucursal 1",
                "date": "2026-09-06",
                "name": "Lead Dos",
                "phone": "6867654321",
                "contact_id": "contact-2",
                "channel": "WhatsApp",
                "origin": "iVentas / Meta Ads",
            },
        ],
    }


def _enriched(rows):
    result = []
    for row in rows:
        item = dict(row)
        item["bought"] = row["contact_id"] == "contact-2"
        item["purchase_status"] = "Sí" if item["bought"] else "No"
        result.append(item)
    return result


def test_portfolio_uses_first_message_date_as_source_date(monkeypatch):
    monkeypatch.setattr(
        service,
        "_resolve_leads_meta_cutoff_base",
        lambda **_kwargs: _base(),
    )
    monkeypatch.setattr(
        service,
        "_enrich_leads_meta_cutoff_rows",
        lambda *, base, rows: _enriched(rows),
    )

    result = service.build_marketing_funnel_portfolio_at_cutoff(
        month="2026-09",
        cutoff_date="2026-09-30",
        access=object(),
    )

    assert result["rows"][0]["source_date"] == "2026-09-05"
    assert result["rows"][0]["bought"] is False
    assert result["buyer_excluded"][0]["bought"] is True


def test_same_month_and_cutoff_produce_same_portfolio(monkeypatch):
    monkeypatch.setattr(
        service,
        "_resolve_leads_meta_cutoff_base",
        lambda **_kwargs: _base(),
    )
    monkeypatch.setattr(
        service,
        "_enrich_leads_meta_cutoff_rows",
        lambda *, base, rows: _enriched(rows),
    )

    first = service.build_marketing_funnel_portfolio_at_cutoff(
        month="2026-09",
        cutoff_date="2026-09-30",
        access=object(),
    )
    second = service.build_marketing_funnel_portfolio_at_cutoff(
        month="2026-09",
        cutoff_date="2026-09-30",
        access=object(),
    )

    assert first == second
    assert first["funnel_month"] == "2026-09"
    assert first["funnel_cutoff_date"] == "2026-09-30"
    assert first["iventas_sync_run_id"] == 99


def test_portfolio_preserves_resolved_scope(monkeypatch):
    base = _base()
    base["scope"] = {"kind": "branch", "branch_ids": [1]}
    monkeypatch.setattr(
        service,
        "_resolve_leads_meta_cutoff_base",
        lambda **_kwargs: base,
    )
    monkeypatch.setattr(
        service,
        "_enrich_leads_meta_cutoff_rows",
        lambda *, base, rows: _enriched(rows),
    )

    result = service.build_marketing_funnel_portfolio_at_cutoff(
        month="2026-09",
        cutoff_date="2026-09-30",
        access=object(),
    )

    assert result["scope"] == {"kind": "branch", "branch_ids": [1]}
    assert {row["sucursal_id"] for row in result["rows"]} == {1}



def test_portfolio_requires_explicit_cutoff():
    try:
        service.build_marketing_funnel_portfolio_at_cutoff(
            month="2026-09",
            cutoff_date=None,
            access=object(),
        )
    except service.MarketingSalesFunnelDetailValidationError as exc:
        assert "cutoff_date es obligatorio" in str(exc)
    else:
        raise AssertionError("La cartera Funnel debe exigir cutoff explícito.")



def test_portfolio_resolver_uses_visible_branch_scope(monkeypatch):
    from types import SimpleNamespace

    seen = {}

    monkeypatch.setattr(
        service,
        "load_visible_marketing_branches",
        lambda _access: (
            [SimpleNamespace(sucursal_id=7, name="Sucursal 7")],
            (7,),
            {"kind": "branch", "branch_ids": [7]},
        ),
    )
    monkeypatch.setattr(
        service,
        "resolve_funnel_cutoff",
        lambda **_kwargs: (date(2026, 9, 30), (date(2026, 9, 30),)),
    )
    monkeypatch.setattr(
        service,
        "_select_exact_iventas_run",
        lambda *_args: SimpleNamespace(id=99),
    )

    def fake_lead_rows(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(service, "_lead_contact_rows", fake_lead_rows)

    result = service._resolve_leads_meta_cutoff_base(
        month="2026-09",
        cutoff_date="2026-09-30",
        access=object(),
        branch_id=None,
    )

    assert seen["branch_ids"] == (7,)
    assert seen["iventas_run_id"] == 99
    assert seen["meta_only"] is True
    assert result["scope"] == {"kind": "branch", "branch_ids": [7]}
