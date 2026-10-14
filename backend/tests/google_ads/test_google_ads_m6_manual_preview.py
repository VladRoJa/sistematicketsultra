"""M6 manual preview HTTP + strict XLSX parsers with synthetic reference RAW."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import google_ads_m6_continuity_routes as routes
from app.warehouse.services import google_ads_m6_manual_preview_service as svc
from test_google_ads_m6_authenticated_postgres import _synthetic_pair, _xlsx, _fake_facts

DAY = date(2026, 10, 13)
API = "/api/integrations/google-ads/manual/preview"


@pytest.fixture
def setup_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="manual-preview-synthetic-key")
    JWTManager(app)
    app.register_blueprint(
        routes.google_ads_m6_continuity_bp,
        url_prefix="/api/integrations/google-ads",
    )
    with app.app_context():
        token = create_access_token(identity="47")
    conn = SimpleNamespace()
    engine = SimpleNamespace()
    def connect():
        class Context:
            def __enter__(self):
                return conn
            def __exit__(self, *args):
                return False
        return Context()
    engine.connect = connect
    class Result:
        def mappings(self):
            return self
        def one_or_none(self):
            return {"id": 47, "username": conn.username, "rol": conn.role}
    def execute(query, params):
        assert "FROM users" in str(query)
        assert params == {"user_id": 47}
        return Result()
    conn.username = "admicorp"
    conn.role = "ADMINISTRADOR"
    conn.execute = execute
    monkeypatch.setattr(svc, "db", SimpleNamespace(engine=engine))

    baseline_campaign, baseline_group = _synthetic_pair()
    _, _, _, identities = _fake_facts()
    manifest = {
        "id": "GOOGLE_ADS_M5_IDENTITY_20261012_V1",
        "customer_id": "2739125201",
        "rows": [
            ["c", "g", row["campaign_key"], row["ad_group_key"],
             row["sucursal_canon"], i + 1, "0"]
            for i, row in enumerate(identities)
        ],
    }
    monkeypatch.setattr(svc, "_load_files", lambda: (baseline_campaign, baseline_group))
    monkeypatch.setattr(svc, "_load_m5", lambda: manifest)
    monkeypatch.setattr(svc, "datetime", SimpleNamespace(
        now=lambda tz: SimpleNamespace(date=lambda: date(2026, 10, 14))
    ))
    return app.test_client(), token, conn


def daily_xlsx():
    campaigns, groups = _synthetic_pair()
    one_day = min(row.report_date for row in campaigns.rows)
    campaign_rows = []
    group_rows = []
    totals = [0, 0, 0]
    group_totals = [0, 0, 0, 0, 0, 0, 0]
    for row in campaigns.rows:
        if row.report_date != one_day:
            continue
        campaign_rows.append([
            DAY.isoformat(), "Apto", row.campaign_name, "MXN",
            float(row.cost), float(row.conversions), float(row.conversion_value),
            row.clicks, row.impressions,
        ])
        totals[0] += float(row.cost)
        totals[1] += row.clicks
        totals[2] += row.impressions
    campaign_rows.append([
        DAY.isoformat(), "Total: Cuenta", None, "MXN", totals[0], 0, 0,
        totals[1], totals[2]
    ])
    for row in groups.rows:
        if row.report_date != one_day:
            continue
        group_rows.append([
            DAY.isoformat(), "Apto", row.campaign_name, row.ad_group_name,
            "MXN", float(row.cost), row.clicks, row.impressions,
            float(row.conversions), float(row.free_pass_conversions),
            float(row.web_purchase_conversions), float(row.conversion_value)
        ])
        for i, val in enumerate((
            row.cost, row.clicks, row.impressions, row.conversions,
            row.free_pass_conversions, row.web_purchase_conversions,
            row.conversion_value,
        )):
            group_totals[i] += float(val)
    for label in ("Total: Cuenta", "Total: Grupos de anuncios"):
        group_rows.append([
            DAY.isoformat(), label, None, None, "MXN", *group_totals
        ])
    from openpyxl import Workbook
    def to_xlsx(title, headings, rows):
        wb = Workbook()
        ws = wb.active
        ws.append([title])
        ws.append(["13 de octubre de 2026 - 13 de octubre de 2026"])
        ws.append(headings)
        for row in rows:
            ws.append(row)
        result = BytesIO()
        wb.save(result)
        wb.close()
        return result.getvalue()
    return (
        to_xlsx("Informe de campaña", [
            "Día", "Estado", "Campaña", "Código de moneda", "Coste",
            "Conversiones", "Valor de conv.", "Clics", "Impr."
        ], campaign_rows),
        to_xlsx("Informe de grupo de anuncios", [
            "Día", "Estado", "Campaña", "Grupo de anuncios",
            "Código de moneda", "Coste", "Clics", "Impr.", "Conversiones",
            "Pase gratis Ads", "Compras web Ads", "Valor de conv. original"
        ], group_rows),
    )


def post(client, token, *, files=None, extra=None):
    first, second = files if files is not None else daily_xlsx()
    data = {
        "campaign": (BytesIO(first), "campaign.xlsx"),
        "ad_group": (BytesIO(second), "group.xlsx"),
    }
    data.update(extra or {})
    return client.post(
        API, headers={"Authorization": "Bearer " + token} if token else {},
        data=data, content_type="multipart/form-data",
    )


def test_preview_validates_real_parsers_without_storage(setup_client, monkeypatch):
    client, token, _ = setup_client
    monkeypatch.setattr(routes, "approve_authenticated",
                        lambda: pytest.fail("approval must not run"))
    r = post(client, token)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["status"] == "PREFLIGHT_OK"
    assert data["business_date"] == "2026-10-13"
    assert data["campaign_rows"] == 27
    assert data["group_rows"] == 43
    assert data["approved_branches"] == 26
    assert data["account_cost_mxn"] == "1073.97"
    assert data["initial_m6_approval_verified"] is False
    assert data["ready_to_confirm"] is False
    assert data["eligible_for_publication"] is False
    assert len(data["campaign_sha256"]) == 64


def test_no_jwt_cannot_preview(setup_client):
    client, token, _ = setup_client
    assert post(client, None).status_code == 401


@pytest.mark.parametrize("name,role", [
    ("someone", "ADMINISTRADOR"),
    ("admicorp", "GERENTE"),
    ("admicorp", "SISTEMAS")
])
def test_role_from_db_is_not_spoofable(setup_client, monkeypatch, name, role):
    client, token, conn = setup_client
    conn.username, conn.role = name, role
    monkeypatch.setattr(svc, "_load_files", lambda: pytest.fail("must reject early"))
    r = post(client, token)
    assert r.status_code == 403


@pytest.mark.parametrize("alter,expected", [
    ("missing", 400), ("extra", 400), ("date", 422),
    ("not_excel", 422), ("mismatch", 422),
])
def test_fail_closed_for_invalid_payload(setup_client, alter, expected):
    client, token, _ = setup_client
    first, second = daily_xlsx()
    if alter == "missing":
        r = client.post(API, headers={"Authorization": "Bearer " + token},
                        data={"campaign": (BytesIO(first), "one.xlsx")},
                        content_type="multipart/form-data")
    elif alter == "extra":
        r = post(client, token, extra={"approved_by_user_id": "47"})
    elif alter == "date":
        # Both files are good, but today is the period being uploaded.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(svc, "datetime", SimpleNamespace(
                now=lambda tz: SimpleNamespace(date=lambda: DAY)))
            r = post(client, token)
    elif alter == "not_excel":
        r = post(client, token, files=(b"not-an-excel", second))
    else:
        # Same layout but two different days after strict XLSX parser.
        r = post(client, token, files=(first, second.replace(
            b"13 de octubre de 2026", b"14 de octubre de 2026"
        )))
    assert r.status_code == expected


def test_preview_rejects_drifted_reference_catalog(setup_client, monkeypatch):
    client, token, _ = setup_client
    monkeypatch.setattr(svc, "_load_files", lambda: (object(), object()))
    response = post(client, token)
    assert response.status_code != 200


def test_writes_are_not_reachable_from_preview(setup_client, monkeypatch):
    client, token, _ = setup_client
    monkeypatch.setattr(routes, "approve_authenticated",
                        lambda: pytest.fail("no approval"))
    response = post(client, token)
    assert response.status_code == 200, response.get_json()
