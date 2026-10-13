"""M5: seed approved 26 historical Google Ads identities, fail closed.

Revision ID: a63e9f21d48b
Revises: c7e4a9b2d601

All writes are within Alembic's PostgreSQL DDL transaction.
No Funnel, Meta, campaign ledger or raw Warehouse changes.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import unicodedata

from alembic import op
import sqlalchemy as sa

revision = "a63e9f21d48b"
down_revision = "c7e4a9b2d601"
branch_labels = None
depends_on = None

TABLE = "google_ads_branch_identity_mappings"
MANIFEST = Path(__file__).resolve().parents[1] / "data/google_ads_m5_identity_seed_20261012.json"
APPROVAL = "APPROVED_PROVISIONAL_XLSX"


def _require(ok, message):
    if not ok:
        raise RuntimeError("M5 seed rechazado: " + message)


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def _load():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = data["rows"]
    triples = [(data["customer_id"], r[2], r[3]) for r in rows]
    _require(len(rows) == len(set(triples)) == 26, "manifiesto con 26 triples únicos")
    _require({r[5] for r in rows} == set(range(1, 27)), "sucursales duplicadas")
    _require(data["id"] == "GOOGLE_ADS_M5_IDENTITY_20261012_V1", "ID de aprobación")
    _require(data["customer_id"] == "2739125201" and data["upload_id"] == 21499, "origen no autorizado")
    _require((data["from"], data["to"], data["approved_on"]) ==
             ("2026-09-24", "2026-10-08", "2026-10-12"), "periodo distinto")
    _require(sum((Decimal(r[6]) for r in rows), Decimal("0")) == Decimal("17624.73"),
             "inversión local del manifiesto")
    for camp, group, ck, gk, canon, _, _ in rows:
        _require(ck == "name:" + sha256(_norm(camp).encode()).hexdigest(), "hash campaña")
        _require(gk == "name:" + sha256((ck + "\x1f" + _norm(group)).encode()).hexdigest(), "hash grupo")
        _require(_norm(group) not in {"marca", "egade", "grupo de anuncios 1"}, "grupo no aprobado")
        _require(bool(canon), "club sin canonicalidad")
    return data


def _validate_source(conn, data):
    start, end = date.fromisoformat(data["from"]), date.fromisoformat(data["to"])
    params = {"customer": data["customer_id"], "start": start, "end": end}
    upload = conn.execute(sa.text("""
        SELECT u.original_filename, u.date_from, u.date_to, u.status,
               u.file_hash_sha256, u.file_size_bytes, u.source_file_deleted_at,
               rt.key AS report_type
        FROM warehouse_uploads u
        JOIN warehouse_report_types rt ON rt.id = u.report_type_id
        WHERE u.id = 21499
    """)).mappings().one_or_none()
    _require(upload is not None and
             (upload["report_type"], upload["original_filename"], upload["date_from"],
              upload["date_to"], upload["status"], upload["file_hash_sha256"],
              upload["file_size_bytes"], upload["source_file_deleted_at"]) ==
             ("google_ads_ad_group_daily", "Informe de grupo de anuncios (7).xlsx",
              start, end, "ACTIVE", data["upload_sha256"], 79836, None),
             "metadata Warehouse upload 21499 no coincide")

    catalog = conn.execute(sa.text("""
        SELECT a.raw_branch_name, a.sucursal_canon, a.is_active,
               t.sucursal_id, t.is_track_active, s.operational_status
        FROM track_branch_aliases a
        JOIN track_branch_catalog t ON t.sucursal_canon = a.sucursal_canon
        JOIN sucursales s ON s.sucursal_id = t.sucursal_id
        WHERE a.source_family = 'google_ads_family'
    """)).mappings().all()
    expected_aliases = {(r[1], r[4], r[5]) for r in data["rows"]}
    _require(len(catalog) == 26 and {
        (a["raw_branch_name"], a["sucursal_canon"], a["sucursal_id"]) for a in catalog
    } == expected_aliases and all(
        a["is_active"] is True and a["is_track_active"] is True
        and a["operational_status"] == "ACTIVA" for a in catalog
    ), "alias M4 o estado operativo alterado")

    facts = conn.execute(sa.text("""
        SELECT campaign_key, ad_group_key, campaign_name, ad_group_name,
               report_date, cost, clicks, impressions,
               free_pass_conversions, web_purchase_conversions,
               currency_code, source_kind, source_upload_id,
               campaign_id, ad_group_id
        FROM google_ads_ad_group_daily_metrics
        WHERE customer_id = :customer AND report_date BETWEEN :start AND :end
    """), params).mappings().all()
    _require(len(facts) == 645, "no hay 645 filas M3")
    days = {start + timedelta(days=i) for i in range(15)}
    groups = defaultdict(list)
    campaign_day = defaultdict(lambda: [Decimal("0"), 0, 0])
    for r in facts:
        _require(r["report_date"] in days and r["source_upload_id"] == 21499
                 and r["source_kind"] == "WAREHOUSE_XLSX" and r["currency_code"] == "MXN"
                 and r["campaign_id"] is None and r["ad_group_id"] is None,
                 "hecho fuera del histórico XLSX autorizado")
        ck, gk = r["campaign_key"], r["ad_group_key"]
        _require(ck == "name:" + sha256(_norm(r["campaign_name"]).encode()).hexdigest()
                 and gk == "name:" + sha256((ck + "\x1f" + _norm(r["ad_group_name"])).encode()).hexdigest(),
                 "identidad derivada ya no concilia")
        groups[(ck, gk)].append(r)
        total = campaign_day[(ck, r["report_date"])]
        total[0] += Decimal(r["cost"])
        total[1] += int(r["clicks"])
        total[2] += int(r["impressions"])
    _require(len(groups) == 43 and all(
        len(rs) == 15 and {r["report_date"] for r in rs} == days for rs in groups.values()
    ), "no hay 43 identidades con 15 días cada una")
    _require(sum((Decimal(r["cost"]) for r in facts), Decimal("0")) == Decimal("19126.37")
             and sum(int(r["clicks"]) for r in facts) == 7887
             and sum(int(r["impressions"]) for r in facts) == 79198
             and sum((Decimal(r["free_pass_conversions"]) for r in facts), Decimal("0")) == 64
             and sum((Decimal(r["web_purchase_conversions"]) for r in facts), Decimal("0")) == 16,
             "métricas históricas han cambiado")
    approved = {(r[2], r[3]) for r in data["rows"]}
    for camp, group, ck, gk, _, _, cost in data["rows"]:
        rs = groups.get((ck, gk), [])
        _require(len(rs) == 15
                 and all(x["campaign_name"] == camp and x["ad_group_name"] == group for x in rs)
                 and sum((Decimal(x["cost"]) for x in rs), Decimal("0")) == Decimal(cost),
                 "triple aprobado o gasto local alterado")
    remainder = [rs for key, rs in groups.items() if key not in approved]
    _require(len(remainder) == 17, "grupos excluidos inesperados")
    excluded = defaultdict(list)
    for rs in remainder:
        name = _norm(rs[0]["ad_group_name"])
        _require(all(_norm(r["ad_group_name"]) == name for r in rs), "renombre no aprobado")
        excluded[name].append(rs)
    _require(len(excluded["marca"]) == len(excluded["egade"]) == 1, "nacionales duplicados")
    for name, cost in (("marca", "1375.60"), ("egade", "126.04")):
        _require(sum((Decimal(x["cost"]) for x in excluded[name][0]), Decimal("0")) == Decimal(cost),
                 "gasto nacional/preapertura distinto")
    others = [rs for name, sets in excluded.items() if name not in {"marca", "egade"} for rs in sets]
    _require(len(others) == 15 and all(
        not (sum(Decimal(x["cost"]) for x in rs)
             or sum(int(x["clicks"]) for x in rs)
             or sum(int(x["impressions"]) for x in rs)
             or sum(Decimal(x["free_pass_conversions"]) for x in rs)
             or sum(Decimal(x["web_purchase_conversions"]) for x in rs))
        for rs in others
    ), "grupo no mapeado con actividad")

    campaigns = conn.execute(sa.text("""
        SELECT campaign_key, report_date, cost, clicks, impressions, currency_code
        FROM google_ads_daily_metrics
        WHERE customer_id = :customer AND report_date BETWEEN :start AND :end
    """), params).mappings().all()
    ledger = {}
    for row in campaigns:
        k = (row["campaign_key"], row["report_date"])
        _require(k not in ledger and row["currency_code"] == "MXN", "ledger duplicado/moneda")
        ledger[k] = (Decimal(row["cost"]), int(row["clicks"]), int(row["impressions"]))
    _require(bool(ledger), "ledger M1 ausente")
    _require(all(tuple(v) == ledger.get(k) for k, v in campaign_day.items()), "grupo/campaña sin conciliar")
    _require(all(v == (Decimal("0"), 0, 0) for k, v in ledger.items()
                 if k not in campaign_day), "campaña no desglosada con inversión")


def _expected(data):
    return [
        dict(customer_id=data["customer_id"], campaign_key=r[2], ad_group_key=r[3],
             sucursal_canon=r[4], source_upload_id=data["upload_id"],
             valid_from=date.fromisoformat(data["from"]), valid_to=date.fromisoformat(data["to"]),
             approval_status=APPROVAL, approval_reference=data["id"],
             approved_on=date.fromisoformat(data["approved_on"]))
        for r in data["rows"]
    ]


def _rows(conn):
    return conn.execute(sa.text("""
        SELECT customer_id, campaign_key, ad_group_key, sucursal_canon,
               source_upload_id, valid_from, valid_to, approval_status,
               approval_reference, approved_on
        FROM google_ads_branch_identity_mappings
    """)).mappings().all()


def _same(actual, expected):
    fields = tuple(expected[0])
    return len(actual) == len(expected) and {
        tuple(x[k] for k in fields) for x in actual
    } == {tuple(x[k] for k in fields) for x in expected}


def upgrade():
    data = _load()
    conn = op.get_bind()
    _validate_source(conn, data)
    expected = _expected(data)
    existing = _rows(conn)
    _require(not existing or _same(existing, expected), "mappings previos ajenos")
    if not existing:
        conn.execute(sa.text("""
            INSERT INTO google_ads_branch_identity_mappings
            (customer_id, campaign_key, ad_group_key, sucursal_canon, source_upload_id,
             valid_from, valid_to, approval_status, approval_reference, approved_on)
            VALUES (:customer_id, :campaign_key, :ad_group_key, :sucursal_canon,
                    :source_upload_id, :valid_from, :valid_to,
                    :approval_status, :approval_reference, :approved_on)
        """), expected)
    _require(_same(_rows(conn), expected), "seed incompleto o alterado")


def downgrade():
    data = _load()
    conn = op.get_bind()
    expected = _expected(data)
    _require(_same(_rows(conn), expected), "downgrade requiere 26 mappings intactos")
    conn.execute(sa.text(
        "DELETE FROM google_ads_branch_identity_mappings WHERE approval_reference = :ref"
    ), {"ref": data["id"]})
    _require(not _rows(conn), "downgrade dejó asociaciones")
