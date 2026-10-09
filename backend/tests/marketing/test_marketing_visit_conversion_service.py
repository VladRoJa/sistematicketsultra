from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.services.marketing_visit_conversion_service as visit_conversion_service
from app.services.marketing_attribution import SaleRecord
from app.services.marketing_sales_funnel_service import (
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    MarketingSalesFunnelLoadedData,
    _CommercialVisit,
    _IventasEvidence,
)
from app.services.marketing_visit_conversion_service import (
    VisitConversionRow,
    _build_attribution_visits_from_rows,
    _metric_matches,
    _serialize_detail_row,
    _serialize_metrics,
)


def _sale() -> SaleRecord:
    return SaleRecord(
        sale_key="sale:1",
        branch_id=4,
        payment_date=date(2026, 9, 10),
        phone="6861234567",
        member_id="123",
        revenue=Decimal("899"),
    )


def _row(
    *,
    event_key: str,
    origin: str | None,
    bought: bool,
) -> VisitConversionRow:
    return VisitConversionRow(
        event_key=event_key,
        branch_id=4,
        visit_date=date(2026, 9, 5),
        phone="6861234567",
        origin=origin,
        sale=_sale() if bought else None,
        sale_origin=origin if bought else None,
    )


def _visit_source_row(
    *,
    id_orden: str,
    visit_date: str,
    phone: str = "6861234567",
):
    return SimpleNamespace(
        id_orden=id_orden,
        folio=None,
        estatus="ACTIVO",
        descripcion="PASE RECORRIDO",
        fecha=visit_date,
        total=0,
        sucursal="Villas del Rey",
        telefono=phone,
    )


def test_serialize_metrics_splits_iventas_and_untraced_conversion():
    rows = [
        _row(
            event_key="iv-bought",
            origin=ORIGIN_IVENTAS_META,
            bought=True,
        ),
        _row(
            event_key="iv-not-bought",
            origin=ORIGIN_IVENTAS_META,
            bought=False,
        ),
        _row(
            event_key="untraced-bought",
            origin=None,
            bought=True,
        ),
        _row(
            event_key="untraced-not-bought-1",
            origin=None,
            bought=False,
        ),
        _row(
            event_key="untraced-not-bought-2",
            origin=None,
            bought=False,
        ),
    ]

    metrics = _serialize_metrics(rows)

    assert metrics["visits_iventas_bought"] == 1
    assert metrics["visits_iventas_not_bought"] == 1
    assert metrics["visits_not_iventas_bought"] == 1
    assert metrics["visits_not_iventas_not_bought"] == 2
    assert metrics["iventas_visit_conversion_rate"] == 0.5
    assert metrics["not_iventas_visit_conversion_rate"] == 1 / 3


def test_metric_filters_match_each_visit_conversion_bucket():
    iventas_bought = _row(
        event_key="iv-bought",
        origin=ORIGIN_IVENTAS_META,
        bought=True,
    )
    untraced_not_bought = _row(
        event_key="untraced-not-bought",
        origin=None,
        bought=False,
    )

    assert _metric_matches(
        iventas_bought,
        "visits_iventas_bought",
    )
    assert not _metric_matches(
        iventas_bought,
        "visits_iventas_not_bought",
    )
    assert _metric_matches(
        untraced_not_bought,
        "visits_not_iventas_not_bought",
    )
    assert not _metric_matches(
        untraced_not_bought,
        "visits_not_iventas_bought",
    )


def test_build_attribution_visits_reuses_rows_without_collapsing_repeat_visits():
    rows = [
        _visit_source_row(id_orden="100", visit_date="2026-09-05"),
        _visit_source_row(id_orden="101", visit_date="2026-09-12"),
        _visit_source_row(
            id_orden="102",
            visit_date="2026-09-15",
            phone="",
        ),
    ]

    events = _build_attribution_visits_from_rows(
        rows=rows,
        month_start=date(2026, 9, 1),
        branch_ids=(4,),
        alias_map={"VILLAS DEL REY": 4},
    )

    assert len(events) == 2
    assert [event.visit_date for event in events] == [
        date(2026, 9, 5),
        date(2026, 9, 12),
    ]
    assert {event.event_key for event in events} == {
        "id_orden:100",
        "id_orden:101",
    }


def test_summary_from_loaded_data_reuses_funnel_rows_and_evidence(monkeypatch):
    source_row = _visit_source_row(
        id_orden="100",
        visit_date="2026-09-05",
    )
    loaded = MarketingSalesFunnelLoadedData(
        month_start=date(2026, 9, 1),
        branch_ids=(4,),
        venta_total_rows=(source_row,),
        alias_map={"VILLAS DEL REY": 4},
        visits=(
            _CommercialVisit(
                event_key="id_orden:4:100",
                branch_id=4,
                visit_date=date(2026, 9, 5),
                phone="6861234567",
            ),
        ),
        evidence={
            (4, "6861234567"): [
                _IventasEvidence(
                    branch_id=4,
                    phone="6861234567",
                    interaction_date=date(2026, 9, 1),
                    has_meta_ad=True,
                )
            ]
        },
    )

    monkeypatch.setattr(
        visit_conversion_service,
        "_load_attribution_sales",
        lambda **_: SimpleNamespace(
            sales=(_sale(),),
            snapshot_ids=(77,),
        ),
    )
    monkeypatch.setattr(
        visit_conversion_service,
        "_load_iventas_data",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("No debe recargar iVentas")
        ),
    )
    monkeypatch.setattr(
        visit_conversion_service,
        "_select_venta_total_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("No debe reseleccionar Venta Total")
        ),
    )

    result = (
        visit_conversion_service.build_visit_conversion_summary_from_loaded_data(
            loaded=loaded,
        )
    )

    assert result["summary"]["visits_iventas_bought"] == 1
    assert result["summary"]["visits_iventas_not_bought"] == 0
    assert result["summary"]["iventas_visit_conversion_rate"] == 1
    assert result["data_quality"]["visit_conversion_sales_snapshot_ids"] == [77]


def test_direct_purchase_without_crm_is_a_bought_untraced_visit(monkeypatch):
    loaded = MarketingSalesFunnelLoadedData(
        month_start=date(2026, 9, 1),
        branch_ids=(4,),
        venta_total_rows=None,
        alias_map={},
        visits=(
            _CommercialVisit(
                event_key="direct_purchase:4:6869999999",
                branch_id=4,
                visit_date=date(2026, 9, 10),
                phone="6869999999",
                kind=visit_conversion_service.VISIT_KIND_DIRECT_PURCHASE,
                sale_key="id_socio:999",
                sale_member_id="999",
                sale_revenue=Decimal("699"),
            ),
        ),
        evidence={},
    )
    monkeypatch.setattr(
        visit_conversion_service,
        "_load_attribution_sales",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("Compra directa no necesita reconciliar otra venta")
        ),
    )

    result = (
        visit_conversion_service.build_visit_conversion_summary_from_loaded_data(
            loaded=loaded,
        )
    )

    assert result["summary"]["visits_not_iventas_bought"] == 1
    assert result["summary"]["visits_not_iventas_not_bought"] == 0


def test_direct_purchase_detail_uses_business_friendly_label():
    row = VisitConversionRow(
        event_key="direct_purchase:4:6869999999",
        branch_id=4,
        visit_date=date(2026, 9, 10),
        phone="6869999999",
        origin=None,
        sale=_sale(),
        visit_kind=visit_conversion_service.VISIT_KIND_DIRECT_PURCHASE,
    )

    detail = _serialize_detail_row(row, {4: "Tec Mexicali"})

    assert detail["visit_type"] == "Compra directa"
    assert detail["source"] == "Venta Nueva sin pase registrado"


def test_summary_from_loaded_data_preserves_missing_venta_total(monkeypatch):
    loaded = MarketingSalesFunnelLoadedData(
        month_start=date(2026, 9, 1),
        branch_ids=(4,),
        venta_total_rows=None,
        alias_map={},
        visits=(),
        evidence={},
    )
    monkeypatch.setattr(
        visit_conversion_service,
        "_load_attribution_sales",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("No debe cargar ventas sin Venta Total")
        ),
    )

    result = (
        visit_conversion_service.build_visit_conversion_summary_from_loaded_data(
            loaded=loaded,
        )
    )

    assert result["summary"]["visits_iventas_bought"] == 0
    assert result["summary"]["visits_not_iventas_bought"] == 0
    assert result["data_quality"]["visit_conversion_cohort_complete"] is False


def test_sale_origin_matches_contact_between_visit_and_purchase(monkeypatch):
    """Pase 5/oct, contacto CRM 6/oct, compra 7/oct: venta CRM, pase no."""
    source = _visit_source_row(id_orden="200", visit_date="2026-10-05")
    loaded = MarketingSalesFunnelLoadedData(
        month_start=date(2026, 10, 1),
        branch_ids=(4,),
        venta_total_rows=(source,),
        alias_map={"VILLAS DEL REY": 4},
        visits=(
            _CommercialVisit(
                event_key="id_orden:4:200",
                branch_id=4,
                visit_date=date(2026, 10, 5),
                phone="6861234567",
            ),
        ),
        evidence={
            (4, "6861234567"): [
                _IventasEvidence(
                    branch_id=4,
                    phone="6861234567",
                    interaction_date=date(2026, 10, 6),
                    has_meta_ad=False,
                ),
            ],
        },
    )
    sale = SaleRecord(
        sale_key="sale:oct",
        branch_id=4,
        payment_date=date(2026, 10, 7),
        phone="6861234567",
        member_id="456",
        revenue=Decimal("599"),
    )
    monkeypatch.setattr(
        visit_conversion_service,
        "_load_attribution_sales",
        lambda **_: SimpleNamespace(sales=(sale,), snapshot_ids=(90,)),
    )

    bundle = visit_conversion_service._build_bundle_from_loaded_data(
        loaded=loaded,
    )
    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.origin is None
    assert row.sale_origin == ORIGIN_IVENTAS_OTHER
    assert row.sale == sale
    assert _serialize_detail_row(row, {4: "Villas del Rey"})["sale_origin"] == (
        "iVentas / Otro"
    )
    # El origen del pase se audita, pero la compra cambia la cohorte efectiva.
    metrics = _serialize_metrics(list(bundle.rows))
    assert metrics["visits_iventas_bought"] == 1
    assert metrics["visits_not_iventas_bought"] == 0
    assert metrics["visits_iventas"] == 1
    assert metrics["visits_not_iventas"] == 0

    from app.services.marketing_sales_funnel_cutoff_detail_service import (
        _normalized_visit_conversion_bundle,
    )

    earlier_cutoff = _normalized_visit_conversion_bundle(
        loaded=loaded,
        cutoff_date=date(2026, 10, 6),
    )
    assert earlier_cutoff.rows[0].sale is None
    assert earlier_cutoff.rows[0].sale_origin is None


def test_sale_origin_does_not_match_contact_after_purchase(monkeypatch):
    source = _visit_source_row(id_orden="201", visit_date="2026-10-05")
    loaded = MarketingSalesFunnelLoadedData(
        month_start=date(2026, 10, 1),
        branch_ids=(4,),
        venta_total_rows=(source,),
        alias_map={"VILLAS DEL REY": 4},
        visits=(
            _CommercialVisit(
                event_key="id_orden:4:201",
                branch_id=4,
                visit_date=date(2026, 10, 5),
                phone="6861234567",
            ),
        ),
        evidence={
            (4, "6861234567"): [
                _IventasEvidence(
                    branch_id=4,
                    phone="6861234567",
                    interaction_date=date(2026, 10, 8),
                    has_meta_ad=False,
                ),
            ],
        },
    )
    monkeypatch.setattr(
        visit_conversion_service,
        "_load_attribution_sales",
        lambda **_: SimpleNamespace(
            sales=(
                SaleRecord(
                    sale_key="sale:early",
                    branch_id=4,
                    payment_date=date(2026, 10, 7),
                    phone="6861234567",
                    member_id="457",
                    revenue=Decimal("599"),
                ),
            ),
            snapshot_ids=(91,),
        ),
    )

    row = visit_conversion_service._build_bundle_from_loaded_data(
        loaded=loaded,
    ).rows[0]
    assert row.sale is not None
    assert row.origin is None
    assert row.sale_origin is None
    assert _serialize_detail_row(row, {4: "Villas del Rey"})["sale_origin"] == (
        "Sin match iVentas"
    )


def test_reclassification_preserves_total_and_moves_six_bought_visits():
    """54 visitas: 6 compraron tras contacto CRM, sin duplicar compradores."""
    rows = []
    def add(count, *, visit_origin, bought, purchase_origin=None):
        for _ in range(count):
            rows.append(
                VisitConversionRow(
                    event_key=f"visit:{len(rows)}",
                    branch_id=9,
                    visit_date=date(2026, 10, 5),
                    phone="6633298580",
                    origin=visit_origin,
                    sale=_sale() if bought else None,
                    sale_origin=purchase_origin,
                )
            )

    add(3, visit_origin=ORIGIN_IVENTAS_META, bought=True,
        purchase_origin=ORIGIN_IVENTAS_META)
    add(8, visit_origin=ORIGIN_IVENTAS_META, bought=False)
    add(6, visit_origin=None, bought=True,
        purchase_origin=ORIGIN_IVENTAS_OTHER)
    add(4, visit_origin=None, bought=True)
    add(33, visit_origin=None, bought=False)

    metrics = _serialize_metrics(rows)
    assert metrics["visits_total"] == 54
    assert metrics["visits_iventas"] == 17
    assert metrics["visits_iventas_bought"] == 9
    assert metrics["visits_iventas_not_bought"] == 8
    assert metrics["visits_not_iventas"] == 37
    assert metrics["visits_not_iventas_bought"] == 4
    assert metrics["visits_not_iventas_not_bought"] == 33
    assert metrics["visits_iventas_meta"] == 11
    assert metrics["visits_iventas_other"] == 6
    assert metrics["iventas_visit_conversion_rate"] == 9 / 17
    assert metrics["not_iventas_visit_conversion_rate"] == 4 / 37
    assert sum(metrics[key] for key in (
        "visits_iventas_bought", "visits_iventas_not_bought",
        "visits_not_iventas_bought", "visits_not_iventas_not_bought",
    )) == metrics["visits_total"]


def test_nonbuyer_stays_in_visit_cohort_and_sale_without_crm_is_untraced():
    crm_visit_without_sale = VisitConversionRow(
        event_key="crm-no-sale",
        branch_id=9,
        visit_date=date(2026, 10, 5),
        phone="6633298580",
        origin=ORIGIN_IVENTAS_META,
        sale=None,
    )
    expired_crm_at_purchase = VisitConversionRow(
        event_key="crm-sale-no-match",
        branch_id=9,
        visit_date=date(2026, 10, 5),
        phone="6633298580",
        origin=ORIGIN_IVENTAS_META,
        sale=_sale(),
        sale_origin=None,
    )
    assert _metric_matches(
        crm_visit_without_sale, "visits_iventas_not_bought"
    )
    assert _metric_matches(
        expired_crm_at_purchase, "visits_not_iventas_bought"
    )
    assert expired_crm_at_purchase.origin == ORIGIN_IVENTAS_META


def test_cutoff_visit_drilldowns_follow_effective_purchase_origin(monkeypatch):
    from app.services.marketing_sales_funnel_cutoff_detail_service import (
        _visit_rows,
    )
    rows = (
        VisitConversionRow(
            event_key="reclassified",
            branch_id=9,
            visit_date=date(2026, 10, 5),
            phone="6633298580",
            origin=None,
            sale=SaleRecord(
                sale_key="purchase",
                branch_id=9,
                payment_date=date(2026, 10, 7),
                phone="6633298580",
                member_id="388624",
                revenue=Decimal("599"),
            ),
            sale_origin=ORIGIN_IVENTAS_OTHER,
        ),
    )
    from app.services.marketing_sales_funnel_cutoff_detail_service import (
        VisitConversionBundle, 
    )
    import app.services.marketing_sales_funnel_cutoff_detail_service as cutoff
    monkeypatch.setattr(
        cutoff,
        "_normalized_visit_conversion_bundle",
        lambda **_: VisitConversionBundle(
            rows=rows, sales_snapshot_ids=(), cohort_complete=False
        ),
    )
    filtered = _visit_rows(
        cutoff_date=date(2026, 10, 9),
        metric="visits_iventas",
        branch_names={9: "Paseo 2000"},
        branch_id_filter=None,
        loaded=None,
    )
    assert len(filtered) == 1
    assert filtered[0]["origin"] == "iVentas / Otro"
    assert filtered[0]["visit_origin"] == "Sin match iVentas"
    assert filtered[0]["sale_origin"] == "iVentas / Otro"
    assert _visit_rows(
        cutoff_date=date(2026, 10, 9),
        metric="visits_not_iventas",
        branch_names={9: "Paseo 2000"},
        branch_id_filter=None,
        loaded=None,
    ) == []
    assert _visit_rows(
        cutoff_date=date(2026, 10, 9),
        metric="visits_iventas",
        branch_names={9: "Paseo 2000"},
        branch_id_filter=10,
        loaded=None,
    ) == []
