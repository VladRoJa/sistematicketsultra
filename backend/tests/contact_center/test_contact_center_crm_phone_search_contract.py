from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_crm_phone_search_has_priority_over_month_filter():
    routes = _read(ROUTES)

    phone_index = routes.index(
        'phone = str(request.args.get("phone") or "").strip()'
    )
    month_index = routes.index(
        'month = str(request.args.get("month") or "").strip()'
    )

    assert phone_index < month_index
    assert "search_crm_candidates_by_phone(phone)" in routes


def test_crm_phone_search_uses_canonical_funnel_semantics():
    service = _read(SERVICE)

    assert "def search_crm_candidates_by_phone" in service
    assert "normalized_phone = normalize_phone(phone)" in service
    assert 'MarketingIventasSyncRunORM.is_canonical.is_(True)' in service
    assert 'MarketingIventasSyncRunORM.status == "COMPLETED"' in service
    assert (
        "build_marketing_lead_contacts_statement(" in service
    )
    assert (
        "MarketingIventasContactORM.phone_mx10 == normalized_phone"
        in service
    )
    assert 'period_key": "HISTORICO"' in service


def test_crm_phone_search_deduplicates_by_branch_and_contact_identity():
    service = _read(SERVICE)

    assert "seen_source_keys: set[str] = set()" in service
    assert "if source_key in seen_source_keys:" in service
    assert "seen_source_keys.add(source_key)" in service
