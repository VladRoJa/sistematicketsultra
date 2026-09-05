from datetime import date, datetime, timezone
from collections import Counter
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import MarketingIventasContactORM
from app.models.warehouse import SociosVencidosSnapshotRowORM
from app.services.marketing_iventas_leads_service import (
    MarketingIventasCanonicalRunRequiredError,
)
from app.warehouse.services import (
    socios_vencidos_current_status_resolver
    as current_status_resolver,
)
from app.warehouse.services import (
    socios_vencidos_reactivation_candidate_resolver
    as resolver,
)


IVENTAS_PERIOD_KEY = "IVENTAS-2026-08-11"
IVENTAS_SYNC_RUN_ID = 41
VENCIDOS_SNAPSHOT_ID = 7
ACTIVOS_SNAPSHOT_ID = 23


def test_batch_phone_count_excludes_rows_with_active_match(monkeypatch):
    rows = [
        SimpleNamespace(id=1, telefono_raw="6861000001"),
        SimpleNamespace(id=2, telefono_raw="6861000001"),
        SimpleNamespace(id=3, telefono_raw="6861000002"),
    ]
    monkeypatch.setattr(
        resolver,
        "resolve_socios_vencidos_rows_with_context",
        lambda **_kwargs: (
            SimpleNamespace(
                vencido_row_id=1,
                status=current_status_resolver.STATUS_ACTIVE_CONFIRMED,
            ),
            SimpleNamespace(
                vencido_row_id=2,
                status=current_status_resolver.STATUS_NOT_FOUND,
            ),
            SimpleNamespace(
                vencido_row_id=3,
                status=current_status_resolver.STATUS_NOT_FOUND,
            ),
        ),
    )
    context = SimpleNamespace(current_status=object())

    counts = resolver.count_socios_vencidos_not_found_phones(
        vencidos_rows=rows,
        context=context,
    )

    assert counts == Counter({"6861000001": 1, "6861000002": 1})


def test_batch_reuses_pre_resolved_current_rows_without_matching_activos_again(
    monkeypatch,
):
    vencido = SimpleNamespace(
        id=1,
        telefono_raw="6861000001",
        fecha_vencimiento_date=date(2026, 8, 11),
    )
    current_rows = (
        current_status_resolver.SocioVencidoCurrentStatus(
            vencido_row_id=1,
            status=current_status_resolver.STATUS_NOT_FOUND,
            active_id_socio=None,
        ),
    )
    monkeypatch.setattr(
        resolver,
        "resolve_socios_vencidos_rows_with_context",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("No debe resolver Activos dos veces")
        ),
    )
    context = resolver.SociosVencidosReactivationResolutionContext(
        current_status=SimpleNamespace(),
        iventas_sync_run_id=IVENTAS_SYNC_RUN_ID,
        iventas_period_key=IVENTAS_PERIOD_KEY,
    )

    result = resolver.resolve_socios_vencidos_reactivation_candidate_batch(
        vencidos_rows=[vencido],
        context=context,
        phone_counts=Counter({"6861000001": 1}),
        current_rows=current_rows,
        session=FakeSession(),
    )

    assert result[0].reason == "NO_MATCH_CURRENT_IVENTAS_RUN"


class FakeQuery:
    def __init__(
        self,
        *,
        session,
        model,
    ):
        self.session = session
        self.model = model
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *args):
        return self

    def all(self):
        if self.model is SociosVencidosSnapshotRowORM:
            return self.session.vencido_rows

        if self.model is MarketingIventasContactORM:
            return self.session.iventas_contacts

        raise AssertionError(
            f"Consulta inesperada para {self.model!r}."
        )


class FakeSession:
    def __init__(
        self,
        *,
        vencido_rows=(),
        iventas_contacts=(),
    ):
        self.vencido_rows = list(vencido_rows)
        self.iventas_contacts = list(
            iventas_contacts
        )
        self.queries = []

    def query(self, model):
        query = FakeQuery(
            session=self,
            model=model,
        )
        self.queries.append(query)
        return query


def _current_row(
    *,
    row_id,
    status,
    active_id_socio=None,
):
    return (
        current_status_resolver
        .SocioVencidoCurrentStatus(
            vencido_row_id=row_id,
            status=status,
            active_id_socio=active_id_socio,
        )
    )


def _current_result(rows):
    rows_tuple = tuple(rows)

    return (
        current_status_resolver
        .SociosVencidosCurrentStatusResult(
            vencidos_snapshot_id=(
                VENCIDOS_SNAPSHOT_ID
            ),
            activos_snapshot_id=(
                ACTIVOS_SNAPSHOT_ID
            ),
            vencidos_date_to="2026-08-11",
            activos_cutoff_date="2026-08-12",
            total_rows=len(rows_tuple),
            status_counts={},
            rows=rows_tuple,
        )
    )


def _vencido(
    *,
    row_id,
    phone,
    expiration=date(2026, 8, 11),
):
    return SimpleNamespace(
        id=row_id,
        snapshot_id=VENCIDOS_SNAPSHOT_ID,
        telefono_raw=phone,
        fecha_vencimiento_date=expiration,
    )


def _contact(
    *,
    phone="6861234567",
    contact_id="CONTACT-1",
    outbound=None,
    sync_run_id=IVENTAS_SYNC_RUN_ID,
    first_message=None,
):
    return SimpleNamespace(
        sync_run_id=sync_run_id,
        phone_mx10=phone,
        contact_id=contact_id,
        last_outbound_message_at_utc=outbound,
        first_message_at_utc=first_message,
    )


def _run_resolver(
    monkeypatch,
    *,
    current_rows,
    vencido_rows=(),
    iventas_contacts=(),
    iventas_period_key=IVENTAS_PERIOD_KEY,
    canonical_sync_run_id=IVENTAS_SYNC_RUN_ID,
    activos_snapshot_id=None,
):
    session = FakeSession(
        vencido_rows=vencido_rows,
        iventas_contacts=iventas_contacts,
    )
    calls = {}

    def fake_current_status(**kwargs):
        calls["current_status"] = kwargs
        return _current_result(
            current_rows
        )

    def fake_canonical_run(**kwargs):
        calls["canonical_run"] = kwargs
        return {
            "sync_run_id": canonical_sync_run_id,
            "period_key": iventas_period_key,
        }

    monkeypatch.setattr(
        resolver,
        "resolve_socios_vencidos_current_status",
        fake_current_status,
    )
    monkeypatch.setattr(
        resolver,
        "read_canonical_iventas_run",
        fake_canonical_run,
    )

    result = (
        resolver
        .resolve_socios_vencidos_reactivation_candidates(
            vencidos_snapshot_id=(
                VENCIDOS_SNAPSHOT_ID
            ),
            iventas_period_key=(
                iventas_period_key
            ),
            activos_snapshot_id=(
                activos_snapshot_id
            ),
            session=session,
        )
    )

    return result, session, calls


def _compiled_query(query):
    return str(
        select(query.model)
        .where(*query.criteria)
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    ).lower()


def test_active_confirmed_is_excluded_active(
    monkeypatch,
):
    result, session, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=(
                    current_status_resolver
                    .STATUS_ACTIVE_CONFIRMED
                ),
                active_id_socio="A1",
            )
        ],
    )

    row = result.rows[0]

    assert row.status == resolver.STATUS_EXCLUDED_ACTIVE
    assert row.reason == "ACTIVE_CONFIRMED"
    assert row.active_status == "ACTIVE_CONFIRMED"
    assert row.active_id_socio == "A1"
    assert session.queries == []


@pytest.mark.parametrize(
    ("active_status", "active_id_socio"),
    [
        (
            current_status_resolver.STATUS_ACTIVE_REVIEW,
            "A2",
        ),
        (
            current_status_resolver.STATUS_AMBIGUOUS,
            None,
        ),
        (
            current_status_resolver
            .STATUS_IDENTIFIER_CONFLICT,
            None,
        ),
    ],
)
def test_uncertain_active_matches_require_review(
    monkeypatch,
    active_status,
    active_id_socio,
):
    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=active_status,
                active_id_socio=(
                    active_id_socio
                ),
            )
        ],
    )

    row = result.rows[0]

    assert (
        row.status
        == resolver.STATUS_REVIEW_ACTIVE_MATCH
    )
    assert row.reason == active_status
    assert row.active_status == active_status


def test_not_found_without_mx10_has_unknown_history(
    monkeypatch,
):
    result, session, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="555",
            )
        ],
    )

    row = result.rows[0]

    assert (
        row.status
        == resolver.STATUS_CONTACT_HISTORY_UNKNOWN
    )
    assert row.reason == resolver.REASON_NO_MX10
    assert len(session.queries) == 1


def test_duplicate_not_found_phone_is_fail_closed(
    monkeypatch,
):
    result, session, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            ),
            _current_row(
                row_id=2,
                status=current_status_resolver.STATUS_NOT_FOUND,
            ),
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            ),
            _vencido(
                row_id=2,
                phone="52 686 123 4567",
            ),
        ],
    )

    assert {
        row.reason
        for row in result.rows
    } == {
        resolver.REASON_DUPLICATE_VENCIDO_PHONE,
    }
    assert len(session.queries) == 1


def test_phone_without_current_run_contact_is_unknown(
    monkeypatch,
):
    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
    )

    assert (
        result.rows[0].reason
        == resolver.REASON_NO_MATCH_CURRENT_IVENTAS_RUN
    )


def test_multiple_iventas_identities_are_ambiguous(
    monkeypatch,
):
    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
        iventas_contacts=[
            _contact(contact_id="CONTACT-1"),
            _contact(contact_id="CONTACT-2"),
        ],
    )

    row = result.rows[0]

    assert (
        row.reason
        == resolver.REASON_AMBIGUOUS_IVENTAS_IDENTITY
    )
    assert row.iventas_contact_id is None


def test_first_message_is_not_outbound_evidence(
    monkeypatch,
):
    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
        iventas_contacts=[
            _contact(
                first_message=datetime(
                    2026,
                    8,
                    12,
                    tzinfo=timezone.utc,
                ),
            )
        ],
    )

    row = result.rows[0]

    assert (
        row.reason
        == resolver.REASON_NO_OUTBOUND_EVIDENCE
    )
    assert row.iventas_contact_id == "CONTACT-1"
    assert row.latest_outbound_at_utc is None


def test_only_pre_expiration_outbound_is_unknown(
    monkeypatch,
):
    outbound = datetime(
        2026,
        8,
        10,
        20,
        tzinfo=timezone.utc,
    )

    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
        iventas_contacts=[
            _contact(outbound=outbound)
        ],
    )

    row = result.rows[0]

    assert (
        row.reason
        == resolver.REASON_ONLY_PRE_EXPIRATION_OUTBOUND
    )
    assert row.latest_outbound_at_utc == outbound


def test_outbound_on_expiration_day_is_excluded(
    monkeypatch,
):
    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
        iventas_contacts=[
            _contact(
                outbound=datetime(
                    2026,
                    8,
                    11,
                    16,
                    tzinfo=timezone.utc,
                )
            )
        ],
    )

    row = result.rows[0]

    assert (
        row.status
        == resolver
        .STATUS_EXCLUDED_POST_EXPIRATION_CONTACT
    )
    assert (
        row.reason
        == resolver.REASON_POST_EXPIRATION_OUTBOUND
    )


def test_outbound_after_expiration_is_excluded(
    monkeypatch,
):
    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
        iventas_contacts=[
            _contact(
                outbound=datetime(
                    2026,
                    8,
                    12,
                    16,
                    tzinfo=timezone.utc,
                )
            )
        ],
    )

    assert (
        result.rows[0].status
        == resolver
        .STATUS_EXCLUDED_POST_EXPIRATION_CONTACT
    )


def test_latest_outbound_uses_max_for_same_identity(
    monkeypatch,
):
    earlier = datetime(
        2026,
        8,
        10,
        20,
        tzinfo=timezone.utc,
    )
    latest = datetime(
        2026,
        8,
        12,
        20,
        tzinfo=timezone.utc,
    )

    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
        iventas_contacts=[
            _contact(outbound=earlier),
            _contact(outbound=latest),
        ],
    )

    row = result.rows[0]

    assert row.iventas_contact_id == "CONTACT-1"
    assert row.latest_outbound_at_utc == latest
    assert (
        row.status
        == resolver
        .STATUS_EXCLUDED_POST_EXPIRATION_CONTACT
    )


def test_outbound_is_converted_to_tijuana_before_date_comparison(
    monkeypatch,
):
    outbound_utc = datetime(
        2026,
        8,
        11,
        6,
        30,
        tzinfo=timezone.utc,
    )

    result, _, _ = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=current_status_resolver.STATUS_NOT_FOUND,
            )
        ],
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
                expiration=date(2026, 8, 11),
            )
        ],
        iventas_contacts=[
            _contact(outbound=outbound_utc)
        ],
    )

    assert (
        result.rows[0].reason
        == resolver.REASON_ONLY_PRE_EXPIRATION_OUTBOUND
    )


def test_uses_canonical_run_for_requested_period_and_contact_query(
    monkeypatch,
):
    requested_period = "IVENTAS-TARGET"
    runs_by_period = {
        requested_period: 41,
        "IVENTAS-NON-CANONICAL": 99,
    }
    session = FakeSession(
        vencido_rows=[
            _vencido(
                row_id=1,
                phone="6861234567",
            )
        ],
        iventas_contacts=[
            _contact(
                sync_run_id=41,
            )
        ],
    )
    calls = {}

    monkeypatch.setattr(
        resolver,
        "resolve_socios_vencidos_current_status",
        lambda **kwargs: _current_result(
            [
                _current_row(
                    row_id=1,
                    status=(
                        current_status_resolver
                        .STATUS_NOT_FOUND
                    ),
                )
            ]
        ),
    )

    def fake_canonical_run(
        *,
        period_key,
        session,
    ):
        calls["period_key"] = period_key
        calls["session"] = session

        return {
            "sync_run_id": runs_by_period[
                period_key
            ],
            "period_key": period_key,
        }

    monkeypatch.setattr(
        resolver,
        "read_canonical_iventas_run",
        fake_canonical_run,
    )

    result = (
        resolver
        .resolve_socios_vencidos_reactivation_candidates(
            vencidos_snapshot_id=(
                VENCIDOS_SNAPSHOT_ID
            ),
            iventas_period_key=requested_period,
            activos_snapshot_id=None,
            session=session,
        )
    )

    contact_query = next(
        query
        for query in session.queries
        if query.model is MarketingIventasContactORM
    )
    sql = _compiled_query(
        contact_query
    )

    assert calls["period_key"] == requested_period
    assert calls["session"] is session
    assert result.iventas_sync_run_id == 41
    assert result.iventas_period_key == requested_period
    assert "sync_run_id = 41" in sql
    assert "phone_mx10 in ('6861234567')" in sql


def test_without_canonical_iventas_run_propagates_error(
    monkeypatch,
):
    session = FakeSession()

    monkeypatch.setattr(
        resolver,
        "resolve_socios_vencidos_current_status",
        lambda **kwargs: _current_result([]),
    )

    def fail_canonical_run(**kwargs):
        raise MarketingIventasCanonicalRunRequiredError(
            "No existe snapshot iVentas canónico."
        )

    monkeypatch.setattr(
        resolver,
        "read_canonical_iventas_run",
        fail_canonical_run,
    )

    with pytest.raises(
        MarketingIventasCanonicalRunRequiredError,
        match="canónico",
    ):
        (
            resolver
            .resolve_socios_vencidos_reactivation_candidates(
                vencidos_snapshot_id=(
                    VENCIDOS_SNAPSHOT_ID
                ),
                iventas_period_key=(
                    IVENTAS_PERIOD_KEY
                ),
                session=session,
            )
        )


def test_result_cardinality_invariants(
    monkeypatch,
):
    result, _, calls = _run_resolver(
        monkeypatch,
        current_rows=[
            _current_row(
                row_id=1,
                status=(
                    current_status_resolver
                    .STATUS_ACTIVE_CONFIRMED
                ),
                active_id_socio="A1",
            ),
            _current_row(
                row_id=2,
                status=current_status_resolver.STATUS_NOT_FOUND,
            ),
            _current_row(
                row_id=3,
                status=current_status_resolver.STATUS_NOT_FOUND,
            ),
        ],
        vencido_rows=[
            _vencido(
                row_id=2,
                phone=None,
            ),
            _vencido(
                row_id=3,
                phone="6861234567",
            ),
        ],
        iventas_contacts=[
            _contact(
                outbound=datetime(
                    2026,
                    8,
                    12,
                    18,
                    tzinfo=timezone.utc,
                )
            )
        ],
    )

    assert len(result.rows) == result.total_rows
    assert (
        sum(result.status_counts.values())
        == result.total_rows
    )
    assert (
        sum(result.reason_counts.values())
        == result.total_rows
    )
    assert (
        calls["current_status"][
            "activos_snapshot_id"
        ]
        is None
    )


def test_period_resolver_reads_cartera_and_reuses_classification(
    monkeypatch,
):
    session = FakeSession()
    calls = {}

    def fake_current_status_for_period(**kwargs):
        calls["current_status"] = kwargs
        return (
            current_status_resolver
            .SociosVencidosCurrentStatusPeriodResult(
                date_from="2026-08-01",
                date_to="2026-08-31",
                activos_snapshot_id=ACTIVOS_SNAPSHOT_ID,
                activos_cutoff_date="2026-09-01",
                total_rows=1,
                status_counts={
                    current_status_resolver.STATUS_ACTIVE_CONFIRMED: 1,
                },
                rows=(
                    _current_row(
                        row_id=91,
                        status=(
                            current_status_resolver
                            .STATUS_ACTIVE_CONFIRMED
                        ),
                        active_id_socio="A91",
                    ),
                ),
            )
        )

    monkeypatch.setattr(
        resolver,
        "resolve_socios_vencidos_current_status_for_period",
        fake_current_status_for_period,
    )
    monkeypatch.setattr(
        resolver,
        "_read_cartera_rows",
        lambda **kwargs: {
            91: _vencido(row_id=91, phone="6861234567")
        },
    )
    monkeypatch.setattr(
        resolver,
        "read_canonical_iventas_run",
        lambda **kwargs: {
            "sync_run_id": IVENTAS_SYNC_RUN_ID,
            "period_key": IVENTAS_PERIOD_KEY,
        },
    )

    result = (
        resolver
        .resolve_socios_vencidos_reactivation_candidates_for_period(
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            iventas_period_key=IVENTAS_PERIOD_KEY,
            session=session,
        )
    )

    assert calls["current_status"]["date_from"] == date(2026, 8, 1)
    assert calls["current_status"]["date_to"] == date(2026, 8, 31)
    assert result.date_from == "2026-08-01"
    assert result.date_to == "2026-08-31"
    assert result.total_rows == 1
    assert result.rows[0].status == resolver.STATUS_EXCLUDED_ACTIVE
