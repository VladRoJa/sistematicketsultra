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
    MarketingCampaignV2RecipientDispatchExclusionORM,
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
        MarketingCampaignV2RecipientDispatchExclusionORM,
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


def test_cobranza_pilot_preparation_freezes_one_branch_and_is_idempotent(
    session, tmp_path, monkeypatch,
):
    """Actual Excel preview+freeze integration; no provider, no dispatch."""
    from types import SimpleNamespace
    from app.warehouse.jobs import cobranza_iventas_preparation as preparation

    monkeypatch.setenv("COBRANZA_IVENTAS_TEMPLATE_ID", "1")
    monkeypatch.setenv("WAREHOUSE_AUTOMATION_USER_ID", "47")
    monkeypatch.setattr(preparation, "db", SimpleNamespace(session=session))
    session.add(MarketingCampaignV2BlacklistORM(
        phone_mx10="6861000003", source_filename="blacklist.xlsx", created_by_user_id=47,
    ))
    session.commit()

    wb = Workbook()
    ws = wb.active
    ws.append(["Socio", "Teléfono", "Estatus"])
    ws.append(["Test A", "6861000001", "Rechazado"])
    ws.append(["Test B", "6861000002", "Rechazado"])
    ws.append(["Blacklist", "6861000003", "Rechazado"])
    file_path = tmp_path / "piloto_azahares.xlsx"
    wb.save(file_path)
    artifacts = [{
        "path": str(file_path), "sucursal_raw": "AZAHARES CUL", "rows_count": 3,
    }]
    result = preparation.prepare_cobranza_iventas_campaign(
        business_date="2026-11-10", artifacts=artifacts,
    )
    assert result["status"] == "PREPARED"
    assert result["recipient_count"] == 2
    assert result["blacklist_excluded_count"] == 1
    assert result["skipped_branches"] == []
    campaign = session.get(MarketingCampaignV2ORM, result["campaign_id"])
    assert campaign.source == "EXCEL_IMPORT"
    assert campaign.audience_definition_json["source_metadata"]["automation_job"] == (
        "cobranza_recurrente_rechazados"
    )
    assert campaign.audience_definition_json["source_metadata"]["business_date"] == "2026-11-10"
    assert sorted(row.phone_mx10 for row in campaign.recipients) == [
        "6861000001", "6861000002",
    ]

    repeat = preparation.prepare_cobranza_iventas_campaign(
        business_date="2026-11-10", artifacts=artifacts,
    )
    assert repeat == {"status": "ALREADY_PREPARED", "campaign_id": result["campaign_id"]}
    assert session.query(MarketingCampaignV2ORM).count() == 1


def test_cobranza_without_template_never_prepares_or_sends(session, monkeypatch):
    from types import SimpleNamespace
    from app.warehouse.jobs import cobranza_iventas_preparation as preparation

    monkeypatch.delenv("COBRANZA_IVENTAS_TEMPLATE_ID", raising=False)
    monkeypatch.setattr(preparation, "db", SimpleNamespace(session=session))
    result = preparation.prepare_cobranza_iventas_campaign(
        business_date="2026-11-10", artifacts=[],
    )
    assert result == {"status": "TEMPLATE_NOT_CONFIGURED"}
    assert session.query(MarketingCampaignV2ORM).count() == 0


@pytest.mark.parametrize(("id_header", "member_ids", "expected"), [
    ("IDSocio", ["000482", "000482"], "000482"),
    ("ID Socio", [482731], "482731"),
    ("IDSocio", ["000482", "927401", "000482"], None),
    ("IDSocio", ["000482", None], None),
    ("IDSocio", ["482731&sid=927401"], None),
    ("Socio", ["000482"], None),
])
def test_cobranza_payment_template_uses_the_frozen_member_id(
    session, tmp_path, monkeypatch, id_header, member_ids, expected,
):
    from types import SimpleNamespace

    from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
    from app.services.marketing_campaign_v2_submit_service import build_campaign_v2_provider_dispatch_batch
    from app.warehouse.jobs import cobranza_iventas_preparation as preparation

    monkeypatch.setenv("COBRANZA_IVENTAS_TEMPLATE_ID", "1")
    monkeypatch.setenv("WAREHOUSE_AUTOMATION_USER_ID", "47")
    monkeypatch.setattr(preparation, "db", SimpleNamespace(session=session))
    template = session.get(MarketingCampaignV2TemplateORM, 1)
    template.variables_json = {"1": "member_id"}
    session.commit()

    workbook = Workbook()
    workbook.active.append([id_header, "Teléfono", "Estatus"])
    for member_id in member_ids:
        workbook.active.append([member_id, "6861000001", "Rechazado"])
    workbook.active.append(["712305", "6861000002", "Rechazado"])
    path = tmp_path / "azahares.xlsx"
    workbook.save(path)

    result = preparation.prepare_cobranza_iventas_campaign(
        business_date="2026-11-10",
        artifacts=[{"path": path, "sucursal_raw": "AZAHARES CUL"}],
        isolated_branch_key="AZAHARES_CUL",
        allowed_phones=frozenset({"6861000001", "6861000002"}),
    )
    campaign = session.get(MarketingCampaignV2ORM, result["campaign_id"])
    frozen = {row.phone_mx10: row.member_id for row in campaign.recipients}
    other_member_id = "712305" if id_header != "Socio" else None
    assert frozen == {"6861000001": expected, "6861000002": other_member_id}

    plan = build_campaign_v2_preflight(
        campaign_id=campaign.id, template_id=template.id,
        allowed_sucursal_keys=None, session=session,
    )
    variables = {row.phone_mx10: dict(row.variables) for row in plan.batches[0].recipients}
    assert variables["6861000001"] == ({"1": expected} if expected else {})
    assert variables["6861000002"] == ({"1": other_member_id} if other_member_id else {})
    assert plan.ready is (expected is not None)
    assert bool(plan.blocked_missing_required_variable) is (expected is None)
    if plan.ready:
        batch = build_campaign_v2_provider_dispatch_batch(plan=plan, batch=plan.batches[0])
        assert {lead.phone: lead.variables for lead in batch.leads} == {
            "5216861000001": (expected,),
            "5216861000002": ("712305",),
        }


def test_cobranza_pilot_only_freezes_villas_and_cannot_expand_on_same_day(
    session, tmp_path, monkeypatch,
):
    """The pilot never includes another branch or creates a second daily cohort."""
    from types import SimpleNamespace
    from app.warehouse.jobs import cobranza_iventas_preparation as preparation

    monkeypatch.setenv("COBRANZA_IVENTAS_TEMPLATE_ID", "1")
    monkeypatch.setenv("WAREHOUSE_AUTOMATION_USER_ID", "47")
    monkeypatch.setattr(preparation, "db", SimpleNamespace(session=session))
    session.add(Sucursal(
        sucursal_id=2, serie="VILLAS", sucursal="Villas del Rey",
        estado="BC", operational_status="ACTIVA", is_demo=False,
        municipio="Mexicali", direccion="Prueba sintetica",
    ))
    session.add(TrackBranchCatalogORM(
        sucursal_canon="VILLAS_DEL_REY", sucursal_id=2,
        track_label="VILLAS DEL REY", display_order=2, is_track_active=True,
    ))
    session.add(MarketingCampaignV2ChannelBindingORM(
        provider="IVENTAS", sucursal_id=2, sucursal_canon="VILLAS_DEL_REY",
        provider_channel_id="channel-villas", is_active=True, is_default=True,
        created_by_user_id=47, updated_by_user_id=47,
    ))
    template = session.get(MarketingCampaignV2TemplateORM, 1)
    template.compatible_channel_ids_json = ["channel-16", "channel-villas"]
    session.commit()

    artifacts = []
    for branch, phone in [
        ("VILLAS DEL REY", "6861000007"),
        ("AZAHARES CUL", "6861000008"),
    ]:
        wb = Workbook()
        ws = wb.active
        ws.append(["Socio", "Telefono", "Estatus"])
        ws.append(["Socio sintetico", phone, "Rechazado"])
        path = tmp_path / (branch.replace(" ", "_") + ".xlsx")
        wb.save(path)
        artifacts.append({"sucursal_raw": branch, "path": str(path)})

    result = preparation.prepare_cobranza_iventas_campaign(
        business_date="2026-11-11", artifacts=artifacts,
        pilot_branch_key="VILLAS_DEL_REY",
    )
    assert result["status"] == "PREPARED"
    assert result["pilot_branch_key"] == "VILLAS_DEL_REY"
    assert result["recipient_count"] == 1
    campaign = session.get(MarketingCampaignV2ORM, result["campaign_id"])
    assert campaign.audience_definition_json["source_metadata"]["pilot_branch_key"] == "VILLAS_DEL_REY"
    assert {recipient.phone_mx10 for recipient in campaign.recipients} == {"6861000007"}
    assert len(session.query(MarketingCampaignV2ORM).all()) == 1

    same_scope = preparation.prepare_cobranza_iventas_campaign(
        business_date="2026-11-11", artifacts=artifacts,
        pilot_branch_key="VILLAS_DEL_REY",
    )
    assert same_scope["status"] == "ALREADY_PREPARED"
    with pytest.raises(preparation.CobranzaCampaignPreparationError, match="otro alcance"):
        preparation.prepare_cobranza_iventas_campaign(
            business_date="2026-11-11", artifacts=artifacts,
        )
    with pytest.raises(preparation.CobranzaCampaignPreparationError, match="otro alcance"):
        preparation.prepare_cobranza_iventas_campaign(
            business_date="2026-11-11", artifacts=artifacts,
            pilot_branch_key="AZAHARES_CUL",
        )
    assert session.query(MarketingCampaignV2ORM).count() == 1


def test_cobranza_pilot_never_falls_back_to_other_branch(
    session, tmp_path, monkeypatch,
):
    from types import SimpleNamespace
    from app.warehouse.jobs import cobranza_iventas_preparation as preparation

    monkeypatch.setenv("COBRANZA_IVENTAS_TEMPLATE_ID", "1")
    monkeypatch.setenv("WAREHOUSE_AUTOMATION_USER_ID", "47")
    monkeypatch.setattr(preparation, "db", SimpleNamespace(session=session))
    wb = Workbook()
    ws = wb.active
    ws.append(["Socio", "Telefono", "Estatus"])
    ws.append(["Socio sintetico", "6861000008", "Rechazado"])
    file_path = tmp_path / "AZAHARES_CUL.xlsx"
    wb.save(file_path)
    with pytest.raises(preparation.CobranzaCampaignPreparationError, match="no aparece"):
        preparation.prepare_cobranza_iventas_campaign(
            business_date="2026-11-11",
            artifacts=[{"sucursal_raw": "AZAHARES CUL", "path": str(file_path)}],
            pilot_branch_key="VILLAS_DEL_REY",
        )
    assert session.query(MarketingCampaignV2ORM).count() == 0



def test_independencia_uses_approved_tec_template_without_losing_origin(session):
    """The source channel lacks approval; a valid frozen TEC route permits it."""
    for branch_id, key in ((3, "INDEPENDENCIA"), (4, "TEC_MXL")):
        session.add(Sucursal(
            sucursal_id=branch_id, serie=key, sucursal=key,
            estado="BC", operational_status="ACTIVA", is_demo=False,
            municipio="Mexicali", direccion="Prueba sintética",
        ))
        session.add(TrackBranchCatalogORM(
            sucursal_canon=key, sucursal_id=branch_id,
            track_label=key, display_order=branch_id, is_track_active=True,
        ))
    source = MarketingCampaignV2ChannelBindingORM(
        provider="IVENTAS", sucursal_id=3, sucursal_canon="INDEPENDENCIA",
        provider_channel_id="channel-independencia", is_active=True, is_default=True,
        created_by_user_id=47, updated_by_user_id=47,
    )
    sender = MarketingCampaignV2ChannelBindingORM(
        provider="IVENTAS", sucursal_id=4, sucursal_canon="TEC_MXL",
        provider_channel_id="channel-tec", is_active=True, is_default=True,
        created_by_user_id=47, updated_by_user_id=47,
    )
    session.add_all((source, sender))
    session.flush()
    source.metadata_json = {"dispatch_via_binding_id": int(sender.id)}
    session.add(MarketingCampaignV2TemplateORM(
        id=18, provider="IVENTAS", template_name="ug_cobranza_cargo_fallido_pago",
        label="Pago en línea", is_active=True, purposes_json=["ACTIVE_MEMBERS"],
        variables_json={"1": "member_id"},
        compatible_channel_ids_json=["channel-tec"],
        created_by_user_id=47, updated_by_user_id=47,
    ))
    session.commit()
    audience = (
        b"sucursal,telefono,id_socio\n"
        b"INDEPENDENCIA,6861000001,247396\n"
    )
    args = dict(
        file_bytes=audience, filename="independencia.csv",
        name="Cobranza TEC", purpose="ACTIVE_MEMBERS",
        template_id=18, allowed_sucursal_keys=None, session=session,
    )
    preview = svc.preview_excel_campaign(**args)
    assert preview["unique_recipient_count"] == 1
    frozen = svc.freeze_excel_campaign(
        **args, expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=47,
    )
    campaign = session.get(MarketingCampaignV2ORM, frozen["campaign_id"])
    assert campaign.recipients[0].member_id == "247396"
    assert campaign.audience_definition_json["source_metadata"]["branch_counts"] == {"INDEPENDENCIA": 1}
    route = campaign.audience_definition_json["dispatch_channel_routing"]["routes"]["INDEPENDENCIA"]
    assert route["outbound_channel_id"] == "channel-tec"
    assert route["outbound_sucursal_canon"] == "TEC_MXL"
