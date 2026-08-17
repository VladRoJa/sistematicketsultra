from sqlalchemy.dialects import postgresql

from app.services.marketing_meta_join_service import (
    build_iventas_meta_export_statement,
)


def test_export_join_uses_meta_ad_id_without_copying_or_summing_leads():
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

    assert (
        "marketing_iventas_contact_tags.meta_ad_id = "
        "marketing_meta_ad_insights.ad_id"
    ) in sql
    assert "left outer join marketing_meta_ad_insights" in sql
    assert "marketing_iventas_contacts.sync_run_id = 41" in sql
    assert "marketing_meta_ad_insights.sync_run_id = 82" in sql
    assert "first_message_at_utc is not null" in sql
    assert "tag_kind = 'meta_ad'" in sql
    assert "actions_json" in sql
    assert "count(" not in sql
    assert "sum(" not in sql
