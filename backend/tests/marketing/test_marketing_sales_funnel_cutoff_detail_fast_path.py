from io import BytesIO

import app.services.marketing_sales_funnel_cutoff_detail_service as service


def _unexpected_full_funnel_path(**_kwargs):
    raise AssertionError(
        "leads_meta no debe reconstruir el funnel completo en el detalle de corte"
    )


def test_leads_meta_cutoff_detail_uses_fast_path(monkeypatch):
    expected = {
        "metric": "leads_meta",
        "kind": "leads",
        "rows": [],
    }

    monkeypatch.setattr(
        service,
        "_build_leads_meta_cutoff_detail_fast",
        lambda **_kwargs: expected,
    )
    monkeypatch.setattr(
        service,
        "_resolve_detail_rows",
        _unexpected_full_funnel_path,
    )

    result = service.build_marketing_sales_funnel_cutoff_detail(
        month="2026-09",
        cutoff_date="2026-09-20",
        access=object(),
        metric="leads_meta",
    )

    assert result is expected


def test_leads_meta_cutoff_export_uses_fast_path(monkeypatch):
    expected = (BytesIO(b"xlsx"), "leads_meta.xlsx")

    monkeypatch.setattr(
        service,
        "_build_leads_meta_cutoff_export_fast",
        lambda **_kwargs: expected,
    )
    monkeypatch.setattr(
        service,
        "_resolve_detail_rows",
        _unexpected_full_funnel_path,
    )

    result = service.build_marketing_sales_funnel_cutoff_export(
        month="2026-09",
        cutoff_date="2026-09-20",
        access=object(),
        metric="leads_meta",
    )

    assert result is expected
