from __future__ import annotations

from datetime import date, datetime, timezone
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect as sa_inspect, text

from app.models.marketing import (
    MarketingCampaignV2TariffORM,
    MarketingCampaignV2TariffOverrideORM,
)
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_creation_service as creation
from app.services import marketing_campaign_v2_tariff_classifier_service as classifier


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, rows_by_model=None):
        self.rows_by_model = rows_by_model or {}
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.queried_models = []

    def query(self, model):
        self.queried_models.append(model)
        return _Query(self.rows_by_model.get(model, ()))

    def add(self, row):
        self.added.append(row)

    def flush(self):
        for index, row in enumerate(self.added, start=1):
            if getattr(row, "id", None) is None:
                row.id = index

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _candidate(raw: str, *, row_id=1):
    return audience.MarketingCampaignV2AudienceCandidate(
        source=audience.SOURCE_ACTIVE_MEMBERS,
        source_ref_type="SOCIOS_ACTIVOS_SNAPSHOT_ROW",
        source_ref_id=row_id,
        source_snapshot_id=77,
        phone_raw=f"68610000{row_id:02d}",
        phone_mx10=f"68610000{row_id:02d}",
        member_id=f"SOCIO-{row_id}",
        member_pin=f"PIN-{row_id}",
        member_name=f"Socio {row_id}",
        sucursal="BRANCH A",
        sucursal_key="BRANCH A",
        tarifa_raw=raw,
        fecha_vencimiento=date(2026, 10, 31),
        evidence=("CANONICAL_ACTIVE_SNAPSHOT",),
    )


def _source_result(candidates):
    rows = tuple(candidates)
    return audience._SourceLoadResult(
        universe_count=len(rows),
        scoped_count=len(rows),
        candidates=rows,
        current_status_blocked=(),
        current_status_counts={},
        metadata={"activos_snapshot_id": 77, "activos_cutoff_date": "2026-10-01"},
    )


CANONICAL_CATEGORIES = (
    "Agregadora",
    "Anualidad",
    "Beca",
    "Bimestre",
    "Convenio",
    "Diario",
    "Domiciliado",
    "Estudiante",
    "Instructor",
    "Mensualidad",
    "Mes Reward",
    "Pase de Cortesía",
    "Recurrente",
    "Semana",
    "Semestre",
    "Trimestre",
)


def _category_snapshot_rows():
    return [
        NS(
            tarifa_key=f"KEY-{index}",
            tarifa_raw=f"Raw {index}",
            categoria_tarifa=category,
            audience_family="DOMICILIADO",
        )
        for index, category in enumerate(CANONICAL_CATEGORIES, start=1)
    ]


def test_canonical_categories_come_only_from_snapshot_distinct_and_sorted():
    snapshot_rows = [
        *_category_snapshot_rows(),
        NS(
            tarifa_key="DUP",
            tarifa_raw="Dup",
            categoria_tarifa="Domiciliado",
            audience_family="DOMICILIADO",
        ),
        NS(
            tarifa_key="BLANK",
            tarifa_raw="Blank",
            categoria_tarifa="   ",
            audience_family="DOMICILIADO",
        ),
    ]
    session = _Session(
        {
            MarketingCampaignV2TariffORM: snapshot_rows,
            MarketingCampaignV2TariffOverrideORM: [
                NS(
                    tarifa_key="OVERRIDE",
                    categoria_tarifa="Nueva categoría accidental",
                    audience_family="CONVENIO",
                )
            ],
        }
    )

    result = classifier.list_canonical_tariff_categories(session=session)

    assert result == CANONICAL_CATEGORIES
    assert session.queried_models == [MarketingCampaignV2TariffORM]
    assert "Nueva categoría accidental" not in result


def test_effective_catalog_precedence_override_over_snapshot():
    snapshot = NS(
        tarifa_key="MEMBRESIA LM",
        categoria_tarifa="Membresía",
        audience_family="DOMICILIADO",
    )
    override = NS(
        tarifa_key="MEMBRESIA LM",
        categoria_tarifa="Convenio",
        audience_family="CONVENIO",
    )
    session = _Session(
        {
            MarketingCampaignV2TariffORM: [snapshot],
            MarketingCampaignV2TariffOverrideORM: [override],
        }
    )

    catalog = audience._read_v2_tariff_catalog(session=session)

    assert catalog["MEMBRESIA LM"] == ("Convenio", "CONVENIO")


def test_snapshot_without_override_and_unknown_without_override_keep_contract():
    snapshot = NS(
        tarifa_key="DOM",
        categoria_tarifa="Domiciliado",
        audience_family="DOMICILIADO",
    )
    session = _Session(
        {
            MarketingCampaignV2TariffORM: [snapshot],
            MarketingCampaignV2TariffOverrideORM: [],
        }
    )
    catalog = audience._read_v2_tariff_catalog(session=session)

    known = audience._classify_candidate(_candidate("DOM"), tariff_catalog=catalog)
    unknown = audience._classify_candidate(_candidate("DESCONOCIDA"), tariff_catalog=catalog)

    assert known.categoria_tarifa == "Domiciliado"
    assert known.audience_family == "DOMICILIADO"
    assert unknown.categoria_tarifa is None
    assert unknown.audience_family is None


def test_unclassified_aggregation_is_by_normalized_key_and_impact(monkeypatch):
    monkeypatch.setattr(
        classifier.audience,
        "_load_active_source",
        lambda **_: _source_result(
            [
                _candidate("  plan   familiar  ", row_id=1),
                _candidate("PLAN FAMILIAR", row_id=2),
                _candidate("Otra", row_id=3),
                _candidate("Otra", row_id=4),
                _candidate("Otra", row_id=5),
                _candidate("Conocida", row_id=6),
            ]
        ),
    )
    monkeypatch.setattr(
        classifier.audience,
        "_read_v2_tariff_catalog",
        lambda **_: {"CONOCIDA": ("Cat", "DOMICILIADO")},
    )

    result = classifier.list_unclassified_tariffs(
        source="ACTIVE_MEMBERS",
        allowed_sucursal_keys=None,
        session=object(),
    )

    assert [row["tarifa_key"] for row in result["rows"]] == [
        "OTRA",
        "PLAN FAMILIAR",
    ]
    assert [row["row_count"] for row in result["rows"]] == [3, 2]
    assert result["total_unique_tariffs"] == 2
    assert result["total_unclassified_rows"] == 5


def test_upsert_normalizes_key_resolves_canonical_category_and_validates_family():
    session = _Session(
        {
            MarketingCampaignV2TariffOverrideORM: [],
            MarketingCampaignV2TariffORM: _category_snapshot_rows(),
        }
    )
    result = classifier.upsert_tariff_classification(
        tarifa_key="  ３ meses   proporcional  ",
        categoria_tarifa=" trimestre ",
        audience_family="trimestral",
        user_id=7,
        representative_raw="3 MESES PROPORCIONAL",
        session=session,
        now=datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc),
    )

    assert result["tarifa_key"] == "3 MESES PROPORCIONAL"
    assert result["categoria_tarifa"] == "Trimestre"
    assert result["audience_family"] == "TRIMESTRAL"
    assert result["created_by_user_id"] == 7
    assert result["updated_by_user_id"] == 7
    assert session.commits == 1

    for invalid_category in ("Dom", "Domiciliados", "Nueva categoría"):
        with pytest.raises(
            classifier.MarketingCampaignV2TariffClassifierValidationError,
            match="catálogo canónico",
        ):
            classifier.upsert_tariff_classification(
                tarifa_key="X",
                categoria_tarifa=invalid_category,
                audience_family="DOMICILIADO",
                user_id=7,
                session=_Session(
                    {
                        MarketingCampaignV2TariffORM: _category_snapshot_rows(),
                        MarketingCampaignV2TariffOverrideORM: [],
                    }
                ),
            )

    with pytest.raises(
        classifier.MarketingCampaignV2TariffClassifierValidationError,
        match="audience_family",
    ):
        classifier.upsert_tariff_classification(
            tarifa_key="X",
            categoria_tarifa="Domiciliado",
            audience_family="NO_EXISTE",
            user_id=7,
            session=_Session(
                {
                    MarketingCampaignV2TariffORM: _category_snapshot_rows(),
                    MarketingCampaignV2TariffOverrideORM: [],
                }
            ),
        )


def test_override_model_has_unique_normalized_business_key_contract():
    table = MarketingCampaignV2TariffOverrideORM.__table__
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("tarifa_key",) in unique_columns
    assert table.c.created_by_user_id.nullable is True
    assert table.c.updated_by_user_id.nullable is True


def test_preview_and_fingerprint_change_after_override(monkeypatch):
    source_result = _source_result([_candidate("NUEVA TARIFA")])
    monkeypatch.setattr(audience, "_load_active_source", lambda **_: source_result)

    before_session = _Session(
        {
            MarketingCampaignV2TariffORM: [],
            MarketingCampaignV2TariffOverrideORM: [],
        }
    )
    after_session = _Session(
        {
            MarketingCampaignV2TariffORM: [],
            MarketingCampaignV2TariffOverrideORM: [
                NS(
                    tarifa_key="NUEVA TARIFA",
                    categoria_tarifa="Domiciliado",
                    audience_family="DOMICILIADO",
                )
            ],
        }
    )

    before = audience._build_campaign_v2_audience_plan(
        source="ACTIVE_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from=None,
        expiration_date_to=None,
        session=before_session,
    )
    after = audience._build_campaign_v2_audience_plan(
        source="ACTIVE_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from=None,
        expiration_date_to=None,
        session=after_session,
    )

    assert audience._serialize_preview(before)["unclassified_family_count"] == 1
    assert audience._serialize_preview(after)["unclassified_family_count"] == 0
    assert audience._serialize_preview(before)["unique_recipient_count"] == 0
    assert audience._serialize_preview(after)["unique_recipient_count"] == 1
    assert creation._fingerprint_plan(before) != creation._fingerprint_plan(after)


def test_classifier_and_audience_do_not_touch_legacy_tariff_model():
    assert "MarketingReactivationTariffORM" not in inspect.getsource(classifier)
    assert "MarketingReactivationTariffORM" not in inspect.getsource(audience)


def test_override_migration_round_trip_and_parent():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "b7c2e9f4a1d6_add_campaign_v2_tariff_overrides.py"
    )
    spec = importlib.util.spec_from_file_location("m71_tariff_override", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.revision == "b7c2e9f4a1d6"
    assert module.down_revision == "f6c1d8a3b2e4"

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = module.op
        module.op = operations
        try:
            module.upgrade()
            inspector = sa_inspect(connection)
            assert "marketing_campaign_v2_tariff_overrides" in inspector.get_table_names()
            uniques = inspector.get_unique_constraints("marketing_campaign_v2_tariff_overrides")
            assert any(item["column_names"] == ["tarifa_key"] for item in uniques)
            module.downgrade()
            assert "marketing_campaign_v2_tariff_overrides" not in sa_inspect(connection).get_table_names()
        finally:
            module.op = original_op
