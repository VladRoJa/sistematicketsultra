from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RECONCILIATION = REPOSITORY_ROOT / (
    "backend/app/services/contact_center_iventas_reconciliation_service.py"
)
CONTACT_CENTER = REPOSITORY_ROOT / (
    "backend/app/services/contact_center_service.py"
)
RUN_SYNC = REPOSITORY_ROOT / (
    "backend/app/services/marketing_iventas_run_sync_service.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reconciliation_only_accepts_completed_canonical_run():
    service = _read(RECONCILIATION)

    assert 'run.status != "COMPLETED"' in service
    assert "not bool(run.is_canonical)" in service
    assert "build_marketing_lead_contacts_statement(" in service


def test_reconciliation_links_only_unique_phone_match():
    service = _read(RECONCILIATION)

    assert "contacts_by_phone" in service
    assert "if not matches:" in service
    assert "if len(matches) != 1:" in service
    assert 'source_type="IVENTAS_CONTACT"' in service
    assert '"matched_by": "PHONE_MX10"' in service


def test_canonical_iventas_sync_triggers_best_effort_reconciliation():
    sync = _read(RUN_SYNC)

    assert "reconcile_contact_center_iventas_run" in sync
    assert "finalized.status == SYNC_STATUS_COMPLETED" in sync
    assert "and finalized.is_canonical" in sync
    assert "Contact Center iVentas reconciliation failed" in sync
    assert "session_value.rollback()" in sync


def test_crm_candidate_falls_back_to_unique_phone_match_without_get_side_effect():
    service = _read(CONTACT_CENTER)

    assert "phone_contact_ids" in service
    assert "len(phone_matches) == 1" in service
    assert '"matched_by_phone": matched_by_phone' in service
    assert '"phone_match_ambiguous": phone_match_ambiguous' in service


def test_crm_import_links_unique_existing_phone_and_rejects_ambiguous():
    service = _read(CONTACT_CENTER)

    assert "exact_phone_matches" in service
    assert "if len(exact_phone_matches) == 1:" in service
    assert "elif len(exact_phone_matches) > 1:" in service
    assert '"matched_by": "PHONE_MX10"' in service
    assert "ContactCenterDuplicateError" in service
