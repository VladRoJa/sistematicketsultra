from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as NS

from openpyxl import load_workbook

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.services import marketing_campaign_v2_delivery_export_service as delivery
from app.services import marketing_campaign_v2_preflight_service as preflight
from app.services.marketing_campaign_v2_dispatch_branch_service import (
    MarketingCampaignV2DispatchBranch,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src" / "app" / "marketing-campaign-v2"


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, rows):
        self.rows = list(rows)

    def query(self, *_args):
        return _Query(self.rows)


def _recipient(index: int):
    phone = f"686100000{index}"
    return NS(
        id=index,
        campaign_id=77,
        phone_mx10=phone,
        member_name=f"SOCIO {index}",
        member_id=f"M{index}",
        member_pin=f"P{index}",
        sucursal="TECNOLOGICO",
        tarifa_raw="MENSUALIDAD",
        audience_family="DOMICILIADO",
        fecha_vencimiento_date=None,
        evidence_rows=[],
    )


def _xlsx_phones(payload: bytes) -> set[str]:
    rows = list(load_workbook(BytesIO(payload)).active.values)
    return {str(row[0]) for row in rows[1:]}


def test_m1_sendable_export_and_preflight_have_exact_phone_set(monkeypatch):
    rows = [_recipient(index) for index in range(1, 6)]
    session = _Session(rows)
    blacklist: set[str] = set()

    monkeypatch.setattr(
        delivery,
        "get_campaign_v2",
        lambda **_kwargs: {
            "id": 77,
            "name": "M1 Acceptance",
            "purpose": "REACTIVATION",
        },
    )
    monkeypatch.setattr(
        delivery,
        "get_blacklisted_phones",
        lambda **_kwargs: set(blacklist),
    )

    baseline = delivery.build_campaign_v2_sendable_projection(
        campaign_id=77,
        allowed_sucursal_keys=None,
        session=session,
    )
    assert len(baseline["frozen_recipients"]) == 5
    assert {row.phone_mx10 for row in baseline["sendable_recipients"]} == {
        row.phone_mx10 for row in rows
    }

    blacklist.update({"6861000002", "6861000004"})

    template = NS(
        id=10,
        template_name="qa_template",
        variables_json={"1": "first_name"},
        compatible_channel_ids_json=[],
    )
    monkeypatch.setattr(
        preflight,
        "resolve_dispatch_template",
        lambda **_kwargs: template,
    )
    monkeypatch.setattr(
        preflight,
        "resolve_frozen_recipient_branch",
        lambda _recipient, **_kwargs: MarketingCampaignV2DispatchBranch(
            sucursal_id=4,
            sucursal_canon="TEC_MXL",
            track_label="Tecnológico",
            matched_key="TECNOLOGICO",
        ),
    )
    monkeypatch.setattr(
        preflight,
        "resolve_dispatch_channel_binding",
        lambda **_kwargs: NS(
            id=9,
            provider_channel_id="channel-tec",
        ),
    )

    frozen_payload, _ = delivery.export_campaign_v2_delivery_package(
        campaign_id=77,
        allowed_sucursal_keys=None,
        session=session,
    )
    sendable_payload, _ = delivery.export_campaign_v2_sendable_package(
        campaign_id=77,
        allowed_sucursal_keys=None,
        session=session,
    )
    plan = preflight.build_campaign_v2_preflight(
        campaign_id=77,
        template_id=10,
        allowed_sucursal_keys=None,
        session=session,
    )

    assert _xlsx_phones(frozen_payload) == {row.phone_mx10 for row in rows}
    assert _xlsx_phones(sendable_payload) == {
        "6861000001",
        "6861000003",
        "6861000005",
    }
    assert set(plan.sendable_phones) == _xlsx_phones(sendable_payload)
    assert plan.frozen_count == 5
    assert plan.blacklisted_phones == ("6861000002", "6861000004")
    assert plan.ready is True


def test_m1_campaign_v2_persists_one_to_many_provider_campaign_contract():
    relationship = MarketingCampaignV2ORM.__mapper__.relationships["provider_campaigns"]

    assert relationship.uselist is True
    assert relationship.mapper.class_ is MarketingCampaignV2ProviderCampaignORM
    assert MarketingCampaignV2ProviderCampaignORM.__table__.c.campaign_v2_id.nullable is False

    parent_columns = MarketingCampaignV2ORM.__table__.c
    assert "provider" in parent_columns
    assert "provider_campaign_id" in parent_columns


def test_m1_backend_dispatch_surface_has_no_provider_post():
    sources = "\n".join(
        (BACKEND_ROOT / path).read_text(encoding="utf-8")
        for path in (
            "app/routes/marketing_campaign_v2_routes.py",
            "app/services/marketing_campaign_v2_delivery_export_service.py",
            "app/services/marketing_campaign_v2_dispatch_branch_service.py",
            "app/services/marketing_campaign_v2_dispatch_config_service.py",
            "app/services/marketing_campaign_v2_preflight_service.py",
        )
    ).lower()

    for forbidden in (
        "post /v2/broadcast",
        "requests.post(",
        "httpx.post(",
        "session.post(",
        "graphql mutation",
        "mutation {",
    ):
        assert forbidden not in sources


def test_m1_frontend_has_no_phone_vars_or_channel_authority_in_preflight_request():
    service_source = (
        FRONTEND_ROOT / "marketing-campaign-v2.service.ts"
    ).read_text(encoding="utf-8")
    start = service_source.index("preflightCampaign(")
    end = service_source.index("exportCampaignDeliveryPackage(", start)
    method_source = service_source[start:end]

    assert "{ template_id: templateId }" in method_source
    for forbidden in (
        "phone_mx10",
        "phones",
        "provider_channel_id",
        "channelId",
        "vars",
        "variables",
    ):
        assert forbidden not in method_source

    ui_sources = "\n".join(
        (FRONTEND_ROOT / name).read_text(encoding="utf-8")
        for name in (
            "marketing-campaign-v2-campaign-detail-dialog.component.ts",
            "marketing-campaign-v2-campaign-detail-dialog.component.html",
        )
    )
    assert "dispatchTemplates" in ui_sources
    assert "listDispatchTemplates" in ui_sources
    assert "/v2/broadcast" not in ui_sources


def test_m1_ui_has_review_action_but_no_real_send_action():
    html = (
        FRONTEND_ROOT / "marketing-campaign-v2-campaign-detail-dialog.component.html"
    ).read_text(encoding="utf-8")

    assert "Revisar envío" in html
    assert "Esta acción no envía mensajes" in html
    assert "(click)=\"reviewDispatch()\"" in html
    assert "(click)=\"send" not in html
    assert "(click)=\"submit" not in html
