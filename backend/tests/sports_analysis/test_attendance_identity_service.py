from datetime import date
from types import SimpleNamespace

from app.sports_analysis import (
    attendance_identity_service as identity,
)


def _visit(
    *,
    visit_id=1,
    attendance_type="SOCIO",
    member_pin="00123",
    member_since=date(2025, 1, 1),
    business_date=date(2026, 9, 25),
    sucursal_id=5,
    first_name="Ana",
    last_name="Prueba",
):
    return SimpleNamespace(
        id=visit_id,
        attendance_type=attendance_type,
        member_pin=member_pin,
        member_since=member_since,
        business_date=business_date,
        sucursal_id=sucursal_id,
        source_first_name=first_name,
        source_last_name=last_name,
    )


def _candidate(
    id_socio,
    *,
    nombre="Nombre Canonico",
    snapshot_id=20,
):
    return identity._IdentityCandidate(
        id_socio=id_socio,
        nombre=nombre,
        snapshot_id=snapshot_id,
    )


def test_exact_pin_alta_has_priority(monkeypatch):
    monkeypatch.setattr(
        identity,
        "_load_exact_candidates",
        lambda *_args, **_kwargs: (
            _candidate(
                "331909",
                nombre="Ana Canonica",
                snapshot_id=21,
            ),
            _candidate(
                "331909",
                nombre="Ana Canonica",
                snapshot_id=20,
            ),
        ),
    )

    resolution = identity.resolve_attendance_identity(
        _visit(),
        session=object(),
    )

    assert resolution.id_socio == "331909"
    assert resolution.display_name == "Ana Canonica"
    assert (
        resolution.identity_method
        == identity.IDENTITY_EXACT_PIN_ALTA
    )
    assert resolution.source_snapshot_id == 21


def test_ambiguous_exact_falls_to_same_day_pin(
    monkeypatch,
):
    monkeypatch.setattr(
        identity,
        "_load_exact_candidates",
        lambda *_args, **_kwargs: (
            _candidate("100", snapshot_id=10),
            _candidate("200", snapshot_id=11),
        ),
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_snapshot_id",
        lambda *_args, **_kwargs: 25,
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_pin_candidates",
        lambda *_args, **_kwargs: (
            _candidate(
                "200",
                nombre="Socio del dia",
                snapshot_id=25,
            ),
        ),
    )

    resolution = identity.resolve_attendance_identity(
        _visit(),
        session=object(),
    )

    assert resolution.id_socio == "200"
    assert (
        resolution.identity_method
        == identity.IDENTITY_SAME_DAY_PIN
    )
    assert resolution.source_snapshot_id == 25


def test_ambiguous_same_day_pin_falls_to_branch(
    monkeypatch,
):
    monkeypatch.setattr(
        identity,
        "_load_exact_candidates",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_snapshot_id",
        lambda *_args, **_kwargs: 25,
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_pin_candidates",
        lambda *_args, **_kwargs: (
            _candidate("331909", snapshot_id=25),
            _candidate("332143", snapshot_id=25),
        ),
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_branch_pin_candidates",
        lambda *_args, **_kwargs: (
            _candidate(
                "332143",
                nombre="Socio Sucursal",
                snapshot_id=25,
            ),
        ),
    )

    resolution = identity.resolve_attendance_identity(
        _visit(sucursal_id=6),
        session=object(),
    )

    assert resolution.id_socio == "332143"
    assert (
        resolution.identity_method
        == identity.IDENTITY_SAME_DAY_BRANCH_PIN
    )
    assert resolution.source_snapshot_id == 25


def test_unresolved_keeps_source_name(monkeypatch):
    monkeypatch.setattr(
        identity,
        "_load_exact_candidates",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_snapshot_id",
        lambda *_args, **_kwargs: None,
    )

    resolution = identity.resolve_attendance_identity(
        _visit(
            first_name="SERGIO AARON",
            last_name="CRUZ",
        ),
        session=object(),
    )

    assert resolution.id_socio is None
    assert resolution.display_name == "SERGIO AARON CRUZ"
    assert (
        resolution.identity_method
        == identity.IDENTITY_UNRESOLVED
    )
    assert resolution.source_snapshot_id is None


def test_non_member_attendance_is_not_resolved(
    monkeypatch,
):
    called = False

    def _unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        return ()

    monkeypatch.setattr(
        identity,
        "_load_exact_candidates",
        _unexpected,
    )

    resolution = identity.resolve_attendance_identity(
        _visit(attendance_type="INSTRUCTOR PISO"),
        session=object(),
    )

    assert called is False
    assert resolution.id_socio is None
    assert resolution.display_name == "Ana Prueba"
    assert (
        resolution.identity_method
        == identity.IDENTITY_UNRESOLVED
    )


def test_canonical_name_falls_back_to_source(
    monkeypatch,
):
    monkeypatch.setattr(
        identity,
        "_load_exact_candidates",
        lambda *_args, **_kwargs: (
            _candidate(
                "331909",
                nombre=None,
                snapshot_id=21,
            ),
        ),
    )

    resolution = identity.resolve_attendance_identity(
        _visit(
            first_name="Ana",
            last_name="Prueba",
        ),
        session=object(),
    )

    assert resolution.id_socio == "331909"
    assert resolution.display_name == "Ana Prueba"


def test_candidate_from_labeled_row():
    row = SimpleNamespace(
        id_socio="331909",
        nombre="Ana Canonica",
        snapshot_id=25,
    )

    candidate = identity._candidate_from_row(row)

    assert candidate.id_socio == "331909"
    assert candidate.nombre == "Ana Canonica"
    assert candidate.snapshot_id == 25


def test_batch_resolver_uses_all_identity_levels(
    monkeypatch,
):
    business_date = date(2026, 9, 25)

    exact_visit = _visit(
        visit_id=1,
        member_pin="001",
        member_since=date(2025, 1, 1),
        business_date=business_date,
        first_name="Exacto",
        last_name="Fuente",
    )
    same_day_visit = _visit(
        visit_id=2,
        member_pin="002",
        member_since=date(2025, 2, 1),
        business_date=business_date,
        first_name="Dia",
        last_name="Fuente",
    )
    branch_visit = _visit(
        visit_id=3,
        member_pin="003",
        member_since=date(2025, 3, 1),
        business_date=business_date,
        sucursal_id=6,
        first_name="Sucursal",
        last_name="Fuente",
    )
    unresolved_visit = _visit(
        visit_id=4,
        member_pin="004",
        member_since=date(2025, 4, 1),
        business_date=business_date,
        first_name="Sin",
        last_name="Match",
    )
    instructor_visit = _visit(
        visit_id=5,
        attendance_type="INSTRUCTOR PISO",
        member_pin="005",
        business_date=business_date,
        first_name="Instructor",
        last_name="Fuente",
    )

    monkeypatch.setattr(
        identity,
        "_load_exact_candidates_batch",
        lambda *_args, **_kwargs: {
            ("001", date(2025, 1, 1)): (
                _candidate(
                    "1001",
                    nombre="Exacto Canonico",
                    snapshot_id=21,
                ),
            ),
        },
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_snapshot_ids_batch",
        lambda *_args, **_kwargs: {
            business_date: 25,
        },
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_pin_candidates_batch",
        lambda *_args, **_kwargs: {
            (25, "002"): (
                _candidate(
                    "1002",
                    nombre="Dia Canonico",
                    snapshot_id=25,
                ),
            ),
            (25, "003"): (
                _candidate("1003", snapshot_id=25),
                _candidate("2003", snapshot_id=25),
            ),
        },
    )
    monkeypatch.setattr(
        identity,
        "_load_same_day_branch_pin_candidates_batch",
        lambda *_args, **_kwargs: {
            (25, "003", 6): (
                _candidate(
                    "2003",
                    nombre="Sucursal Canonica",
                    snapshot_id=25,
                ),
            ),
        },
    )

    timings: dict[str, float] = {}
    resolutions = identity.resolve_attendance_identities(
        [
            exact_visit,
            same_day_visit,
            branch_visit,
            unresolved_visit,
            instructor_visit,
        ],
        session=object(),
        timings=timings,
    )

    assert resolutions[1].id_socio == "1001"
    assert (
        resolutions[1].identity_method
        == identity.IDENTITY_EXACT_PIN_ALTA
    )
    assert resolutions[1].display_name == "Exacto Canonico"

    assert resolutions[2].id_socio == "1002"
    assert (
        resolutions[2].identity_method
        == identity.IDENTITY_SAME_DAY_PIN
    )

    assert resolutions[3].id_socio == "2003"
    assert (
        resolutions[3].identity_method
        == identity.IDENTITY_SAME_DAY_BRANCH_PIN
    )

    assert resolutions[4].id_socio is None
    assert resolutions[4].display_name == "Sin Match"
    assert (
        resolutions[4].identity_method
        == identity.IDENTITY_UNRESOLVED
    )

    assert resolutions[5].id_socio is None
    assert resolutions[5].display_name == "Instructor Fuente"
    assert (
        resolutions[5].identity_method
        == identity.IDENTITY_UNRESOLVED
    )

    assert set(timings) == {
        "fallback_exact",
        "fallback_snapshots",
        "fallback_pin",
        "fallback_branch",
    }
    assert all(
        value >= 0
        for value in timings.values()
    )



def test_branch_batch_lookup_preloads_aliases_and_queries_rows_directly():
    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows
            self.join_calls = 0

        def join(self, *_args, **_kwargs):
            self.join_calls += 1
            return self

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.queries = []
            self.results = iter(
                [
                    [
                        SimpleNamespace(
                            raw_branch_name="RAW A",
                            sucursal_id=5,
                        ),
                        SimpleNamespace(
                            raw_branch_name="RAW A ALT",
                            sucursal_id=5,
                        ),
                        SimpleNamespace(
                            raw_branch_name="RAW B",
                            sucursal_id=6,
                        ),
                    ],
                    [
                        SimpleNamespace(
                            snapshot_id=25,
                            pin="001",
                            sucursal_raw="RAW A ALT",
                            id_socio="1001",
                            nombre="Socio A",
                        ),
                        SimpleNamespace(
                            snapshot_id=25,
                            pin="002",
                            sucursal_raw="RAW B",
                            id_socio="1002",
                            nombre="Socio B",
                        ),
                    ],
                ]
            )

        def query(self, *_args):
            query = FakeQuery(
                next(self.results)
            )
            self.queries.append(query)
            return query

    session = FakeSession()
    result = (
        identity
        ._load_same_day_branch_pin_candidates_batch(
            session,
            keys={
                (25, "001", 5),
                (25, "002", 6),
            },
            chunk_size=1000,
        )
    )

    assert result[(25, "001", 5)][0].id_socio == "1001"
    assert result[(25, "002", 6)][0].id_socio == "1002"

    assert len(session.queries) == 2
    assert session.queries[0].join_calls == 1
    assert session.queries[1].join_calls == 0
