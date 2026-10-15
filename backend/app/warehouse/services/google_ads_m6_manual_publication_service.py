"""Explicit canonical M6 daily publication of a fully verified structured pair.

This operation is not called from RAW upload or structured ingestion. It
intentionally refuses all corrections/replacements until a separate audited
revision workflow is approved. All changes share one PG transaction.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import sqlalchemy as sa

from app.extensions import db
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.models.warehouse import WarehouseAuditLogORM
from app.warehouse.services.google_ads_m6_manual_structured_service import (
    AUDIT_ACTION as INGEST_AUDIT,
    CAMPAIGN_TYPE, GROUP_TYPE, CUSTOMER_ID,
    GoogleAdsM6ManualStructuredError,
    _approval, _campaign_record, _existing_matches, _group_record,
    _load_pair, _provenance, _verify_prior_pair_audits, require,
)

CONFIRMATION = "PUBLICAR_GOOGLE_ADS_M6_DIA_CANONICO"
PUBLISH_AUDIT = "GOOGLE_ADS_M6_PAIR_PUBLISH"


def publish_manual_daily_pair(*, actor_id: int, campaign_upload_id: int,
                              group_upload_id: int) -> dict:
    """One-day canonical publication. Historical substitutions fail closed."""
    require(
        type(actor_id) is int and actor_id > 0
        and type(campaign_upload_id) is int and campaign_upload_id > 0
        and type(group_upload_id) is int and group_upload_id > 0
        and campaign_upload_id != group_upload_id,
        "INVALID_PUBLICATION_REQUEST",
    )
    campaign, group, summary, approved, hashes = _load_pair(
        campaign_upload_id, group_upload_id,
    )
    day = campaign.date_from
    expected_campaigns = [_campaign_record(r, campaign_upload_id)
                          for r in campaign.rows]
    expected_groups = [_group_record(r, group_upload_id) for r in group.rows]
    require(
        len(expected_campaigns) == 27 and len(expected_groups) == 43,
        "PUBLICATION_RECONCILIATION_FAILED",
    )

    with db.engine.begin() as conn:
        # Same day-level lock as structured ingestion. Locks are on the actual
        # transactional connection, never a Flask session on another engine.
        conn.execute(sa.text("""
            SELECT pg_advisory_xact_lock(
                hashtext('google_ads_m6_manual_structured_pair'),
                CAST(:ordinal AS INTEGER))
        """), {"ordinal": day.toordinal()})
        principal = conn.execute(sa.text("""
            SELECT username, rol FROM users WHERE id = :actor FOR UPDATE
        """), {"actor": actor_id}).mappings().one_or_none()
        require(
            principal is not None
            and str(principal["username"]).strip().casefold() == "admicorp"
            and str(principal["rol"]).strip().upper() == "ADMINISTRADOR",
            "FORBIDDEN",
        )
        version_id = _approval(conn, day, approved)
        for upload_id, kind in (
            (campaign_upload_id, CAMPAIGN_TYPE),
            (group_upload_id, GROUP_TYPE),
        ):
            _provenance(
                conn, upload_id, actor_id, day, hashes[0], hashes[1], kind,
            )

        existing_campaigns = [dict(row) for row in conn.execute(sa.text("""
            SELECT * FROM google_ads_daily_metrics
            WHERE customer_id = :customer AND report_date = :day
        """), {"customer": CUSTOMER_ID, "day": day}).mappings()]
        existing_groups = [dict(row) for row in conn.execute(sa.text("""
            SELECT * FROM google_ads_ad_group_daily_metrics
            WHERE customer_id = :customer AND report_date = :day
        """), {"customer": CUSTOMER_ID, "day": day}).mappings()]
        require(
            _existing_matches(existing_campaigns, expected_campaigns,
                              ("campaign_key",))
            and _existing_matches(existing_groups, expected_groups,
                                  ("campaign_key", "ad_group_key")),
            "STRUCTURED_PAIR_REQUIRED",
        )
        _verify_prior_pair_audits(
            conn, actor_id=actor_id, day=day, campaign_id=campaign_upload_id,
            group_id=group_upload_id, version_id=version_id,
        )
        published = conn.execute(sa.text("""
            SELECT id, revision, campaign_upload_id, ad_group_upload_id,
                   approval_version_id, campaign_sha256, ad_group_sha256,
                   is_canonical, published_by_user_id
            FROM google_ads_m6_daily_publications
            WHERE customer_id = :customer AND business_date = :day
        """), {"customer": CUSTOMER_ID, "day": day}).mappings().all()
        # No correction/superseding until an independent approved revision
        # protocol exists. A valid exact request remains idempotent.
        if published:
            require(
                len(published) == 1
                and published[0]["revision"] == 1
                and published[0]["is_canonical"] is True
                and published[0]["campaign_upload_id"] == campaign_upload_id
                and published[0]["ad_group_upload_id"] == group_upload_id
                and published[0]["approval_version_id"] == version_id
                and published[0]["campaign_sha256"] == hashes[0]
                and published[0]["ad_group_sha256"] == hashes[1]
                and published[0]["published_by_user_id"] == actor_id,
                "PUBLISHED_DAY_CONFLICT",
            )
            publication_id = int(published[0]["id"])
            status = "ALREADY_PUBLISHED"
        else:
            now = datetime.now(ZoneInfo("America/Tijuana")).date()
            publication_id = int(conn.execute(
                GoogleAdsM6DailyPublicationORM.__table__.insert()
                .values(
                    customer_id=CUSTOMER_ID, business_date=day, revision=1,
                    campaign_upload_id=campaign_upload_id,
                    ad_group_upload_id=group_upload_id,
                    approval_version_id=version_id,
                    campaign_sha256=hashes[0], ad_group_sha256=hashes[1],
                    is_canonical=True, published_by_user_id=actor_id,
                    published_on=now,
                ).returning(GoogleAdsM6DailyPublicationORM.id)
            ).scalar_one())
            for upload_id, kind in (
                (campaign_upload_id, CAMPAIGN_TYPE),
                (group_upload_id, GROUP_TYPE),
            ):
                conn.execute(WarehouseAuditLogORM.__table__.insert().values(
                    upload_id=upload_id,
                    action=PUBLISH_AUDIT,
                    performed_by_user_id=actor_id,
                    details={
                        "publication_id": publication_id,
                        "business_date": day.isoformat(),
                        "customer_id": CUSTOMER_ID,
                        "approval_version_id": version_id,
                        "revision": 1, "is_canonical": True,
                        "campaign_upload_id": campaign_upload_id,
                        "ad_group_upload_id": group_upload_id,
                        "report_type_key": kind,
                    },
                ))
            status = "CANONICAL_DAY_PUBLISHED"
    return {
        "status": status,
        "publication_id": publication_id,
        "revision": 1,
        "business_date": day.isoformat(),
        "customer_id": CUSTOMER_ID,
        "campaign_upload_id": campaign_upload_id,
        "ad_group_upload_id": group_upload_id,
        "campaign_rows": len(expected_campaigns),
        "group_rows": len(expected_groups),
        "account_cost_mxn": summary["account_cost_mxn"],
        "branch_cost_mxn": summary["branch_cost_mxn"],
        "unassigned_cost_mxn": summary["unassigned_cost_mxn"],
        "is_canonical": True,
        "approval_version_id": version_id,
    }
