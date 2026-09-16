from sqlalchemy.dialects import postgresql

from app.services.marketing_meta_join_service import (
    build_iventas_meta_export_statement,
)


def test_export_join_prefers_ads_source_id_with_legacy_meta_tag_fallback():
    statement = build_iventas_meta_export_statement(
        iventas_sync_run_id=41,
        meta_sync_run_id=82,
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    # Contrato vigente del proveedor: el anuncio se resuelve desde
    # isFromAds + adsSourceId cuando esos campos existen.
    assert "marketing_iventas_contacts.is_from_ads is true" in sql
    assert "marketing_iventas_contacts.ads_source_id" in sql
    assert "marketing_meta_ad_insights.ad_id" in sql

    # Snapshots históricos sin isFromAds conservan el fallback META_AD.
    assert "marketing_iventas_contacts.is_from_ads is null" in sql
    assert "marketing_iventas_contact_tags.meta_ad_id" in sql
    assert "tag_kind = 'meta_ad'" in sql

    assert "left outer join marketing_meta_ad_insights" in sql
    assert "marketing_iventas_contacts.sync_run_id = 41" in sql
    assert "marketing_meta_ad_insights.sync_run_id = 82" in sql
    assert "first_message_at_utc is not null" in sql
    assert "actions_json" in sql

    # El cruce solo enriquece contactos; no debe agregar/copiar leads.
    assert "count(" not in sql
    assert "sum(" not in sql
