from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import MarketingIventasSyncRunORM
from app.models.warehouse import (
    SociosVencidosSnapshotORM,
    SociosVencidosSnapshotRowORM,
)
from app.services.marketing_iventas_leads_service import (
    MarketingIventasCanonicalRunRequiredError,
)
from app.services import marketing_reactivation_service as service
from app.warehouse.services.socios_vencidos_reactivation_candidate_resolver import (
    SocioVencidoReactivationCandidate,
    SociosVencidosReactivationCandidateResolverError,
    SociosVencidosReactivationCandidateResult,
)


class FakeQuery:
    def __init__(self, *, session, model):
        self.session = session
        self.model = model
        self.criteria = []
        self.ordering = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *ordering):
        self.ordering.extend(ordering)
        return self

    def all(self):
        return list(self.session.rows_by_model.get(self.model, ()))


class FakeSession:
    def __init__(self, rows_by_model=None):
        self.rows_by_model = rows_by_model or {}
        self.queries = []
        self.write_calls = []

    def query(self, model):
        query = FakeQuery(session=self, model=model)
        self.queries.append(query)
        return query

    def add(self, value):
        self.write_calls.append(("add", value))

    def flush(self):
        self.write_calls.append(("flush", None))

    def commit(self):
        self.write_calls.append(("commit", None))


def _compiled_query(query):
    statement = select(query.model)
    if query.criteria:
        statement = statement.where(*query.criteria)
    if query.ordering:
        statement = statement.order_by(*query.ordering)

    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


def _candidate_result(*, outbound=None):
    candidate = SocioVencidoReactivationCandidate(
        vencido_row_id=101,
        status="CONTACT_HISTORY_UNKNOWN",
        reason="NO_OUTBOUND_EVIDENCE",
        active_status="NOT_FOUND",
        active_id_socio=None,
        iventas_sync_run_id=26,
        iventas_contact_id="CONTACT-9",
        latest_outbound_at_utc=outbound,
    )
    return SociosVencidosReactivationCandidateResult(
        vencidos_snapshot_id=7,
        activos_snapshot_id=8,
        iventas_sync_run_id=26,
        iventas_period_key="IVENTAS-2026-08",
        total_rows=1,
        status_counts={"CONTACT_HISTORY_UNKNOWN": 1},
        reason_counts={"NO_OUTBOUND_EVIDENCE": 1},
        rows=(candidate,),
    )


def _vencido_row():
    return SimpleNamespace(
        id=101,
        snapshot_id=7,
        pin="PIN-101",
        nombre="Ana Pérez",
        sucursal_raw="CENTRO",
        telefono_raw="686 123 4567",
        correo_raw="ana@example.com",
        fecha_vencimiento_date=date(2026, 8, 23),
        fecha_ultimo_pago_local=datetime(2026, 7, 23, 10, 30),
        tarifa="ANUAL",
        adeudo=Decimal("120.50"),
    )


def test_sources_are_serialized_in_query_order():
    session = FakeSession(
        {
            SociosVencidosSnapshotORM: [
                SimpleNamespace(
                    id=2,
                    date_from=date(2026, 8, 24),
                    date_to=date(2026, 8, 24),
                    row_count_valid=700,
                ),
                SimpleNamespace(
                    id=1,
                    date_from=date(2026, 8, 23),
                    date_to=date(2026, 8, 23),
                    row_count_valid=679,
                ),
            ],
            MarketingIventasSyncRunORM: [
                SimpleNamespace(
                    id=26,
                    period_key="IVENTAS-2026-08",
                    date_from=date(2026, 8, 1),
                    date_to=date(2026, 8, 26),
                    contacts_unique=51451,
                )
            ],
        }
    )

    result = service.list_marketing_reactivation_sources(
        session=session
    )

    assert [row["id"] for row in result["vencidos_snapshots"]] == [2, 1]
    assert result["vencidos_snapshots"][0]["row_count"] == 700
    assert result["vencidos_snapshots"][0]["snapshot_kind"] is None
    assert result["iventas_periods"][0]["sync_run_id"] == 26

    vencidos_sql = _compiled_query(session.queries[0])
    assert "date_to desc" in vencidos_sql
    assert "socios_vencidos_snapshots.id desc" in vencidos_sql


def test_sources_query_only_completed_canonical_iventas_runs():
    session = FakeSession()

    service.list_marketing_reactivation_sources(session=session)

    iventas_sql = _compiled_query(session.queries[1])
    assert "status = 'completed'" in iventas_sql
    assert "is_canonical is true" in iventas_sql
    assert "date_to desc" in iventas_sql
    assert "marketing_iventas_sync_runs.id desc" in iventas_sql


def test_sources_allow_empty_result():
    result = service.list_marketing_reactivation_sources(
        session=FakeSession()
    )

    assert result == {
        "vencidos_snapshots": [],
        "iventas_periods": [],
    }


def test_candidates_use_resolver_contract_and_one_bulk_lookup(monkeypatch):
    outbound = datetime(2026, 8, 24, 18, 5, tzinfo=timezone.utc)
    result = _candidate_result(outbound=outbound)
    calls = {}

    def fake_resolver(**kwargs):
        calls.update(kwargs)
        return result

    monkeypatch.setattr(
        service,
        "resolve_socios_vencidos_reactivation_candidates",
        fake_resolver,
    )
    session = FakeSession(
        {SociosVencidosSnapshotRowORM: [_vencido_row()]}
    )

    response = service.build_marketing_reactivation_candidates(
        vencidos_snapshot_id=7,
        iventas_period_key="IVENTAS-2026-08",
        session=session,
    )

    assert calls == {
        "vencidos_snapshot_id": 7,
        "iventas_period_key": "IVENTAS-2026-08",
        "activos_snapshot_id": None,
        "session": session,
    }
    assert len(session.queries) == 1
    assert session.queries[0].model is SociosVencidosSnapshotRowORM
    assert session.write_calls == []
    assert response["sources"] == {
        "vencidos_snapshot_id": 7,
        "activos_snapshot_id": 8,
        "iventas_sync_run_id": 26,
        "iventas_period_key": "IVENTAS-2026-08",
    }
    assert response["summary"]["status_counts"] == {
        "CONTACT_HISTORY_UNKNOWN": 1
    }
    assert response["summary"]["reason_counts"] == {
        "NO_OUTBOUND_EVIDENCE": 1
    }

    row = response["rows"][0]
    assert row["status"] == "CONTACT_HISTORY_UNKNOWN"
    assert row["reason"] == "NO_OUTBOUND_EVIDENCE"
    assert row["fecha_vencimiento"] == "2026-08-23"
    assert row["fecha_ultimo_pago"] == "2026-07-23"
    assert row["adeudo"] == "120.50"
    assert row["latest_outbound_at_utc"] == "2026-08-24T18:05:00+00:00"


def test_candidates_bulk_lookup_does_not_query_per_row(monkeypatch):
    base_result = _candidate_result()
    second_candidate = SocioVencidoReactivationCandidate(
        vencido_row_id=102,
        status="EXCLUDED_ACTIVE",
        reason="ACTIVE_CONFIRMED",
        active_status="ACTIVE_CONFIRMED",
        active_id_socio="SOCIO-102",
        iventas_sync_run_id=26,
        iventas_contact_id=None,
        latest_outbound_at_utc=None,
    )
    result = SociosVencidosReactivationCandidateResult(
        vencidos_snapshot_id=base_result.vencidos_snapshot_id,
        activos_snapshot_id=base_result.activos_snapshot_id,
        iventas_sync_run_id=base_result.iventas_sync_run_id,
        iventas_period_key=base_result.iventas_period_key,
        total_rows=2,
        status_counts={
            "CONTACT_HISTORY_UNKNOWN": 1,
            "EXCLUDED_ACTIVE": 1,
        },
        reason_counts={
            "NO_OUTBOUND_EVIDENCE": 1,
            "ACTIVE_CONFIRMED": 1,
        },
        rows=(*base_result.rows, second_candidate),
    )
    second_row = SimpleNamespace(
        **{
            **_vencido_row().__dict__,
            "id": 102,
            "pin": "PIN-102",
        }
    )
    monkeypatch.setattr(
        service,
        "resolve_socios_vencidos_reactivation_candidates",
        lambda **kwargs: result,
    )
    session = FakeSession(
        {
            SociosVencidosSnapshotRowORM: [
                _vencido_row(),
                second_row,
            ]
        }
    )

    response = service.build_marketing_reactivation_candidates(
        vencidos_snapshot_id=7,
        iventas_period_key="IVENTAS-2026-08",
        session=session,
    )

    assert len(response["rows"]) == 2
    assert len(session.queries) == 1
    assert session.write_calls == []


def test_candidates_reject_missing_bulk_row(monkeypatch):
    monkeypatch.setattr(
        service,
        "resolve_socios_vencidos_reactivation_candidates",
        lambda **kwargs: _candidate_result(),
    )

    with pytest.raises(
        SociosVencidosReactivationCandidateResolverError,
        match="enriquecer",
    ):
        service.build_marketing_reactivation_candidates(
            vencidos_snapshot_id=7,
            iventas_period_key="IVENTAS-2026-08",
            session=FakeSession(),
        )


def test_candidates_require_timezone_aware_outbound(monkeypatch):
    monkeypatch.setattr(
        service,
        "resolve_socios_vencidos_reactivation_candidates",
        lambda **kwargs: _candidate_result(
            outbound=datetime(2026, 8, 24, 18, 5)
        ),
    )

    with pytest.raises(
        SociosVencidosReactivationCandidateResolverError,
        match="zona horaria",
    ):
        service.build_marketing_reactivation_candidates(
            vencidos_snapshot_id=7,
            iventas_period_key="IVENTAS-2026-08",
            session=FakeSession(
                {SociosVencidosSnapshotRowORM: [_vencido_row()]}
            ),
        )


def test_canonical_error_propagates_without_empty_success(monkeypatch):
    def fail_resolver(**kwargs):
        raise MarketingIventasCanonicalRunRequiredError("Sin canonical")

    monkeypatch.setattr(
        service,
        "resolve_socios_vencidos_reactivation_candidates",
        fail_resolver,
    )

    with pytest.raises(MarketingIventasCanonicalRunRequiredError):
        service.build_marketing_reactivation_candidates(
            vencidos_snapshot_id=7,
            iventas_period_key="IVENTAS-2026-08",
            session=FakeSession(),
        )
