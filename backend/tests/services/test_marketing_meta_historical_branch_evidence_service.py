"""Historical city eligibility: canonical KPI evidence and identity guards."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql

from app.services.marketing_meta_historical_allocation_service import (
    HistoricalMetaAdsetSource,
    allocate_historical_city_spend,
)
from app.services.marketing_meta_historical_branch_evidence_service import (
    NO_CANONICAL_SNAPSHOT,
    NO_CITY_EVIDENCE,
    NO_CITY_IN_CATALOG,
    REQUIRES_REVIEW,
    VERIFIED,
    build_canonical_kpi_month_statement,
    evaluate_historical_city_branch_evidence,
    read_historical_city_branch_evidence,
)


MONTH = date(2025, 12, 1)
ALIASES = [
    ("VILLAS DEL REY", 1),
    ("VILLA VERDE MEXICALI", 2),
    ("INDEPENDENCIA", 3),
    ("TEC MEXICALI", 4),
    ("SENDERO MEXICALI", 5),
    ("PAPALOTE TIJUANA", 13),
    ("CORPORATIVO", 100),
    ("ADMINISTRADOR", 1000),
]
BRANCHES = [
    (1, "Mexicali", False),
    (2, "Mexicali", False),
    (3, "Mexicali", False),
    (4, "Mexicali", False),
    (5, "Mexicali", False),
    (13, "Tijuana", False),
    (100, "Mexicali", False),
    (1000, "Mexicali", False),
]


def resolve(
    *,
    snapshot_ids=(10, 11),
    names=(
        "VILLAS DEL REY",
        "VILLA VERDE MEXICALI",
        "INDEPENDENCIA",
        "TEC MEXICALI",
        "SENDERO MEXICALI",
        "PAPALOTE TIJUANA",
    ),
    aliases=ALIASES,
    branches=BRANCHES,
    city="Mexicali",
):
    return evaluate_historical_city_branch_evidence(
        month_start=MONTH,
        city_key=city,
        snapshot_ids=snapshot_ids,
        raw_branch_names=names,
        gasca_aliases=aliases,
        catalog_branches=branches,
    )


def test_december_2025_five_verified_mexicali_gyms():
    evidence = resolve()
    assert evidence.status == VERIFIED
    assert evidence.eligible_branch_ids == (1, 2, 3, 4, 5)
    assert evidence.snapshot_ids == (10, 11)
    assert evidence.city_key == "MEXICALI"
    assert evidence.unresolved_branch_names == ()
    assert 100 not in evidence.eligible_branch_ids
    assert 1000 not in evidence.eligible_branch_ids


def test_verified_city_evidence_can_feed_existing_exact_spend_engine():
    evidence = resolve()
    source = HistoricalMetaAdsetSource(
        period_key="META-2025-12",
        account_id="1394543581400837",
        campaign_id="120236276194360426",
        adset_id="120236276194480426",
        city_key=evidence.city_key,
    )
    allocated = allocate_historical_city_spend(
        source=source,
        spend=Decimal("36967.6900"),
        eligible_branch_ids=evidence.eligible_branch_ids,
    )
    assert [r.spend for r in allocated] == [
        Decimal("7393.54"),
        Decimal("7393.54"),
        Decimal("7393.54"),
        Decimal("7393.54"),
        Decimal("7393.53"),
    ]


def test_snapshot_absent_never_implies_zero_gyms():
    evidence = resolve(snapshot_ids=(), names=())
    assert evidence.status == NO_CANONICAL_SNAPSHOT
    assert evidence.eligible_branch_ids == ()


def test_city_without_registered_gyms_is_unavailable():
    evidence = resolve(city="Guadalajara")
    assert evidence.status == NO_CITY_IN_CATALOG
    assert evidence.eligible_branch_ids == ()


def test_city_without_monthly_evidence_not_assigned():
    evidence = resolve(names=("PAPALOTE TIJUANA",))
    assert evidence.status == NO_CITY_EVIDENCE
    assert evidence.eligible_branch_ids == ()


def test_unknown_alias_fails_closed_instead_of_dividing_among_four():
    evidence = resolve(aliases=ALIASES[:4] + ALIASES[5:])
    assert evidence.status == REQUIRES_REVIEW
    assert evidence.eligible_branch_ids == ()
    assert evidence.unresolved_branch_names == ("SENDERO MEXICALI",)


def test_ambiguous_alias_is_rejected():
    evidence = resolve(aliases=[*ALIASES, ("SENDERO MEXICALI", 3)])
    assert evidence.status == REQUIRES_REVIEW
    assert evidence.unresolved_branch_names == ("SENDERO MEXICALI",)


def test_unresolved_name_in_other_city_still_blocks_denominator():
    evidence = resolve(names=("VILLAS DEL REY", "SUCURSAL SIN ALIAS"))
    assert evidence.status == REQUIRES_REVIEW
    assert evidence.unresolved_branch_names == ("SUCURSAL SIN ALIAS",)


def test_kpi_out_of_scope_beca_is_ignored():
    evidence = resolve(names=("VILLAS DEL REY", "BECA"))
    assert evidence.status == VERIFIED
    assert evidence.eligible_branch_ids == (1,)


def test_repeated_names_and_snapshots_do_not_duplicate_gyms():
    evidence = resolve(
        snapshot_ids=(12, 11, 12, 10),
        names=("VILLAS DEL REY", "VILLAS DEL REY", "TEC MEXICALI"),
    )
    assert evidence.snapshot_ids == (10, 11, 12)
    assert evidence.eligible_branch_ids == (1, 4)


def test_normalizes_accents_and_underscore_aliases():
    evidence = resolve(
        city="  méXiCali ",
        names=("VILLAS_DEL_REY", "TEC MEXICALI"),
    )
    assert evidence.status == VERIFIED
    assert evidence.eligible_branch_ids == (1, 4)


def test_demo_branch_and_administrative_ids_never_eligible():
    evidence = resolve(
        names=("VILLAS DEL REY", "CORPORATIVO", "ADMINISTRADOR"),
        branches=[
            (1, "Mexicali", True),
            (100, "Mexicali", False),
            (1000, "Mexicali", False),
            (2, "Mexicali", False),
        ],
    )
    assert evidence.status == NO_CITY_EVIDENCE
    assert evidence.eligible_branch_ids == ()


@pytest.mark.parametrize("invalid_month", [date(2025, 12, 2), "2025-12"])
def test_rejects_invalid_month(invalid_month):
    with pytest.raises(ValueError):
        evaluate_historical_city_branch_evidence(
            month_start=invalid_month,
            city_key="Mexicali",
            snapshot_ids=(1,),
            raw_branch_names=(),
            gasca_aliases=(),
            catalog_branches=(),
        )


def test_rejects_empty_city():
    with pytest.raises(ValueError):
        resolve(city=" ")


def test_rejects_catalog_identity_disagreement():
    with pytest.raises(ValueError):
        resolve(branches=BRANCHES + [(1, "Tijuana", False)])


def test_rejects_invalid_snapshot_id():
    with pytest.raises(ValueError):
        resolve(snapshot_ids=(0,))


def test_canonical_statement_restricts_month_and_daily_report():
    sql = str(
        build_canonical_kpi_month_statement(month_start=MONTH).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "report_type_key = 'kpi_desempeno'" in sql
    assert "snapshot_kind = 'daily'" in sql
    assert "is_canonical is true" in sql
    assert "business_date >= '2025-12-01'" in sql
    assert "business_date <= '2025-12-31'" in sql


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _ReadOnlySession:
    def __init__(self, monthly_ids, raw_names, aliases, branches):
        self.answers = iter((monthly_ids, raw_names, aliases, branches))
        self.queries = []

    def execute(self, statement):
        self.queries.append(str(statement))
        return _Scalars(next(self.answers))


def test_db_adapter_uses_only_read_queries_and_maps_evidence():
    session = _ReadOnlySession(
        [10, 11],
        ["VILLAS DEL REY", "TEC MEXICALI"],
        ALIASES,
        BRANCHES,
    )
    evidence = read_historical_city_branch_evidence(
        month_start=MONTH, city_key="MEXICALI", session=session,
    )
    assert evidence.status == VERIFIED
    assert evidence.eligible_branch_ids == (1, 4)
    assert len(session.queries) == 4
    assert all(query.lstrip().startswith("SELECT") for query in session.queries)


def test_db_adapter_short_circuits_when_no_canonical_snapshot():
    session = _ReadOnlySession([], [], [], [])
    evidence = read_historical_city_branch_evidence(
        month_start=MONTH, city_key="MEXICALI", session=session,
    )
    assert evidence.status == NO_CANONICAL_SNAPSHOT
    assert len(session.queries) == 1
