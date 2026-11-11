"""Real PostgreSQL serialization of concurrent QA freezes. Synthetic quota_ci only."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign, MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2RecipientEvidenceORM as Evidence,
    MarketingCampaignV2ProviderCampaignORM as Child,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM as Branch
from app.services import marketing_campaign_v2_template_probe_service as probe
from app.services.marketing_campaign_v2_qa_manual_service import build_campaign_v2_qa_manual_preview


def test_two_connections_freeze_one_qa_cohort_without_provider_requests():
    url = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("isolated PostgreSQL quota_ci required")
    parts = sa.engine.make_url(url)
    if (parts.get_backend_name() != "postgresql" or parts.host not in {"127.0.0.1", "localhost"}
            or parts.database != "quota_ci" or parts.username != "quota_ci"):
        pytest.fail("Refusing a non-synthetic database")
    engine = sa.create_engine(url)
    md = sa.MetaData()
    users = sa.Table("users", md, sa.Column("id", sa.Integer, primary_key=True))
    for name in ["socios_vencidos_cartera", "socios_activos_snapshot_rows", "socios_activos_snapshots"]:
        sa.Table(name, md, sa.Column("id", sa.BigInteger, primary_key=True))
    # The retry eligibility check reads provider children, even when none were
    # submitted. Keep the isolated fixture aligned with that read-only query.
    for table_name in ("marketing_campaign_v2_channel_bindings",
                       "marketing_campaign_v2_templates"):
        sa.Table(table_name, md, sa.Column("id", sa.BigInteger, primary_key=True))
    for model in [Sucursal, Branch, Campaign, Recipient, Evidence, Child]:
        model.__table__.to_metadata(md)
    md.create_all(engine)
    try:
        with engine.begin() as connection:
            connection.execute(users.insert().values(id=47))
            connection.execute(md.tables["sucursales"].insert().values(
                sucursal_id=4, serie="TEC", sucursal="TEC", estado="BC", operational_status="ACTIVA",
                is_demo=False, municipio="Mexicali", direccion="Synthetic QA"))
            connection.execute(md.tables[Branch.__tablename__].insert().values(
                sucursal_canon="TEC_MXL", sucursal_id=4, track_label="TEC MXL",
                display_order=4, is_track_active=True))
        selected = NS(id=7, template_name="selected", variables_json={},
                      compatible_channel_ids_json=[], metadata_json={})
        groups = {"tec": dict(binding_id=40, sender_sucursal_id=4, sender="TEC_MXL",
                              origins=["INDEPENDENCIA", "TEC_MXL"])}
        barrier = Barrier(2)

        def preview(**kwargs):
            kwargs.pop("provider_channel_id")
            return build_campaign_v2_qa_manual_preview(**kwargs)

        def prepare(_):
            with Session(engine) as active:
                barrier.wait(timeout=15)
                probe.prepare_template_probes(campaign_id=42, template_id=7,
                    recipient_name="Authorized QA", phone="6861000001",
                    authorization_reference="Synthetic operator authorization",
                    confirmed_authorized=True, actor_user_id=47, session=active)

        with patch.object(probe, "_context", return_value=(NS(purpose="REACTIVATION"), selected, groups)), \
             patch.object(probe, "commercial_certifications", return_value={}), \
             patch.object(probe, "preview_qa_manual_http", side_effect=preview), \
             patch.object(probe, "template_probe_matrix", return_value={"rows": []}), \
             ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(prepare, range(2)))
        with Session(engine) as active:
            assert active.query(Campaign).count() == 1
            assert active.query(Recipient).count() == 1
            assert active.query(Evidence).count() == 1
            qa = active.query(Campaign).one()
            assert probe.probe_spec(qa)["authorized_by_user_id"] == 47
            assert qa.source == "QA_MANUAL"
    finally:
        md.drop_all(engine)
        engine.dispose()
