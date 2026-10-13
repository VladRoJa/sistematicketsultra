"""JWT -> HTTP -> actual PostgreSQL 16 approval writes and rollback.

All identities, users and XLSX bytes are synthetic. The only patched
boundary is Warehouse raw-file discovery and the M5 historical raw preflight;
the new XLSX parsers, M6 reconciliation, authorization and SQL are real.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from openpyxl import Workbook

from app.models.google_ads_branch_identity_mapping import GoogleAdsBranchIdentityMappingORM
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.routes import google_ads_m6_continuity_routes as routes
from app.warehouse.services import google_ads_m6_continuity_approval_service as service
from app.warehouse.services.google_ads_daily_xlsx_parser import parse_google_ads_daily_xlsx
from app.warehouse.services.google_ads_ad_group_daily_xlsx_parser import parse_google_ads_ad_group_daily_xlsx
from tests.google_ads.test_google_ads_m6_continuity_approval import _fake_facts
from tests.google_ads.test_google_ads_m6_continuity_postgres import _revision, _test_engine
from alembic.migration import MigrationContext
from alembic.operations import Operations


PERIOD = "9 de octubre de 2026 - 12 de octubre de 2026"
CONFIRM = {
    "approval_reference": service.M6_REFERENCE,
    "confirmation": routes.CONFIRMATION,
}


def _xlsx(title, headings, rows):
    workbook = Workbook()
    ws = workbook.active
    ws.append([title])
    ws.append([PERIOD])
    ws.append(headings)
    for row in rows:
        ws.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _synthetic_pair():
    _, campaign_set, group_set, _ = _fake_facts()
    campaign_lines = []
    group_lines = []
    per_campaign = defaultdict(lambda: [Decimal("0"), 0, 0])
    per_group = defaultdict(lambda: [Decimal("0"), 0, 0, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")])
    for r in campaign_set.rows:
        campaign_lines.append([
            r.report_date.isoformat(), "Apto", r.campaign_name, "MXN",
            float(r.cost), float(r.conversions), float(r.conversion_value),
            r.clicks, r.impressions,
        ])
        v = per_campaign[r.report_date]
        v[0] += r.cost
        v[1] += r.clicks
        v[2] += r.impressions
    for r in group_set.rows:
        group_lines.append([
            r.report_date.isoformat(), "Apto", r.campaign_name, r.ad_group_name,
            "MXN", float(r.cost), r.clicks, r.impressions,
            float(r.conversions), float(r.free_pass_conversions),
            float(r.web_purchase_conversions), float(r.conversion_value),
        ])
        v = per_group[r.report_date]
        for i, number in enumerate((
            r.cost, r.clicks, r.impressions, r.conversions,
            r.free_pass_conversions, r.web_purchase_conversions, r.conversion_value
        )):
            v[i] += number
    for day in sorted(per_campaign):
        cost, clicks, impressions = per_campaign[day]
        campaign_lines.append([
            day.isoformat(), "Total: Cuenta", None, "MXN",
            float(cost), 0, 0, clicks, impressions,
        ])
        values = per_group[day]
        total = [
            day.isoformat(), None, None, None, "MXN",
            float(values[0]), values[1], values[2], float(values[3]),
            float(values[4]), float(values[5]), float(values[6]),
        ]
        for status in ("Total: Cuenta", "Total: Grupos de anuncios"):
            copy = list(total)
            copy[1] = status
            group_lines.append(copy)
    campaign_raw = _xlsx(
        "Informe de campaña",
        ["Día", "Estado", "Campaña", "Código de moneda", "Coste",
         "Conversiones", "Valor de conv.", "Clics", "Impr."],
        campaign_lines,
    )
    group_raw = _xlsx(
        "Informe de grupo de anuncios",
        ["Día", "Estado", "Campaña", "Grupo de anuncios",
         "Código de moneda", "Coste", "Clics", "Impr.", "Conversiones",
         "Pase gratis Ads", "Compras web Ads", "Valor de conv. original"],
        group_lines,
    )
    return (
        parse_google_ads_daily_xlsx(campaign_raw),
        parse_google_ads_ad_group_daily_xlsx(group_raw),
    )


def _count(conn, table):
    return conn.execute(sa.text("SELECT count(*) FROM " + table)).scalar_one()


def _post(client, token, body=None):
    return client.post(
        "/api/integrations/google-ads/continuity/approve",
        headers={"Authorization": "Bearer " + token} if token else {},
        json=CONFIRM if body is None else body,
    )


def test_authenticated_approval_end_to_end_postgres16(monkeypatch):
    engine = _test_engine()  # refuses non-local or non-dedicated test DB
    with engine.connect() as c:
        assert c.execute(sa.text("SHOW server_version")).scalar_one().startswith("16.")

    md = sa.MetaData()
    users = sa.Table(
        "users", md, sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("rol", sa.Text, nullable=False),
    )
    uploads = sa.Table("warehouse_uploads", md, sa.Column("id", sa.Integer, primary_key=True))
    branches = sa.Table(
        "track_branch_catalog", md,
        sa.Column("sucursal_canon", sa.Text, primary_key=True),
    )
    m5 = GoogleAdsBranchIdentityMappingORM.__table__.to_metadata(md)
    daily = GoogleAdsDailyMetricORM.__table__.to_metadata(md)
    group_daily = GoogleAdsAdGroupDailyMetricORM.__table__.to_metadata(md)
    rev = _revision()
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-m6-authenticated-ci-jwt")
    JWTManager(app)
    app.register_blueprint(
        routes.google_ads_m6_continuity_bp,
        url_prefix="/api/integrations/google-ads",
    )
    campaign_file, group_file = _synthetic_pair()
    assert len(campaign_file.rows) == 108
    assert len(group_file.rows) == 172
    first_day = [r for r in group_file.rows if r.report_date == service.START]
    assert len(first_day) == 43
    identities = [
        [r.campaign_name, r.ad_group_name, r.campaign_key, r.ad_group_key,
         f"LAB_BRANCH_{index}", index + 1, "0"]
        for index, r in enumerate(first_day[:26])
    ]
    manifest = {
        "id": service.M5_REFERENCE,
        "customer_id": service.CUSTOMER_ID,
        "rows": identities,
    }
    monkeypatch.setattr(service, "db", SimpleNamespace(engine=engine))
    monkeypatch.setattr(service, "_load_m5", lambda: manifest)
    monkeypatch.setattr(service, "_verify_m5_raw", lambda _: None)
    monkeypatch.setattr(service, "_load_files", lambda: (campaign_file, group_file))

    def synthetic_m5_preflight(conn, *, apply):
        assert apply is False
        count = _count(conn, "google_ads_branch_identity_mappings")
        return {"approved_identities": 26, "previous_identities": count}

    monkeypatch.setattr(service, "_m5_preflight", synthetic_m5_preflight)
    with app.app_context():
        ok_token = create_access_token(identity="47")
        other_token = create_access_token(identity="48")
    client = app.test_client()

    try:
        with engine.begin() as c:
            # Fail rather than reusing or clearing an unknown DB schema.
            for name in ("users", "warehouse_uploads", "track_branch_catalog",
                         m5.name, daily.name, group_daily.name, rev.VERSIONS):
                assert not sa.inspect(c).has_table(name), name
            md.create_all(c)
            c.execute(users.insert(), [
                {"id": 47, "username": "admicorp", "rol": "ADMINISTRADOR"},
                {"id": 48, "username": "other", "rol": "ADMINISTRADOR"},
            ])
            c.execute(uploads.insert(), [
                {"id": 21499}, {"id": 21604}, {"id": 21605},
            ])
            c.execute(branches.insert(), [
                {"sucursal_canon": f"LAB_BRANCH_{i}"} for i in range(26)
            ])
            c.execute(m5.insert(), [
                {
                    "customer_id": service.CUSTOMER_ID,
                    "campaign_key": row[2], "ad_group_key": row[3],
                    "sucursal_canon": row[4], "source_upload_id": 21499,
                    "valid_from": date(2026, 9, 24),
                    "valid_to": date(2026, 10, 8),
                    "approval_status": "APPROVED_PROVISIONAL_XLSX",
                    "approval_reference": service.M5_REFERENCE,
                    "approved_on": date(2026, 10, 12),
                } for row in identities
            ])
            def daily_item(r, upload):
                return {
                    "customer_id": service.CUSTOMER_ID,
                    "campaign_id": None, "campaign_key": r.campaign_key,
                    "campaign_name": r.campaign_name,
                    "report_date": r.report_date, "currency_code": "MXN",
                    "cost": r.cost, "clicks": r.clicks,
                    "impressions": r.impressions, "conversions": r.conversions,
                    "conversion_value": r.conversion_value,
                    "source_kind": "WAREHOUSE_XLSX",
                    "source_upload_id": upload,
                }
            c.execute(daily.insert(), [
                daily_item(r, 21604) for r in campaign_file.rows
            ])
            def group_item(r, day, upload, historical=False):
                return {
                    **daily_item(r, upload),
                    "ad_group_id": None, "ad_group_key": r.ad_group_key,
                    "ad_group_name": r.ad_group_name,
                    "free_pass_conversions": Decimal("0") if historical else r.free_pass_conversions,
                    "web_purchase_conversions": Decimal("0") if historical else r.web_purchase_conversions,
                    "cost": Decimal("0") if historical else r.cost,
                    "clicks": 0 if historical else r.clicks,
                    "impressions": 0 if historical else r.impressions,
                    "conversions": Decimal("0") if historical else r.conversions,
                    "conversion_value": Decimal("0") if historical else r.conversion_value,
                    "report_date": day,
                }
            c.execute(group_daily.insert(), [
                group_item(r, r.report_date, 21605) for r in group_file.rows
            ] + [
                group_item(r, date(2026, 10, 8), 21499, historical=True)
                for r in first_day
            ])
            rev.op = Operations(MigrationContext.configure(c))
            rev.upgrade()
            baseline = [
                tuple(row) for row in c.execute(
                    sa.text("""SELECT campaign_key, ad_group_key, sucursal_canon,
                             source_upload_id, valid_from, valid_to,
                             approval_reference FROM google_ads_branch_identity_mappings
                             ORDER BY campaign_key,ad_group_key""")
                ).all()
            ]

        monkeypatch.delenv("GOOGLE_ADS_M6_APPROVAL_ENABLED", raising=False)
        assert _post(client, None).status_code == 401
        assert _post(client, ok_token).status_code == 503
        monkeypatch.setenv("GOOGLE_ADS_M6_APPROVAL_ENABLED", "true")
        assert _post(client, other_token).status_code == 403
        assert _post(client, ok_token, {**CONFIRM, "approved_by_user_id": 47}).status_code == 400
        with engine.begin() as c:
            c.execute(sa.text("UPDATE users SET rol = 'GERENTE' WHERE id = 47"))
        assert _post(client, ok_token).status_code == 403
        with engine.begin() as c:
            c.execute(sa.text("UPDATE users SET rol = 'ADMINISTRADOR' WHERE id = 47"))

        # A forced failure AFTER the first INSERT must roll back BOTH tables.
        original_check = service._check_existing
        def fail_after_insert(conn, rows):
            if _count(conn, rev.VERSIONS):
                raise RuntimeError("synthetic post-write failure")
            return original_check(conn, rows)
        monkeypatch.setattr(service, "_check_existing", fail_after_insert)
        result = _post(client, ok_token)
        assert result.status_code == 409, result.json
        monkeypatch.setattr(service, "_check_existing", original_check)
        with engine.connect() as c:
            assert _count(c, rev.VERSIONS) == 0
            assert _count(c, rev.IDENTITIES) == 0

        result = _post(client, ok_token)
        assert result.status_code == 200, result.json
        assert result.json["action"] == "APPROVED"
        assert result.json["approved_identities"] == 26
        assert result.json["account_cost_mxn"] == "5562.11"
        assert result.json["local_cost_mxn"] == "5211.74"
        initial_id = result.json["approval_version_id"]

        again = _post(client, ok_token)
        assert again.status_code == 200, again.json
        assert again.json["action"] == "ALREADY_APPROVED"
        assert again.json["approval_version_id"] == initial_id
        with engine.connect() as c:
            assert _count(c, rev.VERSIONS) == 1
            assert _count(c, rev.IDENTITIES) == 26
            actor = c.execute(sa.text(
                "SELECT approved_by_user_id FROM google_ads_branch_approval_versions"
            )).scalar_one()
            assert actor == 47
            actual_m5 = [
                tuple(row) for row in c.execute(
                    sa.text("""SELECT campaign_key, ad_group_key, sucursal_canon,
                             source_upload_id, valid_from, valid_to,
                             approval_reference FROM google_ads_branch_identity_mappings
                             ORDER BY campaign_key,ad_group_key""")
                ).all()
            ]
            assert actual_m5 == baseline
    finally:
        # All objects are synthetic in the dedicated CI database.
        with engine.begin() as c:
            if sa.inspect(c).has_table(rev.VERSIONS):
                c.execute(sa.text("DELETE FROM google_ads_branch_approved_identities"))
                c.execute(sa.text("DELETE FROM google_ads_branch_approval_versions"))
                rev.op = Operations(MigrationContext.configure(c))
                rev.downgrade()
            md.drop_all(c, checkfirst=True)
        engine.dispose()
