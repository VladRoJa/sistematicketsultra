from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import MarketingIventasSyncRunORM
from app.models.warehouse import (
    SociosVencidosCarteraORM,
)
from app.services.marketing_iventas_leads_service import (
    MarketingIventasCanonicalRunRequiredError,
)
from app.services import marketing_reactivation_service as service
from app.warehouse.services.socios_vencidos_reactivation_candidate_resolver import (
    SocioVencidoReactivationCandidate,
    SociosVencidosReactivationCandidateResolverError,
)


class FakeQuery:
    def __init__(self, *, session, model, aggregate=False):
        self.session = session
        self.model = model
        self.criteria = []
        self.ordering = []
        self.aggregate = aggregate

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *ordering):
        self.ordering.extend(ordering)
        return self

    def all(self):
        return list(self.session.rows_by_model.get(self.model, ()))

    def one(self):
        if not self.aggregate:
            raise AssertionError("one() sólo se esperaba para coverage")
        return self.session.coverage


class FakeSession:
    def __init__(self, rows_by_model=None, coverage=(None, None, 0)):
        self.rows_by_model = rows_by_model or {}
        self.coverage = coverage
        self.queries = []
        self.write_calls = []

    def query(self, *entities):
        aggregate = len(entities) > 1
        model = "coverage" if aggregate else entities[0]
        query = FakeQuery(session=self, model=model, aggregate=aggregate)
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
    return SociosVencidosReactivationCandidatePeriodResult(
        date_from="2026-08-23",
        date_to="2026-08-23",
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
        sucursal_key="CENTRO",
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


def test_sources_are_serialized_in_query_order(monkeypatch):
    monkeypatch.setattr(
        service,
        "_list_operational_branches",
        lambda **kwargs: [{"key": "CENTRO", "label": "Centro"}],
    )
    session = FakeSession(
        {
            MarketingIventasSyncRunORM: [
                SimpleNamespace(
                    id=26,
                    period_key="IVENTAS-2026-08",
                    date_from=date(2026, 8, 1),
                    date_to=date(2026, 8, 26),
                    contacts_unique=51451,
                )
            ],
        },
        coverage=(date(2026, 8, 23), date(2026, 8, 24), 1379),
    )

    result = service.list_marketing_reactivation_sources(
        session=session
    )

    assert result["vencidos_coverage"] == {
        "min_date": "2026-08-23",
        "max_date": "2026-08-24",
        "total_rows": 1379,
    }
    assert result["iventas_periods"][0]["sync_run_id"] == 26
    assert result["branches"] == [{"key": "CENTRO", "label": "Centro"}]


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
        "vencidos_coverage": {
            "min_date": None,
            "max_date": None,
            "total_rows": 0,
        },
        "iventas_periods": [],
        "branches": [],
    }


class FakeCandidateQuery:
    def __init__(self, rows, *, offset_value=0, limit_value=None):
        self.rows = list(rows)
        self.offset_value = offset_value
        self.limit_value = limit_value

    def _clone(self, **changes):
        return FakeCandidateQuery(
            self.rows,
            offset_value=changes.get("offset_value", self.offset_value),
            limit_value=changes.get("limit_value", self.limit_value),
        )

    def order_by(self, *_ordering):
        return self

    def filter(self, *_criteria):
        return self

    def count(self):
        return len(self.rows)

    def offset(self, value):
        return self._clone(offset_value=value)

    def limit(self, value):
        return self._clone(limit_value=value)

    def all(self):
        end = (
            None
            if self.limit_value is None
            else self.offset_value + self.limit_value
        )
        return self.rows[self.offset_value:end]

    def with_entities(self, *_entities):
        return FakeCandidatePhoneQuery(self.rows)

    def yield_per(self, _batch_size):
        return iter(self.all())


class FakeCandidatePhoneQuery:
    def __init__(self, rows):
        self.rows = rows

    def yield_per(self, _batch_size):
        return iter((row.telefono_raw,) for row in self.rows)


def _candidate_for_row(row, *, status="CONTACT_HISTORY_UNKNOWN", reason="NO_OUTBOUND_EVIDENCE", outbound=None):
    return SocioVencidoReactivationCandidate(
        vencido_row_id=row.id,
        status=status,
        reason=reason,
        active_status=("ACTIVE_CONFIRMED" if status == "EXCLUDED_ACTIVE" else "NOT_FOUND"),
        active_id_socio=("SOCIO-ACTIVO" if status == "EXCLUDED_ACTIVE" else None),
        iventas_sync_run_id=26,
        iventas_contact_id="CONTACT-9",
        latest_outbound_at_utc=outbound,
    )


def _install_candidate_pipeline(monkeypatch, rows, candidates):
    query_calls = {}
    context_calls = {}

    def fake_query(**kwargs):
        query_calls.update(kwargs)
        return FakeCandidateQuery(rows)

    def fake_context(**kwargs):
        context_calls.update(kwargs)
        return SimpleNamespace(
            current_status=SimpleNamespace(activos_snapshot_id=8),
            iventas_sync_run_id=26,
            iventas_period_key="IVENTAS-2026-08",
        )

    candidates_by_id = {candidate.vencido_row_id: candidate for candidate in candidates}
    monkeypatch.setattr(service, "build_latest_operational_episode_query", fake_query)
    monkeypatch.setattr(
        service,
        "prepare_socios_vencidos_reactivation_resolution_context",
        fake_context,
    )
    def fake_interactive(*, vencidos_rows, tariff_catalog, **_kwargs):
        return list(service._serialize_resolved_batch(
            vencidos_rows=vencidos_rows,
            candidates=tuple(
                candidates_by_id[row.id]
                for row in vencidos_rows
                if row.id in candidates_by_id
            ),
            tariff_catalog=tariff_catalog,
        ))

    monkeypatch.setattr(
        service,
        "_resolve_interactive_candidate_batch",
        fake_interactive,
    )
    monkeypatch.setattr(service, "_read_all_active_tariff_catalog", lambda **_kwargs: {})
    return query_calls, context_calls


def test_candidates_all_returns_requested_sql_page_without_full_resolution(monkeypatch):
    outbound = datetime(2026, 8, 24, 18, 5, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(**{**_vencido_row().__dict__, "id": row_id, "pin": f"PIN-{row_id}"})
        for row_id in (101, 102, 103)
    ]
    candidates = [
        _candidate_for_row(rows[0], outbound=outbound),
        _candidate_for_row(rows[1], status="EXCLUDED_ACTIVE", reason="ACTIVE_CONFIRMED"),
        _candidate_for_row(rows[2], reason="NO_MATCH_CURRENT_IVENTAS_RUN"),
    ]
    query_calls, context_calls = _install_candidate_pipeline(
        monkeypatch, rows, candidates
    )

    response = service.build_marketing_reactivation_candidates(
        date_from=date(2026, 8, 23),
        date_to=date(2026, 8, 23),
        iventas_period_key="IVENTAS-2026-08",
        page=2,
        page_size=1,
        operational_status="ALL",
        sucursal="CENTRO",
        session=FakeSession(),
    )

    assert query_calls["sucursal"] == "CENTRO"
    assert context_calls["minimum_cutoff_date"] == date(2026, 8, 23)
    assert response["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total": 3,
        "total_pages": 3,
        "has_next": True,
        "has_prev": True,
        "next_cursor": None,
    }
    assert "summary" not in response
    assert [row["vencido_row_id"] for row in response["rows"]] == [102]
    assert response["rows"][0]["operational_status"] == "ACTIVE"


def test_candidates_work_pending_filters_before_pagination(monkeypatch):
    rows = [
        SimpleNamespace(**{**_vencido_row().__dict__, "id": row_id, "pin": f"PIN-{row_id}"})
        for row_id in (101, 102, 103)
    ]
    candidates = [
        _candidate_for_row(rows[0]),
        _candidate_for_row(rows[1], status="EXCLUDED_ACTIVE", reason="ACTIVE_CONFIRMED"),
        _candidate_for_row(rows[2], status="EXCLUDED_POST_EXPIRATION_CONTACT", reason="POST_EXPIRATION_OUTBOUND"),
    ]
    _install_candidate_pipeline(monkeypatch, rows, candidates)

    response = service.build_marketing_reactivation_candidates(
        date_from="2026-08-23",
        date_to="2026-08-23",
        iventas_period_key="IVENTAS-2026-08",
        operational_status="WORK_PENDING",
        session=FakeSession(),
    )

    assert response["pagination"]["total"] is None
    assert [row["vencido_row_id"] for row in response["rows"]] == [101]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"page": 0}, "page"),
        ({"page_size": 101}, "page_size"),
        ({"sort": "status"}, "sort"),
        ({"direction": "sideways"}, "direction"),
        ({"operational_status": "UNKNOWN"}, "operational_status"),
        ({"tariff_group": "UNKNOWN"}, "tariff_group"),
    ],
)
def test_candidates_reject_invalid_query_values(kwargs, message):
    with pytest.raises(service.MarketingReactivationValidationError, match=message):
        service.build_marketing_reactivation_candidates(
            date_from="2026-08-23",
            date_to="2026-08-23",
            iventas_period_key="IVENTAS-2026-08",
            session=FakeSession(),
            **kwargs,
        )


def test_candidates_reject_incomplete_batch(monkeypatch):
    row = _vencido_row()
    _install_candidate_pipeline(monkeypatch, [row], [])

    with pytest.raises(
        SociosVencidosReactivationCandidateResolverError,
        match="no contiene todos",
    ):
        service.build_marketing_reactivation_candidates(
            date_from="2026-08-23",
            date_to="2026-08-23",
            iventas_period_key="IVENTAS-2026-08",
            session=FakeSession(),
        )


def test_candidates_require_timezone_aware_outbound(monkeypatch):
    row = _vencido_row()
    _install_candidate_pipeline(
        monkeypatch,
        [row],
        [_candidate_for_row(row, outbound=datetime(2026, 8, 24, 18, 5))],
    )

    with pytest.raises(
        SociosVencidosReactivationCandidateResolverError,
        match="zona horaria",
    ):
        service.build_marketing_reactivation_candidates(
            date_from="2026-08-23",
            date_to="2026-08-23",
            iventas_period_key="IVENTAS-2026-08",
            session=FakeSession(),
        )


def test_canonical_error_propagates_without_empty_success(monkeypatch):
    monkeypatch.setattr(
        service,
        "build_latest_operational_episode_query",
        lambda **_kwargs: FakeCandidateQuery([]),
    )
    monkeypatch.setattr(
        service,
        "prepare_socios_vencidos_reactivation_resolution_context",
        lambda **_kwargs: (_ for _ in ()).throw(
            MarketingIventasCanonicalRunRequiredError("Sin canonical")
        ),
    )

    with pytest.raises(MarketingIventasCanonicalRunRequiredError):
        service.build_marketing_reactivation_candidates(
            date_from="2026-08-23",
            date_to="2026-08-23",
            iventas_period_key="IVENTAS-2026-08",
            session=FakeSession(),
        )


def test_all_resolves_only_page_size_from_one_thousand_rows(monkeypatch):
    rows = [
        SimpleNamespace(
            **{
                **_vencido_row().__dict__,
                "id": row_id,
                "pin": f"PIN-{row_id}",
            }
        )
        for row_id in range(1, 1001)
    ]
    resolved_sizes = []
    monkeypatch.setattr(
        service,
        "_build_candidate_base_query",
        lambda **_kwargs: FakeCandidateQuery(rows),
    )
    monkeypatch.setattr(
        service,
        "prepare_socios_vencidos_reactivation_resolution_context",
        lambda **_kwargs: SimpleNamespace(
            current_status=SimpleNamespace(activos_snapshot_id=8),
            iventas_sync_run_id=26,
            iventas_period_key="IVENTAS-2026-08",
        ),
    )
    monkeypatch.setattr(service, "_read_all_active_tariff_catalog", lambda **_kwargs: {})
    monkeypatch.setattr(
        service,
        "_resolve_interactive_candidate_batch",
        lambda *, vencidos_rows, **_kwargs: (
            resolved_sizes.append(len(vencidos_rows))
            or [
                {
                    "vencido_row_id": row.id,
                    "operational_status": "NO_OUTBOUND_MESSAGE",
                }
                for row in vencidos_rows
            ]
        ),
    )

    response = service.build_marketing_reactivation_candidates(
        date_from="2026-08-23",
        date_to="2026-08-23",
        iventas_period_key="IVENTAS-2026-08",
        page=4,
        page_size=50,
        operational_status="ALL",
        session=FakeSession(),
    )

    assert response["pagination"]["total"] == 1000
    assert resolved_sizes == [50]
    assert [row["vencido_row_id"] for row in response["rows"]] == list(
        range(151, 201)
    )


def test_derived_status_stops_after_bounded_batch_and_cursor_resumes(monkeypatch):
    rows = [
        SimpleNamespace(
            **{
                **_vencido_row().__dict__,
                "id": row_id,
                "pin": f"PIN-{row_id}",
            }
        )
        for row_id in range(1000, 0, -1)
    ]
    first_ids = []

    def fake_apply(query, *, cursor, **_kwargs):
        index = next(
            index for index, row in enumerate(query.rows) if row.id == cursor.row_id
        )
        return FakeCandidateQuery(query.rows[index + 1:])

    def fake_resolve(*, vencidos_rows, **_kwargs):
        first_ids.append(vencidos_rows[0].id)
        return [
            {
                "vencido_row_id": row.id,
                "operational_status": (
                    "NO_OUTBOUND_MESSAGE" if row.id % 2 == 0 else "ACTIVE"
                ),
            }
            for row in vencidos_rows
        ]

    monkeypatch.setattr(
        service,
        "_build_candidate_base_query",
        lambda **_kwargs: FakeCandidateQuery(rows),
    )
    monkeypatch.setattr(service, "apply_candidate_cursor", fake_apply)
    monkeypatch.setattr(
        service,
        "prepare_socios_vencidos_reactivation_resolution_context",
        lambda **_kwargs: SimpleNamespace(
            current_status=SimpleNamespace(activos_snapshot_id=8),
            iventas_sync_run_id=26,
            iventas_period_key="IVENTAS-2026-08",
        ),
    )
    monkeypatch.setattr(service, "_read_all_active_tariff_catalog", lambda **_kwargs: {})
    monkeypatch.setattr(service, "_resolve_interactive_candidate_batch", fake_resolve)

    first = service.build_marketing_reactivation_candidates(
        date_from="2026-08-23",
        date_to="2026-08-23",
        iventas_period_key="IVENTAS-2026-08",
        page=1,
        page_size=5,
        operational_status="NO_OUTBOUND_MESSAGE",
        session=FakeSession(),
    )
    second = service.build_marketing_reactivation_candidates(
        date_from="2026-08-23",
        date_to="2026-08-23",
        iventas_period_key="IVENTAS-2026-08",
        page=2,
        page_size=5,
        operational_status="NO_OUTBOUND_MESSAGE",
        cursor=first["pagination"]["next_cursor"],
        session=FakeSession(),
    )

    assert first_ids == [1000, 991]
    assert [row["vencido_row_id"] for row in first["rows"]] == [
        1000, 998, 996, 994, 992
    ]
    assert [row["vencido_row_id"] for row in second["rows"]] == [
        990, 988, 986, 984, 982
    ]
    assert first["pagination"]["total"] is None
    assert first["pagination"]["next_cursor"]


@pytest.mark.parametrize(
    ("peer_is_not_found", "expected_reason"),
    [
        (True, "DUPLICATE_VENCIDO_PHONE"),
        (False, "NO_MATCH_CURRENT_IVENTAS_RUN"),
    ],
)
def test_page_phone_duplicate_checks_peer_outside_page_only_when_not_found(
    monkeypatch,
    peer_is_not_found,
    expected_reason,
):
    visible = _vencido_row()
    peer = SimpleNamespace(
        **{
            **_vencido_row().__dict__,
            "id": 202,
            "pin": "PIN-202",
            "telefono_raw": "+52 686 123 4567",
        }
    )
    context = SimpleNamespace(
        current_status=SimpleNamespace(activos_snapshot_id=8),
        iventas_sync_run_id=26,
        iventas_period_key="IVENTAS-2026-08",
    )
    current_visible = SimpleNamespace(
        vencido_row_id=visible.id,
        status="NOT_FOUND",
        active_id_socio=None,
    )
    observed_counts = {}
    monkeypatch.setattr(
        service,
        "resolve_socios_vencidos_rows_with_context",
        lambda **_kwargs: (current_visible,),
    )
    monkeypatch.setattr(
        service,
        "_build_candidate_base_query",
        lambda **_kwargs: FakeCandidateQuery([peer]),
    )
    monkeypatch.setattr(
        service,
        "count_socios_vencidos_not_found_phones",
        lambda **_kwargs: (
            service.Counter({"6861234567": 1})
            if peer_is_not_found
            else service.Counter()
        ),
    )

    def fake_candidate_resolver(*, phone_counts, **_kwargs):
        observed_counts.update(phone_counts)
        return (
            _candidate_for_row(
                visible,
                reason=(
                    "DUPLICATE_VENCIDO_PHONE"
                    if phone_counts["6861234567"] > 1
                    else "NO_MATCH_CURRENT_IVENTAS_RUN"
                ),
            ),
        )

    monkeypatch.setattr(
        service,
        "resolve_socios_vencidos_reactivation_candidate_batch",
        fake_candidate_resolver,
    )
    query = service._normalize_reactivation_candidate_request(
        date_from="2026-08-23",
        date_to="2026-08-23",
        page=1,
        page_size=50,
        operational_status="ALL",
    )

    result = service._resolve_interactive_candidate_batch(
        vencidos_rows=[visible],
        query=query,
        context=context,
        tariff_catalog={},
        session=FakeSession(),
        allowed_sucursal_keys=None,
    )

    assert result[0]["reason"] == expected_reason
    assert observed_counts["6861234567"] == (2 if peer_is_not_found else 1)


def test_summary_streams_complete_segment_without_returning_rows(monkeypatch):
    rows = [SimpleNamespace(id=row_id) for row_id in range(1, 1001)]
    calls = {}
    monkeypatch.setattr(
        service,
        "_build_candidate_base_query",
        lambda **kwargs: calls.update(kwargs) or FakeCandidateQuery(rows),
    )
    monkeypatch.setattr(
        service,
        "prepare_socios_vencidos_reactivation_resolution_context",
        lambda **_kwargs: SimpleNamespace(
            current_status=SimpleNamespace(activos_snapshot_id=8),
            iventas_sync_run_id=26,
            iventas_period_key="IVENTAS-2026-08",
        ),
    )
    monkeypatch.setattr(
        service,
        "_count_complete_segment_not_found_phones",
        lambda **_kwargs: service.Counter({"6861234567": 2}),
    )
    monkeypatch.setattr(service, "_read_all_active_tariff_catalog", lambda **_kwargs: {})
    monkeypatch.setattr(
        service,
        "_iter_complete_segment_candidates",
        lambda **_kwargs: (
            {
                "status": "CONTACT_HISTORY_UNKNOWN",
                "reason": "DUPLICATE_VENCIDO_PHONE",
                "operational_status": "REVIEW_IDENTITY",
            }
            for _row in rows
        ),
    )

    response = service.build_marketing_reactivation_candidate_summary(
        date_from="2026-08-23",
        date_to="2026-08-23",
        iventas_period_key="IVENTAS-2026-08",
        operational_status="REVIEW_IDENTITY",
        session=FakeSession(),
    )

    assert response["summary"]["total_rows"] == 1000
    assert response["summary"]["reason_counts"] == {
        "DUPLICATE_VENCIDO_PHONE": 1000
    }
    assert "rows" not in response
    assert calls["query"].sort == "fecha_vencimiento"
    assert calls["query"].direction == "desc"
