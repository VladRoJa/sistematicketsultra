from __future__ import annotations

from io import BytesIO
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, select, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from openpyxl import Workbook
import pytest

@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kw):
    return "INTEGER"

from app.models.marketing import (
    MarketingCampaignV2BlacklistORM,
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2TemplateORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchAliasORM, TrackBranchCatalogORM
from app.services import marketing_campaign_v2_excel_import_service as svc


def _csv(rows):
    return ("sucursal,telefono,nombre,pin,tarifa_ultimo_plan,fecha_vencimiento\n" +
            "\n".join(",".join(map(str, row)) for row in rows) + "\n").encode("utf-8")


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["sucursal", "telefono", "nombre", "tarifa_actual", "fecha_vencimiento_2026"])
    for row in rows:
        ws.append(row)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    for table in ("socios_vencidos_cartera", "socios_activos_snapshot_rows", "socios_activos_snapshots"):
        Table(table, metadata, Column("id", BigInteger, primary_key=True))
    for orm in (
        Sucursal, TrackBranchCatalogORM, TrackBranchAliasORM,
        MarketingCampaignV2BlacklistORM, MarketingCampaignV2ChannelBindingORM,
        MarketingCampaignV2TemplateORM, MarketingCampaignV2ORM,
        MarketingCampaignV2RecipientORM, MarketingCampaignV2RecipientEvidenceORM,
    ):
        orm.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as active:
        active.execute(Table("users", MetaData(), autoload_with=engine).insert().values(id=47))
        active.execute(Table("sucursales", MetaData(), autoload_with=engine).insert().values(
            sucursal_id=16, serie="AZAH", sucursal="Azahares Culiacan",
            estado="Sinaloa", operational_status="ACTIVA", is_demo=False,
            municipio="Culiacan", direccion="PRUEBA",
        ))
        active.add(TrackBranchCatalogORM(
            sucursal_canon="AZAHARES_CUL", sucursal_id=16,
            track_label="AZAHARES CUL", display_order=16, is_track_active=True,
        ))
        active.add(MarketingCampaignV2ChannelBindingORM(
            provider="IVENTAS", sucursal_id=16, sucursal_canon="AZAHARES_CUL",
            provider_channel_id="channel-16", is_active=True, is_default=True,
            created_by_user_id=47, updated_by_user_id=47,
        ))
        active.add(MarketingCampaignV2TemplateORM(
            provider="IVENTAS", template_name="anual_3999_v", label="Anualidad",
            is_active=True, purposes_json=["REACTIVATION", "ACTIVE_MEMBERS"],
            variables_json={}, compatible_channel_ids_json=["channel-16"],
            created_by_user_id=47, updated_by_user_id=47,
        ))
        active.commit()
        yield active
    engine.dispose()


def _preview(session, raw, filename="audiencia.csv"):
    return svc.preview_excel_campaign(
        file_bytes=raw, filename=filename, name="ANUAL 3999 2026",
        purpose="REACTIVATION", template_id=1,
        allowed_sucursal_keys=["AZAHARES_CUL"], session=session,
    )


def test_excel_csv_freeze_keeps_auditable_exact_cohort_and_excludes_blacklist(session):
    session.add(MarketingCampaignV2BlacklistORM(
        phone_mx10="6861000002", source_filename="blacklist.xlsx", created_by_user_id=47,
    ))
    session.commit()
    raw = _csv([
        ["AZAHARES CUL", "6861000001", "Uno", "12", "ANUALIDAD", "2026-08-05"],
        ["AZAHARES CUL", "6861000002", "Dos", "13", "ANUALIDAD", "2026-09-05"],
    ])
    preview = _preview(session, raw)
    assert preview["rows_read"] == 2
    assert preview["unique_recipient_count"] == 1
    assert preview["blacklist_excluded_count"] == 1
    result = svc.freeze_excel_campaign(
        file_bytes=raw, filename="audiencia.csv", name="ANUAL 3999 2026",
        purpose="REACTIVATION", template_id=1,
        allowed_sucursal_keys=["AZAHARES_CUL"], session=session,
        created_by_user_id=47,
        expected_preview_fingerprint=preview["preview_fingerprint"],
    )
    assert result["recipient_count"] == 1
    rows = session.query(MarketingCampaignV2RecipientORM).all()
    assert [r.phone_mx10 for r in rows] == ["6861000001"]
    assert rows[0].evidence_rows[0].sucursal_key == "AZAHARES_CUL"
    campaign = session.query(MarketingCampaignV2ORM).one()
    assert campaign.source == "EXCEL_IMPORT"
    assert campaign.audience_definition_json["source_metadata"]["upload_sha256"] == preview["sha256"]


def test_xlsx_parses_active_members_and_preserves_expiration(session):
    raw = _xlsx([["AZAHARES CUL", "6861000001", "Renovacion", "ANUALIDAD", "2026-12-12"]])
    preview = svc.preview_excel_campaign(
        file_bytes=raw, filename="activos.xlsx", name="ANUAL ACTIVOS",
        purpose="ACTIVE_MEMBERS", template_id=1, allowed_sucursal_keys=None,
        session=session,
    )
    assert preview["unique_recipient_count"] == 1


@pytest.mark.parametrize("rows", [
    [["AZAHARES CUL", "6861000001", "Uno", "12", "ANUALIDAD", "2026-09-01"],
     ["AZAHARES CUL", "6861000001", "Dos", "13", "ANUALIDAD", "2026-09-02"]],
    [["INSURGENTES", "6861000001", "Uno", "12", "ANUALIDAD", "2026-09-01"]],
    [["AZAHARES CUL", "invalid", "Uno", "12", "ANUALIDAD", "2026-09-01"]],
])
def test_fail_closed_duplicate_unknown_branch_and_invalid_phone(session, rows):
    with pytest.raises(svc.ExcelCampaignImportValidationError):
        _preview(session, _csv(rows))
    assert session.query(MarketingCampaignV2ORM).count() == 0


def test_stale_preview_blacklist_change_rejects_freeze(session):
    raw = _csv([
        ["AZAHARES CUL", "6861000001", "Uno", "12", "ANUALIDAD", "2026-08-05"],
        ["AZAHARES CUL", "6861000002", "Dos", "13", "ANUALIDAD", "2026-08-05"],
    ])
    preview = _preview(session, raw)
    session.add(MarketingCampaignV2BlacklistORM(
        phone_mx10="6861000002", source_filename="new.xlsx", created_by_user_id=47,
    ))
    session.commit()
    with pytest.raises(svc.ExcelCampaignImportConflictError):
        svc.freeze_excel_campaign(
            file_bytes=raw, filename="audiencia.csv", name="ANUAL 3999 2026",
            purpose="REACTIVATION", template_id=1, session=session,
            allowed_sucursal_keys=["AZAHARES_CUL"], created_by_user_id=47,
            expected_preview_fingerprint=preview["preview_fingerprint"],
        )
    assert session.query(MarketingCampaignV2ORM).count() == 0
