"""Issue 856/C — no-send preview, multi-source union and audited apply gates."""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import pytest

from app.services import marketing_campaign_v2_preparation_service as c


def _session():
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.filter.return_value.first.return_value = None
    return session


def _ambiguous(monkeypatch, count: int, *, other=0):
    rows = [
        {"recipient_id": k + 1, "kind": "AMBIGUOUS_EVIDENCE",
         "branch_keys": ["A", "B"]} for k in range(count)
    ]
    rows += [{"recipient_id": 101 + k, "kind": "MISSING_EVIDENCE",
              "branch_keys": []} for k in range(other)]
    monkeypatch.setattr(c, "_ambiguous_rows", lambda **kw: rows)
    return rows


@pytest.mark.parametrize("count,bulk", [(0, False), (1, False), (9, False), (10, True), (11, True), (626, True)])
def test_ambiguous_review_classifies_and_requires_bulk_confirmation(monkeypatch, count, bulk):
    _ambiguous(monkeypatch, count, other=2)
    session = _session()
    result = c.review_ambiguous_branches(
        campaign_id=15, allowed_sucursal_keys=None, session=session,
        page=1, page_size=25,
    )
    assert result["counts"]["AMBIGUOUS_EVIDENCE"] == count
    assert result["counts"]["MISSING_EVIDENCE"] == 2
    assert result["new_exclusions"] == count
    assert result["requires_bulk_confirmation"] is bulk
    assert len(result["rows"]) <= 25
    assert result["can_apply"] is (count > 0)
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_ambiguous_review_pagination_is_bounded_and_readonly(monkeypatch):
    _ambiguous(monkeypatch, 626)
    session = _session()
    second = c.review_ambiguous_branches(
        campaign_id=15, allowed_sucursal_keys=None, session=session,
        page=2, page_size=25,
    )
    assert second["rows"][0]["recipient_id"] == 26
    assert second["rows"][-1]["recipient_id"] == 50
    assert second["new_exclusions"] == 626
    with pytest.raises(c.ValidationError):
        c.review_ambiguous_branches(
            campaign_id=15, allowed_sucursal_keys=None, session=session,
            page_size=101,
        )


def test_ambiguous_apply_rejects_stale_fingerprint_and_bulk_without_approval(monkeypatch):
    _ambiguous(monkeypatch, 10)
    monkeypatch.setattr(c, "_lock_clean_target", lambda **kw: None)
    session = _session()
    report = c.review_ambiguous_branches(
        campaign_id=15, allowed_sucursal_keys=None, session=session,
    )
    kwargs = dict(
        campaign_id=15, expected_count=10, actor_user_id=7,
        allow_bulk=False, allowed_sucursal_keys=None, session=session,
    )
    with pytest.raises(c.ValidationError, match="desactualizada"):
        c.apply_ambiguous_branch_exclusions(
            expected_fingerprint="wrong", **kwargs,
        )
    with pytest.raises(c.ValidationError, match=r"10\+"):
        c.apply_ambiguous_branch_exclusions(
            expected_fingerprint=report["review_fingerprint"], **kwargs,
        )
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_ambiguous_apply_audits_only_confirmed_candidate_ids(monkeypatch):
    _ambiguous(monkeypatch, 9)
    monkeypatch.setattr(c, "_lock_clean_target", lambda **kw: None)
    saved = []
    monkeypatch.setattr(c, "add_campaign_v2_ambiguous_branch_exclusions",
                        lambda **kwargs: saved.append(kwargs) or {"added": 9})
    session = _session()
    report = c.review_ambiguous_branches(
        campaign_id=15, allowed_sucursal_keys=None, session=session,
    )
    result = c.apply_ambiguous_branch_exclusions(
        campaign_id=15, expected_fingerprint=report["review_fingerprint"],
        expected_count=9, actor_user_id=7, allow_bulk=False,
        allowed_sucursal_keys=None, session=session,
    )
    assert result["added"] == 9
    assert saved[0]["recipient_ids"] == list(range(1, 10))
    session.commit.assert_called_once()


def test_multi_campaign_overlap_uses_one_deterministic_source(monkeypatch):
    proofs = {
        14: {"matched_recipient_ids": [3, 5],
             "source_submitted_phones_count": 2, "matched": 2},
        15: {"matched_recipient_ids": [3, 7],
             "source_submitted_phones_count": 2, "matched": 2},
    }
    monkeypatch.setattr(c, "find_previous_campaign_contact_ids",
                        lambda source_campaign_id, **kw: proofs[source_campaign_id])
    session = _session()
    review = c.review_previous_contacts(
        campaign_id=20, source_campaign_ids=[15, 14],
        allowed_sucursal_keys=None, session=session,
    )
    assert review["matched"] == 3
    assert review["new_exclusions"] == 3
    assert review["source_campaign_ids"] == [14, 15]
    assert [entry["unique_assigned"] for entry in review["source_breakdown"]] == [2, 1]
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("source_ids", [
    [], [True], [14, 14], [20], [0], list(range(1, 23)),
])
def test_invalid_multi_source_request_fails_before_queries(source_ids):
    session = _session()
    with pytest.raises(c.ValidationError):
        c.review_previous_contacts(
            campaign_id=20, source_campaign_ids=source_ids,
            allowed_sucursal_keys=None, session=session,
        )
    session.query.assert_not_called()


def test_multi_campaign_apply_preserves_first_matching_provenance(monkeypatch):
    proofs = {
        14: {"matched_recipient_ids": [3, 5],
             "source_submitted_phones_count": 2, "matched": 2},
        15: {"matched_recipient_ids": [3, 7],
             "source_submitted_phones_count": 2, "matched": 2},
    }
    monkeypatch.setattr(c, "find_previous_campaign_contact_ids",
                        lambda source_campaign_id, **kw: proofs[source_campaign_id])
    monkeypatch.setattr(c, "_lock_clean_target", lambda **kw: None)
    session = _session()
    report = c.review_previous_contacts(
        campaign_id=20, source_campaign_ids=[14, 15],
        allowed_sucursal_keys=None, session=session,
    )
    assert report["matched"] == 3
    with pytest.raises(c.ValidationError, match=r"10\+|desactualizada"):
        c.apply_previous_contacts(
            campaign_id=20, source_campaign_ids=[14,15],
            expected_fingerprint="wrong", expected_count=3,
            actor_user_id=7, allow_bulk=False,
            allowed_sucursal_keys=None, session=session,
        )
    session.add.assert_not_called()
    result = c.apply_previous_contacts(
        campaign_id=20, source_campaign_ids=[14,15],
        expected_fingerprint=report["review_fingerprint"],
        expected_count=3, actor_user_id=7, allow_bulk=False,
        allowed_sucursal_keys=None, session=session,
    )
    assert result["added"] == 3
    records = [call.args[0] for call in session.add.call_args_list]
    assert [(row.recipient_id,row.related_campaign_id) for row in records] == [
        (3,14), (5,14), (7,15),
    ]
    assert all(row.reason == "PREVIOUS_CAMPAIGN_CONTACT" for row in records)
    session.commit.assert_called_once()


def test_preparation_classifies_resolvable_and_unmapped_single_alias(monkeypatch):
    monkeypatch.setattr(c, "get_campaign_v2", lambda **kwargs: {"id": kwargs["campaign_id"]})
    monkeypatch.setattr(c, "resolve_dispatch_branch_key",
                        lambda value, **kwargs: NS(sucursal_id=4)
                        if value == "TEC_MXL" else None)
    rows = [
        NS(id=1, evidence_rows=[NS(sucursal_key="TEC_MXL")]),
        NS(id=2, evidence_rows=[NS(sucursal_key="UNMAPPED_UNKNOWN")]),
        NS(id=3, evidence_rows=[]),
        NS(id=4, evidence_rows=[
            NS(sucursal_key="TEC_MXL"), NS(sucursal_key="UNMAPPED_UNKNOWN"),
        ]),
    ]
    session = _session()
    session.query.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    result = c._ambiguous_rows(
        campaign_id=15, allowed_sucursal_keys=None, session=session,
    )
    assert [row["kind"] for row in result] == [
        "SINGLE_EVIDENCE_RESOLVABLE", "UNMAPPED_BRANCH_ALIAS",
        "MISSING_EVIDENCE", "AMBIGUOUS_EVIDENCE",
    ]
