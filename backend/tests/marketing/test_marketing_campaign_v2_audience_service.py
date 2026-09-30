from __future__ import annotations

from datetime import date, datetime
import inspect
from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_v2_audience_service as service


def _candidate(
    row_id: int,
    *,
    tariff: str | None = "DOM",
    phone: str | None = None,
    branch: str = "BRANCH A",
    name: str | None = None,
    source: str = service.SOURCE_EXPIRED_MEMBERS,
):
    return service.MarketingCampaignV2AudienceCandidate(
        source=source,
        source_ref_type=(
            "SOCIOS_VENCIDOS_CARTERA"
            if source == service.SOURCE_EXPIRED_MEMBERS
            else "SOCIOS_ACTIVOS_SNAPSHOT_ROW"
        ),
        source_ref_id=row_id,
        source_snapshot_id=(7 if source == service.SOURCE_ACTIVE_MEMBERS else None),
        phone_raw=phone,
        phone_mx10=phone,
        member_id=(f"SOCIO-{row_id}" if source == service.SOURCE_ACTIVE_MEMBERS else None),
        member_pin=f"PIN-{row_id}",
        member_name=name or f"Socio {row_id}",
        sucursal=branch,
        sucursal_key=branch,
        tarifa_raw=tariff,
        fecha_vencimiento=date(2026, 8, 15),
        current_status=(
            service.current_status.STATUS_NOT_FOUND
            if source == service.SOURCE_EXPIRED_MEMBERS
            else None
        ),
    )


def _source_result(candidates, *, blocked=(), universe=None, scoped=None, metadata=None):
    rows = tuple(candidates)
    return service._SourceLoadResult(
        universe_count=len(rows) if universe is None else universe,
        scoped_count=len(rows) if scoped is None else scoped,
        candidates=rows,
        current_status_blocked=tuple(blocked),
        current_status_counts={},
        metadata=metadata or {"fixture": True},
    )


def _catalog():
    return {
        "DOM": ("Domiciliado", "DOMICILIADO"),
        "TRI": ("Trimestre", "TRIMESTRAL"),
        "CON": ("Convenio", "CONVENIO"),
        "SEM": ("Semestre", "SEMESTRE"),
        "EST": ("Estudiante", "ESTUDIANTE"),
        "MES": ("Semana", "MES"),
        "OUT": ("Agregadora", "OUT_OF_SEGMENT"),
    }


def _install(monkeypatch, candidates, *, source=service.SOURCE_EXPIRED_MEMBERS, blocked=()):
    result = _source_result(candidates, blocked=blocked)
    if source == service.SOURCE_EXPIRED_MEMBERS:
        monkeypatch.setattr(service, "_load_expired_source", lambda **_: result)
    else:
        monkeypatch.setattr(service, "_load_active_source", lambda **_: result)
    monkeypatch.setattr(service, "_read_v2_tariff_catalog", lambda **_: _catalog())


def _preview(monkeypatch, candidates, *, families=("DOMICILIADO", "TRIMESTRAL")):
    _install(monkeypatch, candidates)
    return service.build_campaign_v2_audience_preview(
        source="EXPIRED_MEMBERS",
        audience_families=families,
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        session=object(),
    )


def test_preview_or_families_separates_mes_out_of_segment_unclassified_and_invalid(monkeypatch):
    rows = [
        _candidate(1, tariff="DOM", phone="6861000001"),
        _candidate(2, tariff="TRI", phone="6861000002"),
        _candidate(3, tariff="CON", phone="6861000003"),
        _candidate(4, tariff="MES", phone="6861000004"),
        _candidate(5, tariff="OUT", phone="6861000005"),
        _candidate(6, tariff="UNKNOWN", phone="6861000006"),
        _candidate(7, tariff="DOM", phone=None),
    ]

    preview = _preview(monkeypatch, rows)

    assert preview["universe_count"] == 7
    assert preview["filtered_count"] == 3
    assert preview["family_counts"] == {
        "DOMICILIADO": 2,
        "TRIMESTRAL": 1,
        "CONVENIO": 1,
        "SEMESTRE": 0,
        "ESTUDIANTE": 0,
        "MES": 1,
        "OUT_OF_SEGMENT": 1,
    }
    assert preview["unclassified_family_count"] == 1
    assert preview["out_of_segment_count"] == 1
    assert preview["invalid_phone_count"] == 1
    assert preview["duplicate_count"] == 0
    assert preview["unique_recipient_count"] == 2


def test_selected_family_domain_rejects_mes_and_out_of_segment():
    with pytest.raises(service.MarketingCampaignV2AudienceValidationError):
        service._normalize_family_selection(["MES"])
    with pytest.raises(service.MarketingCampaignV2AudienceValidationError):
        service._normalize_family_selection(["OUT_OF_SEGMENT"])
    assert service._normalize_family_selection(["TRIMESTRAL", "DOMICILIADO"]) == (
        "DOMICILIADO",
        "TRIMESTRAL",
    )


def test_deduplication_is_deterministic_and_never_picks_conflicting_metadata_silently():
    first = _candidate(20, tariff="DOM", phone="6861000001", name="Nombre B")
    second = _candidate(10, tariff="TRI", phone="6861000001", name="Nombre A")
    classified_first = service._classify_candidate(first, tariff_catalog=_catalog())
    classified_second = service._classify_candidate(second, tariff_catalog=_catalog())

    recipients_a, duplicates_a = service._deduplicate_candidates(
        (classified_first, classified_second)
    )
    recipients_b, duplicates_b = service._deduplicate_candidates(
        (classified_second, classified_first)
    )

    assert service._serialize_recipient(recipients_a[0]) == service._serialize_recipient(recipients_b[0])
    assert [row.source_ref_id for row in duplicates_a] == [20]
    assert [row.source_ref_id for row in duplicates_b] == [20]
    recipient = recipients_a[0]
    assert recipient.member_name is None
    assert recipient.tarifa_raw is None
    assert recipient.audience_family is None
    assert {"member_name", "tarifa_raw", "tarifa_key", "categoria_tarifa", "audience_family"} <= set(
        recipient.conflict_fields
    )
    assert [row.source_ref_id for row in recipient.evidence_rows] == [10, 20]


def test_detail_is_stable_paginated_and_matches_preview(monkeypatch):
    rows = [
        _candidate(3, tariff="DOM", phone="6861000003"),
        _candidate(1, tariff="DOM", phone="6861000001"),
        _candidate(2, tariff="DOM", phone="6861000002"),
    ]
    _install(monkeypatch, rows)

    kwargs = dict(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        bucket="RECIPIENTS",
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        session=object(),
    )
    page_1 = service.build_campaign_v2_audience_preview_detail(page=1, page_size=2, **kwargs)
    page_2 = service.build_campaign_v2_audience_preview_detail(page=2, page_size=2, **kwargs)

    assert page_1["total"] == 3
    assert [row["phone_mx10"] for row in page_1["rows"]] == ["6861000001", "6861000002"]
    assert [row["phone_mx10"] for row in page_2["rows"]] == ["6861000003"]


def test_detail_fails_closed_when_bucket_count_diverges(monkeypatch):
    rows = [_candidate(1, tariff="DOM", phone="6861000001")]
    _install(monkeypatch, rows)
    monkeypatch.setattr(service, "_bucket_rows", lambda *args, **kwargs: [])

    with pytest.raises(RuntimeError, match="no coincide"):
        service.build_campaign_v2_audience_preview_detail(
            source="EXPIRED_MEMBERS",
            audience_families=["DOMICILIADO"],
            allowed_sucursal_keys=None,
            bucket="RECIPIENTS",
            expiration_date_from="2026-08-01",
            expiration_date_to="2026-08-31",
            session=object(),
        )


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)
    def filter(self, *args):
        return self
    def order_by(self, *args):
        return self
    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, rows, expected_model=None):
        self.rows = rows
        self.expected_model = expected_model
        self.queried_models = []
    def query(self, model):
        self.queried_models.append(model)
        if self.expected_model is not None:
            assert model is self.expected_model
        return _Query(self.rows)
    def add(self, _row):
        raise AssertionError("Audience Builder V2 no debe persistir datos.")


def test_expired_adapter_uses_inclusive_range_scope_and_current_status_without_iventas(monkeypatch):
    rows = [
        NS(id=1, fecha_vencimiento_date=date(2026, 7, 31), sucursal_key="BRANCH A", sucursal_raw="BRANCH A", telefono_raw="6861000001", telefono_digits="6861000001", pin="1", nombre="Antes", tarifa="DOM"),
        NS(id=2, fecha_vencimiento_date=date(2026, 8, 1), sucursal_key="BRANCH A", sucursal_raw="BRANCH A", telefono_raw="6861000002", telefono_digits="6861000002", pin="2", nombre="Desde", tarifa="DOM"),
        NS(id=3, fecha_vencimiento_date=date(2026, 8, 31), sucursal_key="BRANCH A", sucursal_raw="BRANCH A", telefono_raw="6861000003", telefono_digits="6861000003", pin="3", nombre="Hasta", tarifa="TRI"),
        NS(id=4, fecha_vencimiento_date=date(2026, 8, 15), sucursal_key="BRANCH B", sucursal_raw="BRANCH B", telefono_raw="6861000004", telefono_digits="6861000004", pin="4", nombre="Otra", tarifa="DOM"),
        NS(id=5, fecha_vencimiento_date=date(2026, 9, 1), sucursal_key="BRANCH A", sucursal_raw="BRANCH A", telefono_raw="6861000005", telefono_digits="6861000005", pin="5", nombre="Despues", tarifa="DOM"),
    ]
    calls = {}
    context = NS(activos_snapshot_id=88, activos_cutoff_date="2026-09-01")

    def prepare(**kwargs):
        calls["minimum_cutoff_date"] = kwargs["minimum_cutoff_date"]
        return context

    def resolve(**kwargs):
        calls["resolved_ids"] = [row.id for row in kwargs["vencidos_rows"]]
        return (
            NS(vencido_row_id=2, status=service.current_status.STATUS_NOT_FOUND),
            NS(vencido_row_id=3, status=service.current_status.STATUS_ACTIVE_CONFIRMED),
        )

    monkeypatch.setattr(service.current_status, "prepare_socios_vencidos_current_status_context", prepare)
    monkeypatch.setattr(service.current_status, "resolve_socios_vencidos_rows_with_context", resolve)
    result = service._load_expired_source(
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        allowed_sucursal_keys=("BRANCH A",),
        session=_Session(rows),
    )

    assert result.universe_count == 3
    assert result.scoped_count == 2
    assert [row.source_ref_id for row in result.candidates] == [2]
    assert [row.source_ref_id for row in result.current_status_blocked] == [3]
    assert calls["minimum_cutoff_date"] == date(2026, 8, 31)
    assert calls["resolved_ids"] == [2, 3]
    source_text = inspect.getsource(service).lower()
    assert "marketing_iventas" not in source_text
    assert "reactivation_group" not in source_text


def test_active_adapter_uses_latest_canonical_snapshot_scope_and_row_reference(monkeypatch):
    rows = [
        NS(id=10, row_index=2, snapshot_id=7, id_socio="A10", pin="10", nombre="B", sucursal_raw="BRANCH B", fecha_vencimiento_date=date(2026, 10, 1), tarifa="DOM", lada_raw="686", telefono_raw="1234567", telefono_digits="1234567"),
        NS(id=9, row_index=1, snapshot_id=7, id_socio="A9", pin="9", nombre="A", sucursal_raw="BRANCH A", fecha_vencimiento_date=date(2026, 10, 1), tarifa="TRI", lada_raw="686", telefono_raw="7654321", telefono_digits="7654321"),
    ]
    snapshot = NS(
        id=7,
        cutoff_date=date(2026, 9, 30),
        captured_at=datetime(2026, 9, 30, 8, 0),
        snapshot_kind="daily",
    )
    calls = {}

    def resolve(**kwargs):
        calls.update(kwargs)
        return snapshot

    monkeypatch.setattr(service.activos_resolver, "resolve_latest_canonical_socios_activos_snapshot", resolve)
    session = _Session(rows, expected_model=service.SociosActivosSnapshotRowORM)
    result = service._load_active_source(
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )

    assert calls["minimum_cutoff_date"] == date.min
    assert result.universe_count == 2
    assert result.scoped_count == 1
    assert result.metadata["activos_snapshot_id"] == 7
    assert result.metadata["activos_cutoff_date"] == "2026-09-30"
    assert result.candidates[0].source_ref_type == "SOCIOS_ACTIVOS_SNAPSHOT_ROW"
    assert result.candidates[0].source_ref_id == 9
    assert result.candidates[0].source_snapshot_id == 7
    assert result.candidates[0].phone_mx10 == "6867654321"


def test_tariff_catalog_reader_uses_only_v2_catalog_model():
    rows = [NS(tarifa_key="DOM", categoria_tarifa="Domiciliado", audience_family="DOMICILIADO")]
    session = _Session(rows, expected_model=service.MarketingCampaignV2TariffORM)
    catalog = service._read_v2_tariff_catalog(session=session)
    assert catalog == {"DOM": ("Domiciliado", "DOMICILIADO")}
    source_text = inspect.getsource(service)
    assert "MarketingReactivationTariffORM" not in source_text


def test_current_status_blocked_has_consistent_drilldown(monkeypatch):
    blocked = service.MarketingCampaignV2AudienceCandidate(
        source=service.SOURCE_EXPIRED_MEMBERS,
        source_ref_type="SOCIOS_VENCIDOS_CARTERA",
        source_ref_id=99,
        member_pin="99",
        member_name="Activo detectado",
        sucursal="BRANCH A",
        sucursal_key="BRANCH A",
        tarifa_raw="DOM",
        fecha_vencimiento=date(2026, 8, 20),
        current_status=service.current_status.STATUS_ACTIVE_CONFIRMED,
        evidence=("CURRENT_STATUS:ACTIVE_CONFIRMED",),
    )
    _install(monkeypatch, [_candidate(1, tariff="DOM", phone="6861000001")], blocked=[blocked])

    detail = service.build_campaign_v2_audience_preview_detail(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        bucket="CURRENT_STATUS_BLOCKED",
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        session=object(),
    )
    assert detail["total"] == 1
    assert detail["rows"][0]["source_ref_id"] == 99
