"""Global-only corrected canonical campaign facts for Google Ads Funnel."""
from __future__ import annotations

from decimal import Decimal
import os
from types import SimpleNamespace

from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.models.google_ads_m6_correction import GoogleAdsM6CorrectionCampaignORM
from app.models.google_ads_m6_continuity import GoogleAdsBranchApprovalVersionORM
from app.models.warehouse import WarehouseUploadORM
from app.services.marketing_google_ads_m6_daily_attribution_service import (
    CORRECTION_READER_FLAG, FIRST_DAILY_DAY, _metadata_ok,
    _promotion_links, _valid_promotion_link, _global_corrected_day_cost,
)
from app.warehouse.services.google_ads_m6_continuity_approval_service import (
    M6_REFERENCE, M5_REFERENCE, CAMPAIGN_UPLOAD_ID, GROUP_UPLOAD_ID,
)


def canonical_correction_campaign_days(customer_id, start, cutoff):
    """Only global account callers may use this helper; never scoped users."""
    if os.getenv(CORRECTION_READER_FLAG, "").strip().lower() != "true":
        return {}
    pub = GoogleAdsM6DailyPublicationORM
    campaign_raw = aliased(WarehouseUploadORM)
    group_raw = aliased(WarehouseUploadORM)
    rows = (
        db.session.query(pub, campaign_raw, group_raw)
        .join(campaign_raw, campaign_raw.id == pub.campaign_upload_id)
        .join(group_raw, group_raw.id == pub.ad_group_upload_id)
        .filter(
            pub.customer_id == customer_id,
            pub.business_date.between(max(start, FIRST_DAILY_DAY), cutoff),
            pub.is_canonical.is_(True),
        ).all()
    )
    links = _promotion_links(tuple(p.id for p, _, _ in rows))
    if links is None:
        raise ValueError("CORRECTION_LINK_CONFLICT")
    result = {}
    for day_pub, camp_raw, grp_raw in rows:
        link = links.get(day_pub.id)
        if link is None:
            if day_pub.revision != 1:
                raise ValueError("CORRECTION_LINK_MISSING")
            continue
        promotion, case, decision = link
        if (day_pub.business_date in result
                or not _metadata_ok(day_pub, camp_raw, grp_raw, day_pub.business_date)
                or not _valid_promotion_link(day_pub, promotion, case, decision)):
            raise ValueError("CORRECTION_CANONICAL_INVALID")
        version = db.session.get(
            GoogleAdsBranchApprovalVersionORM, day_pub.approval_version_id,
        )
        if not (
            version and version.customer_id == customer_id
            and version.approval_reference == M6_REFERENCE
            and version.source_approval_reference == M5_REFERENCE
            and version.source_campaign_upload_id == CAMPAIGN_UPLOAD_ID
            and version.source_ad_group_upload_id == GROUP_UPLOAD_ID
            and version.valid_from <= day_pub.business_date
            and (version.valid_to is None
                 or version.valid_to >= day_pub.business_date)
            and version.approved_by_user_id is not None
        ):
            raise ValueError("CORRECTION_MAPPING_VERSION_INVALID")
        total = _global_corrected_day_cost(
            day_pub, case, decision, Decimal("0"),
        )
        facts = (
            db.session.query(GoogleAdsM6CorrectionCampaignORM)
            .filter(GoogleAdsM6CorrectionCampaignORM.case_id == case.id)
            .all()
        )
        if (total is None or len(facts) != 27
                or len({r.campaign_key for r in facts}) != 27
                or sum((Decimal(r.cost) for r in facts), Decimal("0")) != total):
            raise ValueError("CORRECTION_LEDGER_INVALID")
        result[day_pub.business_date] = SimpleNamespace(
            report_date=day_pub.business_date,
            cost=total, campaign_rows=27,
            clicks=sum(int(row.clicks) for row in facts),
            impressions=sum(int(row.impressions) for row in facts),
            conversions=sum((Decimal(row.conversions) for row in facts),
                            Decimal("0")),
        )
    return result
