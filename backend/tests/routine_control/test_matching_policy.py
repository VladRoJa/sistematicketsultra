from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date

from app.routine_control.pipeline.matching_policy import (
    AMBIGUOUS,
    IDENTITY_CONFLICT,
    INSUFFICIENT_IDENTITY_DATA,
    MATCHED,
    TEMPORALLY_INVALID,
    EvidenceMatchInput,
    MemberMatchCandidate,
    select_evidence_match,
)


class RoutineEvidenceMatchingPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = EvidenceMatchInput(
            evidence_id=10,
            external_member_id="244190",
            email_normalized="member@example.com",
            member_name_normalized="jairo mendoza sanchez",
            routine_activity_date=date(2026, 7, 10),
        )
        self.candidate = MemberMatchCandidate(
            member_id=26,
            external_member_id="244190",
            email_normalized="member@example.com",
            member_name_normalized="jairo mendoza sanchez",
            sale_date=date(2026, 7, 17),
        )

    def _select(self, *, evidence=None, ids=(), emails=()):
        return select_evidence_match(
            evidence or self.evidence,
            external_id_candidates=ids,
            email_candidates=emails,
        )

    def test_preexisting_at_30_days_is_valid(self) -> None:
        candidate = replace(self.candidate, sale_date=date(2026, 8, 9))
        result = self._select(ids=(candidate,))
        self.assertEqual(result.status, MATCHED)
        self.assertEqual(result.temporal_delta_days, -30)
        self.assertEqual(result.assignment_type, "PREEXISTENTE")

    def test_preexisting_at_31_days_is_invalid(self) -> None:
        candidate = replace(self.candidate, sale_date=date(2026, 8, 10))
        result = self._select(ids=(candidate,))
        self.assertEqual(result.status, TEMPORALLY_INVALID)

    def test_same_day_and_posterior_assignment_types(self) -> None:
        same_day = replace(self.candidate, sale_date=date(2026, 7, 10))
        posterior = replace(self.candidate, sale_date=date(2026, 7, 1))
        self.assertEqual(
            self._select(ids=(same_day,)).assignment_type,
            "MISMO_DIA",
        )
        result = self._select(ids=(posterior,))
        self.assertEqual((result.assignment_type, result.temporal_delta_days), ("POSTERIOR", 9))

    def test_name_corroborates_when_email_is_missing(self) -> None:
        evidence = replace(self.evidence, email_normalized=None)
        candidate = replace(self.candidate, email_normalized=None)
        result = self._select(evidence=evidence, ids=(candidate,))
        self.assertEqual((result.status, result.identity_corroborator), (MATCHED, "NAME"))

    def test_name_conflict_invalidates_even_when_email_matches(self) -> None:
        candidate = replace(self.candidate, member_name_normalized="otra persona")
        result = self._select(ids=(candidate,))
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_email_conflict_invalidates_even_when_name_matches(self) -> None:
        candidate = replace(self.candidate, email_normalized="other@example.com")
        result = self._select(ids=(candidate,))
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_nearest_previous_sale_wins_for_posterior_evidence(self) -> None:
        farther = replace(self.candidate, member_id=27, sale_date=date(2026, 7, 1))
        nearest = replace(self.candidate, member_id=28, sale_date=date(2026, 7, 9))
        result = self._select(ids=(farther, nearest))
        self.assertEqual((result.member_id, result.temporal_delta_days), (28, 1))

    def test_nearest_future_sale_wins_for_preexisting_evidence(self) -> None:
        farther = replace(self.candidate, member_id=27, sale_date=date(2026, 7, 30))
        nearest = replace(self.candidate, member_id=28, sale_date=date(2026, 7, 12))
        result = self._select(ids=(farther, nearest))
        self.assertEqual((result.member_id, result.temporal_delta_days), (28, -2))

    def test_equal_minimum_distance_is_ambiguous_without_email_fallback(self) -> None:
        before = replace(self.candidate, member_id=27, sale_date=date(2026, 7, 8))
        after = replace(self.candidate, member_id=28, sale_date=date(2026, 7, 12))
        fallback = replace(self.candidate, member_id=29, external_member_id="999")
        result = self._select(ids=(before, after), emails=(fallback,))
        self.assertEqual(result.status, AMBIGUOUS)
        self.assertEqual(result.ambiguous_member_ids, (27, 28))

    def test_email_fallback_applies_identity_time_and_uniqueness(self) -> None:
        conflicting_id = replace(self.candidate, email_normalized="other@example.com")
        email_candidate = replace(
            self.candidate,
            member_id=30,
            external_member_id="999",
            sale_date=date(2026, 7, 9),
        )
        result = self._select(ids=(conflicting_id,), emails=(email_candidate,))
        self.assertEqual((result.status, result.member_id, result.match_method), (MATCHED, 30, "EMAIL"))

    def test_jairo_is_temporally_invalid_at_minus_192_days(self) -> None:
        evidence = replace(
            self.evidence,
            routine_activity_date=date(2026, 1, 6),
            email_normalized="jairomendozasanchez@gmail.com",
        )
        candidate = replace(
            self.candidate,
            sale_date=date(2026, 7, 17),
            email_normalized="jairomendozasanchez@gmail.com",
        )
        result = self._select(evidence=evidence, ids=(candidate,))
        self.assertEqual(result.status, TEMPORALLY_INVALID)
        self.assertEqual(result.temporal_delta_days, -192)
        self.assertIn(26, result.considered_member_ids)

    def test_missing_external_id_and_email_is_insufficient(self) -> None:
        evidence = replace(
            self.evidence,
            external_member_id=None,
            email_normalized=None,
            member_name_normalized=None,
        )
        result = self._select(evidence=evidence)
        self.assertEqual(result.status, INSUFFICIENT_IDENTITY_DATA)


if __name__ == "__main__":
    unittest.main()
