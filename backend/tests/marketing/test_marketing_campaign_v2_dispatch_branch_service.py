from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchAliasORM, TrackBranchCatalogORM
from app.services import marketing_campaign_v2_dispatch_branch_service as service


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Sucursal.__table__.to_metadata(metadata)
    TrackBranchCatalogORM.__table__.to_metadata(metadata)
    TrackBranchAliasORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        value.add(
            Sucursal(
                sucursal_id=4,
                serie="TEC",
                sucursal="Tecnológico",
                estado="BC",
                operational_status="ACTIVA",
                is_demo=False,
                municipio="Mexicali",
                direccion="QA",
            )
        )
        value.add(
            TrackBranchCatalogORM(
                sucursal_canon="TEC_MXL",
                sucursal_id=4,
                track_label="TEC MXL",
                display_order=4,
                is_track_active=True,
            )
        )
        value.add(
            TrackBranchAliasORM(
                source_family="iventas_family",
                raw_branch_name="tecnologico-2",
                sucursal_canon="TEC_MXL",
                is_active=True,
            )
        )
        value.commit()
        yield value
    engine.dispose()


@pytest.mark.parametrize(
    "value",
    ["Tecnológico", "tecnologico-2", "TEC_MXL", "TEC MXL"],
)
def test_tecnologico_variants_resolve_to_same_suite_branch(session, value):
    result = service.resolve_dispatch_branch_key(value, session=session)

    assert result is not None
    assert result.sucursal_id == 4
    assert result.sucursal_canon == "TEC_MXL"


def test_frozen_recipient_prefers_frozen_evidence_key(session):
    recipient = NS(
        sucursal="Texto no canónico",
        evidence_rows=[NS(sucursal_key="tecnologico-2")],
    )

    result = service.resolve_frozen_recipient_branch(recipient, session=session)

    assert result is not None
    assert result.sucursal_id == 4
    assert result.sucursal_canon == "TEC_MXL"


def test_conflicting_frozen_branch_evidence_is_not_reassigned(session):
    recipient = NS(
        sucursal="Tecnológico",
        evidence_rows=[
            NS(sucursal_key="TEC MXL"),
            NS(sucursal_key="OTRA SUCURSAL"),
        ],
    )

    assert service.resolve_frozen_recipient_branch(
        recipient,
        session=session,
    ) is None


def test_phone_only_recipient_is_unresolved(session):
    recipient = NS(sucursal=None, evidence_rows=[])

    assert service.resolve_frozen_recipient_branch(
        recipient,
        session=session,
    ) is None
