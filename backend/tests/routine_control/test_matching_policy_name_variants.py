"""Regression tests for explainable name variants with one email candidate."""

import unittest
from dataclasses import replace
from datetime import date

from app.routine_control.pipeline.matching_policy import (
    IDENTITY_CONFLICT,
    MATCHED,
    TEMPORALLY_INVALID,
    EvidenceMatchInput,
    MemberMatchCandidate,
    select_evidence_match,
)


class RoutineMatchingNameVariantsTestCase(unittest.TestCase):
    def setUp(self):
        self.evidence = EvidenceMatchInput(
            evidence_id=1,
            external_member_id=None,
            email_normalized="test@example.com",
            member_name_normalized="ana vega",
            routine_activity_date=date(2026, 10, 14),
        )
        self.member = MemberMatchCandidate(
            member_id=10,
            external_member_id="1234",
            email_normalized="test@example.com",
            member_name_normalized="ana vega morales",
            sale_date=date(2026, 10, 1),
        )

    def _match(self, evidence_name, member_name, *, other=(), **overrides):
        evidence = replace(
            self.evidence, member_name_normalized=evidence_name,
            **{key: value for key, value in overrides.items() if key in (
                "external_member_id", "routine_activity_date"
            )},
        )
        member = replace(
            self.member, member_name_normalized=member_name,
        )
        return select_evidence_match(
            evidence,
            external_id_candidates=(),
            email_candidates=(member, *other),
        )

    def test_omitted_last_surname(self):
        result = self._match("ana vega", "ana vega morales")
        self.assertEqual((result.status, result.member_id), (MATCHED, 10))
        self.assertEqual(result.identity_corroborator, "EMAIL_NAME_PREFIX")
        self.assertEqual(result.assignment_type, "POSTERIOR")

    def test_omitted_multiple_trailing_surnames(self):
        result = self._match("maria jose vega morales", "maria jose vega morales rios")
        self.assertEqual(result.status, MATCHED)
        self.assertEqual(result.identity_corroborator, "EMAIL_NAME_PREFIX")

    def test_middle_name_initial(self):
        result = self._match("carlos a rios mora", "carlos antonio rios mora")
        self.assertEqual((result.status, result.identity_corroborator),
                         (MATCHED, "EMAIL_NAME_INITIAL"))

    def test_two_surnames_reversed(self):
        result = self._match("isaac diaz hernandez", "isaac hernandez diaz")
        self.assertEqual((result.status, result.identity_corroborator),
                         (MATCHED, "EMAIL_SURNAME_SWAP"))

    def test_first_name_one_omitted_letter(self):
        result = self._match("emanuel ortega maya", "emmanuel ortega maya")
        self.assertEqual((result.status, result.identity_corroborator),
                         (MATCHED, "EMAIL_FIRST_NAME_INSERTION"))

    def test_exact_match_still_works_with_multiple_candidates(self):
        other = replace(self.member, member_id=11, member_name_normalized="otra persona")
        result = self._match("ana vega morales", "ana vega morales", other=(other,))
        self.assertEqual((result.status, result.member_id), (MATCHED, 10))

    def test_shared_email_does_not_enable_prefix_relaxation(self):
        other = replace(self.member, member_id=11, member_name_normalized="otra persona")
        result = self._match("ana vega", "ana vega morales", other=(other,))
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_different_person_with_same_email_is_conflict(self):
        result = self._match("mariana rios", "ana vega morales")
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_reversed_first_and_last_names_are_not_accepted(self):
        result = self._match("vega ana morales", "ana vega morales")
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_arbitrary_typo_in_surname_is_not_accepted(self):
        result = self._match("emanuel ortega maya", "emanuel ortega mayo")
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_first_name_substitution_is_not_accepted(self):
        result = self._match("mariano ortega maya", "mariana ortega maya")
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_short_first_name_typo_is_not_accepted(self):
        result = self._match("ana ortega maya", "anna ortega maya")
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_external_id_conflict_prevents_relaxed_name_match(self):
        result = self._match("ana vega", "ana vega morales", external_member_id="9999")
        self.assertEqual(result.status, IDENTITY_CONFLICT)

    def test_historical_temporal_limit_is_preserved(self):
        result = self._match(
            "ana vega", "ana vega morales",
            routine_activity_date=date(2026, 8, 1),
        )
        self.assertEqual(result.status, TEMPORALLY_INVALID)

    def test_missing_email_does_not_use_name_variants(self):
        evidence = replace(self.evidence, email_normalized=None)
        result = select_evidence_match(
            evidence,
            external_id_candidates=(),
            email_candidates=(self.member,),
        )
        self.assertNotEqual(result.status, MATCHED)


if __name__ == "__main__":
    unittest.main()
